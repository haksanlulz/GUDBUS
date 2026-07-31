#!/bin/sh
# Snapshot the SQLite database (timestamped, keeps the newest N). Cron-able and
# safe to run while the bot is live: both backup paths use SQLite's online
# backup API (sqlite3 .backup, or python3's Connection.backup), and if neither
# tool exists the script REFUSES rather than falling back to cp — a plain copy
# of a live WAL database can miss committed-but-uncheckpointed pages while
# printing success, which is worse than no backup.
#
#   crontab:  0 4 * * *  /opt/gurps-bot/deploy/backup-db.sh
#
# Override defaults with env vars: BOT_BACKUP_DIR, BOT_BACKUP_KEEP.
# SQLITE3_BIN / PYTHON3_BIN override tool discovery (tests use these; PATH
# stubs are unreliable under Git Bash, which prepends its own bin dir).
#
# POSIX sh, like nas-update.sh: the tests run it under `sh`, and on Ubuntu
# that is dash, which has no `pipefail`. Nothing here needed it — the backup
# commands aren't pipelines, so `set -e` already aborts on their failure, and
# the prune pipeline is best-effort by design.
set -eu

cd "$(dirname "$0")/.."   # project root

DB="data/gurps_bot.db"
DEST="${BOT_BACKUP_DIR:-backups}"
KEEP="${BOT_BACKUP_KEEP:-14}"

if [ ! -f "$DB" ]; then
  echo "no database at $DB (nothing to back up yet)"; exit 0
fi

mkdir -p "$DEST"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="$DEST/gurps_bot-$TS.db"

SQLITE3="${SQLITE3_BIN:-sqlite3}"
PYTHON3="${PYTHON3_BIN:-python3}"

if command -v "$SQLITE3" >/dev/null 2>&1; then
  "$SQLITE3" "$DB" ".backup '$OUT'"        # consistent snapshot, WAL-safe
elif command -v "$PYTHON3" >/dev/null 2>&1; then
  # Same online-backup API through the interpreter the bot already ships with
  # (the Docker image carries no sqlite3 CLI).
  "$PYTHON3" - "$DB" "$OUT" <<'PY'
import sqlite3
import sys

src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close()
src.close()
PY
else
  echo "!! neither sqlite3 nor python3 found — refusing to cp a live database" >&2
  echo "   (a plain copy can silently lose committed-but-uncheckpointed WAL pages)" >&2
  exit 1
fi
echo "backed up -> $OUT"

# Prune: keep the newest $KEEP, delete the rest.
ls -1t "$DEST"/gurps_bot-*.db 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f
echo "retained newest $KEEP backups in $DEST/"

# OPSEC + durability: copy $DEST somewhere off this box (another disk / encrypted
# remote). The DB holds user characters, notes, and wealth — don't keep the only
# copy on the same machine.
