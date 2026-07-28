#!/bin/sh
# Update a Compose-managed GUDBUS container to a published image tag.
#
#   ./nas-update.sh sha-ef30b62
#
# Written after a 2026-07-27 deploy that edited the compose file, reported
# nothing wrong, and left the old container running — caught only because
# /status reported a 34-hour uptime. Every step here that can silently no-op is
# therefore verified against the running artifact rather than against its own
# exit code.
#
# Override for a different host layout:
#   GUDBUS_PROJECT_DIR   compose project dir (holds docker-compose.yml)
#   GUDBUS_CONTAINER     container name as `docker ps` reports it
#   GUDBUS_REPO          owner/repo, for the CI status check
#   GUDBUS_SKIP_CI_CHECK=1   deploy a tag whose tests are red/missing (asks first)
#   GUDBUS_SKIP_BACKUP=1     skip the pre-deploy DB copy
#   GUDBUS_IMAGE_REPO    registry repo to prune within (never anything else)
#   GUDBUS_KEEP_IMAGES   old images to keep besides the running one (default 1)
#   GUDBUS_KEEP_BACKUPS  in-volume DB backups to keep (default 7)
#
# Pass --no-prune to keep every old image and backup.
#
# Each deploy leaves behind the image it replaced and one more DB backup, and
# neither was ever cleaned up, so both grew without bound on a box with other
# people's services on it. Pruning runs only AFTER the new container is verified
# healthy, and keeps one previous image so a rollback does not need the network.
#
# Pass --dry-run to run every check and stop before anything is modified. Worth
# doing once on a new host: it proves the container really is the one this
# script thinks it is, on a box that may be running other people's services.

set -eu

PROJECT_DIR=${GUDBUS_PROJECT_DIR:-/boot/config/plugins/compose.manager/projects/GUDBUS}
CONTAINER=${GUDBUS_CONTAINER:-gudbus}
REPO=${GUDBUS_REPO:-haksanlulz/GUDBUS}
COMPOSE="$PROJECT_DIR/docker-compose.yml"
IMAGE_REPO=${GUDBUS_IMAGE_REPO:-ghcr.io/haksanlulz/gudbus}
KEEP_IMAGES=${GUDBUS_KEEP_IMAGES:-1}
KEEP_BACKUPS=${GUDBUS_KEEP_BACKUPS:-7}

die() { printf '\nFAILED: %s\n' "$1" >&2; exit 1; }
step() { printf '\n== %s\n' "$1"; }

DRY_RUN=0
PRUNE=1
while :; do
  case "${1:-}" in
    --dry-run)  DRY_RUN=1; shift ;;
    --no-prune) PRUNE=0; shift ;;
    *) break ;;
  esac
done

# Remove superseded images for OUR repo only, newest-first, keeping the running
# one plus $KEEP_IMAGES previous.
#
# The reference filter is the whole safety story: this host runs 60+ containers
# belonging to other people, so `docker image prune -a` — the obvious thing —
# would delete their images too. `docker rmi` is deliberately called WITHOUT
# -f, so an image another container still references refuses to be removed
# rather than being torn out from under it.
prune_images() {
  [ "$PRUNE" = "1" ] || return 0
  step "Old images"
  RUNNING_IMG=$(docker inspect -f '{{.Image}}' "$CONTAINER" 2>/dev/null || true)

  # Every image any container is built on, running or stopped. A second
  # instance of this bot (the :nightly dev container) is built from the SAME
  # repo, so it shows up in the listing below and would otherwise be a
  # deletion candidate the moment prod is deployed. `docker rmi` would refuse
  # it, but relying on that means the protection is a side effect of an error
  # path rather than something this script decided. One inspect call, not one
  # per container: this host has 60+ of them.
  ALL_C=$(docker ps -aq 2>/dev/null | tr '\n' ' ')
  IN_USE=""
  # Flattened to a space-separated list because the membership test below is a
  # `case` glob on " $IN_USE ", and a newline is not a space — the ids would
  # never match and every in-use image would silently stay a deletion
  # candidate. That is precisely how this went in first.
  # shellcheck disable=SC2086
  [ -n "$ALL_C" ] && IN_USE=$(docker inspect -f '{{.Image}}' $ALL_C 2>/dev/null \
                              | tr '\n' ' ')

  # One image can carry several tags; de-duplicate so a keep-slot is an image,
  # not a tag. docker images lists newest first.
  IMG_IDS=$(docker images --no-trunc --filter=reference="$IMAGE_REPO" \
            --format '{{.ID}}' 2>/dev/null | awk '!seen[$0]++')
  [ -n "$IMG_IDS" ] || { printf '  none found for %s\n' "$IMAGE_REPO"; return 0; }
  kept=0
  for id in $IMG_IDS; do
    if [ "$id" = "$RUNNING_IMG" ]; then
      printf '  running  %s\n' "$(echo "$id" | cut -c8-19)"
      continue
    fi
    # In use by some other container — another instance of this bot, most
    # likely. Not a rollback slot: it is not spare capacity, it is spoken for.
    case " $IN_USE " in
      *" $id "*)
        printf '  in use   %s (another container)\n' "$(echo "$id" | cut -c8-19)"
        continue
        ;;
    esac
    kept=$((kept + 1))
    if [ "$kept" -le "$KEEP_IMAGES" ]; then
      printf '  rollback %s\n' "$(echo "$id" | cut -c8-19)"
      continue
    fi
    if [ "$DRY_RUN" = "1" ]; then
      printf '  would rm %s\n' "$(echo "$id" | cut -c8-19)"
    elif docker rmi "$id" >/dev/null 2>&1; then
      printf '  removed  %s\n' "$(echo "$id" | cut -c8-19)"
    else
      printf '  in use, kept %s\n' "$(echo "$id" | cut -c8-19)"
    fi
  done
}

