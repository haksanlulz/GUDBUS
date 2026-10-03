"""Startup schema gate — the live-game launch path must refuse a stale DB.

The failure this guards: a bot launches clean while its database sits several
migrations behind, then crashes mid-game at the first missing column.
``db/bootstrap.py`` already had the right semantics for the DEPLOY path
(fresh -> create+stamp; stamped -> upgrade; unstamped legacy -> refuse, never
guess), but ``python -m gurps_bot`` never ran it — ``init_db`` -> ``create_all``
builds NEW tables and can never ALTER an existing one, so a stale schema boots
silently.

What is pinned here:

* the gate is a single owner living in ``db/bootstrap.py`` (it reuses the same
  create+stamp / legacy-refusal code the deploy entry point uses);
* it is WIRED into ``bot.run_bot()`` — the real ``python -m gurps_bot`` path —
  and fires BEFORE any Discord connection (``GURPSBot.run`` is patched, so no
  token and no network are needed);
* it is scoped to that path only: in-memory URLs (every existing test fixture)
  are a no-op, and ``init_db`` itself is untouched.

Unlike the deploy entry point, the gate never silently migrates a live game DB:
a stale stamp is a loud REFUSAL naming the database, its revision, head, and the
exact command to fix it.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest import mock

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from gurps_bot.db.models import Base

REPO_ROOT = Path(__file__).resolve().parents[1]


# --- helpers ----------------------------------------------------------------


def _script_revisions() -> list[str]:
    """Every migration revision, head first."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    return [r.revision for r in ScriptDirectory.from_config(cfg).walk_revisions()]


def _head() -> str:
    return _script_revisions()[0]


def _base_revision() -> str:
    """The oldest revision — a maximally stale stamp (derived, never hardcoded)."""
    revisions = _script_revisions()
    assert len(revisions) > 1, "need >1 migration for a stale-stamp test"
    return revisions[-1]


def _url(tmp_path: Path, name: str) -> str:
    return f"sqlite+aiosqlite:///{(tmp_path / name).as_posix()}"


async def _build(url: str, *, stamp: str | None) -> None:
    """Create the schema the way a legacy deploy did, optionally stamping ``stamp``."""
    eng = create_async_engine(url)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            if stamp is not None:
                await conn.execute(
                    text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
                await conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                    {"v": stamp},
                )
    finally:
        await eng.dispose()


async def _stamped_revision(url: str) -> str | None:
    eng = create_async_engine(url)
    try:
        async with eng.connect() as conn:

            def _read(sync_conn):
                if not inspect(sync_conn).has_table("alembic_version"):
                    return None
                return sync_conn.execute(text("SELECT version_num FROM alembic_version")).scalar()

            return await conn.run_sync(_read)
    finally:
        await eng.dispose()


# --- the gate itself --------------------------------------------------------


