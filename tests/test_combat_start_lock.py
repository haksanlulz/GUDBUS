"""/combat start must not hold SQLite's write lock across Discord calls.

start_combat flushes, which takes the database's single write lock, and the
command then sent its reply and fetched the reply message before committing.
Both are network round trips; while they ran, every write command in every
guild queued behind the lock, and past busy_timeout (5s) they failed with
"database is locked".
"""

from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio

from gurps_bot.db.engine import dispose_engine, get_session_factory, init_db, init_engine


@pytest_asyncio.fixture
async def db(tmp_path):
    path = tmp_path / "lock.db"
    init_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    await init_db()
    yield path, get_session_factory()
    await dispose_engine()


def _can_write_now(path) -> bool:
    """A separate connection that refuses to wait: can it write right now?"""
    conn = sqlite3.connect(path, timeout=0)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


async def test_the_reply_is_sent_with_no_write_lock_held(db, monkeypatch):
    from gurps_bot.cogs import combat as combat_cog

    path, factory = db
    observed = {}

    async def fake_respond(interaction, *a, **k):
        observed["during_reply"] = _can_write_now(path)

    async def fake_original_response():
        observed["during_fetch"] = _can_write_now(path)
        return MagicMock(id=555)

    monkeypatch.setattr(combat_cog, "respond", fake_respond)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.channel_id = 2
    interaction.user.id = 3
    interaction.client.db = factory
    interaction.original_response = AsyncMock(side_effect=fake_original_response)

    group = combat_cog.CombatTrackerGroup(bot=MagicMock())
    await group.start.callback(group, interaction)

    assert observed == {"during_reply": True, "during_fetch": True}

    from gurps_bot.services.combat import get_combat

    async with factory() as s:
        combat = await get_combat(s, 1, 2)
    assert combat is not None and combat.message_id == 555
