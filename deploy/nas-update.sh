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
#   GUDBUS_SKIP_FRESHNESS_CHECK=1  skip the local-vs-registry digest comparison
#   GUDBUS_CURL          curl binary to use (default: whatever is on PATH)
#
# GUDBUS_CURL exists because PATH is not a reliable seam for the tests: Git Bash
# on Windows prepends its own bin directory ahead of anything the caller
# prepended, so a stub `curl` placed on PATH was silently ignored and the suite
# made real calls to ghcr.io instead. It doubles as a genuine knob for a host
# where curl is not on the default PATH.
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
# Verified against the running box 2026-07-29: the template container is
# `GUDBUS`, uppercase. The default was `gudbus` because that is what Compose
# Manager named it, and it went stale when production moved to the template on
# 07-28 — so --preflight would have failed with "container not found" on its
# first real use. Docker names are case-sensitive; the mismatch is invisible
# until something looks. GAUNTLET §2 lists five different spellings across this
# one deployment, and this is the fourth time one of them was guessed wrong.
CONTAINER=${GUDBUS_CONTAINER:-GUDBUS}
REPO=${GUDBUS_REPO:-haksanlulz/GUDBUS}
COMPOSE="$PROJECT_DIR/docker-compose.yml"
IMAGE_REPO=${GUDBUS_IMAGE_REPO:-ghcr.io/haksanlulz/gudbus}
KEEP_IMAGES=${GUDBUS_KEEP_IMAGES:-1}
KEEP_BACKUPS=${GUDBUS_KEEP_BACKUPS:-7}
CURL=${GUDBUS_CURL:-curl}

die() { printf '\nFAILED: %s\n' "$1" >&2; exit 1; }
step() { printf '\n== %s\n' "$1"; }

# What a tag resolves to in the registry right now, without pulling it.
#
# A HEAD on the manifest returns Docker-Content-Digest, which is the same
# digest `docker pull <tag>` records in the image's RepoDigests — so the two
# are directly comparable, which is the whole basis of the freshness check
# below. GHCR requires a bearer token even for public packages; its token
# endpoint issues one anonymously for a pull scope.
#
# One Accept header listing every media type rather than several headers: a
# registry is entitled to honour only the first, and a multi-arch image
# answered as a single-platform manifest would return a digest that compares
# unequal to the locally pulled one for no real reason.
registry_digest() {
  _host=${IMAGE_REPO%%/*}
  _path=${IMAGE_REPO#*/}
  _tok=$("$CURL" -fsSL "https://$_host/token?scope=repository:$_path:pull&service=$_host" 2>/dev/null \
         | tr -d ' \n' | sed -n 's/.*"token":"\([^"]*\)".*/\1/p') || true
  [ -n "${_tok:-}" ] || return 1
  _dig=$("$CURL" -fsSL -I -H "Authorization: Bearer $_tok" \
           -H 'Accept: application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.docker.distribution.manifest.v2+json' \
           "https://$_host/v2/$_path/manifests/$1" 2>/dev/null \
         | tr -d '\r' | sed -n 's/^[Dd]ocker-[Cc]ontent-[Dd]igest: *//p' | head -1) || true
  [ -n "${_dig:-}" ] || return 1
  printf '%s' "$_dig"
}

# The digest the local copy of a reference was pulled under. Empty when the tag
# is not in the local image store at all, or when the image was built here
# rather than pulled — both mean there is no stale cached copy to worry about.
local_digest() {
  docker inspect -f '{{range .RepoDigests}}{{println .}}{{end}}' "$1" 2>/dev/null \
    | sed -n 's/.*@//p' | head -1
}

short_digest() { printf '%s' "$1" | cut -c1-24; }

DRY_RUN=0
PRUNE=1
PREFLIGHT=0
while :; do
  case "${1:-}" in
    --dry-run)   DRY_RUN=1; shift ;;
    --no-prune)  PRUNE=0; shift ;;
    --preflight) PREFLIGHT=1; shift ;;
    *) break ;;
  esac
done

# --preflight runs the checks worth having and then stops, without requiring a
# Compose project or touching the container.
#
# Production moved to an unRAID Docker *template* on 2026-07-28. A template
# container carries no `com.docker.compose.*` labels and has no compose file to
# rewrite, so the recreate below cannot drive it and the ownership check
# correctly refuses it. What was lost with it was not the recreate — the unRAID
# UI does that well — but the things around it: nobody checks whether the
# commit's tests passed, and nobody takes a backup first.
#
# So this mode does exactly those, and mutates nothing except writing a backup.
# That restriction is deliberate: this script cannot be tested against the real
# box from a development machine, and a session that has already found a stale
# copy of it and two shadow data directories there should not be writing an
# untested recreate path for someone else's production container.

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
[ -n "$TAG" ] || die "usage: $0 [--dry-run] [--no-prune] [--preflight] <image-tag>
       e.g. $0 sha-ef30b62

