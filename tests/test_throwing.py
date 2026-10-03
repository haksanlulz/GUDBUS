"""throwing distance + damage (B355) and thrust-by-ST (B16); formulas only, no SJ Games text"""

import pytest
from gurps_bot.mechanics.dice import DiceSpec
from gurps_bot.mechanics.throwing import (
    ThrowEstimate,
    ThrowResult,
    throw,
    throw_damage,
    throw_distance,
    thrust_for_st,
)


class TestThrustForSt:
    """B16 Thrust column anchors"""

    def test_st_10_baseline(self):
        # canonical ST 10 baseline: 1d-2
        assert thrust_for_st(10) == DiceSpec(1, 6, -2)

    def test_st_28(self):
        # second book example: ST 28 thrust = 3d-1
        assert thrust_for_st(28) == DiceSpec(3, 6, -1)

    def test_st_40_upper_bound(self):
        # upper supported bound: 4d+1
        assert thrust_for_st(40) == DiceSpec(4, 6, 1)

    def test_st_12(self):
        assert thrust_for_st(12) == DiceSpec(1, 6, -1)

    def test_st_20(self):
        assert thrust_for_st(20) == DiceSpec(2, 6, -1)

    @pytest.mark.parametrize(
        "st,expected",
        [
            (1, DiceSpec(1, 6, -6)),
            (2, DiceSpec(1, 6, -6)),
            (3, DiceSpec(1, 6, -5)),
            (5, DiceSpec(1, 6, -4)),
            (7, DiceSpec(1, 6, -3)),
            (9, DiceSpec(1, 6, -2)),
            (11, DiceSpec(1, 6, -1)),
            (13, DiceSpec(1, 6, 0)),
            (15, DiceSpec(1, 6, 1)),
            (17, DiceSpec(1, 6, 2)),
            (19, DiceSpec(2, 6, -1)),
            (21, DiceSpec(2, 6, 0)),
            (23, DiceSpec(2, 6, 1)),
            (25, DiceSpec(2, 6, 2)),
            (27, DiceSpec(3, 6, -1)),
            (29, DiceSpec(3, 6, 0)),
            (31, DiceSpec(3, 6, 1)),
            (33, DiceSpec(3, 6, 2)),
            (35, DiceSpec(4, 6, -1)),
            (37, DiceSpec(4, 6, 0)),
            (39, DiceSpec(4, 6, 1)),
        ],
    )
    def test_table_rows(self, st, expected):
        assert thrust_for_st(st) == expected

    def test_full_table_continuous(self):
        for st in range(1, 41):
            spec = thrust_for_st(st)
            assert spec.sides == 6
            assert spec.count >= 1

    def test_st_below_one_raises(self):
        with pytest.raises(ValueError):
            thrust_for_st(0)
        with pytest.raises(ValueError):
            thrust_for_st(-3)

    def test_st_above_forty_raises(self):
        with pytest.raises(ValueError):
            thrust_for_st(41)
        with pytest.raises(ValueError):
            thrust_for_st(100)


