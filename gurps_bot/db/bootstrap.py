"""Create-or-migrate the database — the single owner of schema-currency logic.

Two entry points, one implementation:

``uv run python -m gurps_bot.db.bootstrap`` — the DEPLOY path (deploy.sh runs it
on every update):

* brand-new DB -> ``create_tables()`` builds the full current schema and
  stamps it at Alembic head. create_all can never ADD columns to an existing
  table, so the stamp is what makes every future ``upgrade head`` meaningful;
* stamped DB -> ``alembic upgrade head`` applies whatever is pending;
* unstamped DB that already has tables (a create_all deploy predating this
  tool) -> refuses with the one-time fix instead of guessing a revision —
  stamping head would lie about migrations that never ran.

:func:`ensure_schema_current` — the STARTUP GATE, called by ``bot.run_bot()``
(i.e. ``python -m gurps_bot``) before any Discord connection. Same fresh-DB and
legacy-DB semantics, but a stale stamp is a loud REFUSAL rather than an
automatic upgrade: the deploy path migrates deliberately, a live game launch
must never silently rewrite the operator's database mid-session.

Why the gate exists: a bot can boot clean with its DB several migrations
behind and only crash mid-game at the first missing column. Startup runs
``init_db`` -> ``create_all``, which builds new tables and never ALTERs an
existing one, so nothing complains until a command touches a missing column.

The alembic helpers are sync on purpose: ``migrations/env.py`` calls
``asyncio.run`` itself, so they must never run on a live event-loop thread
(``create_tables`` dispatches via ``asyncio.to_thread``, and the gate runs
before the bot's event loop exists).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class SchemaGateError(RuntimeError):
    """Startup refusal: the database is not safe for this code to open.

    Carries the whole operator-facing message (database, revision, head, fix
    command) so a caller can log it verbatim.
    """


def is_transient_sqlite_url(url: str) -> bool:
    """True for in-memory SQLite URLs — no file to manage, never stamped."""
    return ":memory:" in url or url.rstrip("/") in ("sqlite+aiosqlite:", "sqlite:")


def _run_alembic(url: str, op: str) -> None:
    """Run ``alembic <op> head`` against exactly ``url``.

    env.py resolves its URL as DATABASE_URL env var > config-set option, and
    ``load_dotenv()`` (gurps_bot.config) exports .env's DATABASE_URL into the
    process — so pinning the config option alone is NOT enough: a stamp aimed
    at the caller's engine would silently land on the .env database instead.
    Pin BOTH, restoring the env var afterwards. Process-global env mutation is
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
    """Mark ``url``'s schema as current-head WITHOUT running migrations.

    Only correct immediately after create_all built a brand-fresh schema —
    the schema IS head at that moment.
    """
    _run_alembic(url, "stamp")


def upgrade_head(url: str) -> None:
    """Apply pending migrations up to head."""
    _run_alembic(url, "upgrade")


