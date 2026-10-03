#!/usr/bin/env bash
# Deploy or update the GURPS bot. Idempotent — run it for first setup and for
# every update. Run from anywhere; it cd's to the project root itself.
set -euo pipefail

cd "$(dirname "$0")/.."   # deploy/ -> project root

echo "==> Pulling latest"
# Only a missing remote is a skip (the rsync'd-tree setup in DEPLOY.md). Any
# other pull failure — diverged branch, local edits, network — must stop here:
# carrying on would migrate, test and restart the OLD code and then say Done.
if git remote get-url origin >/dev/null 2>&1; then
  git pull --ff-only
else
  echo "    (no git remote — skipping)"
fi

echo "==> Syncing dependencies (creates/updates .venv)"
uv sync

echo "==> Vendoring GCS reference data (gitignored — required for /skill etc.)"
uv run python tools/sync_gcs_library.py
uv run python tools/sync_gcs_library.py --check

echo "==> Checking .env"
if [ ! -f .env ]; then
  echo "!!  .env missing. Copy .env.example to .env and fill DISCORD_TOKEN +"
  echo "    BOT_AUTHOR_LEGAL_NAME (your handle), then re-run."
  exit 1
fi
grep -qE '^DISCORD_TOKEN=.+' .env || { echo "!!  DISCORD_TOKEN not set in .env"; exit 1; }
grep -qE '^BOT_AUTHOR_LEGAL_NAME=.+' .env \
  || echo "!!  warning: BOT_AUTHOR_LEGAL_NAME unset — /legal notice ships non-compliant"

echo "==> Database create/stamp + migrations"
# Fresh DB: created at current schema + stamped at Alembic head. Stamped DB:
# alembic upgrade head. Unstamped legacy DB: refuses with the one-time fix
# (create_all can't add columns — updates need migrations to actually run).
uv run python -m gurps_bot.db.bootstrap

echo "==> Smoke test"
uv run python -m pytest tests/ -q || { echo "!!  tests failed — review before restarting"; exit 1; }

echo "==> Restarting service"
if systemctl list-unit-files 2>/dev/null | grep -q '^gurps-bot.service'; then
  sudo systemctl restart gurps-bot
  echo "    restarted. tail logs:  journalctl -u gurps-bot -f"
else
  echo "    service not installed yet. Install it:"
  echo "      sudo cp deploy/gurps-bot.service /etc/systemd/system/"
  echo "      sudo systemctl daemon-reload && sudo systemctl enable --now gurps-bot"
fi

echo "==> Done. Slash commands re-register at startup when they change;"
echo "    if they ever go missing, mention the bot with: @<bot> sync"
