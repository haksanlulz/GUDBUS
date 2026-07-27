"""Injury Tolerance wounding (B380 sidebar), operator-ruled into scope 2026-07-27.

Printed multipliers, verbatim:

  Unliving: "impaling and huge piercing a wounding modifier of x1; large
    piercing, x1/2; piercing, x1/3; and small piercing, x1/5."
  Homogenous: "Impaling and huge piercing have a wounding modifier of x1/2;
    large piercing, x1/3; piercing, x1/5; and small piercing, x1/10."
  Diffuse: "Impaling and piercing attacks (of any size) never do more than 1 HP
    of injury, regardless of penetrating damage! Other attacks can never do more
    than 2 HP of injury."
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics.damage import wound_from_penetrating
from gurps_bot.mechanics.traits import InjuryTolerance


def _wound(penetrating, dtype, dr=0, location=None, it=None):
    """Injury for a known penetrating total — no dice, so every case is exact."""
    raw = max(0, int(penetrating) - dr)
    return wound_from_penetrating(
        raw, dtype, location=location, injury_tolerance=it
    )[1]


class TestBookWorkedExample:
    """B380's own example: a zombie with Injury Tolerance (Unliving) and DR 1 is
    shot three times for 8, 7 and 10 points of *penetrating* damage. "The usual
    x1 wounding modifier for piercing damage drops to x1/3. Rounding down, the
    three bullets inflict 2 HP, 2 HP, and 3 HP of injury."
    """

    @pytest.mark.parametrize("penetrating,expected", [(8, 2), (7, 2), (10, 3)])
    def test_zombie_bullets(self, penetrating, expected):
        # express penetrating damage directly: DR 0, flat damage value
        assert _wound(str(penetrating), "pi", it=InjuryTolerance.UNLIVING) == expected


class TestUnliving:
    @pytest.mark.parametrize(
        "dtype,expected",
        [("imp", 10), ("pi++", 10), ("pi+", 5), ("pi", 3), ("pi-", 2)],
    )
    def test_printed_multipliers(self, dtype, expected):
        # 10 penetrating: x1 -> 10, x1/2 -> 5, x1/3 -> 3 (floor), x1/5 -> 2
        assert _wound("10", dtype, it=InjuryTolerance.UNLIVING) == expected

    def test_non_piercing_types_are_untouched(self):
        """The sidebar only names impaling and piercing families."""
        assert _wound("10", "cr", it=InjuryTolerance.UNLIVING) == 10
        assert _wound("10", "cut", it=InjuryTolerance.UNLIVING) == 15


class TestHomogenous:
    @pytest.mark.parametrize(
        "dtype,expected",
        [("imp", 5), ("pi++", 5), ("pi+", 3), ("pi", 2), ("pi-", 1)],
    )
    def test_printed_multipliers(self, dtype, expected):
        # 10 penetrating: x1/2 -> 5, x1/3 -> 3, x1/5 -> 2, x1/10 -> 1
        assert _wound("10", dtype, it=InjuryTolerance.HOMOGENOUS) == expected

    def test_strictly_tougher_than_unliving(self):
        for dtype in ("imp", "pi++", "pi+", "pi", "pi-"):
            homo = _wound("20", dtype, it=InjuryTolerance.HOMOGENOUS)
            unliving = _wound("20", dtype, it=InjuryTolerance.UNLIVING)
            assert homo <= unliving, dtype


class TestDiffuse:
    @pytest.mark.parametrize("dtype", ["imp", "pi++", "pi+", "pi", "pi-"])
    def test_impaling_and_piercing_capped_at_one(self, dtype):
        assert _wound("100", dtype, it=InjuryTolerance.DIFFUSE) == 1

    @pytest.mark.parametrize("dtype", ["cr", "cut", "burn", "tox", "cor"])
    def test_everything_else_capped_at_two(self, dtype):
        assert _wound("100", dtype, it=InjuryTolerance.DIFFUSE) == 2

    def test_cap_does_not_become_a_floor(self):
        """A 1-point crushing hit stays 1, not 2."""
        assert _wound("1", "cr", it=InjuryTolerance.DIFFUSE) == 1

    def test_no_penetration_still_no_wound(self):
        assert _wound("5", "imp", dr=10, it=InjuryTolerance.DIFFUSE) == 0


class TestInteractionWithLocationAndFloor:
    def test_location_and_tolerance_take_the_more_protective(self):
        """B399 drops imp to x1 against a limb; Unliving also gives imp x1.
        Homogenous gives x1/2, which is more protective and must win."""
        assert _wound("10", "imp", location="right arm") == 10
        assert (
            _wound("10", "imp", location="right arm", it=InjuryTolerance.HOMOGENOUS)
            == 5
        )

    def test_minimum_one_injury_floor_survives(self):
        """B379: any attack that penetrates DR inflicts at least 1 HP."""
        assert _wound("1", "pi-", it=InjuryTolerance.HOMOGENOUS) == 1

    def test_none_leaves_everything_unchanged(self):
        for dtype in ("imp", "pi", "cr", "cut"):
            assert _wound("10", dtype, it=None) == _wound("10", dtype)
