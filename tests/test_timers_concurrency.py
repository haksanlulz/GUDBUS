"""Two /timer tick commands at once must both land.

tick_timers read the rows, subtracted in Python and flushed. Under SQLite's
deferred BEGIN the second command's SELECT runs before the first commits, so
it reads the old value, waits on the lock, and then writes its stale result:
two ticks, one decrement, and the expiry a round late. Measured on a file
database, because the interleaving needs a real lock between two connections.
"""

from __future__ import annotations

import asyncio

import pytest_asyncio
from sqlalchemy import select

from gurps_bot.db.engine import dispose_engine, get_session_factory, init_db, init_engine
from gurps_bot.db.timers import Timer
from gurps_bot.services.timers import add_timer, tick_timers

GUILD, CHANNEL = 1, 2


@pytest_asyncio.fixture
async def factory(tmp_path):
    init_engine(f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}")
    await init_db()
    yield get_session_factory()
    await dispose_engine()


async def _remaining(factory) -> int:
    async with factory() as s:
        return (await s.scalars(select(Timer.remaining))).one()


async def test_overlapping_ticks_both_count(factory):
    async with factory() as s:
        await add_timer(s, GUILD, CHANNEL, "Haste", 5, "turns")
        await s.commit()

    a = factory()
    b = factory()
    try:
        await tick_timers(a, GUILD, CHANNEL, "turns", 1)  # written, not committed

        async def second():
            await tick_timers(b, GUILD, CHANNEL, "turns", 1)
            await b.commit()

        task = asyncio.create_task(second())
        await asyncio.sleep(0.3)  # let B read and queue behind A's lock
        await a.commit()
        await task
    finally:
        await a.close()
        await b.close()

    assert await _remaining(factory) == 3


async def test_the_tick_that_reaches_zero_reports_the_expiry(factory):
    async with factory() as s:
        await add_timer(s, GUILD, CHANNEL, "Poison", 2, "turns")
        await s.commit()
    async with factory() as s:
        assert await tick_timers(s, GUILD, CHANNEL, "turns", 1) == []
        expired = await tick_timers(s, GUILD, CHANNEL, "turns", 5)
        await s.commit()
    assert [t.label for t in expired] == ["Poison"]
    assert expired[0].remaining == 0
