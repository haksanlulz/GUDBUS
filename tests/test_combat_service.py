from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from gurps_bot.gcs.parser import parse_gcs
from gurps_bot.mechanics.combat_constants import StatusEffect
from gurps_bot.services.characters import import_character
from gurps_bot.services.combat import (
    add_npc_combatant,
    add_pc_combatant,
    add_status,
    advance_turn,
    cleanup_stale_combats,
    current_combatant,
    end_combat,
    get_combat,
    modify_fp,
    modify_hp,
    previous_turn,
    record_defense,
    remove_combatant,
    remove_status,
    set_maneuver,
    start_combat,
    ordered_combatants,
)

USER_ID = 111111111
GM_ID = 222222222
GUILD_ID = 999999999
CHANNEL_ID = 888888888


class TestStartEndCombat:
    async def test_start_creates_combat(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await db_session.commit()
        assert combat.guild_id == GUILD_ID
        assert combat.channel_id == CHANNEL_ID
        assert combat.started_by == GM_ID
        assert combat.round_number == 1
        assert combat.current_index == 0

    async def test_start_duplicate_raises(self, db_session):
        await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await db_session.commit()
        with pytest.raises(ValueError, match="already active"):
            await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)

    async def test_get_combat_returns_none_when_empty(self, db_session):
        result = await get_combat(db_session, GUILD_ID, CHANNEL_ID)
        assert result is None

    async def test_get_combat_returns_with_combatants(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "Goblin", 5.25, 10, 10)
        await db_session.commit()

        loaded = await get_combat(db_session, GUILD_ID, CHANNEL_ID)
        assert loaded is not None
        assert len(loaded.combatants) == 1

    async def test_end_combat_deletes(self, db_session):
        await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await db_session.commit()

        deleted = await end_combat(db_session, GUILD_ID, CHANNEL_ID)
        await db_session.commit()
        assert deleted is True

        result = await get_combat(db_session, GUILD_ID, CHANNEL_ID)
        assert result is None

    async def test_end_nonexistent_returns_false(self, db_session):
        deleted = await end_combat(db_session, GUILD_ID, CHANNEL_ID)
        assert deleted is False


