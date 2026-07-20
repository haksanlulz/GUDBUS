# syntax=docker/dockerfile:1
#
# GUDBUS — GURPS 4e Discord bot.
#
# Multi-stage build:
#   * builder  — installs deps with uv (from uv.lock) and vendors the pinned
#                GCS reference library (needs git + network at build time).
#   * runtime  — slim, non-root, no build tools; ships the built venv + source
#                + vendored data. The SQLite DB and logs live in the /app/data
#                volume so they survive image rebuilds.
#
# Build:  docker build -t gudbus .
# Run:    docker run --env-file .env -v gurps-data:/app/data gudbus
# (or just `docker compose up -d --build` — see docker-compose.yml)

############################
# Stage 1 — builder
############################
FROM python:3.12-slim AS builder

# uv gives us reproducible installs straight from the repo's uv.lock.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# git: tools/sync_gcs_library.py clones the pinned GCS master-library snapshot.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Dependency layer — cached until pyproject.toml / uv.lock change.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# 2) Project source, then install the package itself.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# 3) Vendor the pinned GCS reference data (gitignored; required at runtime for
#    /skill, /spell, etc.), then verify the snapshot matches the pin.
RUN uv run python tools/sync_gcs_library.py \
    && uv run python tools/sync_gcs_library.py --check

############################
# Stage 2 — runtime
############################
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Non-root runtime user.
RUN groupadd --system --gid 10001 gurps \
    && useradd --system --uid 10001 --gid gurps --home-dir /app gurps

WORKDIR /app

# Bring over the built venv + source (incl. the vendored GCS library). The venv
# is pinned to the absolute path /app/.venv, identical in both stages, so it
# works unchanged here.
COPY --from=builder --chown=gurps:gurps /app /app

# Ensure the entrypoint is executable regardless of the host's git file mode.
RUN chmod +x /app/deploy/docker-entrypoint.sh

# data/ holds the SQLite DB + rotating logs. Declaring it a volume (and chowning
# it) means a fresh named volume inherits gurps ownership on first run, so the
# non-root process can write to it.
RUN mkdir -p /app/data && chown gurps:gurps /app/data
VOLUME ["/app/data"]

USER gurps

# Entrypoint runs the DB create/migrate bootstrap, then execs the bot.
ENTRYPOINT ["/app/deploy/docker-entrypoint.sh"]