# The backup step below writes one file per deploy into the data volume and
# nothing ever removed them.
prune_backups() {
  [ "$PRUNE" = "1" ] || return 0
  step "Old database backups"
  docker exec "$CONTAINER" sh -c '
    keep=$1
    total=$(ls -1 /app/data/gurps_bot-*.db 2>/dev/null | wc -l)
    [ "$total" -gt "$keep" ] || { echo "  $total backup(s), keeping all"; exit 0; }
    ls -1t /app/data/gurps_bot-*.db | tail -n +$((keep + 1)) | while read -r f; do
      rm -f "$f" && echo "  removed $(basename "$f")"
    done
    echo "  kept newest $keep of $total"
  ' sh "$KEEP_BACKUPS" 2>/dev/null || printf '  WARNING: could not prune backups\n'
}

TAG=${1:-}
[ -n "$TAG" ] || die "usage: $0 [--dry-run] <image-tag>   e.g. $0 sha-ef30b62

Find the tag: it is 'sha-' plus the short commit sha of what you want deployed.
This script checks that commit's CI itself and refuses a red one."

# ---------------------------------------------------------------- preflight
step "Preflight"
[ -f "$COMPOSE" ] || die "no compose file at $COMPOSE (set GUDBUS_PROJECT_DIR)"
command -v docker >/dev/null 2>&1 || die "docker not on PATH"
docker compose version >/dev/null 2>&1 || die "'docker compose' (v2) unavailable"

CURRENT_IMAGE=$(docker inspect -f '{{.Config.Image}}' "$CONTAINER" 2>/dev/null) \
  || die "container '$CONTAINER' not found. Running containers:
$(docker ps --format '  {{.Names}}')"
CURRENT_ID=$(docker inspect -f '{{.Id}}' "$CONTAINER")

# --- ownership: prove this container is ours before touching anything -------
# This host runs 60+ containers belonging to other people. Everything below
# acts on $CONTAINER and $PROJECT_DIR, but those are defaults, and a default is
# not a guarantee. Refuse unless the container's own Compose labels say it
# belongs to the project directory we were pointed at.
EXPECT_PROJECT=$(cat "$PROJECT_DIR/name" 2>/dev/null || basename "$PROJECT_DIR")
EXPECT_PROJECT=$(printf '%s' "$EXPECT_PROJECT" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
GOT_PROJECT=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$CONTAINER" 2>/dev/null || true)
SERVICE=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$CONTAINER" 2>/dev/null || true)

[ -n "$GOT_PROJECT" ] || die "container '$CONTAINER' carries no Compose project
label, so it is not managed by this project dir. Refusing to touch it."
[ -n "$SERVICE" ] || die "container '$CONTAINER' carries no Compose service label."
[ "$GOT_PROJECT" = "$EXPECT_PROJECT" ] || die "container '$CONTAINER' belongs to
Compose project '$GOT_PROJECT', but $PROJECT_DIR is project '$EXPECT_PROJECT'.
Refusing to act on another project's container."

# The service is named explicitly on every compose call below, so a project
# that grew a second service cannot have it recreated as a side effect.
SERVICES=$(cd "$PROJECT_DIR" && docker compose config --services 2>/dev/null || true)
printf '%s\n' "$SERVICES" | grep -qx "$SERVICE" \
  || die "service '$SERVICE' is not defined in $COMPOSE. Defined:
$(printf '%s' "$SERVICES" | sed 's/^/  /')"

printf '  container : %s\n  project   : %s\n  service   : %s\n  image now : %s\n  target    : %s\n' \
  "$CONTAINER" "$GOT_PROJECT" "$SERVICE" "$CURRENT_IMAGE" "$TAG"

case "$CURRENT_IMAGE" in
  *":$TAG") die "already running $TAG — nothing to do" ;;
