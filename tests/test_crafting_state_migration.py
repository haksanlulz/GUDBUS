"""Migration b6c2d9e4f1a7 on a database that predates it — the TRUE one.

`test_crafting_migration.py` builds its pre-migration database with
`create_all` over a trimmed metadata, which reproduces the historical TABLES
but not a historical column's NOT NULL: the model now says `complexity` is
nullable, so create_all would build it nullable and the one thing this
migration relaxes would already be relaxed before it ran (Rule 25 — a
population that cannot express the defect). So this file lets the migration
chain itself build the crafting tables: the base is stamped at the revision
BEFORE they existed, `alembic upgrade` runs `e2a7c4d18b93` (whose own
`nullable=False` is the constraint under test) up to the previous head, and
the fixture asserts the constraint is there to relax before the deploy path
asserts that it was.
"""

from __future__ import annotations

import os
import sqlite3

import pytest
from alembic import command
from alembic.config import Config

from gurps_bot.db import bootstrap

# Imported for their side effect on Base.metadata, as the sibling file does.
from gurps_bot.db import crafting as _crafting  # noqa: F401
from tests.test_bootstrap_new_table import _build_pre_migration_db

#: The stamp the base is built at: the last revision before the crafting
#: tables. From here the chain, not create_all, owns crafting_projects' shape.
BEFORE_CRAFTING = "c3f1a8b56d20"
PREVIOUS_HEAD = "a3d9e5f71c08"
THIS_REVISION = "b6c2d9e4f1a7"


