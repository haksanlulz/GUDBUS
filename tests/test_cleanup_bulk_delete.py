"""cleanup_stale_combats: the row-by-row sweep became bulk DML.

It runs hourly across every guild, so it is the only write whose lock duration
grows with guild count — and because SQLite serialises writers, a live command
lands behind the *whole* sweep rather than part of it. Measured on the previous
row-by-row version: ~1 ms per stale combat, the waiting command paying
essentially the full sweep (0.888 s against a 0.852 s sweep at 900 stale).

Bulk DML is faster and also more dangerous, which is what these pin. It fires
no ORM cascade, so combatants have to be deleted explicitly or they are
stranded — rows pointing at a combat that no longer exists. The old
implementation could not strand anything (the ORM cascade handled it), so no
existing test covers that, and it is exactly what a bulk rewrite breaks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import func, select, update

from gurps_bot.db.engine import (
    dispose_engine,
    get_session_factory,
    init_db,
    init_engine,
)
from gurps_bot.db.models import Combat, Combatant
from gurps_bot.services.combat import (
    add_npc_combatant,
    cleanup_stale_combats,
    get_combat,
    start_combat,
)

CHANNEL = 4_242
GM = 700_000


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "cleanup.db"
    init_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    await init_db()
    yield get_session_factory()
    await dispose_engine()


async def _combat(session_factory, guild_id: int, *, combatants: int = 3):
    async with session_factory() as s:
        c = await start_combat(s, guild_id, CHANNEL, GM)
        for i in range(combatants):
            await add_npc_combatant(
                s, c, name=f"M{i}", basic_speed=5.0, hp=10, fp=10, ht=10
            )
        await s.commit()


async def _age(session_factory, guild_ids: list[int], *, days: int = 3):
    async with session_factory() as s:
        await s.execute(
            update(Combat)
            .where(Combat.guild_id.in_(guild_ids))
            .values(updated_at=datetime.now(timezone.utc) - timedelta(days=days))
        )
        await s.commit()


async def _counts(session_factory) -> tuple[int, int]:
    async with session_factory() as s:
        combats = await s.scalar(select(func.count(Combat.id)))
        combatants = await s.scalar(select(func.count(Combatant.id)))
    return combats, combatants


class TestItDeletesTheRightThings:
    async def test_stale_combats_go(self, session_factory):
        await _combat(session_factory, 1)
        await _combat(session_factory, 2)
        await _age(session_factory, [1, 2])

        async with session_factory() as s:
            removed = await cleanup_stale_combats(s, max_age_hours=24)
            await s.commit()

        assert removed == 2
        assert await _counts(session_factory) == (0, 0)

    async def test_fresh_combats_stay(self, session_factory):
        await _combat(session_factory, 1)
        await _combat(session_factory, 2)
        await _age(session_factory, [1])

        async with session_factory() as s:
            removed = await cleanup_stale_combats(s, max_age_hours=24)
            await s.commit()

        assert removed == 1
        combats, combatants = await _counts(session_factory)
        assert combats == 1 and combatants == 3

        async with session_factory() as s:
            assert await get_combat(s, 2, CHANNEL) is not None
            assert await get_combat(s, 1, CHANNEL) is None

    async def test_it_returns_the_real_count(self, session_factory):
        """rowcount, not len() of a list the function no longer builds."""
        for g in range(1, 6):
            await _combat(session_factory, g, combatants=1)
        await _age(session_factory, [1, 2, 3])

        async with session_factory() as s:
            removed = await cleanup_stale_combats(s, max_age_hours=24)
            await s.commit()

        assert removed == 3

    async def test_nothing_stale_deletes_nothing(self, session_factory):
        await _combat(session_factory, 1)
        async with session_factory() as s:
            removed = await cleanup_stale_combats(s, max_age_hours=24)
            await s.commit()
        assert removed == 0
        assert await _counts(session_factory) == (1, 3)


class TestItStrandsNothingWithoutTheDatabasesHelp:
    """The case a fresh test database cannot express, and the only one that
    makes the explicit combatant delete load-bearing.

    On the current schema `Combatant.combat_id` carries ON DELETE CASCADE and
    the engine sets `PRAGMA foreign_keys=ON`, so deleting a combat takes its
    combatants whether or not this code asks. Every test below in
    `TestItStrandsNothing` therefore passes with the explicit delete **removed**
    — mutation testing said so, which is the only reason this class exists.

    A database created before that FK clause existed has no such cascade, and
    that is the deployment `purge_guild_combats` warns about. `foreign_keys=OFF`
    reproduces exactly that condition: the DB will not help, so the two-statement
    delete has to be right on its own.
    """

    async def test_no_strand_when_the_database_cascade_does_not_fire(
        self, session_factory
    ):
        from sqlalchemy import text

        for g in range(1, 6):
            await _combat(session_factory, g, combatants=4)
        await _age(session_factory, [1, 2, 3])

        async with session_factory() as s:
            # Same connection the delete runs on, so it governs that delete.
            await s.execute(text("PRAGMA foreign_keys=OFF"))
            removed = await cleanup_stale_combats(s, max_age_hours=24)
            await s.commit()

        assert removed == 3
        async with session_factory() as s:
            live_ids = set((await s.scalars(select(Combat.id))).all())
            orphans = (
                await s.scalars(
                    select(Combatant.id).where(Combatant.combat_id.notin_(live_ids))
                )
            ).all()
        assert not orphans, (
            f"{len(orphans)} combatants stranded once the database stopped "
            "cascading for us — the explicit delete is what has to prevent this"
        )


class TestItStrandsNothing:
    """The failure mode bulk DML introduces and the ORM version could not have."""

    async def test_no_combatant_outlives_its_combat(self, session_factory):
        for g in range(1, 8):
            await _combat(session_factory, g, combatants=4)
        await _age(session_factory, [1, 2, 3, 4, 5])

        async with session_factory() as s:
            await cleanup_stale_combats(s, max_age_hours=24)
            await s.commit()

        async with session_factory() as s:
            live_ids = set((await s.scalars(select(Combat.id))).all())
            orphans = (
                await s.scalars(
                    select(Combatant.id).where(Combatant.combat_id.notin_(live_ids))
                )
            ).all()

        assert not orphans, f"{len(orphans)} combatants outlived their combat"

    async def test_surviving_combats_keep_all_their_combatants(self, session_factory):
        """A subquery that matched too broadly would take these too."""
        await _combat(session_factory, 1, combatants=4)
        await _combat(session_factory, 2, combatants=4)
        await _age(session_factory, [1])

        async with session_factory() as s:
            await cleanup_stale_combats(s, max_age_hours=24)
            await s.commit()

        async with session_factory() as s:
            survivor = await get_combat(s, 2, CHANNEL)
            assert survivor is not None
            assert len(survivor.combatants) == 4