esac

# ------------------------------------------------------------- CI gate
# docker-publish.yml now gates on the test matrix, so a red commit should no
# longer produce an image at all. This check stays as the belt to that braces:
# images published before the gate landed still exist and are still pullable
# (sha-56422b8 is one), and a workflow edit could remove the gate again without
# anything here noticing. Cheap to keep, and it fails closed.
if [ "${GUDBUS_SKIP_CI_CHECK:-0}" != "1" ]; then
  step "CI status for ${TAG#sha-}"
  API="https://api.github.com/repos/$REPO/commits/${TAG#sha-}/check-runs"
  if RUNS=$(curl -fsSL -H 'Accept: application/vnd.github+json' "$API" 2>/dev/null); then
    FLAT=$(printf '%s' "$RUNS" | tr -d ' \n')
    if printf '%s' "$FLAT" | grep -q '"conclusion":"failure"'; then
      die "that commit has a FAILING check run — refusing to deploy a red build.
Re-run with GUDBUS_SKIP_CI_CHECK=1 only if you know why it is red."
    fi
    if printf '%s' "$FLAT" | grep -q '"status":"in_progress"\|"status":"queued"'; then
      die "CI is still running for that commit — wait for it to finish."
    fi
    printf '  no failing check runs\n'
  else
    printf '  WARNING: could not reach the GitHub API; CI status UNVERIFIED\n'
  fi

  # ----------------------------------------------------------- which channel
  # dev is trunk and main is the release branch, and both publish sha- tags, so
  # a tag alone does not say which one you are about to put on the box. This
  # reports rather than refuses: deploying a nightly to try it is a legitimate
  # thing to do, and the failure mode worth preventing is doing it without
  # knowing. `behind` and `identical` mean the commit is an ancestor of main.
  step "Release channel"
  CMP="https://api.github.com/repos/$REPO/compare/main...${TAG#sha-}"
  if OUT=$(curl -fsSL -H 'Accept: application/vnd.github+json' "$CMP" 2>/dev/null); then
    # Anchored on the adjacent "ahead_by" key, not on "status" alone: an
    # `ahead` comparison also carries a files[] array whose entries each have
    # their own "status", and a greedy match takes the LAST one. That would
    # have misread exactly the nightly case this check exists to catch, while
    # looking correct on every release tag it was tried against.
    STATUS=$(printf '%s' "$OUT" | tr -d ' \n' | sed -n 's/.*"status":"\([a-z]*\)","ahead_by".*/\1/p')
    case "$STATUS" in
      identical|behind) printf '  RELEASE — this commit is on main\n' ;;
      ahead|diverged)   printf '  NIGHTLY — this commit is NOT on main (trunk build)\n' ;;
      *)                printf '  WARNING: could not read the channel (status=%s)\n' "${STATUS:-none}" ;;
    esac
  else
    printf '  WARNING: could not reach the GitHub API; channel UNVERIFIED\n'
  fi
fi

if [ "$DRY_RUN" = "1" ]; then
  # Preview the prune against the images actually on this host. Reads only.
  prune_images
  step "Dry run"
  printf '  All checks passed. Would now:\n'
  printf '    1. back up /app/data/gurps_bot.db inside the container\n'
  printf '    2. pin %s in %s\n' "$TAG" "$COMPOSE"
  printf '    3. docker compose up -d --force-recreate --no-deps %s\n' "$SERVICE"
  printf '    4. verify the container id changed and the image matches\n'
  if [ "$PRUNE" = "1" ]; then
    printf '    5. remove the superseded images listed above, and all but the\n'
    printf '       newest %s database backup(s)\n' "$KEEP_BACKUPS"
  fi
  printf '\n  Nothing was modified. Re-run without --dry-run to deploy.\n'
  exit 0
