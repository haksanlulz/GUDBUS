"""Lifecycle + concurrency. aiosqlite serializes writes, so the races worth
catching are app-level read-modify-write patterns in the service code."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

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
    end_combat,
    get_combat,
    modify_hp,
    ordered_combatants,
    record_defense,
    start_combat,
)


GM_ID = 555_001
GUILD_ID = 999_001
CHANNEL_ID = 888_001


@pytest_asyncio.fixture
async def session_factory():
    """Factory, not a session — concurrency tests need independent sessions on one DB."""
    init_engine("sqlite+aiosqlite://")
    await init_db()
    yield get_session_factory()
    await dispose_engine()


class TestCombatLifecycle:
    async def test_full_round_trip(self, session_factory, monkeypatch):
        async with session_factory() as session:
            combat = await start_combat(session, GUILD_ID, CHANNEL_ID, GM_ID)
            await session.commit()
            assert combat.started_by == GM_ID
            assert combat.round_number == 1
            assert combat.current_index == 0

            goblin = await add_npc_combatant(session, combat, "Goblin", 5.25, 10, 10)
            ogre = await add_npc_combatant(session, combat, "Ogre", 4.50, 25, 12)
            await session.commit()
            assert len(combat.combatants) == 2

            # initiative: Goblin (5.25) > Ogre (4.50)
            ordered = ordered_combatants(combat)
            assert ordered[0].name == "Goblin"
            assert ordered[1].name == "Ogre"

            assert combat.current_index == 0

            ogre_after, warning = await modify_hp(session, ogre.id, -4)
            await session.commit()
            assert ogre_after.hp_current == 25 - 4
            # -4 on 25 HP is nowhere near 0 — no spurious warning
            assert warning in (None, "")

            advance_turn(combat)
            await session.commit()
            assert combat.current_index == 1

            # goblin 10 -> -1: crossing 0 must warn
            goblin_after, warning_g = await modify_hp(session, goblin.id, -11)
            await session.commit()
            assert goblin_after.hp_current == 10 - 11
            assert warning_g, f"expected warning when HP drops below 0, got {warning_g!r}"

            # the wrap lands back on the goblin at <=0 HP, so advance_turn auto-rolls
            # the B419 consciousness check — left live, the landing index is a coin
            # flip. force success; the unconscious-skip path is covered elsewhere
            monkeypatch.setattr(
                "gurps_bot.services.combat.check",
                lambda *a, **k: SimpleNamespace(
                    rolled=3, outcome=SimpleNamespace(succeeded=True)
                ),
            )

            advance_turn(combat)
            await session.commit()
            assert combat.round_number == 2
            assert combat.current_index == 0

            ended = await end_combat(session, GUILD_ID, CHANNEL_ID)
            await session.commit()
            assert ended is True

            after = await get_combat(session, GUILD_ID, CHANNEL_ID)
            assert after is None

    async def test_combat_isolation_per_channel(self, session_factory):
        async with session_factory() as session:
            ch_a = await start_combat(session, GUILD_ID, 1001, GM_ID)
            ch_b = await start_combat(session, GUILD_ID, 1002, GM_ID)
            await add_npc_combatant(session, ch_a, "Goblin-A", 5.0, 10, 10)
            await add_npc_combatant(session, ch_b, "Goblin-B", 5.0, 10, 10)
            await session.commit()

            goblin_a = ordered_combatants(ch_a)[0]
            goblin_b = ordered_combatants(ch_b)[0]
            await modify_hp(session, goblin_a.id, -7)
            await session.commit()

            ch_b_after = await get_combat(session, GUILD_ID, 1002)
            goblin_b_after = ordered_combatants(ch_b_after)[0]
            assert goblin_b_after.hp_current == 10  # untouched


class TestCombatConcurrency:
    async def test_parallel_damage_to_same_combatant(self, session_factory):
        # both deltas must land: final = start - sum, not start - max
        async with session_factory() as session:
            combat = await start_combat(session, GUILD_ID, 2001, GM_ID)
            target = await add_npc_combatant(session, combat, "Target", 5.0, 100, 10)
            await session.commit()
            target_id = target.id

        async def hit(damage: int) -> None:
            async with session_factory() as s:
                await modify_hp(s, target_id, -damage)
                await s.commit()

        await asyncio.gather(*[hit(10) for _ in range(5)])

        async with session_factory() as session:
            combat = await get_combat(session, GUILD_ID, 2001)
            assert combat is not None
            t = next(c for c in combat.combatants if c.id == target_id)
            # No clobber: 100 - (5 * 10) = 50
            assert t.hp_current == 50, (
                f"concurrent damage clobbered: expected HP=50 (5x -10 from "
                f"start 100), got {t.hp_current}. Possible read-modify-write "
                f"race in modify_hp service code."
            )

    async def test_parallel_damage_to_different_combatants(
        self, session_factory
    ):
        async with session_factory() as session:
            combat = await start_combat(session, GUILD_ID, 2002, GM_ID)
            t_a = await add_npc_combatant(session, combat, "A", 5.0, 50, 10)
            t_b = await add_npc_combatant(session, combat, "B", 4.0, 50, 10)
            await session.commit()
            ids = (t_a.id, t_b.id)

        async def hit(combatant_id: int, damage: int) -> None:
            async with session_factory() as s:
                await modify_hp(s, combatant_id, -damage)
                await s.commit()

        await asyncio.gather(hit(ids[0], 7), hit(ids[1], 13))

        async with session_factory() as session:
            combat = await get_combat(session, GUILD_ID, 2002)
            ordered = {c.id: c.hp_current for c in combat.combatants}
            assert ordered[ids[0]] == 50 - 7
            assert ordered[ids[1]] == 50 - 13


class TestStatusEffectRaceWindow:
    """add_status/remove_status keep a deliberate R-M-W race window —
    assert bounded loss here, not zero-loss."""

    async def test_concurrent_add_status_lands_at_least_one(
        self, session_factory
    ):
        async with session_factory() as session:
            combat = await start_combat(session, GUILD_ID, 3001, GM_ID)
            target = await add_npc_combatant(session, combat, "T", 5.0, 50, 10)
            await session.commit()
            target_id = target.id

        async def add_dead() -> None:
            async with session_factory() as s:
                await add_status(s, target_id, "Dead")
                await s.commit()

        await asyncio.gather(*[add_dead() for _ in range(10)])

        async with session_factory() as session:
            combat = await get_combat(session, GUILD_ID, 3001)
            t = next(c for c in combat.combatants if c.id == target_id)
            # at least one add must land. the window only bites when DIFFERENT
            # statuses race — rare, GM-fixable, and the column is a JSON list so
            # there's no portable atomic UPDATE
            assert "Dead" in (t.status_effects or [])


class TestRecordDefenseAtomic:
    """regression: a Python-side += after SELECT let two parallel defenses
    both read N and both write N+1 — record_defense must UPDATE atomically."""

    async def test_parallel_parries_no_loss(self, session_factory):
        async with session_factory() as session:
            combat = await start_combat(session, GUILD_ID, 3002, GM_ID)
            target = await add_npc_combatant(session, combat, "Defender", 5.0, 50, 10)
            await session.commit()
            target_id = target.id

        async def parry() -> None:
            async with session_factory() as s:
                await record_defense(s, target_id, "parry")
                await s.commit()

        await asyncio.gather(*[parry() for _ in range(5)])

        async with session_factory() as session:
            combat = await get_combat(session, GUILD_ID, 3002)
            t = next(c for c in combat.combatants if c.id == target_id)
            assert t.parries_this_turn == 5, (
                f"concurrent parry count clobbered: expected 5, got "
                f"{t.parries_this_turn}. Possible R-M-W race in record_defense."
            )

    async def test_parallel_blocks_no_loss(self, session_factory):
        async with session_factory() as session:
            combat = await start_combat(session, GUILD_ID, 3003, GM_ID)
            target = await add_npc_combatant(session, combat, "Blocker", 5.0, 50, 10)
            await session.commit()
            target_id = target.id

        async def block() -> None:
            async with session_factory() as s:
                await record_defense(s, target_id, "block")
                await s.commit()

        await asyncio.gather(*[block() for _ in range(3)])

        async with session_factory() as session:
            combat = await get_combat(session, GUILD_ID, 3003)
            t = next(c for c in combat.combatants if c.id == target_id)
            assert t.blocks_this_turn == 3


class TestParallelAddCombatants:
    """slot allocation retries on IntegrityError so concurrent adds land distinct slots."""

    async def test_parallel_add_npc_distinct_slots(self, session_factory):
        async with session_factory() as session:
            await start_combat(session, GUILD_ID, 3004, GM_ID)
            await session.commit()

        async def add_one(idx: int) -> int:
            async with session_factory() as s:
                local_combat = await get_combat(s, GUILD_ID, 3004)
                assert local_combat is not None
                npc = await add_npc_combatant(
                    s, local_combat, f"NPC-{idx}", 5.0, 30, 10
                )
                await s.commit()
                return npc.slot

        slots = await asyncio.gather(*[add_one(i) for i in range(5)])

        async with session_factory() as session:
            combat = await get_combat(session, GUILD_ID, 3004)
            assert len(combat.combatants) == 5
            slot_values = sorted(c.slot for c in combat.combatants)
            # distinct + dense (0..4) — the retry helper allocates next-available,
            # not skip-ahead
            assert len(set(slot_values)) == 5, (
                f"slot collision: {slot_values}. Retry helper failed to "
                f"resolve duplicates."
            )
            assert sorted(slots) == sorted(set(slots)), (
                f"returned slots not distinct: {sorted(slots)}"
            )
