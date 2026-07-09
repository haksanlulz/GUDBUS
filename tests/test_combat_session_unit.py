"""Tests for CombatSession permission and lookup logic."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gurps_bot.services.combat_session import (
    CombatPermissionError,
    CombatSession,
    CombatTargetNotFound,
)


def _make_combatant(*, name: str, discord_user_id: int | None = None, slot: int = 0,
                     basic_speed: float = 5.0, dx: int = 10, tiebreaker: int = 0) -> MagicMock:
    c = MagicMock()
    c.name = name
    c.discord_user_id = discord_user_id
    c.slot = slot
    c.basic_speed = basic_speed
    c.dx = dx
    c.tiebreaker = tiebreaker
    c.status_effects = []
    c.maneuver = None
    c.parries_this_turn = 0
    c.blocks_this_turn = 0
    return c


def _make_combat(*, started_by: int = 100, combatants: list | None = None,
                  current_index: int = 0) -> MagicMock:
    combat = MagicMock()
    combat.started_by = started_by
    combat.combatants = combatants or []
    combat.current_index = current_index
    combat.round_number = 1
    return combat


class TestIsGM:
    def test_true_for_starter(self):
        combat = _make_combat(started_by=42)
        cs = CombatSession(combat, user_id=42)
        assert cs.is_gm is True

    def test_false_for_other(self):
        combat = _make_combat(started_by=42)
        cs = CombatSession(combat, user_id=99)
        assert cs.is_gm is False


class TestRequireGM:
    def test_passes_for_gm(self):
        combat = _make_combat(started_by=42)
        cs = CombatSession(combat, user_id=42)
        cs.require_gm()  # should not raise

    def test_raises_for_non_gm(self):
        combat = _make_combat(started_by=42)
        cs = CombatSession(combat, user_id=99)
        with pytest.raises(CombatPermissionError):
            cs.require_gm()


class TestRequireTurnOrGM:
    def test_allows_gm(self):
        c1 = _make_combatant(name="Alice", discord_user_id=10)
        combat = _make_combat(started_by=42, combatants=[c1], current_index=0)
        cs = CombatSession(combat, user_id=42)
        cs.require_turn_or_gm()  # should not raise

    def test_allows_current_turn_player(self):
        c1 = _make_combatant(name="Alice", discord_user_id=10, basic_speed=6.0)
        combat = _make_combat(started_by=42, combatants=[c1], current_index=0)
        cs = CombatSession(combat, user_id=10)
        cs.require_turn_or_gm()  # should not raise

    def test_raises_for_other_player(self):
        c1 = _make_combatant(name="Alice", discord_user_id=10)
        combat = _make_combat(started_by=42, combatants=[c1], current_index=0)
        cs = CombatSession(combat, user_id=99)
        with pytest.raises(CombatPermissionError):
            cs.require_turn_or_gm()


class TestFindOwnCombatant:
    def test_found(self):
        c1 = _make_combatant(name="Alice", discord_user_id=10)
        c2 = _make_combatant(name="Bob", discord_user_id=20)
        combat = _make_combat(combatants=[c1, c2])
        cs = CombatSession(combat, user_id=10)
        assert cs.find_own_combatant() is c1

    def test_none_when_not_in_combat(self):
        c1 = _make_combatant(name="Alice", discord_user_id=10)
        combat = _make_combat(combatants=[c1])
        cs = CombatSession(combat, user_id=99)
        assert cs.find_own_combatant() is None


class TestFindCombatant:
    def test_exact_match(self):
        c1 = _make_combatant(name="Goblin Warrior")
        combat = _make_combat(combatants=[c1])
        cs = CombatSession(combat, user_id=42)
        assert cs.find_combatant("Goblin Warrior") is c1

    def test_fuzzy_match(self):
        c1 = _make_combatant(name="Goblin Warrior")
        combat = _make_combat(combatants=[c1])
        cs = CombatSession(combat, user_id=42)
        assert cs.find_combatant("goblin") is c1

    def test_no_match_raises(self):
        c1 = _make_combatant(name="Goblin Warrior")
        combat = _make_combat(combatants=[c1])
        cs = CombatSession(combat, user_id=42)
        with pytest.raises(CombatTargetNotFound):
            cs.find_combatant("xyzzy_nonexistent")


class TestRespondAndRefresh:
    """ack the interaction before the HTTP tracker edit; warn if the edit failed."""

    async def test_acks_before_refresh_then_warns_on_failure(self):
        from unittest.mock import AsyncMock, MagicMock

        from gurps_bot.services.combat_session import CombatContext

        order: list[str] = []
        interaction = MagicMock()
        interaction.response.send_message = AsyncMock(
            side_effect=lambda *a, **k: order.append("ack")
        )
        interaction.followup.send = AsyncMock(
            side_effect=lambda *a, **k: order.append("warn")
        )

        ctx = CombatContext(interaction)
        ctx.refresh_tracker = AsyncMock(side_effect=lambda: order.append("refresh") or False)

        await ctx.respond_and_refresh("done")

        # ack first, tracker edit second, warning last
        assert order == ["ack", "refresh", "warn"]
        interaction.followup.send.assert_awaited_once()

    async def test_no_warning_when_refresh_succeeds(self):
        from unittest.mock import AsyncMock, MagicMock

        from gurps_bot.services.combat_session import CombatContext

        interaction = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup.send = AsyncMock()

        ctx = CombatContext(interaction)
        ctx.refresh_tracker = AsyncMock(return_value=True)

        await ctx.respond_and_refresh("done")

        interaction.response.send_message.assert_awaited_once()
        interaction.followup.send.assert_not_awaited()

    async def test_refresh_tracker_returns_false_when_combat_ended(self):
        # a concurrent /combat end can delete the combat between commit and refresh;
        # refresh_tracker must return False on the None, not AttributeError
        from unittest.mock import AsyncMock, MagicMock, patch

        from gurps_bot.services.combat_session import CombatContext

        interaction = MagicMock()
        ctx = CombatContext(interaction)
        ctx.session = MagicMock()

        with patch(
            "gurps_bot.services.combat_session.get_combat",
            new=AsyncMock(return_value=None),
        ):
            result = await ctx.refresh_tracker()

        assert result is False
