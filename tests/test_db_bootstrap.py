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

import pytest
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


class TestNoMigrationScriptsAtAll:
    """A head of None is a packaging fault, and has to say so.

    Alembic returns None for the head when it finds no revision files —
    `script_location` points somewhere wrong, or `versions/` never made it into
    the image. That is a different fault from "this database is behind the
    code", with a different fix, and before this the operator got the stale
    refusal with `head: None` printed in it.

    The condition cannot occur in a correctly packaged tree, so it is built
    here out of a real versions-less Alembic config rather than asserted about.
    """

    def _versionless_root(self, tmp_path: Path) -> Path:
        (tmp_path / "migrations" / "versions").mkdir(parents=True)
        (tmp_path / "alembic.ini").write_text(
            "[alembic]\nscript_location = %(here)s/migrations\n", encoding="utf-8"
        )
        return tmp_path

    def test_script_head_refuses_rather_than_returning_none(
        self, tmp_path, monkeypatch
    ):
        from gurps_bot.db import bootstrap

        monkeypatch.setattr(bootstrap, "REPO_ROOT", self._versionless_root(tmp_path))
        with pytest.raises(bootstrap.SchemaGateError) as exc:
            bootstrap.script_head()
        message = str(exc.value)
        assert "alembic.ini" in message, message
        assert "script_location" in message, message
        assert "versions" in message, message

    def test_the_gate_names_the_packaging_fault_not_a_stale_schema(
        self, tmp_path, monkeypatch
    ):
        """The whole point: a real stamped DB must not be blamed for this."""
        from gurps_bot.db import bootstrap

        # Built with the real alembic.ini, so the database itself is fine.
        url = _url(tmp_path, "stamped.db")
        assert bootstrap.main(url) == 0

        root = tmp_path / "alembic_root"
        root.mkdir()
        monkeypatch.setattr(bootstrap, "REPO_ROOT", self._versionless_root(root))
        with pytest.raises(bootstrap.SchemaGateError) as exc:
            bootstrap.ensure_schema_current(url)
        message = str(exc.value)
        assert "script_location" in message, message
        assert "head:     None" not in message, message
        assert "behind the code" not in message, message

    def test_the_gate_refuses_a_fresh_db_instead_of_booting_unstamped(
        self, tmp_path, monkeypatch
    ):
        """The fresh-DB branch was the fail-open: it returned before any check.

        Measured before the fix: the gate took `not has_tables ->
        create_and_stamp -> return`, alembic resolved "head" to nothing, and
        the bot booted on a database left (has_tables=True, revision=None) out
        of an image carrying no migrations at all.
        """
        from gurps_bot.db import bootstrap

        url = _url(tmp_path, "fresh.db")
        root = tmp_path / "alembic_root"
        root.mkdir()
        monkeypatch.setattr(bootstrap, "REPO_ROOT", self._versionless_root(root))

        with pytest.raises(bootstrap.SchemaGateError) as exc:
            bootstrap.ensure_schema_current(url)
        assert "script_location" in str(exc.value), exc.value
        assert not (tmp_path / "fresh.db").exists(), "the gate created a database"

    def test_the_deploy_path_blames_packaging_not_a_brand_new_database(
        self, tmp_path, monkeypatch, capsys
    ):
        """main() is the entry point deploy/deploy.sh and the Dockerfile run.

        Before the fix a fresh database here drew the LEGACY refusal, which
        blames a correctly-created database and prescribes `alembic stamp
        head` — a no-op in a tree with no revisions.
        """
        from gurps_bot.db import bootstrap

        url = _url(tmp_path, "fresh_deploy.db")
        root = tmp_path / "alembic_root"
        root.mkdir()
        monkeypatch.setattr(bootstrap, "REPO_ROOT", self._versionless_root(root))

        assert bootstrap.main(url) == 2
        err = capsys.readouterr().err
        assert "script_location" in err, err
        assert "predates Alembic" not in err, err

    def test_the_deploy_path_refuses_a_stamped_db_without_a_raw_traceback(
        self, tmp_path, monkeypatch, capsys
    ):
        """Before the fix this reached upgrade_head, and alembic raised
        CommandError("Can't locate revision identified by ...") out of main().
        """
        from gurps_bot.db import bootstrap

        url = _url(tmp_path, "stamped.db")
        assert bootstrap.main(url) == 0  # built with the real alembic.ini

        root = tmp_path / "alembic_root"
        root.mkdir()
        monkeypatch.setattr(bootstrap, "REPO_ROOT", self._versionless_root(root))

        assert bootstrap.main(url) == 2
        assert "script_location" in capsys.readouterr().err