class TestAddCombatants:
    async def test_add_npc(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Orc", 5.5, 12, 10, dx=11, ht=11)
        await db_session.commit()

        assert npc.name == "Orc"
        assert npc.is_npc is True
        assert npc.basic_speed == 5.5
        assert npc.hp_max == 12
        assert npc.hp_current == 12
        assert npc.character_id is None
        assert npc.discord_user_id is None

    async def test_add_pc(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await db_session.commit()

        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        pc = await add_pc_combatant(db_session, combat, char.id, char.name, USER_ID)
        await db_session.commit()

        assert pc.name == "Sir Brannar"
        assert pc.is_npc is False
        assert pc.character_id == char.id
        assert pc.discord_user_id == USER_ID
        assert pc.basic_speed == 5.75
        assert pc.hp_max == 13

    async def test_add_duplicate_pc_raises(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await db_session.commit()

        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_pc_combatant(db_session, combat, char.id, char.name, USER_ID)
        await db_session.commit()

        with pytest.raises(ValueError, match="already in"):
            await add_pc_combatant(db_session, combat, char.id, char.name, USER_ID)

    async def test_ordering_by_speed(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "Slow", 4.0, 10, 10)
        await add_npc_combatant(db_session, combat, "Fast", 6.0, 10, 10)
        await add_npc_combatant(db_session, combat, "Mid", 5.0, 10, 10)
        await db_session.commit()

        ordered = ordered_combatants(combat)
        assert [c.name for c in ordered] == ["Fast", "Mid", "Slow"]


class TestRemoveCombatant:
    async def test_remove_existing(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Goblin", 5.0, 10, 10)
        await db_session.commit()

        removed = await remove_combatant(db_session, combat, npc.id)
        await db_session.commit()
        assert removed is True
        assert len(combat.combatants) == 0

    async def test_remove_nonexistent(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await db_session.commit()

        removed = await remove_combatant(db_session, combat, 99999)
        assert removed is False


class TestAdvanceTurn:
    async def test_basic_advance(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "A", 6.0, 10, 10)
        await add_npc_combatant(db_session, combat, "B", 5.0, 10, 10)
        await db_session.commit()

        assert combat.current_index == 0
        advance_turn(combat)
        assert combat.current_index == 1

    async def test_round_wraps(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "A", 6.0, 10, 10)
        await add_npc_combatant(db_session, combat, "B", 5.0, 10, 10)
        await db_session.commit()

        assert combat.round_number == 1
        advance_turn(combat)  # A -> B
        advance_turn(combat)  # B -> A (round 2)
        assert combat.current_index == 0
        assert combat.round_number == 2

    async def test_skips_dead(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "Alive1", 6.0, 10, 10)
        dead = await add_npc_combatant(db_session, combat, "Dead", 5.5, 10, 10)
        await add_npc_combatant(db_session, combat, "Alive2", 5.0, 10, 10)
        await db_session.commit()

        dead.status_effects = [StatusEffect.DEAD]
        advance_turn(combat)  # Alive1 -> skip Dead -> Alive2
        ordered = ordered_combatants(combat)
        assert ordered[combat.current_index].name == "Alive2"

    async def test_stunned_forces_do_nothing(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "Normal", 6.0, 10, 10)
        stunned = await add_npc_combatant(db_session, combat, "Stunned", 5.0, 10, 10)
        await db_session.commit()

        stunned.status_effects = [StatusEffect.STUNNED]
        msg = advance_turn(combat)  # Normal -> Stunned
        assert stunned.maneuver == "Do Nothing"
        assert "Stunned" in (msg or "")


class TestConsciousnessCheck:
    """Turn-start HT-to-stay-conscious auto-roll (B419): combatants at <=0 HP."""

    def _fake(self, succeeded, rolled=10):
        return SimpleNamespace(outcome=SimpleNamespace(succeeded=succeeded), rolled=rolled)

    async def test_healthy_combatant_rolls_no_check(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "A", 6.0, 10, 10)
        await add_npc_combatant(db_session, combat, "B", 5.0, 10, 10)
        await db_session.commit()

        with patch("gurps_bot.services.combat.check") as mock_check:
            advance_turn(combat)  # A -> B (healthy)
        mock_check.assert_not_called()
        assert ordered_combatants(combat)[combat.current_index].name == "B"

    async def test_downed_combatant_fails_and_falls_unconscious(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "A", 6.0, 10, 10)
        downed = await add_npc_combatant(db_session, combat, "B", 5.0, 10, 10)
        await add_npc_combatant(db_session, combat, "C", 4.0, 10, 10)
        await db_session.commit()
        downed.hp_current = 0

        with patch("gurps_bot.services.combat.check", return_value=self._fake(False)):
            msg = advance_turn(combat)  # A -> B(0hp) fails HT -> skip -> C

        assert StatusEffect.UNCONSCIOUS in (downed.status_effects or [])
        assert ordered_combatants(combat)[combat.current_index].name == "C"
        assert "unconscious" in (msg or "").lower()

    async def test_downed_combatant_succeeds_and_acts(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "A", 6.0, 10, 10)
        downed = await add_npc_combatant(db_session, combat, "B", 5.0, 10, 10)
        await db_session.commit()
        downed.hp_current = -2

        with patch("gurps_bot.services.combat.check", return_value=self._fake(True, rolled=8)):
            msg = advance_turn(combat)  # A -> B(-2hp) makes HT -> B acts

        assert StatusEffect.UNCONSCIOUS not in (downed.status_effects or [])
        assert ordered_combatants(combat)[combat.current_index].name == "B"
        assert "stays conscious" in (msg or "").lower()


class TestPreviousTurn:
    async def test_basic_undo(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "A", 6.0, 10, 10)
        await add_npc_combatant(db_session, combat, "B", 5.0, 10, 10)
        await db_session.commit()

        advance_turn(combat)  # 0 -> 1
        assert combat.current_index == 1
        previous_turn(combat)
        assert combat.current_index == 0

    async def test_undo_wraps_round(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "A", 6.0, 10, 10)
        await add_npc_combatant(db_session, combat, "B", 5.0, 10, 10)
        await db_session.commit()

        advance_turn(combat)  # round 1, idx 1
        advance_turn(combat)  # round 2, idx 0
        assert combat.round_number == 2
        previous_turn(combat)
        assert combat.current_index == 1
        assert combat.round_number == 1


class TestModifyHP:
    async def test_damage(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Target", 5.0, 10, 10)
        await db_session.commit()

        c, warning = await modify_hp(db_session, npc.id, -5)
        assert c.hp_current == 5
        assert warning == ""

    async def test_heal_capped(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Target", 5.0, 10, 10)
        await db_session.commit()

        await modify_hp(db_session, npc.id, -3)
        c, _ = await modify_hp(db_session, npc.id, 100)
        assert c.hp_current == 10  # capped at max

    async def test_zero_hp_warning(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Target", 5.0, 10, 10)
        await db_session.commit()

        _, warning = await modify_hp(db_session, npc.id, -10)
        assert "conscious" in warning.lower()

    async def test_negative_hp_survival_warning(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Target", 5.0, 10, 10)
        await db_session.commit()

        _, warning = await modify_hp(db_session, npc.id, -20)
        assert "survive" in warning.lower()

    async def test_auto_dead_at_minus_5x(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Target", 5.0, 10, 10)
        await db_session.commit()

        c, warning = await modify_hp(db_session, npc.id, -60)
        assert "dead" in warning.lower()
        assert StatusEffect.DEAD in c.status_effects


class TestModifyFP:
    async def test_fp_change(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Target", 5.0, 10, 10)
        await db_session.commit()

        c = await modify_fp(db_session, npc.id, -3)
        assert c.fp_current == 7


class TestStatus:
    async def test_add_status(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Target", 5.0, 10, 10)
        await db_session.commit()

        c = await add_status(db_session, npc.id, StatusEffect.STUNNED)
        assert StatusEffect.STUNNED in c.status_effects

    async def test_add_status_idempotent(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Target", 5.0, 10, 10)
        await db_session.commit()

        await add_status(db_session, npc.id, StatusEffect.PRONE)
        c = await add_status(db_session, npc.id, StatusEffect.PRONE)
        assert c.status_effects.count(StatusEffect.PRONE) == 1

    async def test_add_invalid_status_raises(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Target", 5.0, 10, 10)
        await db_session.commit()

        with pytest.raises(ValueError, match="Unknown status"):
            await add_status(db_session, npc.id, "OnFire")

    async def test_remove_status(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Target", 5.0, 10, 10)
        await db_session.commit()

        await add_status(db_session, npc.id, StatusEffect.STUNNED)
        c = await remove_status(db_session, npc.id, StatusEffect.STUNNED)
        assert StatusEffect.STUNNED not in c.status_effects


class TestManeuver:
    async def test_set_maneuver(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Fighter", 5.0, 10, 10)
        await db_session.commit()

        c = await set_maneuver(db_session, npc.id, "Attack")
        assert c.maneuver == "Attack"


class TestDefenseTracking:
    async def test_record_parry(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Defender", 5.0, 10, 10)
        await db_session.commit()

        c = await record_defense(db_session, npc.id, "parry")
        assert c.parries_this_turn == 1
        c = await record_defense(db_session, npc.id, "parry")
        assert c.parries_this_turn == 2

    async def test_record_block(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        npc = await add_npc_combatant(db_session, combat, "Defender", 5.0, 10, 10)
        await db_session.commit()

        c = await record_defense(db_session, npc.id, "block")
        assert c.blocks_this_turn == 1


class TestTurnIdentityAnchor:
    """the turn anchors to current_combatant_id — ordered_combatants re-sorts on
    every call, so a bare index re-points whose turn it is when the roster changes."""

    async def test_add_faster_combatant_midturn_keeps_current(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "A", 6.0, 10, 10)
        await add_npc_combatant(db_session, combat, "B", 5.0, 10, 10)
        await db_session.commit()

        advance_turn(combat)  # A -> B; it is now B's turn
        assert current_combatant(combat).name == "B"

        # GM adds reinforcements faster than everyone, mid-combat
        await add_npc_combatant(db_session, combat, "C", 9.0, 10, 10)
        await db_session.commit()

        # still B's turn — must not silently jump to C/A
        assert current_combatant(combat).name == "B"
        # ...and the cached index must point at B's new sorted position
        ordered = ordered_combatants(combat)
        assert ordered[combat.current_index].name == "B"

    async def test_add_slower_combatant_keeps_current(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "A", 6.0, 10, 10)
        await add_npc_combatant(db_session, combat, "B", 5.0, 10, 10)
        await db_session.commit()

        advance_turn(combat)  # B's turn
        await add_npc_combatant(db_session, combat, "Slow", 1.0, 10, 10)
        await db_session.commit()

        assert current_combatant(combat).name == "B"

    async def test_anchor_persists_across_reload(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "A", 6.0, 10, 10)
        await add_npc_combatant(db_session, combat, "B", 5.0, 10, 10)
        await db_session.commit()

        advance_turn(combat)
        await db_session.commit()

        loaded = await get_combat(db_session, GUILD_ID, CHANNEL_ID)
        assert loaded.current_combatant_id is not None
        assert current_combatant(loaded).name == "B"

    async def test_remove_current_advances_to_next(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "A", 7.0, 10, 10)
        b = await add_npc_combatant(db_session, combat, "B", 6.0, 10, 10)
        await add_npc_combatant(db_session, combat, "C", 5.0, 10, 10)
        await db_session.commit()

        advance_turn(combat)  # A -> B current
        assert current_combatant(combat).name == "B"

        await remove_combatant(db_session, combat, b.id)  # remove the current actor
        await db_session.commit()

        assert current_combatant(combat).name == "C"

    async def test_remove_noncurrent_keeps_current(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        a = await add_npc_combatant(db_session, combat, "A", 7.0, 10, 10)
        await add_npc_combatant(db_session, combat, "B", 6.0, 10, 10)
        await add_npc_combatant(db_session, combat, "C", 5.0, 10, 10)
        await db_session.commit()

        advance_turn(combat)  # A -> B current
        await remove_combatant(db_session, combat, a.id)  # remove an already-acted, non-current
        await db_session.commit()

        assert current_combatant(combat).name == "B"
        ordered = ordered_combatants(combat)
        assert ordered[combat.current_index].name == "B"

    async def test_current_combatant_falls_back_to_index_without_anchor(self, db_session):
        # before any turn is taken there is no anchor; the fastest (index 0) is current
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await add_npc_combatant(db_session, combat, "A", 6.0, 10, 10)
        await add_npc_combatant(db_session, combat, "B", 5.0, 10, 10)
        await db_session.commit()

        assert combat.current_combatant_id is None
        assert current_combatant(combat).name == "A"

    async def test_advance_when_all_down_does_not_inflate_round(self, db_session):
        # skip loop advances at most one full pass — with everyone Dead/Unconscious
        # it must not wrap twice (round +2) or emit duplicate "Round N begins"
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        a = await add_npc_combatant(db_session, combat, "A", 6.0, 10, 10)
        b = await add_npc_combatant(db_session, combat, "B", 5.0, 10, 10)
        await db_session.commit()

        advance_turn(combat)  # A -> B; anchor on the last combatant
        assert current_combatant(combat).name == "B"

        a.status_effects = [StatusEffect.DEAD]
        b.status_effects = [StatusEffect.DEAD]
        round_before = combat.round_number
        msg = advance_turn(combat)

        assert combat.round_number - round_before <= 1
        assert (msg or "").count("Round") <= 1
        assert "All combatants are down" in (msg or "")


class TestStaleCleanup:
    async def test_cleanup_old_combats(self, db_session):
        combat = await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await db_session.commit()

        # backdate past the 24h cutoff
        from datetime import timedelta
        combat.updated_at = combat.updated_at - timedelta(hours=25)
        await db_session.commit()

        count = await cleanup_stale_combats(db_session, max_age_hours=24)
        await db_session.commit()
        assert count == 1

        result = await get_combat(db_session, GUILD_ID, CHANNEL_ID)
        assert result is None

    async def test_cleanup_preserves_fresh(self, db_session):
        await start_combat(db_session, GUILD_ID, CHANNEL_ID, GM_ID)
        await db_session.commit()

        count = await cleanup_stale_combats(db_session, max_age_hours=24)
        assert count == 0
