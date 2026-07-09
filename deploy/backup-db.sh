#!/usr/bin/env bash
# Snapshot the SQLite database (timestamped, keeps the newest N). Cron-able and
# safe to run while the bot is live (uses sqlite3 .backup for a consistent copy).
#
#   crontab:  0 4 * * *  /opt/gurps-bot/deploy/backup-db.sh
#
# Override defaults with env vars: BOT_BACKUP_DIR, BOT_BACKUP_KEEP.
set -euo pipefail

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

if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB" ".backup '$OUT'"          # consistent snapshot, WAL-safe
else
  cp "$DB" "$OUT"                          # fallback; prefer installing sqlite3
fi
echo "backed up -> $OUT"

# Prune: keep the newest $KEEP, delete the rest.
ls -1t "$DEST"/gurps_bot-*.db 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f
echo "retained newest $KEEP backups in $DEST/"

# OPSEC + durability: copy $DEST somewhere off this box (another disk / encrypted
# remote). The DB holds user characters, notes, and wealth — don't keep the only
# copy on the same machine.
