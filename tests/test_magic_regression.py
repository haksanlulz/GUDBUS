"""Regression: _extra_energy_bonus ran max() over an empty generator on a sub-+20% surplus."""

from __future__ import annotations

import pytest

from gurps_bot.mechanics import magic
from gurps_bot.mechanics.magic import _extra_energy_bonus, ceremonial_energy


# lowest tier threshold, read from the module so the test tracks the real table
_FIRST_TIER_THRESHOLD = magic._EXTRA_ENERGY_TIERS[0][0]


class TestExtraEnergyBonusEmptyMaxRegression:
    @pytest.mark.parametrize(
        "ratio", [0.0, 0.001, 0.05, 0.1, 0.15, 0.19, 0.199, _FIRST_TIER_THRESHOLD - 1e-9]
    )
    def test_below_first_tier_returns_zero_never_raises(self, ratio: float) -> None:
        # the band strictly below the first tier is what empties the max() generator
        assert ratio < _FIRST_TIER_THRESHOLD
        assert _extra_energy_bonus(ratio) == 0

    def test_exact_first_tier_boundary_is_one(self) -> None:
        # the boundary itself is the +20% tier -> +1; the guard must be strict <
        assert _extra_energy_bonus(_FIRST_TIER_THRESHOLD) == 1

    def test_public_surface_small_surplus_no_bonus_no_crash(self) -> None:
        # public-api trigger: a small legal surplus -> 0 bonus, no raise
        result = ceremonial_energy(10, caster_energy=11)  # surplus 1, ratio 0.1
        assert result.extra_energy == 1
        assert result.skill_bonus == 0

    def test_smallest_possible_surplus_does_not_raise(self) -> None:
        result = ceremonial_energy(100, caster_energy=101)  # surplus 1, ratio 0.01
        assert result.skill_bonus == 0
