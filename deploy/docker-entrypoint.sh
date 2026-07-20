#!/usr/bin/env sh
# Container entrypoint: create-or-migrate the database, then run the bot.
#
# Mirrors the systemd deploy path (deploy/deploy.sh) so a container start is
# self-healing: a brand-new volume gets a fresh schema stamped at Alembic head,
# and an existing one gets `alembic upgrade head` applied. Both are idempotent,
# so this is safe to run on every start/restart.
set -eu

echo "==> Bootstrapping database (create/stamp + migrations)"
python -m gurps_bot.db.bootstrap

echo "==> Starting bot"
# exec so the bot becomes PID 1's replacement and receives SIGTERM directly
# (clean shutdown: disposes the DB engine).
exec python -m gurps_bot
