"""Deploy-path migration coherence.

The documented update path never ran Alembic, and startup create_all cannot
add columns to existing tables — so the repo's own migration history
(combatants.will etc.) would break a live DB updated as documented. The fix:

* ``DatabaseManager.create_tables`` stamps a brand-fresh file database at
  Alembic head (the schema create_all just built is head);
* in-memory databases (every test fixture) and pre-existing unstamped
  databases are never stamped — guessing a legacy DB's revision could
  mis-apply migrations;
* ``python -m gurps_bot.db.bootstrap`` is the deploy entry point: create/stamp
  fresh, ``upgrade head`` stamped, refuse-with-instructions on legacy.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from gurps_bot.db.engine import DatabaseManager
from gurps_bot.db.models import Base

REPO_ROOT = Path(__file__).resolve().parents[1]


def _script_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    return ScriptDirectory.from_config(cfg).get_current_head()


async def _stamped_revision(url: str) -> str | None:
    """The alembic_version stamp in the DB at ``url``, or None if unstamped."""
    eng = create_async_engine(url)
    try:
        async with eng.connect() as conn:

            def _read(sync_conn):
                if not inspect(sync_conn).has_table("alembic_version"):
                    return None
                return sync_conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()

            return await conn.run_sync(_read)
    finally:
        await eng.dispose()


def _url(tmp_path: Path, name: str) -> str:
    return f"sqlite+aiosqlite:///{(tmp_path / name).as_posix()}"


async def _create_all_only(url: str) -> None:
    """Build the schema the way a legacy deploy did: bare create_all, no stamp."""
    eng = create_async_engine(url)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await eng.dispose()


class TestFreshDbStamp:
    async def test_fresh_file_db_is_stamped_at_head(self, tmp_path):
        url = _url(tmp_path, "fresh.db")
        mgr = DatabaseManager()
        mgr.init(url)
        await mgr.create_tables()
        await mgr.dispose()

        assert await _stamped_revision(url) == _script_head()

    async def test_existing_unstamped_db_is_left_unstamped(self, tmp_path):
        # A DB that already had tables may be at any historical schema —
        # stamping head would lie about migrations that never ran.
        url = _url(tmp_path, "legacy.db")
        await _create_all_only(url)

        mgr = DatabaseManager()
        mgr.init(url)
        await mgr.create_tables()
        await mgr.dispose()

        assert await _stamped_revision(url) is None

    async def test_in_memory_db_never_stamps(self):
        # Every test fixture in this repo builds in-memory DBs via create_all;
        # stamping would drag alembic into hundreds of unrelated tests.
        mgr = DatabaseManager()
        mgr.init("sqlite+aiosqlite://")
        await mgr.create_tables()
        async with mgr.engine.connect() as conn:
            has = await conn.run_sync(
                lambda c: inspect(c).has_table("alembic_version")
            )
        await mgr.dispose()

        assert has is False


class TestBootstrapEntryPoint:
    def test_fresh_db_bootstraps_to_head(self, tmp_path):
        from gurps_bot.db import bootstrap

        url = _url(tmp_path, "deploy.db")
        rc = bootstrap.main(url)

        assert rc == 0
        assert asyncio.run(_stamped_revision(url)) == _script_head()

    def test_upgrade_head_is_noop_on_freshly_stamped_db(self, tmp_path):
        # The deploy path runs bootstrap on every update — a fresh install
        # followed immediately by an update must not error.
        from gurps_bot.db import bootstrap

        url = _url(tmp_path, "again.db")
        assert bootstrap.main(url) == 0
        assert bootstrap.main(url) == 0
        assert asyncio.run(_stamped_revision(url)) == _script_head()

    def test_legacy_unstamped_db_refuses_with_instructions(self, tmp_path, capsys):
        from gurps_bot.db import bootstrap

        url = _url(tmp_path, "old.db")
        asyncio.run(_create_all_only(url))
        rc = bootstrap.main(url)

        assert rc == 2
        err = capsys.readouterr().err
        assert "stamp head" in err
        # and it must not have guessed a stamp
        assert asyncio.run(_stamped_revision(url)) is None


class TestDeployScriptRunsMigrations:
    def test_deploy_sh_invokes_bootstrap(self):
        # The documented update path used to run no alembic at all; pin the
        # deploy script to the bootstrap entry point.
        content = (REPO_ROOT / "deploy" / "deploy.sh").read_text(encoding="utf-8")
        assert "gurps_bot.db.bootstrap" in content
