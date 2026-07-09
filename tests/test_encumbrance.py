"""Encumbrance & Move (B15/B17)."""

import math

import pytest
from gurps_bot.mechanics.encumbrance import (
    EncumbranceResult,
    EncumbranceThreshold,
    _MOVE_MULTIPLIERS,
    basic_lift,
    effective_move,
    encumbrance_level,
    encumbrance_report,
    encumbrance_thresholds,
    full_dodge,
)


class TestBasicLift:
    """B15: BL = ST*ST/5, rounded to a whole number once BL >= 10."""

    def test_canonical_anchor_st10(self):
        # 10*10/5 = 20, >= 10 -> whole number
        assert basic_lift(10) == 20.0

    def test_st13_rounds_up(self):
        # 169/5 = 33.8 -> 34
        assert basic_lift(13) == 34.0

    def test_st11_rounds_down(self):
        # 121/5 = 24.2 -> 24 (round-to-nearest, not truncate)
        assert basic_lift(11) == 24.0

    def test_st6_keeps_fraction(self):
        # 36/5 = 7.2, under 10 keeps the fraction
        assert basic_lift(6) == 7.2

    def test_st5_at_fractional_branch(self):
        # 25/5 = 5.0, fractional branch, value happens to be whole
        assert basic_lift(5) == 5.0

    def test_st7_keeps_fraction(self):
        # 49/5 = 9.8, still under the cutoff
        assert basic_lift(7) == 9.8

    def test_returns_float_type(self):
        assert isinstance(basic_lift(10), float)
        assert isinstance(basic_lift(6), float)

    def test_st0_is_zero(self):
        assert basic_lift(0) == 0.0

    def test_cutoff_is_on_bl_not_st(self):
        # ST 8 -> 64/5 = 12.8 -> rounds to 13
        assert basic_lift(8) == 13.0
        # ST 9 -> 81/5 = 16.2 -> rounds to 16
        assert basic_lift(9) == 16.0

    def test_no_half_ties_ever(self):
        # ST*ST/5 ends in .0/.2/.4/.6/.8, never .5, so banker's round()
        # agrees with round-half-up for every ST
        for st in range(1, 200):
            raw = (st * st) / 5.0
            assert raw % 1 != 0.5
            bl = basic_lift(st)
            if raw >= 10:
                expected = float(math.floor(raw + 0.5))  # round-half-up
                assert bl == expected
            else:
                assert bl == raw

    def test_negative_st_raises(self):
        with pytest.raises(ValueError):
            basic_lift(-1)


class TestEncumbranceLevel:
    """B15: levels 0..5, band upper bounds inclusive."""

    def test_w_equals_bl_is_none(self):
        # W == BL is still None (inclusive bound)
        assert encumbrance_level(20, 20.0) == 0

    def test_just_over_bl_is_light(self):
        assert encumbrance_level(20.01, 20.0) == 1

    def test_w_equals_2bl_is_light(self):
        assert encumbrance_level(40, 20.0) == 1

    def test_w_equals_3bl_is_medium(self):
        # 3*20 = 60, W <= 60 -> Medium
        assert encumbrance_level(60, 20.0) == 2

    def test_just_over_3bl_is_heavy(self):
        assert encumbrance_level(60.01, 20.0) == 3

    def test_w_equals_6bl_is_heavy(self):
        assert encumbrance_level(120, 20.0) == 3

    def test_w_equals_10bl_is_extra_heavy(self):
        # W == 10*BL is still Extra-Heavy, not overloaded
        assert encumbrance_level(200, 20.0) == 4

    def test_over_10bl_is_overloaded(self):
        assert encumbrance_level(200.5, 20.0) == 5

    def test_zero_weight_is_none(self):
        assert encumbrance_level(0, 20.0) == 0

    def test_bl_zero_any_weight_overloaded(self):
        # BL 0: any positive weight overloads
        assert encumbrance_level(5, 0.0) == 5
        assert encumbrance_level(0.1, 0.0) == 5

    def test_bl_zero_zero_weight_is_none(self):
        assert encumbrance_level(0, 0.0) == 0

    def test_fractional_weight_against_sub10_bl(self):
        # BL 7.2: 14.4 == 2*BL Light bound; 14.41 -> Medium
        assert encumbrance_level(14.4, 7.2) == 1
        assert encumbrance_level(14.41, 7.2) == 2

    def test_negative_weight_raises(self):
        with pytest.raises(ValueError):
            encumbrance_level(-1, 20.0)

    def test_negative_bl_raises(self):
        with pytest.raises(ValueError):
            encumbrance_level(10, -1.0)


