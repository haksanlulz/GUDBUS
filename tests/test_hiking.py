"""Hiking / daily travel (B351, FP B426); pure math — hiking_success is caller-supplied."""

import pytest

from gurps_bot.mechanics.hiking import (
    Encumbrance,
    HikingResult,
    Terrain,
    Weather,
    calc_hiking,
    effective_move,
    encumbrance_move_multiplier,
    fp_cost_per_hour,
)


class TestEncumbranceMoveMultiplier:
    """B17 Move multipliers — one owner for the table."""

    def test_none(self):
        assert encumbrance_move_multiplier(Encumbrance.NONE) == 1.0

    def test_light(self):
        assert encumbrance_move_multiplier(Encumbrance.LIGHT) == 0.8

    def test_medium(self):
        assert encumbrance_move_multiplier(Encumbrance.MEDIUM) == 0.6

    def test_heavy(self):
        assert encumbrance_move_multiplier(Encumbrance.HEAVY) == 0.4

    def test_extra_heavy(self):
        assert encumbrance_move_multiplier(Encumbrance.EXTRA_HEAVY) == 0.2

    def test_member_value_is_multiplier(self):
        # each member's .value is its Move multiplier
        assert Encumbrance.NONE.value == 1.0
        assert Encumbrance.EXTRA_HEAVY.value == 0.2


class TestEnumMultipliers:
    """Terrain / Weather members carry .mult per B351."""

    def test_terrain_mults(self):
        assert Terrain.VERY_BAD.mult == 0.20
        assert Terrain.BAD.mult == 0.50
        assert Terrain.AVERAGE.mult == 1.00
        assert Terrain.GOOD.mult == 1.25

    def test_weather_mults(self):
        assert Weather.CLEAR.mult == 1.0
        assert Weather.RAIN.mult == 0.5
        assert Weather.SNOW_ANKLE.mult == 0.5
        assert Weather.SNOW_DEEP.mult == 0.25
        assert Weather.ICE.mult == 0.5


class TestEffectiveMove:
    """Encumbrance applied then fractions dropped (floor), min 1 unless Move 0."""

    def test_no_encumbrance(self):
        assert effective_move(6, Encumbrance.NONE) == 6

    def test_medium_floors(self):
        # 5 * 0.6 = 3.0 -> 3
        assert effective_move(5, Encumbrance.MEDIUM) == 3

    def test_heavy_floors_fraction(self):
        # 6 * 0.4 = 2.4 -> floor 2
        assert effective_move(6, Encumbrance.HEAVY) == 2

    def test_light_floors_fraction(self):
        # 6 * 0.8 = 4.8 -> floor 4
        assert effective_move(6, Encumbrance.LIGHT) == 4

    def test_min_one_clamp(self):
        # 1 * 0.2 = 0.2 -> floor 0 -> clamp to 1
        assert effective_move(1, Encumbrance.EXTRA_HEAVY) == 1

    def test_zero_move_stays_zero(self):
        assert effective_move(0, Encumbrance.NONE) == 0
        assert effective_move(0, Encumbrance.EXTRA_HEAVY) == 0

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            effective_move(-1, Encumbrance.NONE)


class TestFpCostPerHour:
    """B426 forced-march FP/hour costs."""

    def test_base_costs(self):
        assert fp_cost_per_hour(Encumbrance.NONE) == 1
        assert fp_cost_per_hour(Encumbrance.LIGHT) == 2
        assert fp_cost_per_hour(Encumbrance.MEDIUM) == 3
        assert fp_cost_per_hour(Encumbrance.HEAVY) == 4
        assert fp_cost_per_hour(Encumbrance.EXTRA_HEAVY) == 5

    def test_hot_day_adds_one(self):
        # B426 worked example: Light = 2, +1 hot = 3.
        assert fp_cost_per_hour(Encumbrance.LIGHT, hot_day=True) == 3

    def test_hot_day_heavy_garb_adds_two(self):
        # Plate/overcoat on a hot day: +2 instead of +1.
        assert fp_cost_per_hour(Encumbrance.LIGHT, hot_day=True, heavy_garb=True) == 4

    def test_heavy_garb_without_hot_day_adds_nothing(self):
        # heavy_garb only matters when hot_day is True (avoid double-add).
        assert fp_cost_per_hour(Encumbrance.MEDIUM, heavy_garb=True) == 3

    def test_hot_day_none_encumbrance(self):
        assert fp_cost_per_hour(Encumbrance.NONE, hot_day=True) == 2


