"""Create-or-migrate the database — the deploy path's single entry point.

``uv run python -m gurps_bot.db.bootstrap`` (deploy.sh runs it on every
update):

* brand-new DB -> ``create_tables()`` builds the full current schema and
  stamps it at Alembic head. create_all can never add columns to an existing
  table, so the stamp is what makes every future ``upgrade head`` meaningful;
* stamped DB -> ``alembic upgrade head`` applies whatever is pending;
* unstamped DB that already has tables (a create_all deploy predating this
  tool) -> refuses with the one-time fix instead of guessing a revision —
  stamping head would lie about migrations that never ran.

The alembic helpers are sync on purpose: migrations/env.py calls
``asyncio.run`` itself, so they must never run on a live event-loop thread
(``create_tables`` dispatches via ``asyncio.to_thread``).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def is_transient_sqlite_url(url: str) -> bool:
    """True for in-memory SQLite URLs — no file to manage, never stamped."""
    return ":memory:" in url or url.rstrip("/") in ("sqlite+aiosqlite:", "sqlite:")


def _run_alembic(url: str, op: str) -> None:
    """Run ``alembic <op> head`` against exactly ``url``.

    env.py resolves its URL as DATABASE_URL env var > config-set option, and
    ``load_dotenv()`` (gurps_bot.config) exports .env's DATABASE_URL into the
    process — so pinning the config option alone is not enough: a stamp aimed
    at the caller's engine would silently land on the .env database instead.
    Pin both, restoring the env var afterwards. Process-global env mutation is
    fine here: these run at bootstrap/startup, not concurrently.
    """
    import os

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    saved = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        getattr(command, op)(cfg, "head")
    finally:
        if saved is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = saved


def stamp_head(url: str) -> None:
    """Mark ``url``'s schema as current-head without running migrations.

    Only correct immediately after create_all built a brand-fresh schema —
    the schema is head at that moment.
    """
    _run_alembic(url, "stamp")


def upgrade_head(url: str) -> None:
    """Apply pending migrations up to head."""
    _run_alembic(url, "upgrade")


async def _inspect_db(url: str) -> tuple[bool, bool]:
    """(has_any_tables, has_alembic_stamp) for the DB at ``url``."""
    from sqlalchemy import inspect
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(url)
    try:
        async with eng.connect() as conn:

            def _read(sync_conn):
                names = inspect(sync_conn).get_table_names()
                return bool(names), "alembic_version" in names

            return await conn.run_sync(_read)
    finally:
        await eng.dispose()


def main(url: str | None = None) -> int:
    if url is None:
        import os

        from gurps_bot.config import DATABASE_URL

        url = os.getenv("DATABASE_URL") or DATABASE_URL
    if is_transient_sqlite_url(url):
        print("In-memory database URL — nothing to bootstrap.")
        return 0

    async def _create() -> None:
        from gurps_bot.db.engine import DatabaseManager

        mgr = DatabaseManager()
        mgr.init(url)
        await mgr.create_tables()  # stamps head when the schema is brand-fresh
        await mgr.dispose()

    asyncio.run(_create())

    _, stamped = asyncio.run(_inspect_db(url))
    if not stamped:
        print(
            "!!  This database predates Alembic management: tables exist but\n"
            "    there is no alembic_version stamp. One-time fix — confirm the\n"
            "    schema is current (the bot ran fine on this exact code), then:\n"
            "        uv run python -m alembic stamp head\n"
            "    and re-run this bootstrap.",
            file=sys.stderr,
        )
        return 2

    upgrade_head(url)
    print("Database at Alembic head.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
