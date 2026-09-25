"""Migration a3d9e5f71c08 on a database that already holds duplicate default wallets.

The partial unique index cannot be built over duplicates, and the duplicates
hold real money a first-touch race wrote. So the migration folds them — one
row per user, balances summed, lowest id kept — before creating the index.
"""

from __future__ import annotations

import sqlite3

from gurps_bot.db import bootstrap
from tests.test_bootstrap_new_table import _build_pre_migration_db

PREVIOUS_HEAD = "e2a7c4d18b93"


def _db_with_duplicates(tmp_path):
    db = tmp_path / "gurps_bot.db"
    _build_pre_migration_db(
        db,
        drop_tables=[],
        # state_json arrived with b6c2d9e4f1a7, later than this stamp
        drop_columns={"crafting_projects": "state_json"},
        drop_indexes=["uq_wealth_default"],
    )
    con = sqlite3.connect(db)
    con.execute("create table alembic_version (version_num varchar(32) not null primary key)")
    con.execute(f"insert into alembic_version values ('{PREVIOUS_HEAD}')")
    rows = [
        (1, 42, None, 100.0, 2),
        (2, 42, None, 250.0, 0),
        (3, 42, None, 5.0, 0),
        (4, 43, None, 7.0, 1),
    ]
    con.executemany(
        "insert into wealth (id, discord_user_id, character_id, balance, status, updated_at)"
        " values (?,?,?,?,?, '2026-09-01 00:00:00')",
        rows,
    )
    con.commit()
    con.close()
    return db


def test_duplicates_fold_into_one_wallet_and_the_index_lands(tmp_path):
    db = _db_with_duplicates(tmp_path)
    # the real deploy path, as test_crafting_migration drives it
    assert bootstrap.main(f"sqlite+aiosqlite:///{db}") == 0

    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "select id, discord_user_id, balance, status from wealth order by id"
        ).fetchall()
        assert rows == [(1, 42, 355.0, 2), (4, 43, 7.0, 1)]
        index_sql = con.execute(
            "select sql from sqlite_master where name='uq_wealth_default'"
        ).fetchone()
        assert index_sql and "character_id IS NULL" in index_sql[0]
        assert con.execute("select version_num from alembic_version").fetchone()[0] == bootstrap.script_head()
    finally:
        con.close()
