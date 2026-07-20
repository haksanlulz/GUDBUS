# Deploying

Small discord.py bot, one SQLite file, runs as a systemd service. ~200 MB RAM,
~70 MB vendored data. Any cheap Linux host works: Oracle Cloud Always-Free (steps
below), a $4-5 VPS (Hetzner/Vultr/DO), or a Raspberry Pi. Not serverless — the bot
holds a persistent gateway connection.

Two ways to run it: **Docker** (below — one file to persist, nothing to install on
the host but the engine) or **systemd + uv** (the rest of this doc). Pick one.

## Docker (recommended)

The image bakes in dependencies and the vendored GCS library; the SQLite DB and
logs live in a `/app/data` volume, and the container bootstraps/migrates the DB
on every start. Multi-arch friendly — builds on x86-64 and ARM (Oracle A1, Pi).

```sh
git clone https://github.com/haksanlulz/GUDBUS.git /opt/gurps-bot
cd /opt/gurps-bot
cp .env.example .env
nano .env                 # set DISCORD_TOKEN + BOT_AUTHOR_LEGAL_NAME

docker compose up -d --build
docker compose logs -f
```

Then once, in Discord as the bot owner: `/sync clear:true` (global sync takes up
to an hour; instant if you set `DEV_GUILD_ID`).

**Updating:**

```sh
cd /opt/gurps-bot && git pull && docker compose up -d --build
```

The bootstrap step (`gurps_bot.db.bootstrap`) runs automatically on each start, so
schema migrations apply themselves. Re-vendoring the GCS data happens at build
time, so a rebuild picks up any pin bump. Run `/sync clear:true` only if commands
changed.

**Prebuilt image:** pushes to `main` publish `ghcr.io/haksanlulz/gudbus:latest`
(see `.github/workflows/docker-publish.yml`). The same workflow also pushes to
Docker Hub (`docker.io/<user>/gudbus`) when the `DOCKERHUB_USERNAME` and
`DOCKERHUB_TOKEN` repo secrets are set — without them it publishes to GHCR only.
To pull instead of build, swap the `build:`/`image:` lines in
`docker-compose.yml` as noted there, then `docker compose pull && docker compose up -d`.

**Data & backups:** the DB is in the `gurps-data` named volume. Back it up with

```sh
docker compose exec gurps-bot sh -c 'sqlite3 data/gurps_bot.db ".backup /app/data/backup.db"'
docker compose cp gurps-bot:/app/data/backup.db ./gurps_bot-backup.db
```

or bind-mount a host path instead (see the comment in `docker-compose.yml`).

---

## systemd + uv (manual)

Get the source onto the host:

```sh
sudo mkdir -p /opt/gurps-bot && sudo chown $USER /opt/gurps-bot
git clone https://github.com/haksanlulz/GUDBUS.git /opt/gurps-bot
```

(or rsync a local working tree to the same path)

## Oracle Cloud free tier

1. Create instance: shape **Ampere A1.Flex** (ARM, free up to 4 OCPU / 24 GB), or
   **VM.Standard.E2.1.Micro** (1 GB) if A1 is out of capacity. Image: Ubuntu
   22.04/24.04. Add your SSH key. Login user is `ubuntu`.
2. No inbound ports needed — the bot only dials out. Don't open anything in
   Security Lists.
3. `ssh -i your-key ubuntu@<instance-public-ip>`
4. On the 1 GB micro, add swap (the in-memory catalog needs headroom):
   ```sh
   sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
   sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```

## Setup

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
cd /opt/gurps-bot
cp .env.example .env
nano .env                 # set DISCORD_TOKEN + BOT_AUTHOR_LEGAL_NAME

./deploy/deploy.sh        # deps, re-vendor GCS data, DB create/migrations, smoke test

sudo cp deploy/gurps-bot.service /etc/systemd/system/
sudo sed -i 's/^User=.*/User=ubuntu/' /etc/systemd/system/gurps-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now gurps-bot
journalctl -u gurps-bot -f
```

Then once, in Discord as the bot owner: `/sync clear:true`. Global sync takes up
to an hour; instant if you set `DEV_GUILD_ID`.

## .env

| Var | Required | Notes |
|---|---|---|
| `DISCORD_TOKEN` | yes | From the Discord Developer Portal. |
| `DATABASE_URL` | no | Defaults to `sqlite+aiosqlite:///data/gurps_bot.db`. |
| `BOT_AUTHOR_LEGAL_NAME` | for `/legal` | Name in the SJG game-aid notice. A handle is fine. Warns at startup if unset. |
| `DEV_GUILD_ID` | no | Test server ID for instant command sync. |
| `SYNC_ON_START` | no | `true` auto-syncs to `DEV_GUILD_ID` on boot. |
| `BOT_INVITE_URL` | no | OAuth2 invite link. |
| `BOT_SUPPORT_URL` | no | Support/contact link for `/legal`. |
| `KOFI_URL`, `BUYMEACOFFEE_URL`, `PATREON_URL`, `GITHUB_SPONSORS_URL`, `PAYPAL_URL`, `LIBERAPAY_URL` | no | Donation links for `/support` + `/donate`. Unset = the commands show a "share the bot" message. |
| `SUPPORT_MESSAGE` | no | Custom blurb on the `/support` embed. |

## Discord portal

- Don't put "GURPS" in the bot's name (SJG trademark). "for GURPS, unofficial"
  in the description is fine.
- Public Bot on, default intents. No message-content intent, so no
  privileged-intent review.
- Your account must own the app — `/sync` is owner-gated.

## Updating

```sh
cd /opt/gurps-bot && git pull && ./deploy/deploy.sh
```

**Migrations:** `deploy.sh` runs `uv run python -m gurps_bot.db.bootstrap` on
every update — a fresh database is created at the current schema and stamped
at Alembic head; a stamped database gets `alembic upgrade head`. Startup
`create_all` can only create tables, never add columns to existing ones, so
updates rely on this step. One-time note for a database deployed before the
bootstrap existed (tables present, no `alembic_version`): confirm the bot
ran fine on the code that built it, then `uv run python -m alembic stamp head`
once — the bootstrap refuses to guess and will tell you the same thing.

Run `/sync clear:true` only if commands changed. Never overwrite
`data/gurps_bot.db` — if you rsync instead of pull, exclude it.

## Backups

```sh
crontab -e
0 4 * * *  /opt/gurps-bot/deploy/backup-db.sh   # daily, keeps newest 14
```

Copy `backups/` somewhere off the box now and then.

## Compliance

Free under the SJ Games Online Policy: facts-only reference data, verbatim notice
in `/legal`. Donations toward hosting are fine. Don't paywall the bot.
