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

set -eu

PROJECT_DIR=${GUDBUS_PROJECT_DIR:-/boot/config/plugins/compose.manager/projects/GUDBUS}
CONTAINER=${GUDBUS_CONTAINER:-gudbus}
REPO=${GUDBUS_REPO:-haksanlulz/GUDBUS}
COMPOSE="$PROJECT_DIR/docker-compose.yml"

die() { printf '\nFAILED: %s\n' "$1" >&2; exit 1; }
step() { printf '\n== %s\n' "$1"; }

TAG=${1:-}
[ -n "$TAG" ] || die "usage: $0 <image-tag>   e.g. $0 sha-ef30b62

Find the tag: it is 'sha-' plus the short commit sha of what you want deployed.
Check that commit's Tests run is green first — publishing does not depend on it."

# ---------------------------------------------------------------- preflight
step "Preflight"
[ -f "$COMPOSE" ] || die "no compose file at $COMPOSE (set GUDBUS_PROJECT_DIR)"
command -v docker >/dev/null 2>&1 || die "docker not on PATH"
docker compose version >/dev/null 2>&1 || die "'docker compose' (v2) unavailable"

CURRENT_IMAGE=$(docker inspect -f '{{.Config.Image}}' "$CONTAINER" 2>/dev/null) \
  || die "container '$CONTAINER' not found. Running containers:
$(docker ps --format '  {{.Names}}')"
CURRENT_ID=$(docker inspect -f '{{.Id}}' "$CONTAINER")
printf '  container : %s\n  image now : %s\n  target    : %s\n' \
  "$CONTAINER" "$CURRENT_IMAGE" "$TAG"

case "$CURRENT_IMAGE" in
  *":$TAG") die "already running $TAG — nothing to do" ;;
esac

# ------------------------------------------------------------- CI gate
# The publish workflow has no `needs:` on the test workflow, so an image
# existing proves only that it built. A commit with a red matrix still ships a
# pullable tag. Refuse it unless explicitly overridden.
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
docker compose up -d --force-recreate || die "compose up failed"

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

step "Done. Following logs (Ctrl+C to stop)"
printf '  expect: migrations apply, all cogs load, a command re-sync if the\n'
printf '          command set changed, then the gateway connects.\n\n'
exec docker logs -f --since 2m "$CONTAINER"