class TestEffectiveMove:
    """B15/B17: Move under encumbrance."""

    def test_floor_boundary_bm5_extra_heavy(self):
        # 5*0.2 = 1.0 -> floor 1, right at the boundary
        assert effective_move(5, 4) == 1

    def test_floor_to_one_bm4_extra_heavy(self):
        # 4*0.2 = 0.8 -> floor 0 -> bumped to min 1
        assert effective_move(4, 4) == 1

    def test_no_encumbrance_unchanged(self):
        assert effective_move(6, 0) == 6

    def test_overloaded_forces_zero(self):
        assert effective_move(6, 5) == 0

    def test_basic_move_zero_stays_zero(self):
        # the min-1 clamp must not lift a true Move 0
        assert effective_move(0, 0) == 0

    def test_basic_move_zero_stays_zero_every_level(self):
        for level in range(0, 6):
            assert effective_move(0, level) == 0

    def test_light_floor(self):
        # 6*0.8 = 4.8 -> floor 4
        assert effective_move(6, 1) == 4

    def test_medium_floor(self):
        # 6*0.6 = 3.6 -> floor 3
        assert effective_move(6, 2) == 3

    def test_heavy_floor(self):
        # 6*0.4 = 2.4 -> floor 2
        assert effective_move(6, 3) == 2

    def test_negative_basic_move_raises(self):
        with pytest.raises(ValueError):
            effective_move(-1, 0)

    def test_bad_level_raises(self):
        with pytest.raises(ValueError):
            effective_move(6, 6)
        with pytest.raises(ValueError):
            effective_move(6, -1)


class TestFullDodge:
    """B17: Dodge under encumbrance."""

    def test_baseline_speed5(self):
        # floor(5)+3-0 = 8
        assert full_dodge(5.0, 0) == 8

    def test_fractional_speed_floors_before_penalty(self):
        # floor(5.75)=5, +3-2 = 6; Speed floors before the +3
        assert full_dodge(5.75, 2) == 6

    def test_extra_heavy_penalty(self):
        # floor(6)+3-4 = 5
        assert full_dodge(6.0, 4) == 5

    def test_speed_increments_dont_raise_until_integer(self):
        # 5.25 and 5.75 both floor to 5
        assert full_dodge(5.25, 0) == 8
        assert full_dodge(5.75, 0) == 8

    def test_overloaded_still_computes_dodge(self):
        # level 5 still computes: floor(5)+3-5 = 3
        assert full_dodge(5.0, 5) == 3

    def test_bad_level_raises(self):
        with pytest.raises(ValueError):
            full_dodge(5.0, 6)
        with pytest.raises(ValueError):
            full_dodge(5.0, -1)

    def test_negative_speed_raises(self):
        with pytest.raises(ValueError):
            full_dodge(-1.0, 0)