def _alembic(url: str, op: str, revision: str) -> None:
    """`alembic <op> <revision>` against exactly ``url`` — the same double pin
    `bootstrap._run_alembic` uses, because env.py prefers DATABASE_URL."""
    cfg = Config(str(bootstrap.REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    saved = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        getattr(command, op)(cfg, revision)
    finally:
        if saved is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = saved


@pytest.fixture
def db_at_previous_head(tmp_path):
    """crafting_projects exactly as the migration chain built it one release ago."""
    db = tmp_path / "gurps_bot.db"
    _build_pre_migration_db(
        db,
        drop_tables=["crafting_charges", "crafting_projects"],
        drop_columns={},
        # created by a3d9e5f71c08, so absent at this stamp
        drop_indexes=["uq_wealth_default"],
    )
    con = sqlite3.connect(db)
    con.execute(
        "create table alembic_version (version_num varchar(32) not null primary key)"
    )
    con.execute(f"insert into alembic_version values ('{BEFORE_CRAFTING}')")
    con.commit()
    con.close()
    _alembic(f"sqlite+aiosqlite:///{db}", "upgrade", PREVIOUS_HEAD)
    con = sqlite3.connect(db)
    con.execute(
        "insert into crafting_projects (discord_user_id, guild_id, name, domain,"
        " complexity, stage, skill, retail_price, flawed_theory, attempts,"
        " elapsed_days, major_bugs, minor_bugs)"
        " values (1, 2, 'mansion', 'invention', 'amazing', 'prototype', 18,"
        " 250000, 0, 2, 40, 1, 0)"
    )
    con.execute(
        "insert into crafting_charges (project_id, kind, amount, outcome)"
        " values (1, 'attempt', 250000, 'failure')"
    )
    con.commit()
    con.close()
    return db


def _columns(db, table: str) -> dict[str, int]:
    """column name -> notnull flag."""
    con = sqlite3.connect(db)
    info = {r[1]: r[3] for r in con.execute(f"pragma table_info({table})")}
    con.close()
    return info


def _revision(db) -> str | None:
    con = sqlite3.connect(db)
    row = con.execute("select version_num from alembic_version").fetchone()
    con.close()
    return row[0] if row else None


class TestTheFixtureIsHonest:
    """FAIL CLOSED: the constraint must exist before the migration relaxes it."""

    def test_it_starts_at_the_previous_head(self, db_at_previous_head):
        assert _revision(db_at_previous_head) == PREVIOUS_HEAD

    def test_state_json_is_absent_and_complexity_is_not_null(self, db_at_previous_head):
        columns = _columns(db_at_previous_head, "crafting_projects")
        assert "state_json" not in columns
        assert columns["complexity"] == 1

    def test_this_migration_is_still_the_one_after_it(self):
        from gurps_bot.db.migrations.versions import (
            b6c2d9e4f1a7_add_crafting_project_state as migration,
        )

        assert migration.revision == THIS_REVISION
        assert migration.down_revision == PREVIOUS_HEAD
        assert bootstrap.script_head() == THIS_REVISION


class TestTheDeployPath:
    def test_bootstrap_reaches_head_with_the_new_shape(self, db_at_previous_head):
        rc = bootstrap.main(f"sqlite+aiosqlite:///{db_at_previous_head}")
        assert rc == 0
        assert _revision(db_at_previous_head) == bootstrap.script_head()
        columns = _columns(db_at_previous_head, "crafting_projects")
        assert "state_json" in columns
        assert columns["complexity"] == 0

    def test_the_invention_row_and_its_charge_survive_the_rebuild(self, db_at_previous_head):
        """SQLite relaxes NOT NULL by rebuilding the table — the copy must be whole."""
        bootstrap.main(f"sqlite+aiosqlite:///{db_at_previous_head}")
        con = sqlite3.connect(db_at_previous_head)
        project = con.execute(
            "select name, complexity, stage, attempts, elapsed_days, state_json"
            " from crafting_projects"
        ).fetchone()
        charge = con.execute("select kind, amount, outcome from crafting_charges").fetchone()
        con.close()
        assert project == ("mansion", "amazing", "prototype", 2, 40, None)
        assert charge == ("attempt", 250000, "failure")

    def test_the_indexes_survive_the_rebuild(self, db_at_previous_head):
        bootstrap.main(f"sqlite+aiosqlite:///{db_at_previous_head}")
        con = sqlite3.connect(db_at_previous_head)
        names = {r[1] for r in con.execute("pragma index_list(crafting_projects)")}
        con.close()
        assert {"ix_crafting_projects_guild_id", "ix_crafting_projects_discord_user_id"} <= names

    def test_running_it_twice_is_idempotent(self, db_at_previous_head):
        url = f"sqlite+aiosqlite:///{db_at_previous_head}"
        assert bootstrap.main(url) == 0
        assert bootstrap.main(url) == 0
        assert _revision(db_at_previous_head) == bootstrap.script_head()

    def test_the_migrated_columns_match_the_model(self, db_at_previous_head):
        from gurps_bot.db.crafting import CraftingCharge, CraftingProject

        bootstrap.main(f"sqlite+aiosqlite:///{db_at_previous_head}")
        con = sqlite3.connect(db_at_previous_head)
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

    def test_a_domain_project_with_no_complexity_inserts_afterwards(self, db_at_previous_head):
        bootstrap.main(f"sqlite+aiosqlite:///{db_at_previous_head}")
        con = sqlite3.connect(db_at_previous_head)
        con.execute(
            "insert into crafting_projects (discord_user_id, guild_id, name, domain,"
            " complexity, stage, skill, retail_price, flawed_theory, attempts,"
            " elapsed_days, major_bugs, minor_bugs, state_json)"
            " values (1, 2, 'a ladder', 'crafting', NULL, 'working', 14, 0, 0, 0,"
            " 0, 0, 0, '{\"inputs\": {}, \"progress\": {\"hours_worked\": 0}}')"
        )
        con.commit()
        rows = con.execute(
            "select domain, complexity from crafting_projects order by id"
        ).fetchall()
        con.close()
        assert rows == [("invention", "amazing"), ("crafting", None)]


class TestDowngrade:
    def test_downgrade_restores_the_previous_shape(self, db_at_previous_head):
        """With only invention rows present the rebuild back to NOT NULL succeeds."""
        url = f"sqlite+aiosqlite:///{db_at_previous_head}"
        bootstrap.main(url)
        _alembic(url, "downgrade", PREVIOUS_HEAD)
        assert _revision(db_at_previous_head) == PREVIOUS_HEAD
        columns = _columns(db_at_previous_head, "crafting_projects")
        assert "state_json" not in columns
        assert columns["complexity"] == 1

    def test_downgrade_refuses_to_invent_a_complexity(self, db_at_previous_head):
        """A domain project has no B473 rating; the downgrade must fail loudly
        rather than fabricate one."""
        url = f"sqlite+aiosqlite:///{db_at_previous_head}"
        bootstrap.main(url)
        con = sqlite3.connect(db_at_previous_head)
        con.execute(
            "insert into crafting_projects (discord_user_id, guild_id, name, domain,"
            " complexity, stage, skill, retail_price, flawed_theory, attempts,"
            " elapsed_days, major_bugs, minor_bugs)"
            " values (1, 2, 'the truck', 'repair', NULL, 'repairing', 12, 0, 0, 0, 0, 0, 0)"
        )
        con.commit()
        con.close()
        with pytest.raises(Exception):
            _alembic(url, "downgrade", PREVIOUS_HEAD)
