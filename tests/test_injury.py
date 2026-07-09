"""Shock (B419) and major wound (B420); HP-state labels live in combat_constants, not here."""

from __future__ import annotations

import pytest

from gurps_bot.mechanics.injury import (
    SHOCK_CAP,
    KnockdownOutcome,
    injury_effects,
    is_major_wound,
    knockdown_label,
    knockdown_modifier,
    knockdown_statuses,
    resolve_knockdown,
    shock_penalty,
)


class TestShockPenalty:
    @pytest.mark.parametrize(
        "injury,expected",
        [(0, 0), (1, -1), (2, -2), (3, -3), (4, -4), (5, -4), (8, -4), (100, -4)],
    )
    def test_minus_one_per_hp_capped(self, injury, expected):
        assert shock_penalty(injury) == expected

    @pytest.mark.parametrize("healed", [-1, -5, -100])
    def test_heal_or_no_damage_is_zero(self, healed):
        assert shock_penalty(healed) == 0

    def test_cap_constant_is_four(self):
        assert SHOCK_CAP == 4


class TestIsMajorWound:
    def test_exactly_half_is_not_major(self):
        # "more than half" is strict — 5 of 10 HP is exactly half, not a major wound.
        assert is_major_wound(5, 10) is False

    def test_over_half_is_major(self):
        assert is_major_wound(6, 10) is True

    @pytest.mark.parametrize(
        "injury,hp_max,expected",
        [
            (5, 9, True),    # 10 > 9
            (5, 11, False),  # 10 < 11
            (6, 11, True),   # 12 > 11
            (1, 1, True),    # 2 > 1
            (0, 10, False),  # no injury
            (-5, 10, False),  # heal
            (10, 0, False),  # guard: non-positive hp_max
            (5, -1, False),  # guard: negative hp_max
        ],
    )
    def test_threshold_cases(self, injury, hp_max, expected):
        assert is_major_wound(injury, hp_max) is expected


class TestInjuryEffects:
    def test_no_damage_is_empty(self):
        assert injury_effects(0, 10) == []

    def test_heal_is_empty(self):
        assert injury_effects(-4, 10) == []

    def test_minor_wound_is_shock_only(self):
        # 3 of 10 HP: shock but not a major wound.
        notes = injury_effects(3, 10)
        assert len(notes) == 1
        joined = " ".join(notes)
        assert "Shock" in joined and "B419" in joined
        assert "Major" not in joined

    def test_exactly_half_is_shock_only(self):
        # 5 of 10 is exactly half — shock (capped -4) but NOT a major wound.
        notes = injury_effects(5, 10)
        joined = " ".join(notes)
        assert "Shock" in joined
        assert "-4" in joined
        assert "Major" not in joined

    def test_major_wound_has_both_lines(self):
        notes = injury_effects(6, 10)
        assert len(notes) == 2
        # Major-wound line first (it gates a roll), then the shock reminder.
        assert "Major wound" in notes[0] and "B420" in notes[0]
        assert "Shock" in notes[1] and "B419" in notes[1]

    def test_major_wound_shock_still_capped(self):
        notes = injury_effects(8, 10)
        joined = " ".join(notes)
        assert "Major wound" in joined
        assert "-4" in joined  # shock capped even on a big blow


class TestResolveKnockdown:
    def test_success_is_none(self):
        assert (
            resolve_knockdown(succeeded=True, margin=3, critical_failure=False)
            is KnockdownOutcome.NONE
        )

    def test_success_by_zero_is_none(self):
        assert (
            resolve_knockdown(succeeded=True, margin=0, critical_failure=False)
            is KnockdownOutcome.NONE
        )

    @pytest.mark.parametrize("margin", [-1, -2, -4])
    def test_ordinary_failure_stuns_and_knocks_down(self, margin):
        assert (
            resolve_knockdown(succeeded=False, margin=margin, critical_failure=False)
            is KnockdownOutcome.STUNNED_PRONE
        )

    @pytest.mark.parametrize("margin", [-5, -8, -12])
    def test_failure_by_five_plus_knocks_out(self, margin):
        assert (
            resolve_knockdown(succeeded=False, margin=margin, critical_failure=False)
            is KnockdownOutcome.KNOCKED_OUT
        )

    def test_critical_failure_knocks_out_even_by_one(self):
        assert (
            resolve_knockdown(succeeded=False, margin=-1, critical_failure=True)
            is KnockdownOutcome.KNOCKED_OUT
        )


class TestKnockdownStatuses:
    def test_none_applies_nothing(self):
        assert knockdown_statuses(KnockdownOutcome.NONE) == ()

    def test_stun_applies_stunned_and_prone(self):
        assert knockdown_statuses(KnockdownOutcome.STUNNED_PRONE) == ("Stunned", "Prone")

    def test_knockout_applies_unconscious(self):
        assert knockdown_statuses(KnockdownOutcome.KNOCKED_OUT) == ("Unconscious",)

    def test_labels_distinct_and_nonempty(self):
        labels = {o: knockdown_label(o) for o in KnockdownOutcome}
        assert all(labels.values())
        assert len(set(labels.values())) == 3


class TestKnockdownModifier:
    def test_none_and_empty_are_zero(self):
        assert knockdown_modifier(None) == 0
        assert knockdown_modifier("") == 0

    @pytest.mark.parametrize(
        "location,expected",
        [
            ("face", -5),
            ("FACE", -5),
            (" face ", -5),
            ("vitals", -5),
            ("groin", -5),
            ("skull", -10),
            ("eye", -10),
            ("eyes", -10),
            ("torso", 0),
            ("arm", 0),
            ("leg", 0),
        ],
    )
    def test_b420_location_penalties(self, location, expected):
        assert knockdown_modifier(location) == expected
