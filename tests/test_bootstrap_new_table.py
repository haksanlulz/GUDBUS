"""Deploy bootstrap must not create new tables behind Alembic's back.

Production incident 2026-07-27: deploying a build that added a brand-new table
crash-looped the hosted bot with

    (sqlite3.OperationalError) table campaign_settings already exists

`bootstrap.main()` called `create_and_stamp()` unconditionally, and that runs
`Base.metadata.create_all`. On an existing database create_all cannot ALTER a
table — so every migration up to that point had been column adds and the flaw
stayed hidden — but it *will* create a table that is new in the models. Alembic
then ran the migration that creates the same table and collided with it.

The startup gate already had the right shape (`create_and_stamp` only when the
DB has no tables); the deploy path did not.
"""

from __future__ import annotations

import sqlite3

import pytest

from gurps_bot.db import bootstrap
from gurps_bot.db.models import Base


def _build_pre_migration_db(db_path, drop_tables: list[str], drop_columns: dict):
    """Create the schema as it was BEFORE a migration, stamped at that revision.

    Mirrors a real deployed database: tables from an older release, an
    alembic_version row naming that release, and no trace of what came after.
    """
    from sqlalchemy import create_engine

    removed_tables = []
    removed_cols = []
    for name in drop_tables:
        table = Base.metadata.tables[name]
        removed_tables.append(table)
        Base.metadata.remove(table)
    for tname, cname in drop_columns.items():
        col = Base.metadata.tables[tname].c[cname]
        removed_cols.append((Base.metadata.tables[tname], col))
        Base.metadata.tables[tname]._columns.remove(col)

    try:
        eng = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(eng)
        eng.dispose()
    finally:
        for table in removed_tables:
            Base.metadata._add_table(table.name, table.schema, table)
        for tbl, col in removed_cols:
            tbl.append_column(col)


@pytest.fixture
def legacy_db(tmp_path):
    """A DB at the revision just before campaign_settings existed."""
    db = tmp_path / "gurps_bot.db"
    _build_pre_migration_db(
        db,
        drop_tables=["campaign_settings"],
        drop_columns={"combatants": "parries_by_weapon"},
    )
    con = sqlite3.connect(db)
    con.execute("create table alembic_version (version_num varchar(32) not null primary key)")
    con.execute("insert into alembic_version values ('a7d3e9c1f2b4')")
    con.commit()
    con.close()
    return db


def _tables(db):
    con = sqlite3.connect(db)
    names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    con.close()
    return names


def _revision(db):
    con = sqlite3.connect(db)
    row = con.execute("select version_num from alembic_version").fetchone()
    con.close()
    return row[0] if row else None


class TestDeployPathOnAnExistingDatabase:
    def test_bootstrap_reaches_head_when_a_migration_adds_a_new_table(self, legacy_db):
        """The regression. Before the fix this raised OperationalError:
        'table campaign_settings already exists'."""
        assert "campaign_settings" not in _tables(legacy_db)

        rc = bootstrap.main(f"sqlite+aiosqlite:///{legacy_db}")

        assert rc == 0
        assert _revision(legacy_db) == bootstrap.script_head()
        assert "campaign_settings" in _tables(legacy_db)

    def test_the_new_column_lands_too(self, legacy_db):
        """create_all can never ALTER, so only a real migration adds this."""
        bootstrap.main(f"sqlite+aiosqlite:///{legacy_db}")
        con = sqlite3.connect(legacy_db)
        cols = [r[1] for r in con.execute("pragma table_info(combatants)")]
        con.close()
        assert "parries_by_weapon" in cols

    def test_existing_rows_survive(self, legacy_db):
        """A deploy migrates a live game database; it must not lose anything."""
        con = sqlite3.connect(legacy_db)
        con.execute(
            "insert into characters (discord_user_id, name, total_points,"
            " profile_json, calc_json, equipment_json, settings_json,"
            " raw_gcs_json, source_filename, imported_at)"
            " values (42, 'Keeper', 150, '{}', '{}', '[]', '{}', '{}', 'x.gcs',"
            " '2026-07-27 00:00:00')"
        )
        con.commit()
        con.close()

        bootstrap.main(f"sqlite+aiosqlite:///{legacy_db}")

        con = sqlite3.connect(legacy_db)
        rows = con.execute("select name from characters").fetchall()
        con.close()
        assert rows == [("Keeper",)]

    def test_running_it_twice_is_idempotent(self, legacy_db):
        url = f"sqlite+aiosqlite:///{legacy_db}"
        assert bootstrap.main(url) == 0
        assert bootstrap.main(url) == 0
        assert _revision(legacy_db) == bootstrap.script_head()


class TestFreshDatabaseStillWorks:
    def test_brand_new_db_is_created_and_stamped(self, tmp_path):
        """The path create_and_stamp exists for must not regress."""
        db = tmp_path / "fresh.db"
        rc = bootstrap.main(f"sqlite+aiosqlite:///{db}")
        assert rc == 0
        assert _revision(db) == bootstrap.script_head()
        assert "campaign_settings" in _tables(db)


class TestUnstampedLegacyStillRefuses:
    def test_tables_without_a_stamp_is_still_a_refusal(self, tmp_path):
        """Never guess a legacy revision — this refusal is load-bearing."""
        db = tmp_path / "legacy.db"
        _build_pre_migration_db(db, drop_tables=["campaign_settings"], drop_columns={})
        assert bootstrap.main(f"sqlite+aiosqlite:///{db}") == 2
