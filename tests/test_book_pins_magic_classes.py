"""Book pins for the two spell-class exceptions to the high-skill rules (B237).

B237, verbatim: "Such requirements override the rules above. For instance, high
skill has no effect on the cost to cast Blocking spells (p. 241) or the time to
cast Missile spells (p. 240)."

B236 states the cost half again: "Exception: Never reduce the cost of a Blocking
spell."

Everything else in magic.py reproduced the printed book; these two exceptions
had no way to be expressed, so a skill-25 caster got a Blocking spell discounted
and a Missile spell's casting time quartered, both against RAW.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics.magic import (
    casting_time,
    effective_spell_cost,
    maintenance_cost,
    spell_energy_reduction,
)


class TestBlockingSpellsNeverGetACostReduction:
    def test_high_skill_still_reduces_an_ordinary_spell(self):
        """Guard against over-correcting: the general rule must survive."""
        assert effective_spell_cost(6, 25).final_cost == 3

    @pytest.mark.parametrize("skill", [15, 20, 25, 30, 40])
    def test_blocking_spell_pays_full_cost_at_any_skill(self, skill):
        result = effective_spell_cost(6, skill, blocking=True)
        assert result.reduction == 0
        assert result.final_cost == 6

    def test_blocking_maintenance_is_also_unreduced(self):
        assert maintenance_cost(3, 30) == 0          # ordinary: reduced to 0
        assert maintenance_cost(3, 30, blocking=True) == 3

    def test_blocking_still_scales_for_size_and_area(self):
        """Only the reduction is blocked, not the size/area multiplier."""
        result = effective_spell_cost(2, 30, area_radius=3, blocking=True)
        assert result.scaled_cost == 6
        assert result.final_cost == 6

    def test_reduction_helper_reports_zero_for_blocking(self):
        assert spell_energy_reduction(30) == 4
        assert spell_energy_reduction(30, blocking=True) == 0


class TestMissileSpellsNeverGetATimeReduction:
    def test_high_skill_still_shortens_an_ordinary_spell(self):
        """Guard against over-correcting."""
        assert casting_time(4, 25) == 1  # divided by 4 at skill 25-29

    @pytest.mark.parametrize("skill", [20, 25, 30, 40])
    def test_missile_spell_keeps_its_printed_time(self, skill):
        assert casting_time(3, skill, missile=True) == 3

    def test_missile_spell_still_doubles_at_low_skill(self):
        """B237's "Skill 9 or less - Time: Doubled" is not a *reduction*, so
        the Missile exception does not exempt a fumbling caster from it."""
        assert casting_time(2, 9, missile=True) == 4

    def test_missile_spell_unchanged_in_the_flat_band(self):
        assert casting_time(3, 14, missile=True) == 3
        assert casting_time(3, 19, missile=True) == 3

    def test_ceremonial_still_multiplies_for_a_missile_spell(self):
        """Ceremonial x10 is not a high-skill reduction either."""
        assert casting_time(2, 30, missile=True, ceremonial=True) == 20
