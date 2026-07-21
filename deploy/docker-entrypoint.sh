#!/usr/bin/env sh
# Container entrypoint: create-or-migrate the database, then run the bot.
#
# Mirrors the systemd deploy path (deploy/deploy.sh) so a container start is
# self-healing: a brand-new volume gets a fresh schema stamped at Alembic head,
# and an existing one gets `alembic upgrade head` applied. Both are idempotent,
# so this is safe to run on every start/restart.
set -eu

# The compose file guards this too, but `docker run` bypasses compose entirely,
# and a published image will be started that way. /legal renders the SJG Online
# Policy notice with the author's name injected; unset, it renders a placeholder
# where the name belongs, which is not a policy-compliant notice. Refuse rather
# than run a game aid whose legal notice is broken.
if [ -z "${BOT_AUTHOR_LEGAL_NAME:-}" ]; then
    echo "FATAL: BOT_AUTHOR_LEGAL_NAME is not set." >&2
    echo "  /legal must name the game aid's author to satisfy the Steve Jackson" >&2
    echo "  Games Online Policy. Set it to the name you publish under, e.g." >&2
    echo "  docker run -e BOT_AUTHOR_LEGAL_NAME='Your Name' ..." >&2
    exit 1
fi

echo "==> Bootstrapping database (create/stamp + migrations)"
python -m gurps_bot.db.bootstrap

echo "==> Starting bot"
# exec so the bot becomes PID 1's replacement and receives SIGTERM directly
# (clean shutdown: disposes the DB engine).
exec python -m gurps_bot