fi

# ------------------------------------------------------------- backup
if [ "${GUDBUS_SKIP_BACKUP:-0}" != "1" ]; then
  step "Backing up the database"
  STAMP=$(date -u +%Y%m%d-%H%M%S)
  # sqlite3 is not in the image; use Python's online-backup API, which is
  # WAL-safe against a live DB (a plain cp is not).
  if docker exec "$CONTAINER" python -c "
import sqlite3, sys
src = sqlite3.connect('/app/data/gurps_bot.db')
dst = sqlite3.connect('/app/data/gurps_bot-$STAMP.db')
src.backup(dst); dst.close(); src.close()
" 2>/dev/null; then
    printf '  wrote /app/data/gurps_bot-%s.db (inside the data volume)\n' "$STAMP"
  else
    printf '  WARNING: backup failed (no DB yet?) — continuing\n'
  fi
fi

# ------------------------------------------------------------- edit the pin
step "Pinning $TAG"
TMP=/tmp/gudbus-compose.$$
sed "s#\(image: *ghcr\.io/[^:]*\):.*#\1:$TAG#" "$COMPOSE" > "$TMP" || die "sed failed"
grep -q ":$TAG" "$TMP" || die "tag rewrite produced no match — is the image line a ghcr.io ref?
$(grep -n 'image:' "$COMPOSE")"
# copy rather than mv: the project dir is on the FAT32 flash, where rename
# semantics are less predictable than a plain overwrite
cp "$TMP" "$COMPOSE" || die "could not write $COMPOSE"
rm -f "$TMP"
grep -q ":$TAG" "$COMPOSE" || die "compose file does not contain $TAG after the write"
printf '  %s\n' "$(grep 'image:' "$COMPOSE" | head -1 | sed 's/^ *//')"

# ------------------------------------------------------------- recreate
# `docker compose` only finds the project when run from inside its directory.
# Running it from elsewhere exits 0 and does nothing, which is the exact way
# the 2026-07-27 deploy silently failed.
step "Recreating"
cd "$PROJECT_DIR" || die "cannot cd to $PROJECT_DIR"
# Named service, and --no-deps: an unqualified `up` recreates every service in
# the project and can start ones someone deliberately stopped. Nothing here
# uses `down` or --remove-orphans, both of which reach past this service.
docker compose up -d --force-recreate --no-deps "$SERVICE" \
  || die "compose up failed for service '$SERVICE'"

# ------------------------------------------------------------- verify
# Verify against the running container, not against compose's exit code.
step "Verifying"
NEW_ID=$(docker inspect -f '{{.Id}}' "$CONTAINER" 2>/dev/null) \
  || die "container '$CONTAINER' is gone after recreate — check: docker compose ps"
NEW_IMAGE=$(docker inspect -f '{{.Config.Image}}' "$CONTAINER")

[ "$NEW_ID" != "$CURRENT_ID" ] \
  || die "container id did not change ($CURRENT_ID) — the recreate was a no-op.
This is what a wrong-directory 'docker compose up' looks like. cwd was: $PROJECT_DIR"

case "$NEW_IMAGE" in
  *":$TAG") ;;
  *) die "running image is $NEW_IMAGE, expected :$TAG" ;;
esac

RUNNING=$(docker inspect -f '{{.State.Running}}' "$CONTAINER")
[ "$RUNNING" = "true" ] || die "container is not running — docker logs $CONTAINER"

printf '  image  : %s\n  id     : %s -> %s\n  running: yes\n' \
  "$NEW_IMAGE" "$(echo "$CURRENT_ID" | cut -c1-12)" "$(echo "$NEW_ID" | cut -c1-12)"

# Only now — a prune before this point could delete the image a failed deploy
# needs to roll back to.
prune_images
prune_backups

step "Done. Following logs (Ctrl+C to stop)"
printf '  expect: migrations apply, all cogs load, a command re-sync if the\n'
printf '          command set changed, then the gateway connects.\n\n'
exec docker logs -f --since 2m "$CONTAINER"
