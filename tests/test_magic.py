"""Spell-mechanics calculators (mechanics/magic.py, B234-242)."""

from __future__ import annotations

import pytest

from gurps_bot.mechanics.dice import DiceSpec
from gurps_bot.mechanics.magic import (
    casting_time,
    ceremonial_energy,
    effective_spell_cost,
    long_distance_modifier,
    maintenance_cost,
    missile_spell_damage,
    regular_spell_distance_penalty,
    spell_energy_reduction,
)


# high-skill energy reduction (B236)
class TestEnergyReduction:
    def test_tiers(self):
        # 15-19 -> -1, 20-24 -> -2, +1 per full 5 beyond 20
        assert spell_energy_reduction(15) == 1
        assert spell_energy_reduction(19) == 1
        assert spell_energy_reduction(20) == 2
        assert spell_energy_reduction(24) == 2
        assert spell_energy_reduction(25) == 3
        assert spell_energy_reduction(30) == 4
        assert spell_energy_reduction(35) == 5

    def test_below_15_no_reduction(self):
        assert spell_energy_reduction(14) == 0
        assert spell_energy_reduction(0) == 0

    def test_low_mana_lowers_base_skill(self):
        # low mana: -5 to skill before the tier lookup (20 -> eff 15 -> -1)
        assert spell_energy_reduction(20, low_mana=True) == 1
        assert spell_energy_reduction(19, low_mana=True) == 0


# cost: size/area scaling then high-skill reduction (B239-240)
class TestEffectiveSpellCost:
    def test_regular_size_modifier(self):
        # SM+2 -> x3; skill 10 no reduction
        r = effective_spell_cost(2, 10, size_modifier=2)
        assert r.scaled_cost == 6
        assert r.final_cost == 6

    def test_area_radius(self):
        # scale THEN reduce: r3 -> 6, skill 20 -> -2 -> 4
        r = effective_spell_cost(2, 20, area_radius=3)
        assert r.scaled_cost == 6
        assert r.final_cost == 4

    def test_fractional_area_base_floors_at_one(self):
        # fractional base still costs min 1 (B240)
        r = effective_spell_cost(0.5, 10, area_radius=1)
        assert r.scaled_cost == 1

    def test_negative_size_modifier_no_discount(self):
        # SM <= 0: no discount
        r = effective_spell_cost(3, 10, size_modifier=-2)
        assert r.scaled_cost == 3
        assert r.final_cost == 3

    def test_high_skill_can_floor_cost_at_zero(self):
        r = effective_spell_cost(1, 20, low_mana=False)
        assert r.final_cost == 0  # base 1, skill 20 -> -2 -> max(0, -1) = 0

    def test_size_and_area_together_raises(self):
        with pytest.raises(ValueError):
            effective_spell_cost(2, 10, size_modifier=1, area_radius=2)


# maintenance (B237) — same reduction as casting cost
class TestMaintenanceCost:
    def test_high_skill_can_zero_maintenance(self):
        # skill 15 -> -1; a 1/turn maintenance becomes free
        assert maintenance_cost(1, 15) == 0

    def test_no_reduction_below_15(self):
        assert maintenance_cost(2, 14) == 2


# casting time / ritual tiers (B236-237)
class TestCastingTime:
    def test_halving_tiers(self):
        assert casting_time(4, 20) == 2   # /2 round up
        assert casting_time(4, 25) == 1   # /4 round up
        assert casting_time(4, 30) == 1   # /8 round up, min 1

    def test_low_skill_doubles(self):
        assert casting_time(1, 5) == 2

    def test_as_listed_band(self):
        assert casting_time(3, 12) == 3   # 10-19 unchanged
        assert casting_time(3, 18) == 3

    def test_minimum_one_second(self):
        assert casting_time(1, 25) == 1

    def test_ceremonial_x10_no_high_skill_reduction(self):
        assert casting_time(3, 15, ceremonial=True) == 30
        assert casting_time(1, 30, ceremonial=True) == 10


# ceremonial energy pool + extra-energy bonus (B238)
class TestCeremonialEnergy:
    def test_supporters_capped_and_20pct_bonus(self):
        # caster 2 + 10 supporters (1 each) = 12 -> +20% surplus -> +1
        r = ceremonial_energy(10, caster_energy=2, supporters=10)
        assert r.total_energy == 12
        assert r.extra_energy == 2
        assert r.skill_bonus == 1

    def test_100pct_surplus_plus4(self):
        r = ceremonial_energy(10, caster_energy=10, mage_energy=10)
        assert r.total_energy == 20
        assert r.extra_energy == 10
        assert r.skill_bonus == 4

    def test_supporter_cap_100(self):
        r = ceremonial_energy(10, supporters=500)
        assert r.total_energy == 100  # capped at +100

    def test_opposers_cap_negative_100(self):
        r = ceremonial_energy(10, caster_energy=100, opposers=500)
        assert r.total_energy == 0  # 100 - min(100, 5*500)=100 -> 0

    def test_skilled_nonmages_three_each(self):
        r = ceremonial_energy(10, skilled_nonmages=2, low_skill_mages=1)
        assert r.total_energy == 9  # 3*2 + 3*1

    def test_no_surplus_no_bonus(self):
        r = ceremonial_energy(10, caster_energy=10)
        assert r.extra_energy == 0
        assert r.skill_bonus == 0


