"""Book pins for the two modules the S4 ledger had no row for (2026-07-27).

`defense.py` (B374-376 active defenses) and `combat_constants.py` (B419 HP
thresholds) are rules-bearing but appeared in no ledger row, so they had never
been checked against the printed Basic Set.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics.combat_constants import hp_status_label
from gurps_bot.mechanics.defense import cumulative_parry_penalty, defense_penalty


class TestParryPenaltyHasTheReducedVariant:
    """B376 Number of Parries, verbatim:

        "Once you have attempted a parry with a particular weapon or bare hand,
         further attempts to parry with that weapon or hand are at a cumulative
         -4 per parry after the first. Reduce this to -2 per parry if you are
         using a fencing weapon or have the Trained By A Master or Weapon Master
         advantage."

    The -4 was right; the -2 case had no way to be expressed at all.
    """

    def test_first_parry_is_unpenalized(self):
        assert cumulative_parry_penalty(0) == 0
        assert cumulative_parry_penalty(0, reduced=True) == 0

    @pytest.mark.parametrize("prior,expected", [(1, -4), (2, -8), (3, -12)])
    def test_default_step_is_minus_four(self, prior, expected):
        assert cumulative_parry_penalty(prior) == expected

    @pytest.mark.parametrize("prior,expected", [(1, -2), (2, -4), (3, -6)])
    def test_fencing_or_master_step_is_minus_two(self, prior, expected):
        assert cumulative_parry_penalty(prior, reduced=True) == expected

    def test_defense_penalty_threads_the_reduced_flag(self):
        penalty, note = defense_penalty("parry", 2, 0, reduced_parry=True)
        assert penalty == -4
        assert note is not None and "-4" in note

    def test_defense_penalty_default_is_unreduced(self):
        penalty, _ = defense_penalty("parry", 2, 0)
        assert penalty == -8


class TestReelingThresholdIsStrictlyLessThanOneThird:
    """B419 chart, verbatim: "Less than 1/3 your HP left - You are reeling from
    your wounds. Halve your Move and Dodge (round up)."

    Strictly less than. `<= hp_max // 3` fires one HP early whenever HP is
    divisible by 3, and Reeling halves Move and Dodge, so the error is live.
    """

    def test_exactly_one_third_is_not_reeling(self):
        # HP 12, 4 left: 4 is exactly 1/3, so not "less than 1/3".
        assert hp_status_label(4, 12) == ""

    def test_one_below_a_third_is_reeling(self):
        assert hp_status_label(3, 12) == "Reeling"

    @pytest.mark.parametrize("hp_max", [3, 6, 9, 12, 15, 18, 21, 24, 30])
    def test_divisible_by_three_boundary(self, hp_max):
        third = hp_max // 3
        assert hp_status_label(third, hp_max) == "", (
            f"HP {hp_max} at {third}: exactly 1/3 is not reeling"
        )
        # At HP 3 the next step down is 0 HP, which is Collapsing — the ladder
        # above Reeling wins there, so only assert Reeling where it applies.
        if third - 1 > 0:
            assert hp_status_label(third - 1, hp_max) == "Reeling"
        else:
            assert hp_status_label(third - 1, hp_max) == "Collapsing"

    @pytest.mark.parametrize("hp_max,cur", [(10, 3), (11, 3), (13, 4), (14, 4)])
    def test_non_divisible_cases_unchanged(self, hp_max, cur):
        """Don't regress the values that were already right."""
        assert hp_status_label(cur, hp_max) == "Reeling"

    def test_healthy_is_unlabelled(self):
        assert hp_status_label(12, 12) == ""
        assert hp_status_label(5, 12) == ""


class TestNegativeHpThresholdsUnchanged:
    """These were already correct — pin them so the Reeling fix can't disturb
    the ladder below it. B419: "0 HP or less" / fully negative HP risks death /
    "If you reach -5xHP, you die automatically."
    """

    def test_zero_or_less_is_collapsing(self):
        assert hp_status_label(0, 10) == "Collapsing"
        assert hp_status_label(-9, 10) == "Collapsing"

    def test_fully_negative_is_dying(self):
        assert hp_status_label(-10, 10) == "Dying"
        assert hp_status_label(-49, 10) == "Dying"

    def test_five_times_negative_is_dead(self):
        assert hp_status_label(-50, 10) == "Dead"
        assert hp_status_label(-60, 10) == "Dead"

    def test_zero_hp_max_is_unlabelled(self):
        assert hp_status_label(0, 0) == ""