class TestThrowDistance:
    def test_book_example_st12_120lb(self):
        # exact worked example on B355
        result = throw_distance(st=12, weight_lbs=120)
        assert result.basic_lift == pytest.approx(28.8)
        assert result.weight_ratio == pytest.approx(120 / 28.8)  # ~4.17
        assert result.distance_modifier == 0.12  # rounds up to 5.0 row
        assert result.distance_yards == 1.44
        assert result.throwable is True
        assert result.one_handed is False  # 120 > 2*28.8 = 57.6

    def test_ratio_exact_table_key(self):
        # ST 10, weight equal to BL -> ratio 1.0 exactly -> modifier 0.6
        # BL = 20, weight 20 -> ratio 1.0 (a table key, no rounding up)
        result = throw_distance(st=10, weight_lbs=20)
        assert result.basic_lift == pytest.approx(20.0)
        assert result.weight_ratio == pytest.approx(1.0)
        assert result.distance_modifier == 0.6
        assert result.distance_yards == round(10 * 0.6, 2)  # 6.0

    def test_ratio_between_rounds_up(self):
        # ratio between two keys must round UP to the higher key
        # BL=20 (st 10), weight 13 -> ratio 0.65 -> between 0.50 and 0.75 -> use 0.75 row (0.7)
        result = throw_distance(st=10, weight_lbs=13)
        assert result.weight_ratio == pytest.approx(0.65)
        assert result.distance_modifier == 0.7
        assert result.distance_yards == 7.0

    def test_very_small_ratio_clamps_to_smallest_row(self):
        # ratio < 0.05 clamps to the 0.05 row (max modifier 3.5)
        # BL=20, weight 0.5 -> ratio 0.025 < 0.05 -> use 0.05 row
        result = throw_distance(st=10, weight_lbs=0.5)
        assert result.distance_modifier == 3.5
        assert result.distance_yards == 35.0
        assert result.throwable is True

    def test_zero_weight_uses_smallest_row(self):
        # weight 0 -> ratio 0 -> smallest 0.05 row (modifier 3.5)
        result = throw_distance(st=10, weight_lbs=0)
        assert result.weight_ratio == 0.0
        assert result.distance_modifier == 3.5
        assert result.distance_yards == 35.0
        assert result.throwable is True
        assert result.one_handed is True  # 0 <= 2*BL

    def test_one_handed_flag_true(self):
        # weight within 2*BL -> one-handed
        # BL=20, 2*BL=40, weight 30 -> one_handed True
        result = throw_distance(st=10, weight_lbs=30)
        assert result.one_handed is True

    def test_one_handed_boundary_inclusive(self):
        # weight exactly 2*BL -> still one-handed (<= boundary)
        # BL=20, 2*BL=40
        result = throw_distance(st=10, weight_lbs=40)
        assert result.one_handed is True

    def test_not_throwable_over_8bl(self):
        # weight 200 > 8*BL (160) for ST 10 -> not throwable
        result = throw_distance(st=10, weight_lbs=200)
        assert result.throwable is False
        assert result.distance_yards == 0.0
        assert result.distance_modifier == 0.0

    def test_throwable_at_exactly_8bl(self):
        # weight exactly 8*BL is still throwable (<= boundary)
        # BL=20, 8*BL=160 -> ratio 8.0 (a table key) -> modifier 0.08
        result = throw_distance(st=10, weight_lbs=160)
        assert result.throwable is True
        assert result.weight_ratio == pytest.approx(8.0)
        assert result.distance_modifier == 0.08

    def test_st_zero_raises(self):
        with pytest.raises(ValueError):
            throw_distance(st=0, weight_lbs=10)

    def test_st_negative_raises(self):
        with pytest.raises(ValueError):
            throw_distance(st=-5, weight_lbs=10)

    def test_negative_weight_raises(self):
        with pytest.raises(ValueError):
            throw_distance(st=10, weight_lbs=-1)

    def test_result_is_frozen_dataclass(self):
        result = throw_distance(st=10, weight_lbs=10)
        with pytest.raises((AttributeError, Exception)):
            result.distance_yards = 99.0  # frozen