class TestStartupSchemaGate:
    def test_stale_stamp_refuses(self, tmp_path):
        from gurps_bot.db.bootstrap import SchemaGateError, ensure_schema_current

        url = _url(tmp_path, "stale.db")
        asyncio.run(_build(url, stamp=_base_revision()))

        with pytest.raises(SchemaGateError):
            ensure_schema_current(url)

    def test_stale_refusal_names_db_revision_head_and_the_fix(self, tmp_path):
        """Loud AND actionable: an operator reading only this message can fix it."""
        from gurps_bot.db.bootstrap import SchemaGateError, ensure_schema_current

        url = _url(tmp_path, "stale-detail.db")
        stale = _base_revision()
        asyncio.run(_build(url, stamp=stale))

        with pytest.raises(SchemaGateError) as excinfo:
            ensure_schema_current(url)
        message = str(excinfo.value)
        assert "stale-detail.db" in message, "refusal must name the database"
        assert stale in message, "refusal must name the DB's current revision"
        assert _head() in message, "refusal must name the head revision"
        assert "gurps_bot.db.bootstrap" in message, "refusal must name the fix command"

    def test_stale_db_is_not_silently_migrated(self, tmp_path):
        """The live-game path REFUSES; it never migrates the operator's DB for them."""
        from gurps_bot.db.bootstrap import SchemaGateError, ensure_schema_current

        url = _url(tmp_path, "untouched.db")
        stale = _base_revision()
        asyncio.run(_build(url, stamp=stale))

        with pytest.raises(SchemaGateError):
            ensure_schema_current(url)
        assert asyncio.run(_stamped_revision(url)) == stale

    def test_head_stamped_db_proceeds(self, tmp_path):
        from gurps_bot.db.bootstrap import ensure_schema_current

        url = _url(tmp_path, "current.db")
        asyncio.run(_build(url, stamp=_head()))

        ensure_schema_current(url)  # must not raise

    def test_absent_db_proceeds_and_ends_stamped_at_head(self, tmp_path):
        """First run keeps working: bootstrap's create+stamp path builds the schema."""
        from gurps_bot.db.bootstrap import ensure_schema_current

        url = _url(tmp_path, "first-run.db")
        assert not (tmp_path / "first-run.db").exists()

        ensure_schema_current(url)  # must not raise

        assert asyncio.run(_stamped_revision(url)) == _head()

    def test_unstamped_legacy_db_refuses(self, tmp_path):
        """Tables but no alembic_version: refuse with the one-time fix, never guess."""
        from gurps_bot.db.bootstrap import SchemaGateError, ensure_schema_current

        url = _url(tmp_path, "legacy.db")
        asyncio.run(_build(url, stamp=None))

        with pytest.raises(SchemaGateError) as excinfo:
            ensure_schema_current(url)
        message = str(excinfo.value)
        assert "legacy.db" in message
        assert "stamp head" in message
        # and it must NOT have guessed a stamp
        assert asyncio.run(_stamped_revision(url)) is None

    def test_in_memory_url_is_a_noop(self):
        """SCOPE GUARD: the gate must never touch the in-memory DBs the suite uses."""
        from gurps_bot.db.bootstrap import ensure_schema_current

        ensure_schema_current("sqlite+aiosqlite://")  # must not raise


# --- wired into the real startup path (test through the real channel) --------


@pytest.fixture
def quiet_logging(tmp_path, monkeypatch):
    """Point run_bot()'s log file at tmp_path and restore root handlers after."""
    from gurps_bot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    before = list(logging.root.handlers)
    yield
    for handler in list(logging.root.handlers):
        if handler not in before:
            logging.root.removeHandler(handler)
            handler.close()


class TestGateIsWiredIntoStartup:
    """The gate is worthless unless ``python -m gurps_bot`` actually runs it.

    ``__main__`` calls ``bot.run_bot()``, so that is the channel under test —
    with ``GURPSBot.run`` patched out, no token or network is involved.
    """

    def test_run_bot_refuses_stale_db_before_connecting(
        self, tmp_path, monkeypatch, quiet_logging
    ):
        from gurps_bot import bot as bot_module
        from gurps_bot.bot import GURPSBot
        from gurps_bot.db.bootstrap import SchemaGateError

        url = _url(tmp_path, "live.db")
        asyncio.run(_build(url, stamp=_base_revision()))
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.setattr(bot_module, "DISCORD_TOKEN", "not-a-real-token")

        with mock.patch.object(GURPSBot, "run") as fake_run:
            with pytest.raises(SchemaGateError):
                bot_module.run_bot()
        fake_run.assert_not_called()

    def test_run_bot_proceeds_when_schema_is_current(
        self, tmp_path, monkeypatch, quiet_logging
    ):
        from gurps_bot import bot as bot_module
        from gurps_bot.bot import GURPSBot

        url = _url(tmp_path, "live-ok.db")
        asyncio.run(_build(url, stamp=_head()))
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.setattr(bot_module, "DISCORD_TOKEN", "not-a-real-token")

        with mock.patch.object(GURPSBot, "run") as fake_run:
            bot_module.run_bot()
        fake_run.assert_called_once()
