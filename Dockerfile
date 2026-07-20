# syntax=docker/dockerfile:1
#
# GUDBUS — GURPS 4e Discord bot.
#
# Multi-stage build:
#   * builder  — installs deps with uv (from uv.lock) and vendors the pinned
#                GCS reference library (needs git + network at build time).
#   * runtime  — slim, non-root, no build tools; ships the built venv + source
#                + vendored data.
#
# Build:  docker build -t gudbus .
# Run:    docker run --env-file .env -v gurps-data:/app/data gudbus
# (or `docker compose up -d --build` — see docker-compose.yml)
#
# Base images are pinned by digest for reproducible, tamper-resistant builds
# (the tag stays for readability; the digest is enforced, and is a multi-arch
# manifest list so ARM still resolves). Bump with:
#   docker buildx imagetools inspect python:3.12-slim
#   docker buildx imagetools inspect ghcr.io/astral-sh/uv:latest

############################
# Stage 1 — builder
############################
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS builder

# uv: reproducible installs from the repo's uv.lock.
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:93b61e21202b1dab861092748e46bbd6e0e41dd84f59b9174efd2353186e1b47 /uv /uvx /bin/

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

# 2) Project source, then install the package.
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
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Non-root runtime user.
RUN groupadd --system --gid 10001 gurps \
    && useradd --system --uid 10001 --gid gurps --home-dir /app gurps

WORKDIR /app

# Copy the built venv + source (incl. vendored GCS library). The venv's absolute
# path /app/.venv is identical in both stages, so it works unchanged.
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
