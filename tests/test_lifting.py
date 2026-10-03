"""Tests for GURPS lifting & moving capacity calculator (B353)."""

import pytest
from gurps_bot.mechanics.lifting import (
    LiftCapacities,
    basic_lift,
    carry_on_back,
    drag,
    lifting_capacities,
    one_handed_lift,
    shift_slightly,
    shove,
    two_handed_lift,
)


class TestBasicLift:
    def test_st_10_baseline(self):
        # ST 10 -> 10*10/5 = 20 lb BL
        assert basic_lift(10) == 20.0

    def test_st_11_not_rounded(self):
        # 121/5 = 24.2; a stray int() cast would yield 24
        assert basic_lift(11) == 24.2

    def test_returns_float(self):
        assert isinstance(basic_lift(10), float)

    def test_st_20(self):
        assert basic_lift(20) == 80.0

    def test_large_st_no_cap(self):
        # ST 30 -> BL 180; no premature int cast
        assert basic_lift(30) == 180.0

    def test_st_1_minimum(self):
        # 1*1/5 = 0.2; smallest valid ST
        assert basic_lift(1) == 0.2


class TestOneHandedLift:
    def test_st_10(self):
        # 2*BL = 40 lb (B353)
        assert one_handed_lift(10) == 40.0

    def test_equals_twice_bl(self):
        for st in (1, 5, 11, 20, 30):
            assert one_handed_lift(st) == 2 * basic_lift(st)


class TestTwoHandedLift:
    def test_st_10(self):
        # 8*BL = 160 lb (B353)
        assert two_handed_lift(10) == 160.0

    def test_st_11_fractional(self):
        # 8*24.2 = 193.6; fractional BL flows through
        assert two_handed_lift(11) == 193.6

    def test_equals_eight_bl(self):
        for st in (1, 5, 11, 20, 30):
            assert two_handed_lift(st) == 8 * basic_lift(st)


class TestShove:
    def test_standing_st_10(self):
        # 12*BL = 240 lb standing shove
        assert shove(10) == 240.0

    def test_running_start_st_10(self):
        # running start doubles
        assert shove(10, running_start=True) == 480.0

    def test_running_is_exactly_double(self):
        for st in (1, 5, 11, 20, 30):
            assert shove(st, running_start=True) == 2 * shove(st)

    def test_running_start_is_keyword_only(self):
        with pytest.raises(TypeError):
            shove(10, True)  # type: ignore[misc]


class TestCarryOnBack:
    def test_st_10(self):
        # 15*BL = 300 lb
        assert carry_on_back(10) == 300.0

    def test_equals_fifteen_bl(self):
        for st in (1, 5, 11, 20, 30):
            assert carry_on_back(st) == 15 * basic_lift(st)


class TestDrag:
    def test_st_10(self):
        # 15*BL = 300 lb drag ceiling
        assert drag(10) == 300.0

    def test_equals_carry_on_back(self):
        # both are 15*BL by the rules — intentional, not a copy-paste error
        for st in (1, 5, 11, 20, 30):
            assert drag(st) == carry_on_back(st)


class TestShiftSlightly:
    def test_st_10(self):
        # 50*BL = 1000 lb; the 50x coefficient cross-checks at ST 20 -> 4000, ST 30 -> 9000
        assert shift_slightly(10) == 1000.0

    def test_st_30_cross_check(self):
        # ST 30 -> BL 180; 50*180 = 9000
        assert shift_slightly(30) == 9000.0

    def test_equals_fifty_bl(self):
        for st in (1, 5, 11, 20, 30):
            assert shift_slightly(st) == 50 * basic_lift(st)


class TestLiftingCapacities:
    def test_st_20_full_round_trip(self):
        # ST 20 -> BL 80; every coefficient at once
        result = lifting_capacities(20)
        assert result == LiftCapacities(
            st=20,
            basic_lift=80.0,
            one_handed_lift=160.0,
            two_handed_lift=640.0,
            shove=960.0,
            shove_running=1920.0,
            carry_on_back=1200.0,
            drag=1200.0,
            shift_slightly=4000.0,
            one_handed_lift_seconds=2,
            two_handed_lift_seconds=4,
        )

    def test_st_10_aggregator_matches_individuals(self):
        result = lifting_capacities(10)
        assert result.st == 10
        assert result.basic_lift == basic_lift(10)
        assert result.one_handed_lift == one_handed_lift(10)
        assert result.two_handed_lift == two_handed_lift(10)
        assert result.shove == shove(10)
        assert result.shove_running == shove(10, running_start=True)
        assert result.carry_on_back == carry_on_back(10)
        assert result.drag == drag(10)
        assert result.shift_slightly == shift_slightly(10)

    def test_action_time_constants(self):
        result = lifting_capacities(10)
        assert result.one_handed_lift_seconds == 2
        assert result.two_handed_lift_seconds == 4

    def test_is_frozen(self):
        result = lifting_capacities(10)
        with pytest.raises((AttributeError, Exception)):
            result.basic_lift = 999.0  # type: ignore[misc]

    def test_fractional_st_11(self):
        result = lifting_capacities(11)
        assert result.basic_lift == 24.2
        assert result.two_handed_lift == 193.6


class TestEdgeCases:
    def test_st_zero_raises_value_error(self):
        # non-positive ST: guard fires at the base function
        with pytest.raises(ValueError):
            basic_lift(0)

    def test_negative_st_raises_value_error(self):
        with pytest.raises(ValueError):
            basic_lift(-5)

    def test_derived_functions_inherit_guard(self):
        # derived capacities inherit the guard via basic_lift
        for fn in (
            one_handed_lift,
            two_handed_lift,
            shove,
            carry_on_back,
            drag,
            shift_slightly,
            lifting_capacities,
        ):
            with pytest.raises(ValueError):
                fn(0)

    def test_float_st_raises_type_error(self):
        # reject float rather than truncate
        with pytest.raises(TypeError):
            basic_lift(10.5)  # type: ignore[arg-type]

    def test_bool_st_raises_type_error(self):
        # bool is an int subclass; reject explicitly
        with pytest.raises(TypeError):
            basic_lift(True)  # type: ignore[arg-type]
