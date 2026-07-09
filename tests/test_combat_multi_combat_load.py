"""Cross-combat parallelism + cleanup-race shapes the single-combat tests don't cover."""
from __future__ import annotations

import asyncio
import random

import pytest
import pytest_asyncio

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
    end_combat,
    get_combat,
    modify_hp,
    record_defense,
    start_combat,
)


GM_BASE = 700_000
GUILD_ID = 999_500


@pytest_asyncio.fixture
async def session_factory():
    """Provide a session factory so concurrency tests spawn independent sessions."""
    init_engine("sqlite+aiosqlite://")
    await init_db()
    yield get_session_factory()
    await dispose_engine()


class TestMultiCombatLoad:
    async def test_parallel_combat_creation_distinct_channels(
        self, session_factory
    ):
        N = 10

        async def start_one(idx: int) -> int:
            channel_id = 10_000 + idx
            async with session_factory() as s:
                combat = await start_combat(
                    s, GUILD_ID, channel_id, GM_BASE + idx
                )
                await s.commit()
                return combat.id

        ids = await asyncio.gather(*[start_one(i) for i in range(N)])
        assert len(set(ids)) == N, f"duplicate combat IDs: {ids}"

    async def test_parallel_adds_across_combats(self, session_factory):
        N_COMBATS = 5
        N_NPCS_PER_COMBAT = 5

        # pre-create serially; creation isn't what's under test here
        async with session_factory() as s:
            combat_ids = []
            for i in range(N_COMBATS):
                c = await start_combat(s, GUILD_ID, 11_000 + i, GM_BASE + i)
                combat_ids.append((c.id, 11_000 + i))
            await s.commit()

        async def add_npc(combat_channel: int, idx: int) -> tuple[int, int]:
            async with session_factory() as s:
                c = await get_combat(s, GUILD_ID, combat_channel)
                npc = await add_npc_combatant(
                    s, c, f"NPC-{combat_channel}-{idx}", 5.0, 30, 10
                )
                await s.commit()
                return c.id, npc.slot

        tasks = [
            add_npc(channel, i)
            for _, channel in combat_ids
            for i in range(N_NPCS_PER_COMBAT)
        ]
        results = await asyncio.gather(*tasks)

        # each combat numbers slots independently — must come out 0..4, no cross-talk
        slots_by_combat: dict[int, list[int]] = {}
        for combat_id, slot in results:
            slots_by_combat.setdefault(combat_id, []).append(slot)

        for combat_id, slots in slots_by_combat.items():
            assert sorted(slots) == [0, 1, 2, 3, 4], (
                f"combat {combat_id} slot allocation broken: {sorted(slots)}"
            )

    async def test_mixed_command_storm(self, session_factory):
        N_COMBATS = 3
        N_NPCS = 3

        async with session_factory() as s:
            channels = [12_000 + i for i in range(N_COMBATS)]
            for i, ch in enumerate(channels):
                c = await start_combat(s, GUILD_ID, ch, GM_BASE + i)
                for n in range(N_NPCS):
                    await add_npc_combatant(
                        s, c, f"C{i}-NPC{n}", 5.0 + 0.1 * n, 100, 10
                    )
            await s.commit()

        async def fetch_random_target(channel: int) -> int | None:
            async with session_factory() as s:
                c = await get_combat(s, GUILD_ID, channel)
                if not c or not c.combatants:
                    return None
                return random.choice(c.combatants).id

        async def damage_op(channel: int) -> None:
            target_id = await fetch_random_target(channel)
            if target_id is None:
                return
            async with session_factory() as s:
                await modify_hp(s, target_id, -random.randint(5, 15))
                await s.commit()

        async def parry_op(channel: int) -> None:
            target_id = await fetch_random_target(channel)
            if target_id is None:
                return
            async with session_factory() as s:
                await record_defense(s, target_id, "parry")
                await s.commit()

        async def status_op(channel: int) -> None:
            target_id = await fetch_random_target(channel)
            if target_id is None:
                return
            async with session_factory() as s:
                await add_status(s, target_id, "Stunned")
                await s.commit()

        async def advance_op(channel: int) -> None:
            async with session_factory() as s:
                c = await get_combat(s, GUILD_ID, channel)
                if c is None:
                    return
                advance_turn(c)
                await s.commit()

        # 10 ops per combat, mixed
        ops = []
        for ch in channels:
            for _ in range(3):
                ops.append(damage_op(ch))
                ops.append(parry_op(ch))
                ops.append(status_op(ch))
            ops.append(advance_op(ch))

        random.seed(14)
        random.shuffle(ops)
        await asyncio.gather(*ops, return_exceptions=False)

        async with session_factory() as session:
            for ch in channels:
                c = await get_combat(session, GUILD_ID, ch)
                assert c is not None, f"combat in channel {ch} disappeared"
                assert len(c.combatants) == N_NPCS, (
                    f"combat {ch} lost combatants: {len(c.combatants)}"
                )

    async def test_cleanup_stale_does_not_clobber_active(
        self, session_factory
    ):
        async with session_factory() as session:
            combat = await start_combat(session, GUILD_ID, 13_000, GM_BASE)
            await add_npc_combatant(
                session, combat, "Survivor", 5.0, 100, 10
            )
            await session.commit()

        async def hammer_combat() -> None:
            async with session_factory() as s:
                c = await get_combat(s, GUILD_ID, 13_000)
                if c and c.combatants:
                    await modify_hp(s, c.combatants[0].id, -1)
                    await s.commit()

        async def cleanup_run() -> int:
            async with session_factory() as s:
                deleted = await cleanup_stale_combats(s, max_age_hours=24)
                await s.commit()
                return deleted

        tasks = [hammer_combat() for _ in range(5)] + [
            cleanup_run() for _ in range(2)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        # ints in the results are the cleanup returns; combat is fresh, so both 0
        cleanup_results = [r for r in results if isinstance(r, int)]
        assert all(r == 0 for r in cleanup_results), (
            f"cleanup_stale_combats deleted active combat: {cleanup_results}"
        )

        async with session_factory() as session:
            c = await get_combat(session, GUILD_ID, 13_000)
            assert c is not None, "active combat was clobbered by cleanup"
            assert len(c.combatants) == 1
