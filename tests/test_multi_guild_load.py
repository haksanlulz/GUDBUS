"""Concurrency across GUILDS, which the existing load test cannot reach.

`test_combat_multi_combat_load.py` pins `GUILD_ID` to one constant and varies
channels, so what it exercises is many combats at one table — the shape a
single server produces. Every guild-scoped code path is therefore covered only
at N=1, which is also what the hosted instance reports (`/status`: Guilds 1).

That matters for DONE clause (e), "an instance strangers can invite": the first
thing a public bot does that this one never has is serve writes from unrelated
guilds at the same time. These tests supply that dimension.

Two things are being checked, and they are different questions:

  * **isolation** — a write in one guild must never be visible as, or clobber,
    another guild's state. This should hold by construction, since every combat
    lookup is keyed on (guild_id, channel_id).
  * **contention** — SQLite serialises writers. The engine sets
    `busy_timeout=5000`, and Discord invalidates an un-deferred interaction
    token after **3 seconds**. The combat cog never calls `defer()`. So a write
    that waits on the lock longer than 3s produces a dead interaction while the
    query is still patiently succeeding. These tests measure the wait rather
    than assume it.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import update

from gurps_bot.db.models import Combat
from gurps_bot.db.engine import (
    dispose_engine,
    get_session_factory,
    init_db,
    init_engine,
)
from gurps_bot.services.combat import (
    add_npc_combatant,
    add_status,
    advance_turn,
    cleanup_stale_combats,
    get_combat,
    modify_hp,
    start_combat,
)

GM_BASE = 700_000
FIRST_GUILD = 990_000
CHANNEL = 12_345

# Discord invalidates an interaction token this long after receipt unless the
# app defers. Anything slower than this is a user-visible failure regardless of
# whether the database eventually succeeded.
INTERACTION_DEADLINE_S = 3.0


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    """File-backed, matching production and the sibling load test.

    In-memory sqlite forces one shared connection (StaticPool), which would
    make a contention test measure the fixture instead of the engine.
    """
    db_path = tmp_path / "multi_guild.db"
    init_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    await init_db()
    yield get_session_factory()
    await dispose_engine()


async def _seed_guild(session_factory, guild_id: int, hp: int = 20) -> None:
    async with session_factory() as s:
        combat = await start_combat(s, guild_id, CHANNEL, GM_BASE)
        await add_npc_combatant(
            s, combat, name="Mook", basic_speed=5.0, hp=hp, fp=hp, ht=10,
        )
        await s.commit()


class TestCrossGuildIsolation:
    """A guild must not be able to observe or damage another guild's combat."""

    async def test_same_channel_id_in_different_guilds_are_distinct_combats(
        self, session_factory
    ):
        """The dangerous coincidence: two servers using the same channel id.

        Channel ids are globally unique in practice, but the lookup is keyed on
        the pair, and a regression that dropped guild_id from the WHERE clause
        would still pass every single-guild test in the suite.
        """
        await _seed_guild(session_factory, FIRST_GUILD)
        await _seed_guild(session_factory, FIRST_GUILD + 1)

        async with session_factory() as s:
            a = await get_combat(s, FIRST_GUILD, CHANNEL)
            b = await get_combat(s, FIRST_GUILD + 1, CHANNEL)

        assert a is not None and b is not None
        assert a.id != b.id, "one combat served two guilds"
        assert a.guild_id != b.guild_id

    async def test_damage_in_one_guild_does_not_reach_another(self, session_factory):
        await _seed_guild(session_factory, FIRST_GUILD)
        await _seed_guild(session_factory, FIRST_GUILD + 1)

        async with session_factory() as s:
            victim = (await get_combat(s, FIRST_GUILD, CHANNEL)).combatants[0]
            await modify_hp(s, victim.id, -7)
            await s.commit()

        async with session_factory() as s:
            hurt = (await get_combat(s, FIRST_GUILD, CHANNEL)).combatants[0]
            bystander = (await get_combat(s, FIRST_GUILD + 1, CHANNEL)).combatants[0]

        assert hurt.hp_current == 13
        assert bystander.hp_current == 20, "damage crossed a guild boundary"

    async def test_concurrent_writes_in_many_guilds_all_land(self, session_factory):
        """Every guild's write must survive, not just the last one to commit."""
        guilds = [FIRST_GUILD + i for i in range(12)]
        for g in guilds:
            await _seed_guild(session_factory, g)

        async def hit(guild_id: int) -> None:
            async with session_factory() as s:
                c = await get_combat(s, guild_id, CHANNEL)
                await modify_hp(s, c.combatants[0].id, -3)
                await add_status(s, c.combatants[0].id, "Stunned")
                await s.commit()

        await asyncio.gather(*(hit(g) for g in guilds))

        async with session_factory() as s:
            for g in guilds:
                c = await get_combat(s, g, CHANNEL)
                assert c.combatants[0].hp_current == 17, f"guild {g} lost its write"
                assert "Stunned" in (c.combatants[0].status_effects or [])