# long-distance modifiers (B241)
class TestLongDistanceModifier:
    def test_table_anchors(self):
        assert long_distance_modifier(yards=200) == 0
        assert long_distance_modifier(miles=0.5) == -1
        assert long_distance_modifier(miles=1) == -2
        assert long_distance_modifier(miles=3) == -3
        assert long_distance_modifier(miles=10) == -4
        assert long_distance_modifier(miles=30) == -5
        assert long_distance_modifier(miles=100) == -6
        assert long_distance_modifier(miles=300) == -7
        assert long_distance_modifier(miles=1000) == -8

    def test_between_values_uses_higher_bracket(self):
        # between brackets -> the higher one (-3)
        assert long_distance_modifier(miles=2) == -3

    def test_beyond_1000_minus2_per_decade(self):
        assert long_distance_modifier(miles=10000) == -10
        assert long_distance_modifier(miles=100000) == -12

    def test_requires_exactly_one_arg(self):
        with pytest.raises(ValueError):
            long_distance_modifier()
        with pytest.raises(ValueError):
            long_distance_modifier(yards=1, miles=1)


# regular-spell distance penalty (B240)
class TestRegularDistancePenalty:
    def test_minus_one_per_yard(self):
        assert regular_spell_distance_penalty(5) == -5

    def test_cannot_see_or_touch_extra_minus5(self):
        assert regular_spell_distance_penalty(5, can_see=False) == -10

    def test_touch_is_free(self):
        assert regular_spell_distance_penalty(5, can_touch=True) == 0


# missile damage — magery/second, up to 3 s buildup (B240)
class TestMissileSpellDamage:
    def test_one_second_caps_at_magery(self):
        assert missile_spell_damage(2) == DiceSpec(2, 6, 0)

    def test_three_seconds_triples(self):
        assert missile_spell_damage(2, seconds=3) == DiceSpec(6, 6, 0)

    def test_seconds_clamped_to_three(self):
        assert missile_spell_damage(2, seconds=5) == DiceSpec(6, 6, 0)

    def test_investing_under_cap(self):
        assert missile_spell_damage(2, seconds=3, energy=5) == DiceSpec(5, 6, 0)

    def test_magery_zero_no_dice(self):
        assert missile_spell_damage(0) == DiceSpec(0, 6, 0)


class TestMagicGuardsAndRendering:
    def test_spell_cost_str_area(self):
        s = str(effective_spell_cost(2, skill=15, area_radius=3))
        assert "area r3" in s and "FP" in s

    def test_spell_cost_str_size_modifier(self):
        assert "SM+2" in str(effective_spell_cost(2, skill=10, size_modifier=2))

    def test_spell_cost_str_plain(self):
        s = str(effective_spell_cost(3, skill=20))
        assert "cost 3" in s and "(skill)" in s

    def test_effective_cost_negative_base_raises(self):
        with pytest.raises(ValueError, match="base_cost"):
            effective_spell_cost(-1, skill=10)

    def test_effective_cost_negative_area_raises(self):
        with pytest.raises(ValueError, match="area_radius"):
            effective_spell_cost(2, skill=10, area_radius=-1)

    def test_casting_time_base_below_one_raises(self):
        with pytest.raises(ValueError, match="base_seconds"):
            casting_time(0, skill=10)

    def test_ceremonial_str(self):
        assert "ceremonial" in str(ceremonial_energy(10, caster_energy=12))

    def test_ceremonial_zero_cost_raises(self):
        with pytest.raises(ValueError, match="spell_cost"):
            ceremonial_energy(0)

    def test_ceremonial_negative_count_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            ceremonial_energy(10, supporters=-1)

    def test_ceremonial_small_surplus_no_bonus(self):
        # surplus < +20% of cost -> no skill bonus (the low-ratio branch)
        r = ceremonial_energy(10, caster_energy=11)
        assert r.extra_energy == 1
        assert r.skill_bonus == 0

    def test_long_distance_negative_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            long_distance_modifier(miles=-1)

    def test_regular_distance_negative_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            regular_spell_distance_penalty(-1)

    def test_missile_negative_magery_raises(self):
        with pytest.raises(ValueError, match="magery"):
            missile_spell_damage(-1)

    def test_missile_seconds_below_one_raises(self):
        with pytest.raises(ValueError, match="seconds"):
            missile_spell_damage(3, seconds=0)