Find the tag: it is 'sha-' plus the short commit sha of what you want deployed.
This script checks that commit's CI itself and refuses a red one."

# ---------------------------------------------------------------- preflight
step "Preflight"
command -v docker >/dev/null 2>&1 || die "docker not on PATH"
if [ "$PREFLIGHT" = "0" ]; then
  [ -f "$COMPOSE" ] || die "no compose file at $COMPOSE (set GUDBUS_PROJECT_DIR).
If this container is managed by the unRAID Docker template rather than Compose,
run with --preflight: it performs the checks and leaves the update to the UI."
  docker compose version >/dev/null 2>&1 || die "'docker compose' (v2) unavailable"
fi

# On a miss, name the case-insensitive match rather than only listing every
# container. Docker names ARE case-sensitive, this deployment spells itself five
# different ways across the app / project / service / container / repo, and a
# 60-container listing does not make `GUDBUS` vs `gudbus` jump out — which is
# exactly how the stale default above survived a whole day unnoticed.
CURRENT_IMAGE=$(docker inspect -f '{{.Config.Image}}' "$CONTAINER" 2>/dev/null) \
  || die "container '$CONTAINER' not found.$(
      NEAR=$(docker ps -a --format '{{.Names}}' 2>/dev/null \
             | grep -ix "$CONTAINER" || true)
      [ -z "$NEAR" ] && NEAR=$(docker ps -a --format '{{.Names}}' 2>/dev/null \
             | grep -i "$CONTAINER" || true)
      [ -n "$NEAR" ] && printf '\nDid you mean one of these? Names are case-sensitive:\n%s' \
        "$(printf '%s' "$NEAR" | sed 's/^/  /')"
    )
All containers:
$(docker ps -a --format '  {{.Names}}')"
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
MANAGED_BY=$(docker inspect -f '{{index .Config.Labels "net.unraid.docker.managed"}}' "$CONTAINER" 2>/dev/null || true)

if [ "$PREFLIGHT" = "1" ]; then
  # Nothing below this mode modifies the container, so the Compose-label proof
  # is not load-bearing here — report what manages it instead, because that is
  # what decides how the operator applies the update.
  if [ -n "$GOT_PROJECT" ]; then
    printf '  managed by: Compose (project %s, service %s)\n' "$GOT_PROJECT" "$SERVICE"
  elif [ -n "$MANAGED_BY" ]; then
    printf '  managed by: unRAID Docker template (%s)\n' "$MANAGED_BY"
  else
    printf '  managed by: unknown — neither Compose nor unRAID labels present\n'
  fi
  printf '  container : %s\n  image now : %s\n  target    : %s\n' \
    "$CONTAINER" "$CURRENT_IMAGE" "$TAG"
fi

[ -n "$GOT_PROJECT" ] || [ "$PREFLIGHT" = "1" ] || die "container '$CONTAINER' carries no Compose project
label, so it is not managed by this project dir. Refusing to touch it.
If it is an unRAID Docker template container, use --preflight: it runs the CI
check and takes a backup, then leaves the update itself to the UI."
if [ "$PREFLIGHT" = "0" ]; then
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
fi

case "$CURRENT_IMAGE" in
  *":$TAG")
    if [ "$PREFLIGHT" = "1" ]; then
      # Not an error here: on the template path the operator often runs this
      # AFTER updating, to confirm the box is where they think it is.
      printf '\n  Already running %s.\n' "$TAG"
    else
      die "already running $TAG — nothing to do"
    fi
    ;;
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
  if RUNS=$("$CURL" -fsSL -H 'Accept: application/vnd.github+json' "$API" 2>/dev/null); then
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
  if OUT=$("$CURL" -fsSL -H 'Accept: application/vnd.github+json' "$CMP" 2>/dev/null); then
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

