# Deploying

Small discord.py bot, one SQLite file, runs as a systemd service. ~200 MB RAM,
~70 MB vendored data. Any cheap Linux host works: Oracle Cloud Always-Free (steps
below), a $4-5 VPS (Hetzner/Vultr/DO), or a Raspberry Pi. Not serverless — the bot
holds a persistent gateway connection.

Two ways to run it: **Docker** (below; only the container engine to install) or
**systemd + uv** (the rest of this doc). Pick one.

## Docker (recommended)

The image bakes in dependencies and the vendored GCS library; the SQLite DB and
logs live in a `/app/data` volume, and the container bootstraps/migrates the DB
on every start. Multi-arch: builds on x86-64 and ARM (Oracle A1, Pi).

```sh
git clone https://github.com/haksanlulz/GUDBUS.git /opt/gurps-bot
cd /opt/gurps-bot
cp .env.example .env
nano .env                 # set DISCORD_TOKEN + BOT_AUTHOR_LEGAL_NAME

docker compose up -d --build
docker compose logs -f
```

Slash commands register themselves on first boot (globally, fingerprint-gated —
nothing to run). If registrations are ever missing, mention the bot: `@<bot> sync`.

**Updating:**

```sh
cd /opt/gurps-bot && git pull && docker compose up -d --build
```

The bootstrap step (`gurps_bot.db.bootstrap`) runs automatically on each start, so
schema migrations apply themselves. Re-vendoring the GCS data happens at build
time, so a rebuild picks up any pin bump. Command changes re-register themselves
on the next start.

**Prebuilt image:** two channels on `ghcr.io/haksanlulz/gudbus`
(see `.github/workflows/docker-publish.yml`):

| Tag | Branch | Architectures | What it is |
|---|---|---|---|
| `:latest` | `main` | amd64 + arm64 | Release. What you want unless you have a reason. |
| `:nightly` | `dev` | amd64 | Trunk. Tests pass, but it has not been released. |
| `:sha-<commit>` | either | as its branch | An exact build. What `deploy/nas-update.sh` pins. |

Releases carry **`linux/amd64` and `linux/arm64`**, so the ARM hosts above
(Oracle A1, Raspberry Pi) can pull rather than build. `docker pull` picks the
right one; nothing to specify.

⚠️ **`:latest` and `:nightly` are moving tags, and recreating a container does
not pull.** Whatever "restart" or "recreate" button your host gives you rebuilds
the container on the copy of that tag already in the local image store, so a
release published after your last pull is simply not there. The container comes
up healthy, the logs are clean, and you are running the previous version — that
happened here on 2026-07-28, and the only tell was a missing extension and a
command sync reporting no change. Pull first, then recreate:

```sh
docker pull ghcr.io/haksanlulz/gudbus:latest
```

Pulling `:sha-<commit>` instead does **not** help: it fetches the right image
but leaves `:latest` pointing at the old one, and `:latest` is what your
container references. `deploy/nas-update.sh --preflight <tag>` compares your
local copy against the registry and says which case you are in. Pinning a
`:sha-` tag avoids the whole question, since those never move.

Trunk is amd64 only, deliberately: arm64 is emulated on the build runner and
roughly doubles it, and nothing pulls an arm64 nightly — the ARM advice is for
strangers deploying a release, and they take `:latest`.

Releases were amd64-only until 2026-07-27, while this document recommended ARM
hosts: the publish job passed no `platforms:` at all, so it built the runner's
architecture and nothing else. `tests/test_ci_workflows.py` now asserts the
built platforms against the ones named here, so the promise and the build
cannot drift apart again.

At a release both branches sit on the same commit and both publish its `sha-`
tag, so that tag belongs to whichever run finished last. The two images are
built from identical source and differ only in the `version` label and build
timestamp — pinning either gets the same bot.

