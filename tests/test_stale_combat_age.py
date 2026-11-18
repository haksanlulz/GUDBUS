"""STALE_COMBAT_HOURS: how long an untouched combat survives the hourly sweep.

The sweep was a hard-coded 24 hours. A play-by-post table often goes more than a
day between moves, so its fight was deleted between turns and the GM rebuilt it
every time something happened. The age is now an env setting, and 0 turns the
sweep off.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select, update

from gurps_bot import config
from gurps_bot.cogs.combat import CombatTrackerGroup
from gurps_bot.config import _parse_hours
from gurps_bot.db.engine import (
    dispose_engine,
    get_session_factory,
    init_db,
    init_engine,
)
from gurps_bot.db.models import Combat
from gurps_bot.services.combat import cleanup_stale_combats, start_combat

GM = 700_000


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    init_engine(f"sqlite+aiosqlite:///{(tmp_path / 'age.db').as_posix()}")
    await init_db()
    yield get_session_factory()
    await dispose_engine()


async def _aged_combat(session_factory, *, hours: int) -> None:
    async with session_factory() as s:
        await start_combat(s, 1, 4_242, GM)
        await s.commit()
        await s.execute(
            update(Combat)
            .values(updated_at=datetime.now(timezone.utc) - timedelta(hours=hours))
        )
        await s.commit()


async def _combats(session_factory) -> int:
    async with session_factory() as s:
        return await s.scalar(select(func.count(Combat.id)))


class _Bot:
    def __init__(self, session_factory) -> None:
        self.db = session_factory


async def _sweep(session_factory) -> None:
    cog = CombatTrackerGroup(_Bot(session_factory))
    await CombatTrackerGroup._cleanup_task.coro(cog)


class TestParseHours:
    def test_unset_or_blank_keeps_the_default(self):
        assert _parse_hours(None, 24) == 24
        assert _parse_hours("", 24) == 24
        assert _parse_hours("  ", 24) == 24

    def test_a_number_is_read(self):
        assert _parse_hours("336", 24) == 336
        assert _parse_hours(" 72 ", 24) == 72

    def test_zero_is_allowed(self):
        assert _parse_hours("0", 24) == 0

    @pytest.mark.parametrize("raw", ["-1", "abc", "1.5", "two weeks", "²"])
    def test_garbage_fails_loudly(self, raw):
        with pytest.raises(ValueError, match="STALE_COMBAT_HOURS"):
            _parse_hours(raw, 24)


class TestTheSweepReadsTheSetting:
    async def test_default_is_still_a_day(self):
        assert config.STALE_COMBAT_HOURS == 24

    async def test_a_longer_age_keeps_a_two_day_old_fight(self, session_factory, monkeypatch):
        monkeypatch.setattr(config, "STALE_COMBAT_HOURS", 72)
        await _aged_combat(session_factory, hours=48)
        await _sweep(session_factory)
        assert await _combats(session_factory) == 1

    async def test_the_default_still_sweeps_it(self, session_factory, monkeypatch):
        monkeypatch.setattr(config, "STALE_COMBAT_HOURS", 24)
        await _aged_combat(session_factory, hours=48)
        await _sweep(session_factory)
        assert await _combats(session_factory) == 0

    async def test_zero_turns_the_sweep_off(self, session_factory, monkeypatch):
        monkeypatch.setattr(config, "STALE_COMBAT_HOURS", 0)
        await _aged_combat(session_factory, hours=24 * 30)
        await _sweep(session_factory)
        assert await _combats(session_factory) == 1


class TestTheServiceRefusesToSweepEverything:
    async def test_zero_hours_deletes_nothing(self, session_factory):
        # a zero cutoff is "now", which every combat is older than
        await _aged_combat(session_factory, hours=1)
        async with session_factory() as s:
            removed = await cleanup_stale_combats(s, max_age_hours=0)
            await s.commit()
        assert removed == 0
        assert await _combats(session_factory) == 1