def script_head() -> str:
    """The Alembic head revision THIS code expects (single owner of the lookup)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    return ScriptDirectory.from_config(cfg).get_current_head()


async def _inspect_db(url: str) -> tuple[bool, str | None]:
    """(has_any_tables, stamped_revision) for the DB at ``url``.

    ``stamped_revision`` is ``None`` when there is no ``alembic_version`` table
    OR the table exists but holds no row — both mean "unstamped", and both are
    falsy, so callers can test the stamp with a plain truth check.
    """
    from sqlalchemy import inspect, text
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(url)
    try:
        async with eng.connect() as conn:

            def _read(sync_conn):
                names = inspect(sync_conn).get_table_names()
                if "alembic_version" not in names:
                    return bool(names), None
                revision = sync_conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
                return bool(names), revision

            return await conn.run_sync(_read)
    finally:
        await eng.dispose()


def create_and_stamp(url: str) -> None:
    """Build the current schema and stamp head when the DB is brand-fresh.

    Single implementation of the fresh-DB path, shared by :func:`main` (deploy)
    and :func:`ensure_schema_current` (startup). ``create_tables`` only stamps a
    database that had NO tables beforehand — see ``db/engine.py``.
    """

    async def _create() -> None:
        from gurps_bot.db.engine import DatabaseManager

        mgr = DatabaseManager()
        mgr.init(url)
        await mgr.create_tables()  # stamps head when the schema is brand-fresh
        await mgr.dispose()

    asyncio.run(_create())


def _resolve_url() -> str:
    """The database URL the bot's engine will actually open.

    Mirrors ``DatabaseManager.init``: ``gurps_bot.config`` runs ``load_dotenv``,
    so DATABASE_URL from .env is already in the environment by import time; the
    explicit ``getenv`` also honours a URL exported after import.
    """
    import os

    from gurps_bot.config import DATABASE_URL

    return os.getenv("DATABASE_URL") or DATABASE_URL


def _display_url(url: str) -> str:
    """The URL as shown to an operator, with any password redacted.

    Refusals are logged; a Postgres URL would otherwise write its credentials
    into the log file.
    """
    try:
        from sqlalchemy.engine import make_url

        return make_url(url).render_as_string(hide_password=True)
    except Exception:  # pragma: no cover - never let formatting break the refusal
        return url


def _legacy_refusal(url: str) -> str:
    """Message for a DB with tables but no stamp (shared by deploy + startup)."""
    return (
        f"!!  This database predates Alembic management: tables exist but\n"
        f"    there is no alembic_version stamp.\n"
        f"        database: {_display_url(url)}\n"
        f"    One-time fix — confirm the schema is current (the bot ran fine on\n"
        f"    this exact code), then:\n"
        f"        uv run python -m alembic stamp head\n"
        f"    and re-run:\n"
        f"        uv run python -m gurps_bot.db.bootstrap"
    )


def _stale_refusal(url: str, revision: str, head: str) -> str:
    """Message for a DB stamped BELOW head."""
    return (
        f"!!  REFUSING TO START: this database's schema is behind the code.\n"
        f"        database: {_display_url(url)}\n"
        f"        stamped:  {revision}\n"
        f"        head:     {head}\n"
        f"    Startup builds missing tables but can never ALTER an existing one,\n"
        f"    so launching now would crash mid-session on the first command that\n"
        f"    touches a new column. Migrate first, then relaunch:\n"
        f"        uv run python -m gurps_bot.db.bootstrap"
    )


def ensure_schema_current(url: str | None = None) -> None:
    """STARTUP GATE — raise :class:`SchemaGateError` unless the DB is safe to open.

    Called by ``bot.run_bot()`` before the Discord connection, never by
    ``init_db``: every in-memory test fixture must stay untouched, and an
    in-memory URL is a no-op here for the same reason.

    * transient / in-memory URL -> no-op;
    * absent or empty database   -> :func:`create_and_stamp` (first run works);
    * tables but no stamp        -> REFUSE (never guess a legacy revision);
    * stamped below head         -> REFUSE, loudly, naming the fix;
    * stamped at head            -> proceed.

    Deliberately does NOT upgrade: migrating a live game database is the deploy
    path's job (``main``), run by an operator who chose that moment.

    Sync, and must not be called from a running event loop (it drives alembic,
    which runs ``asyncio.run`` itself).
    """
    if url is None:
        url = _resolve_url()
    if is_transient_sqlite_url(url):
        return

    has_tables, revision = asyncio.run(_inspect_db(url))
    if not has_tables:
        create_and_stamp(url)
        return
    if not revision:
        raise SchemaGateError(_legacy_refusal(url))
    head = script_head()
    if revision != head:
        raise SchemaGateError(_stale_refusal(url, revision, head))


def main(url: str | None = None) -> int:
    if url is None:
        url = _resolve_url()
    if is_transient_sqlite_url(url):
        print("In-memory database URL — nothing to bootstrap.")
        return 0

    # create_and_stamp runs create_all, so it is ONLY correct on a database
    # with no tables. On an existing one create_all cannot ALTER a table, but it
    # will happily create a table that is new in the models — behind Alembic's
    # back and without a stamp — and the migration that creates the same table
    # then dies with "table ... already exists". That crash-looped the hosted
    # bot on 2026-07-27. Every migration before that one added columns, which
    # create_all ignores, which is why this survived so long.
    has_tables, stamped = asyncio.run(_inspect_db(url))
    if not has_tables:
        create_and_stamp(url)
        _, stamped = asyncio.run(_inspect_db(url))

    if not stamped:
        print(_legacy_refusal(url), file=sys.stderr)
        return 2

    upgrade_head(url)
    print("Database at Alembic head.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