class TestEncumbranceThresholds:
    """B15 threshold table."""

    def test_max_weight_sequence(self):
        # BL, 2BL, 3BL, 6BL, 10BL
        maxes = [t.max_weight for t in encumbrance_thresholds(20.0)]
        assert maxes == [20.0, 40.0, 60.0, 120.0, 200.0]

    def test_exactly_five_bands(self):
        # overloaded is not a band
        assert len(encumbrance_thresholds(20.0)) == 5

    def test_returns_tuple_of_dataclass(self):
        result = encumbrance_thresholds(20.0)
        assert isinstance(result, tuple)
        assert all(isinstance(t, EncumbranceThreshold) for t in result)

    def test_levels_are_0_to_4(self):
        levels = [t.level for t in encumbrance_thresholds(20.0)]
        assert levels == [0, 1, 2, 3, 4]

    def test_names_in_order(self):
        names = [t.name for t in encumbrance_thresholds(20.0)]
        assert names == ["None", "Light", "Medium", "Heavy", "Extra-Heavy"]

    def test_move_multipliers_in_order(self):
        mults = [t.move_multiplier for t in encumbrance_thresholds(20.0)]
        assert mults == [1.0, 0.8, 0.6, 0.4, 0.2]

    def test_dodge_penalty_equals_level(self):
        for t in encumbrance_thresholds(20.0):
            assert t.dodge_penalty == t.level

    def test_negative_bl_raises(self):
        with pytest.raises(ValueError):
            encumbrance_thresholds(-1.0)


class TestEncumbranceReport:
    """end-to-end report (B15/B17)."""

    def test_end_to_end_light(self):
        # 25 <= 40 -> Light; floor(4.8)=4; floor(5)+3-1=7
        result = encumbrance_report(10, 6, 5.0, 25)
        assert result == EncumbranceResult(
            basic_lift=20.0,
            carried_weight=25,
            level=1,
            level_name="Light",
            move_multiplier=0.8,
            effective_move=4,
            dodge=7,
            overloaded=False,
        )

    def test_end_to_end_overloaded(self):
        # 250 > 200 -> level 5, Move forced 0; Dodge = floor(5)+3-5 = 3
        result = encumbrance_report(10, 6, 5.0, 250)
        assert result == EncumbranceResult(
            basic_lift=20.0,
            carried_weight=250,
            level=5,
            level_name="Overloaded",
            move_multiplier=0.0,
            effective_move=0,
            dodge=3,
            overloaded=True,
        )

    def test_end_to_end_none(self):
        result = encumbrance_report(10, 6, 5.0, 20)
        assert result.basic_lift == 20.0
        assert result.level == 0
        assert result.level_name == "None"
        assert result.move_multiplier == 1.0
        assert result.effective_move == 6
        assert result.dodge == 8
        assert result.overloaded is False

    def test_report_field_types(self):
        result = encumbrance_report(10, 6, 5.0, 25)
        assert isinstance(result.basic_lift, float)
        assert isinstance(result.level, int)
        assert isinstance(result.level_name, str)
        assert isinstance(result.move_multiplier, float)
        assert isinstance(result.effective_move, int)
        assert isinstance(result.dodge, int)
        assert isinstance(result.overloaded, bool)

    def test_carried_weight_echoed(self):
        result = encumbrance_report(10, 6, 5.0, 33.5)
        assert result.carried_weight == 33.5

    def test_negative_inputs_raise(self):
        with pytest.raises(ValueError):
            encumbrance_report(-1, 6, 5.0, 25)
        with pytest.raises(ValueError):
            encumbrance_report(10, -1, 5.0, 25)
        with pytest.raises(ValueError):
            encumbrance_report(10, 6, -1.0, 25)
        with pytest.raises(ValueError):
            encumbrance_report(10, 6, 5.0, -1)


class TestMoveMultipliersConstant:
    """The _MOVE_MULTIPLIERS map is the single source of truth for bands."""

    def test_map_values(self):
        assert _MOVE_MULTIPLIERS == {
            0: 1.0,
            1: 0.8,
            2: 0.6,
            3: 0.4,
            4: 0.2,
            5: 0.0,
        }

    def test_covers_all_six_levels(self):
        assert set(_MOVE_MULTIPLIERS.keys()) == {0, 1, 2, 3, 4, 5}