class TestCalcHikingSpecCases:
    def test_canonical_baseline(self):
        r = calc_hiking(
            basic_move=6,
            encumbrance=Encumbrance.NONE,
            terrain=Terrain.AVERAGE,
            weather=Weather.CLEAR,
            hiking_success=False,
        )
        assert r.effective_move == 6
        assert r.base_miles == 60
        assert r.miles_per_day == 60
        assert r.fp_per_hour == 1

    def test_hiking_success_adds_twenty_percent(self):
        r = calc_hiking(
            basic_move=6,
            encumbrance=Encumbrance.NONE,
            terrain=Terrain.AVERAGE,
            weather=Weather.CLEAR,
            hiking_success=True,
        )
        assert r.skill_mult == 1.2
        assert r.miles_per_day == 72

    def test_medium_encumbrance(self):
        r = calc_hiking(
            basic_move=5,
            encumbrance=Encumbrance.MEDIUM,
            terrain=Terrain.AVERAGE,
            weather=Weather.CLEAR,
        )
        assert r.effective_move == 3
        assert r.base_miles == 30
        assert r.miles_per_day == 30
        assert r.fp_per_hour == 3

    def test_very_bad_terrain(self):
        r = calc_hiking(
            basic_move=6,
            encumbrance=Encumbrance.NONE,
            terrain=Terrain.VERY_BAD,
            weather=Weather.CLEAR,
        )
        assert r.terrain_mult == 0.20
        assert r.miles_per_day == 12

    def test_rain_halves(self):
        r = calc_hiking(
            basic_move=6,
            encumbrance=Encumbrance.NONE,
            terrain=Terrain.AVERAGE,
            weather=Weather.RAIN,
        )
        assert r.weather_mult == 0.5
        assert r.miles_per_day == 30

    def test_full_stack(self):
        r = calc_hiking(
            basic_move=6,
            encumbrance=Encumbrance.HEAVY,
            terrain=Terrain.GOOD,
            weather=Weather.CLEAR,
            hiking_success=True,
        )
        assert r.effective_move == 2  # 6 * 0.4 = 2.4 -> floor 2
        assert r.base_miles == 20
        assert r.terrain_mult == 1.25
        assert r.skill_mult == 1.2
        assert r.miles_per_day == 30  # 10*2*1.25*1.2 = 30
        assert r.fp_per_hour == 4

    def test_fp_light_hot_day(self):
        assert fp_cost_per_hour(Encumbrance.LIGHT, hot_day=True) == 3

    def test_min_move_clamp_distance(self):
        r = calc_hiking(basic_move=1, encumbrance=Encumbrance.EXTRA_HEAVY)
        assert r.effective_move == 1  # clamp
        assert r.base_miles == 10
        assert r.miles_per_day == 10
        assert r.fp_per_hour == 5

    def test_enhanced_move_doubles(self):
        r = calc_hiking(basic_move=6, enhanced_move_mult=2.0)
        assert r.miles_per_day == 120

    def test_negative_basic_move_raises(self):
        with pytest.raises(ValueError):
            calc_hiking(basic_move=-1)


class TestCalcHikingEdgeCases:
    def test_zero_move_zero_distance(self):
        r = calc_hiking(basic_move=0, encumbrance=Encumbrance.NONE)
        assert r.effective_move == 0
        assert r.base_miles == 0
        assert r.miles_per_day == 0
        # FP note still reports a cost band even though distance is 0.
        assert r.fp_per_hour == 1
        assert "B426" in r.fp_note

    def test_very_bad_plus_deep_snow_rounds_not_floors(self):
        # Move 5 -> 10*5*0.2*0.25 = 2.5 -> standard round (banker's) to 2.
        r = calc_hiking(
            basic_move=5,
            terrain=Terrain.VERY_BAD,
            weather=Weather.SNOW_DEEP,
        )
        assert r.miles_per_day == 2

    def test_small_distance_not_floored_to_zero(self):
        # Move 1, Very Bad, deep snow: 10*1*0.2*0.25 = 0.5 -> round to 0 (banker's),
        # but Move 2: 10*2*0.2*0.25 = 1.0 -> 1.
        r = calc_hiking(
            basic_move=2,
            terrain=Terrain.VERY_BAD,
            weather=Weather.SNOW_DEEP,
        )
        assert r.miles_per_day == 1

    def test_enhanced_move_below_one_raises(self):
        with pytest.raises(ValueError):
            calc_hiking(basic_move=6, enhanced_move_mult=0.5)

    def test_default_terrain_weather_are_average_clear(self):
        r = calc_hiking(basic_move=6)
        assert r.terrain == Terrain.AVERAGE
        assert r.weather == Weather.CLEAR
        assert r.hiking_success is False
        assert r.enhanced_move_mult == 1.0
        assert r.miles_per_day == 60

    def test_result_is_frozen(self):
        r = calc_hiking(basic_move=6)
        with pytest.raises((AttributeError, Exception)):
            r.miles_per_day = 999  # type: ignore[misc]

    def test_result_fields_populated(self):
        r = calc_hiking(
            basic_move=6,
            encumbrance=Encumbrance.LIGHT,
            terrain=Terrain.GOOD,
            weather=Weather.RAIN,
            hiking_success=True,
            enhanced_move_mult=2.0,
        )
        assert isinstance(r, HikingResult)
        assert r.basic_move == 6
        assert r.encumbrance == Encumbrance.LIGHT
        assert r.terrain == Terrain.GOOD
        assert r.weather == Weather.RAIN
        assert r.hiking_success is True
        assert r.enhanced_move_mult == 2.0
        # effective_move = floor(6*0.8)=4; base=40; 40*1.25*0.5*1.2*2 = 60
        assert r.effective_move == 4
        assert r.base_miles == 40
        assert r.miles_per_day == 60

    def test_fp_note_mentions_per_hour(self):
        r = calc_hiking(basic_move=6, encumbrance=Encumbrance.MEDIUM)
        assert "3" in r.fp_note  # 3 FP/hour for Medium
        assert "hour" in r.fp_note.lower()


class TestRoundingBehavior:
    """Rounding applied once at the very end on miles_per_day only."""

    def test_round_half_to_even_on_distance(self):
        # 2.5 -> 2 under Python's round (banker's rounding).
        r = calc_hiking(basic_move=5, terrain=Terrain.VERY_BAD, weather=Weather.SNOW_DEEP)
        assert r.miles_per_day == 2

    def test_base_miles_integral(self):
        # base_miles = 10 * effective_move, always integral.
        r = calc_hiking(basic_move=7, encumbrance=Encumbrance.LIGHT)
        # 7 * 0.8 = 5.6 -> floor 5 -> base 50
        assert r.effective_move == 5
        assert r.base_miles == 50