class TestThrowDamage:
    def test_book_example_st28_50lb_straight_thrust(self):
        # second B355 worked example: BL/2 band -> straight thrust 3d-1
        assert throw_damage(st=28, weight_lbs=50) == DiceSpec(3, 6, -1)

    def test_lightest_band_minus_two_per_die(self):
        # ST 12, weight 3: BL=28.8, BL/8=3.6, 3<=3.6 -> -2/die
        # base 1d-1 -> mod = -1 + (-2*1) = -3 -> 1d-3
        assert throw_damage(st=12, weight_lbs=3) == DiceSpec(1, 6, -3)

    def test_plus_one_per_die_band_scales(self):
        # ST 40, weight 200: BL=320, BL/2=160, BL=320; 200<=320 & >160 -> +1/die
        # base 4d+1 -> mod = 1 + (1*4) = 5 -> 4d+5
        assert throw_damage(st=40, weight_lbs=200) == DiceSpec(4, 6, 5)

    def test_four_bl_band_half_per_die_floor(self):
        # ST 20, weight 300: BL=80, 2*BL=160, 4*BL=320; 300<=320 & >160 -> -1/2/die floor
        # base 2d-1 -> mod = -1 - floor(2/2) = -1 - 1 = -2 -> 2d-2
        assert throw_damage(st=20, weight_lbs=300) == DiceSpec(2, 6, -2)

    def test_minus_one_per_die_band_quarter(self):
        # BL/4 band -> -1/die. ST 28, BL=156.8, BL/8=19.6, BL/4=39.2
        # weight 30 (>19.6, <=39.2) -> -1/die. base 3d-1 -> mod = -1 + (-1*3) = -4 -> 3d-4
        assert throw_damage(st=28, weight_lbs=30) == DiceSpec(3, 6, -4)

    def test_two_bl_band_straight_thrust(self):
        # 2*BL band -> straight thrust. ST 28, BL=156.8, BL=156.8, 2*BL=313.6
        # weight 200 (>156.8, <=313.6) -> straight thrust 3d-1
        assert throw_damage(st=28, weight_lbs=200) == DiceSpec(3, 6, -1)

    def test_bl_band_plus_one_per_die(self):
        # BL band (>BL/2, <=BL) -> +1/die. ST 28: BL/2=78.4, BL=156.8; weight 100 qualifies
        # base 3d-1 -> mod = -1 + (1*3) = 2 -> 3d+2
        assert throw_damage(st=28, weight_lbs=100) == DiceSpec(3, 6, 2)

    def test_eight_bl_band_minus_one_per_die(self):
        # 8*BL band (>4*BL, <=8*BL) -> -1/die. ST 20, BL=80, 4*BL=320, 8*BL=640
        # weight 500 (>320, <=640) -> -1/die. base 2d-1 -> mod = -1 + (-1*2) = -3 -> 2d-3
        assert throw_damage(st=20, weight_lbs=500) == DiceSpec(2, 6, -3)

    def test_over_8bl_raises(self):
        with pytest.raises(ValueError):
            throw_damage(st=10, weight_lbs=200)  # BL=20, 8*BL=160

    def test_zero_weight_lightest_band(self):
        # weight 0 falls in BL/8 band -> -2/die
        # ST 13, BL=33.8, base 1d (1,0) -> mod = 0 + (-2*1) = -2 -> 1d-2
        assert throw_damage(st=13, weight_lbs=0) == DiceSpec(1, 6, -2)

    def test_st_above_forty_raises(self):
        with pytest.raises(ValueError):
            throw_damage(st=41, weight_lbs=10)

    def test_returns_dicespec_sides_six(self):
        spec = throw_damage(st=15, weight_lbs=10)
        assert isinstance(spec, DiceSpec)
        assert spec.sides == 6

    def test_does_not_clamp_negative_min(self):
        # a deeply negative modifier is left as-is (min-1-injury applied elsewhere)
        # ST 1, weight 0: BL=0.2, BL/8=0.025, weight 0 <= 0.025 -> -2/die
        # base 1d-6 -> mod = -6 + (-2*1) = -8 -> 1d-8 (min would be 1-8 = -7, NOT clamped)
        spec = throw_damage(st=1, weight_lbs=0)
        assert spec == DiceSpec(1, 6, -8)


class TestThrow:
    def test_orchestrator_throwable(self):
        # combines distance + damage for the ST 28 / 50 lb book example
        est = throw(st=28, weight_lbs=50)
        assert isinstance(est, ThrowEstimate)
        assert est.result.throwable is True
        assert est.damage == DiceSpec(3, 6, -1)
        assert est.damage_type == "cr"

    def test_orchestrator_distance_matches_primitive(self):
        est = throw(st=12, weight_lbs=120)
        direct = throw_distance(st=12, weight_lbs=120)
        assert est.result == direct
        assert est.result.distance_yards == 1.44

    def test_orchestrator_not_throwable_no_damage(self):
        # weight > 8*BL -> throwable False, damage None (no ValueError leak)
        est = throw(st=10, weight_lbs=200)
        assert est.result.throwable is False
        assert est.damage is None
        assert est.damage_type == "cr"

    def test_orchestrator_custom_damage_type(self):
        est = throw(st=20, weight_lbs=20, damage_type="imp")
        assert est.damage_type == "imp"
        assert est.damage is not None

    def test_orchestrator_st_zero_raises(self):
        with pytest.raises(ValueError):
            throw(st=0, weight_lbs=10)


class TestThrowDistanceStContract:
    """regression: throw_distance must reject ST>40 like throw_damage, or throw() crashes halfway"""

    def test_throw_distance_rejects_st_above_40(self):
        with pytest.raises(ValueError, match="40"):
            throw_distance(50, 10)
