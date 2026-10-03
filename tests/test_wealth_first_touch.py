"""Two first-touch wallet commands at once must end in ONE default wallet.

get_or_create_wealth SELECTs, then INSERTs. Under SQLite's deferred BEGIN two
overlapping first commands both see no wallet and both insert; uq_wealth_owner
cannot stop it because SQLite treats two NULL character_ids as distinct. The
second row's money was then invisible — get_wealth reads the oldest row only.
"""

from __future__ import annotations

import asyncio

import pytest_asyncio
from sqlalchemy import select

from gurps_bot.db.engine import dispose_engine, get_session_factory, init_db, init_engine
from gurps_bot.db.wealth import Wealth
from gurps_bot.services.wealth import adjust_balance, get_wealth

USER = 77


@pytest_asyncio.fixture
async def factory(tmp_path):
    init_engine(f"sqlite+aiosqlite:///{(tmp_path / 'w.db').as_posix()}")
    await init_db()
    yield get_session_factory()
    await dispose_engine()


async def test_overlapping_first_adjusts_share_one_wallet(factory):
    a = factory()
    b = factory()
    try:
        await adjust_balance(a, USER, 100.0)  # creates the wallet, not committed

        async def second():
            await adjust_balance(b, USER, 250.0)
            await b.commit()

        task = asyncio.create_task(second())
        await asyncio.sleep(0.3)  # B has looked, found nothing, and is queued
        await a.commit()
        await task
    finally:
        await a.close()
        await b.close()

    async with factory() as s:
        rows = (await s.scalars(select(Wealth).where(Wealth.discord_user_id == USER))).all()
        assert len(rows) == 1, [(r.id, r.balance) for r in rows]
        assert (await get_wealth(s, USER)).balance == 350.0