# ------------------------------------------------------- image freshness
# Production tracks `:latest`, a MOVING tag, and an unRAID template "Apply"
# recreates the container without pulling — so it comes up on whatever copy of
# that tag is already in the local image store. That is a deploy which looks
# entirely successful and is running the previous release. It happened on
# 2026-07-28: new container, healthy, clean logs, the 18th extension absent and
# the command sync reporting `Command set unchanged`.
#
# Two failures end the same way and need saying separately:
#
#   the local copy of the moving tag is behind the registry  -> pull, then apply
#   the moving tag does not point at the commit you asked for -> apply nothing
#
# Reports, never refuses, and pulls nothing. Preflight's entire basis for being
# safe to ship without a test against someone else's production box is that it
# mutates nothing, and a pull changes what the next recreate will run.
STALE_POINTER=0
if [ "${GUDBUS_SKIP_FRESHNESS_CHECK:-0}" != "1" ]; then
  step "Image freshness"

  # Split the running reference into repo and tag. Done on the segment after
  # the last slash so a registry host carrying a port (host:5000/repo) is not
  # mistaken for a tag.
  AFTER_SLASH=${CURRENT_IMAGE##*/}
  case "$AFTER_SLASH" in
    *:*) RUN_TAG=${AFTER_SLASH##*:}; RUN_REF=$CURRENT_IMAGE ;;
    *)   RUN_TAG=latest;             RUN_REF="$CURRENT_IMAGE:latest" ;;
  esac

  case "$CURRENT_IMAGE" in
    *@sha256:*)
      printf '  running a digest pin — immutable, so a recreate cannot drift\n'
      ;;
    *)
      case "$RUN_TAG" in
        sha-*)
          printf '  running :%s — an immutable tag, so a recreate cannot drift\n' "$RUN_TAG"
          ;;
        *)
          printf '  running   : :%s (MOVING — a recreate reuses the local copy)\n' "$RUN_TAG"
          LOCAL_DIG=$(local_digest "$RUN_REF") || true
          REMOTE_DIG=$(registry_digest "$RUN_TAG" || true)
          TARGET_DIG=$(registry_digest "$TAG" || true)

          if [ -z "${LOCAL_DIG:-}" ]; then
            printf '  local     : not present locally — the recreate must pull it\n'
          elif [ -z "${REMOTE_DIG:-}" ]; then
            printf '  local     : %s\n' "$(short_digest "$LOCAL_DIG")"
            printf '  WARNING: could not reach the registry; freshness UNVERIFIED\n'
          else
            printf '  local     : %s\n  registry  : %s\n' \
              "$(short_digest "$LOCAL_DIG")" "$(short_digest "$REMOTE_DIG")"
            if [ "$LOCAL_DIG" = "$REMOTE_DIG" ]; then
              printf '  the cached :%s is up to date\n' "$RUN_TAG"
            else
              STALE_POINTER=1
              printf '  ⚠ STALE — the cached :%s is NOT what the registry serves.\n' "$RUN_TAG"
              printf '    Applying now recreates the container on the OLD image and\n'
              printf '    looks like a successful deploy. Pull the moving tag first —\n'
              printf '    pulling the sha- tag instead fetches the right image but\n'
              printf '    leaves :%s pointing at the old one:\n\n' "$RUN_TAG"
              printf '        docker pull %s\n' "$RUN_REF"
            fi
          fi

          # Separate question: does that moving tag carry the commit asked for?
          if [ -n "${TARGET_DIG:-}" ] && [ -n "${REMOTE_DIG:-}" ]; then
            if [ "$TARGET_DIG" = "$REMOTE_DIG" ]; then
              printf '  :%s carries %s\n' "$RUN_TAG" "$TAG"
            else
              printf '\n  ⚠ :%s does NOT carry %s — it resolves to %s.\n' \
                "$RUN_TAG" "$TAG" "$(short_digest "$REMOTE_DIG")"
              printf '    Applying would deploy something other than the commit\n'
              printf '    whose CI was just checked. Either wait for the release to\n'
              printf '    move the pointer, or pin %s explicitly.\n' "$TAG"
            fi
          fi
          ;;
      esac
      ;;
  esac
fi

if [ "$PREFLIGHT" = "1" ]; then
  if [ "${GUDBUS_SKIP_BACKUP:-0}" != "1" ] && [ "$DRY_RUN" != "1" ]; then
    step "Backing up the database"
    STAMP=$(date -u +%Y%m%d-%H%M%S)
    if docker exec "$CONTAINER" python -c "
import sqlite3
src = sqlite3.connect('/app/data/gurps_bot.db')
dst = sqlite3.connect('/app/data/gurps_bot-$STAMP.db')
src.backup(dst); dst.close(); src.close()
" 2>/dev/null; then
      printf '  wrote /app/data/gurps_bot-%s.db\n' "$STAMP"
      printf '  ⚠ that is INSIDE the data volume — copy it off the volume if\n'
      printf '    what you are guarding against is losing the volume itself\n'
    else
      printf '  WARNING: backup failed (no DB yet?)\n'
    fi
  fi

  step "Preflight complete — nothing was modified"
  printf '  The checks are done; the update itself is not this script'"'"'s to make\n'
  printf '  on a template-managed container. Apply it the way the box is\n'
  printf '  managed:\n\n'
  if [ "$STALE_POINTER" = "1" ]; then
    # The report above is only useful if it reaches the instructions the
    # operator actually acts on. A bare Apply here is the failure, not the fix.
    printf '    unRAID template : docker pull %s FIRST — Apply alone\n' "$RUN_REF"
    printf '                      recreates on the stale cached image — then Apply\n'
  else
    printf '    unRAID template : set the tag in the container template, Apply\n'
  fi
  printf '    Compose project : re-run this script WITHOUT --preflight\n\n'
  printf '  Afterwards, confirm the box is actually where you think it is —\n'
  printf '  the running artifact, not the form that describes it:\n\n'
  printf '    docker inspect -f '"'"'{{index .Config.Labels "org.opencontainers.image.revision"}}'"'"' %s\n\n' "$CONTAINER"
  exit 0
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
