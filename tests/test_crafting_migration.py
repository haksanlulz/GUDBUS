"""The crafting tables must arrive by migration, on a database that predates them.

Slice 1a-B adds the first NEW TABLES since `campaign_settings`, which is the
exact change that crash-looped production on 2026-07-27: `bootstrap.main()` ran
`create_all` unconditionally, create_all built the new table behind Alembic's
back, and the migration then collided with it. Column adds had hidden the flaw
for every release before that, because create_all silently ignores those.

`tests/test_bootstrap_new_table.py` guards the mechanism using the
campaign_settings scenario. This file guards THIS migration, on a database
stamped at the revision just before it — because a guard that only ever
exercises one historical table proves the code path, not the new work.

The failure it would have caught in 2026-07-27 terms:
    (sqlite3.OperationalError) table crafting_projects already exists
"""

from __future__ import annotations

import sqlite3

import pytest

from gurps_bot.db import bootstrap

# Imported for its side effect: a table nobody imported is not on the shared
# metadata, and the fixture below can only remove what is registered.
from gurps_bot.db import crafting as _crafting  # noqa: F401
from tests.test_bootstrap_new_table import _build_pre_migration_db

#: The revision this migration follows. Pinned so that inserting a migration
#: between them makes this test say so rather than silently testing a gap.
PREVIOUS_HEAD = "c3f1a8b56d20"
THIS_REVISION = "e2a7c4d18b93"

NEW_TABLES = ("crafting_projects", "crafting_charges")


@pytest.fixture
def db_without_crafting(tmp_path):
    """A database as it stood one release before crafting existed.

    ⚠️ Same trap as `test_bootstrap_new_table.legacy_db`: this drop list is
    "every table that did not exist at c3f1a8b56d20", so the NEXT migration
    adding a table has to be added here too. Otherwise `create_all` builds it
    into a database stamped in its past and `bootstrap.main` dies on
    "already exists" — which reads exactly like the production incident and is
    entirely the fixture's doing.
    """
    db = tmp_path / "gurps_bot.db"
    _build_pre_migration_db(
        db, drop_tables=list(NEW_TABLES), drop_columns={},
        # created by a later migration (a3d9e5f71c08), so absent at this stamp
        drop_indexes=["uq_wealth_default"],
    )
    con = sqlite3.connect(db)
    con.execute(
        "create table alembic_version "
        "(version_num varchar(32) not null primary key)"
    )
    con.execute(f"insert into alembic_version values ('{PREVIOUS_HEAD}')")
    con.commit()
    con.close()
    return db


def _tables(db) -> set[str]:
    con = sqlite3.connect(db)
    names = {
        r[0] for r in con.execute("select name from sqlite_master where type='table'")
    }
    con.close()
    return names


def _indexes(db, table: str) -> set[str]:
    con = sqlite3.connect(db)
    names = {r[1] for r in con.execute(f"pragma index_list({table})")}
    con.close()
    return names


def _revision(db) -> str | None:
    con = sqlite3.connect(db)
    row = con.execute("select version_num from alembic_version").fetchone()
    con.close()
    return row[0] if row else None


class TestTheFixtureIsHonest:
    """FAIL CLOSED: if the fixture already had the tables, everything below
    would pass without the migration ever running."""

    def test_the_tables_really_are_absent_to_begin_with(self, db_without_crafting):
        assert not _tables(db_without_crafting) & set(NEW_TABLES)

    def test_it_starts_at_the_revision_this_migration_follows(self, db_without_crafting):
        assert _revision(db_without_crafting) == PREVIOUS_HEAD

    def test_this_migration_is_still_the_one_after_it(self):
        """A migration inserted between the two would make the fixture test a
        gap rather than this change."""
        from gurps_bot.db.migrations.versions import (
            e2a7c4d18b93_add_crafting_projects as migration,
        )

        assert migration.revision == THIS_REVISION
        assert migration.down_revision == PREVIOUS_HEAD


class TestTheDeployPath:
    def test_bootstrap_reaches_head_and_creates_both_tables(self, db_without_crafting):
        rc = bootstrap.main(f"sqlite+aiosqlite:///{db_without_crafting}")

        assert rc == 0
        assert _revision(db_without_crafting) == bootstrap.script_head()
        assert set(NEW_TABLES) <= _tables(db_without_crafting)

    def test_the_indexes_land_too(self, db_without_crafting):
        """guild_id is indexed because `cleanup_guild_data` purges on it, and
        that purge runs on a box sharing a disk with sixty containers."""
        bootstrap.main(f"sqlite+aiosqlite:///{db_without_crafting}")
        assert "ix_crafting_projects_guild_id" in _indexes(
            db_without_crafting, "crafting_projects"
        )
        assert "ix_crafting_charges_project_id" in _indexes(
            db_without_crafting, "crafting_charges"
        )

    def test_existing_rows_survive(self, db_without_crafting):
        con = sqlite3.connect(db_without_crafting)
        con.execute(
            "insert into characters (discord_user_id, name, total_points,"
            " profile_json, calc_json, equipment_json, settings_json,"
            " raw_gcs_json, source_filename, imported_at)"
            " values (42, 'Keeper', 150, '{}', '{}', '[]', '{}', '{}', 'x.gcs',"
            " '2026-08-09 00:00:00')"
        )
        con.commit()
        con.close()

        bootstrap.main(f"sqlite+aiosqlite:///{db_without_crafting}")

        con = sqlite3.connect(db_without_crafting)
        rows = con.execute("select name from characters").fetchall()
        con.close()
        assert rows == [("Keeper",)]

    def test_running_it_twice_is_idempotent(self, db_without_crafting):
        url = f"sqlite+aiosqlite:///{db_without_crafting}"
        assert bootstrap.main(url) == 0
        assert bootstrap.main(url) == 0
        assert _revision(db_without_crafting) == bootstrap.script_head()


class TestTheNewTablesAreUsableAfterMigrating:
    def test_a_project_and_its_charge_insert(self, db_without_crafting):
        """The schema the migration writes must match what the models expect —
        a migration that creates a table with the wrong columns still reaches
        head and still passes every test above."""
        bootstrap.main(f"sqlite+aiosqlite:///{db_without_crafting}")

        con = sqlite3.connect(db_without_crafting)
        con.execute(
            "insert into crafting_projects (discord_user_id, guild_id, name,"
            " domain, complexity, stage, skill, retail_price, flawed_theory,"
            " attempts, elapsed_days, major_bugs, minor_bugs)"
            " values (1, 2, 'thing', 'invention', 'average', 'concept', 14, 100,"
            " 0, 0, 0, 0, 0)"
        )
        con.execute(
            "insert into crafting_charges (project_id, kind, amount, outcome)"
            " values (1, 'attempt', 100, 'failure')"
        )
        con.commit()
        rows = con.execute(
            "select kind, outcome from crafting_charges"
        ).fetchall()
        con.close()
        assert rows == [("attempt", "failure")]

    def test_the_migrated_columns_match_the_model(self, db_without_crafting):
        from gurps_bot.db.crafting import CraftingCharge, CraftingProject

        bootstrap.main(f"sqlite+aiosqlite:///{db_without_crafting}")

        con = sqlite3.connect(db_without_crafting)
        for model in (CraftingProject, CraftingCharge):
            table = model.__tablename__
            actual = {r[1] for r in con.execute(f"pragma table_info({table})")}
            expected = set(model.__table__.columns.keys())
            assert actual == expected, (
                f"{table}: migration and model disagree.\n"
                f"  only in db    : {sorted(actual - expected)}\n"
                f"  only in model : {sorted(expected - actual)}"
            )
        con.close()