class TestWriteContentionAgainstTheInteractionDeadline:
    """Does a contended write finish inside Discord's 3-second window?"""

    async def test_concurrent_guild_writes_stay_inside_the_deadline(
        self, session_factory
    ):
        guilds = [FIRST_GUILD + i for i in range(24)]
        for g in guilds:
            await _seed_guild(session_factory, g)

        slowest = 0.0

        async def timed(guild_id: int) -> float:
            start = time.perf_counter()
            async with session_factory() as s:
                c = await get_combat(s, guild_id, CHANNEL)
                # Mirrors /combat hp: write, then mechanics, then write, then
                # commit — so the write lock spans the non-DB work too.
                # advance_turn is sync and mutates the loaded combat.
                await modify_hp(s, c.combatants[0].id, -2)
                advance_turn(c)
                await s.commit()
            return time.perf_counter() - start

        elapsed = await asyncio.gather(*(timed(g) for g in guilds))
        slowest = max(elapsed)

        assert slowest < INTERACTION_DEADLINE_S, (
            f"slowest concurrent write took {slowest:.2f}s across "
            f"{len(guilds)} guilds; Discord invalidates an un-deferred "
            f"interaction at {INTERACTION_DEADLINE_S}s and the combat cog "
            "never defers"
        )

    async def test_hourly_cleanup_does_not_stall_a_live_guilds_write(
        self, session_factory
    ):
        """The cleanup task is the one write whose cost grows with guild count.

        `cleanup_stale_combats` selects every stale combat across every guild
        and deletes them row by row in one transaction. A live guild's command
        landing during that transaction waits on the same write lock.
        """
        stale = [FIRST_GUILD + 100 + i for i in range(40)]
        for g in stale:
            await _seed_guild(session_factory, g)
        live = FIRST_GUILD + 999
        await _seed_guild(session_factory, live)

        # Backdate only the stale ones. A zero max_age would sweep the live
        # guild too and the test would be measuring its own setup.
        async with session_factory() as s:
            await s.execute(
                update(Combat)
                .where(Combat.guild_id.in_(stale))
                .values(updated_at=datetime.now(timezone.utc) - timedelta(days=3))
            )
            await s.commit()

        async def sweep() -> None:
            async with session_factory() as s:
                await cleanup_stale_combats(s, max_age_hours=24)
                await s.commit()

        async def live_command() -> float:
            start = time.perf_counter()
            async with session_factory() as s:
                c = await get_combat(s, live, CHANNEL)
                if c is not None:
                    await modify_hp(s, c.combatants[0].id, -1)
                    await s.commit()
            return time.perf_counter() - start

        _, took = await asyncio.gather(sweep(), live_command())

        assert took < INTERACTION_DEADLINE_S, (
            f"a live guild's write waited {took:.2f}s behind the hourly "
            "cleanup sweep"
        )