class TestPackagingFaultsAlembicRaisesOn:
    """The other two shapes of the same fault, which Alembic RAISES on.

    An empty ``versions/`` is the only one that returns None. Measured against
    built trees: a tree with no alembic.ini at all raises ``CommandError("No
    'script_location' key found in configuration.")``, and a script_location
    naming a directory that is not there raises ``CommandError("Path doesn't
    exist: ...")``. Both escaped as a raw traceback out of BOTH entry points —
    past ``run_bot``'s ``except SchemaGateError``, so the refusal never reached
    the rotating log file either, and out of ``main()`` instead of an exit 2.

    Each root below is a real Alembic config, not a mock, so these stay honest
    if Alembic changes which faults it raises on.
    """

    def _no_ini_root(self, tmp_path: Path) -> Path:
        root = tmp_path / "no_ini"
        root.mkdir()
        return root

    def _bad_location_root(self, tmp_path: Path) -> Path:
        root = tmp_path / "bad_location"
        root.mkdir()
        (root / "alembic.ini").write_text(
            "[alembic]\nscript_location = %(here)s/not_shipped\n", encoding="utf-8"
        )
        return root

    @pytest.fixture(params=["_no_ini_root", "_bad_location_root"])
    def broken_root(self, request, tmp_path):
        return getattr(self, request.param)(tmp_path)

    def test_script_head_refuses_instead_of_raising_commanderror(
        self, broken_root, monkeypatch
    ):
        from gurps_bot.db import bootstrap

        monkeypatch.setattr(bootstrap, "REPO_ROOT", broken_root)
        with pytest.raises(bootstrap.SchemaGateError) as exc:
            bootstrap.script_head()
        message = str(exc.value)
        assert "script_location" in message, message
        # Alembic's own words are quoted, because they are the only thing that
        # tells these two faults apart for the operator reading the log.
        assert "alembic says:" in message, message

    def test_the_startup_gate_refuses_and_touches_no_database(
        self, tmp_path, broken_root, monkeypatch
    ):
        from gurps_bot.db import bootstrap

        url = _url(tmp_path, "untouched.db")
        monkeypatch.setattr(bootstrap, "REPO_ROOT", broken_root)
        with pytest.raises(bootstrap.SchemaGateError) as exc:
            bootstrap.ensure_schema_current(url)
        assert "script_location" in str(exc.value), exc.value
        assert not (tmp_path / "untouched.db").exists(), "the gate created a database"

    def test_the_deploy_path_exits_2_instead_of_a_traceback(
        self, tmp_path, broken_root, monkeypatch, capsys
    ):
        from gurps_bot.db import bootstrap

        url = _url(tmp_path, "deploy.db")
        monkeypatch.setattr(bootstrap, "REPO_ROOT", broken_root)
        assert bootstrap.main(url) == 2
        err = capsys.readouterr().err
        assert "script_location" in err, err
        assert "predates Alembic" not in err, err


class TestDeployScriptRunsMigrations:
    def test_deploy_sh_invokes_bootstrap(self):
        # The documented update path used to run no alembic at all; pin the
        # deploy script to the bootstrap entry point.
        content = (REPO_ROOT / "deploy" / "deploy.sh").read_text(encoding="utf-8")
        assert "gurps_bot.db.bootstrap" in content