Every published tag comes from a commit whose test matrix passed — the publish
job depends on the test workflow, so a red commit produces no image at all.
Verified by dispatching the publish workflow at a branch carrying a deliberate
failure: both matrix legs failed, the build job was skipped, and no `sha-` tag
appeared for that commit. `nas-update.sh` re-checks anyway, since a workflow
edit could remove the gate.

The same workflow also pushes to Docker Hub (`docker.io/<user>/gudbus`) when the
`DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` repo secrets are set — without them it
publishes to GHCR only. To pull instead of build, swap the `build:`/`image:`
lines in `docker-compose.yml` as noted there, then
`docker compose pull && docker compose up -d`.

**Running a second instance on trunk:** `deploy/nightly-compose.yml` stands up
a `:nightly` container alongside production — same host, same image repo, its
own container, volume and env file. Copy it into its own Compose project
directory as `docker-compose.yml` and `docker compose pull && docker compose up -d`
to refresh it.

It needs **its own Discord application and token**. Two processes signed in on
one token both hold a gateway session and both answer every interaction, so you
get duplicate replies; that is the one mistake here that does not correct
itself. Its slash commands register globally like production's, but global
registration is per-application, so they only appear in guilds that second bot
is actually in — keep it out of the real guild and they never meet.

`tests/test_deploy_compose.py` asserts the two composes share no container
name, volume or env file, and that the nightly one carries the same hardening;
a dev instance running with more privilege than production is not testing
production.

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

## Pre-flight: is the vendoring source still there?

```sh
uv run python tools/sync_gcs_library.py --verify-upstream
```

Exit 0 means upstream still serves the pinned commit. Exit 1 means it does not,
and every deploy and image build that re-vendors the catalog is broken until
`PINNED_REF` is bumped — so check this *before* a deploy rather than discovering
it mid-build. Cheap by design (blob-filtered fetch, ~1 MB), touches the network,
never writes to the vendored tree.

This exists because upstream deleted its `master` branch on 2026-07-21 and broke
every deploy at once with no detector. Vendoring is keyed on a pinned SHA now, so
a rename is survivable, but a force-push upstream can still orphan the pin.

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

Slash commands register themselves on first boot (globally, fingerprint-gated —
nothing to run). If registrations are ever missing, mention the bot: `@<bot> sync`.

## .env

| Var | Required | Notes |
|---|---|---|
| `DISCORD_TOKEN` | yes | From the Discord Developer Portal. |
| `DATABASE_URL` | no | Defaults to `sqlite+aiosqlite:///data/gurps_bot.db`. |
| `BOT_AUTHOR_LEGAL_NAME` | for `/legal` | Name in the SJG game-aid notice. A handle is fine. Warns at startup if unset. |
| `AUTO_SYNC` | no | Default on: global command registration at startup, only when the command set changed. `0` disables. |
| `DEFER_INTERACTIONS` | no | Default **off**. `1` makes combat commands acknowledge Discord before touching the DB. Discord kills an un-deferred interaction at 3s while SQLite waits up to 5s for a write lock, so a contended write can outlive its token — deferring moves that to 15 min, at the cost of a "thinking…" state on every such command. Unreachable at one table (~10 ms writes); turn on when writes start overlapping or before going public. |
| `BOT_INVITE_URL` | no | OAuth2 invite link. |
| `BOT_SUPPORT_URL` | no | Support/contact link for `/legal`. |
| `KOFI_URL`, `BUYMEACOFFEE_URL`, `PATREON_URL`, `GITHUB_SPONSORS_URL`, `PAYPAL_URL`, `LIBERAPAY_URL` | no | Donation links for `/support` + `/donate`. Unset = the commands show a "share the bot" message. |
| `SUPPORT_MESSAGE` | no | Custom blurb on the `/support` embed. |

## Discord portal

- Don't put "GURPS" in the bot's name (SJG trademark). "for GURPS, unofficial"
  in the description is fine.
- Public Bot on, default intents. No message-content intent, so no
  privileged-intent review.
- Your account must own the app — `/sync` and `@<bot> sync` are owner-gated.

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

Command changes re-register themselves on the next start. Never overwrite
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
