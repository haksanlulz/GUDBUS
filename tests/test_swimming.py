"""swimming movement & fatigue (B354)"""

import pytest
from gurps_bot.mechanics.swimming import (
    Build,
    Encumbrance,
    SwimResult,
    effective_water_move,
    swim_distance,
    swim_entry_target,
    swim_fatigue_schedule,
    swim_fatigue_target,
    swim_report,
    water_move,
)


class TestWaterMove:
    def test_baseline_divisor(self):
        # 10 // 5 = 2; baseline land-dweller divisor B354
        assert water_move(10) == 2

    def test_min_one_floor(self):
        # 3 // 5 = 0 but min-1 floor forces 1
        assert water_move(3) == 1

    def test_floor_applies_for_basic_move_0_through_4(self):
        for bm in range(0, 5):
            assert water_move(bm) == 1, f"basic_move={bm} should floor to 1"

    def test_basic_move_5_is_one(self):
        assert water_move(5) == 1  # 5 // 5 = 1

    def test_basic_move_25_is_five(self):
        assert water_move(25) == 5

    def test_aquatic_uses_full_basic_move(self):
        # Amphibious/Aquatic bypass the /5 divisor and the floor
        assert water_move(12, aquatic=True) == 12

    def test_aquatic_does_not_floor(self):
        # aquatic returns basic_move unchanged, even when small
        assert water_move(2, aquatic=True) == 2
        assert water_move(0, aquatic=True) == 0

    def test_returns_int(self):
        assert isinstance(water_move(10), int)
        assert isinstance(water_move(12, aquatic=True), int)

    def test_negative_basic_move_raises(self):
        with pytest.raises(ValueError):
            water_move(-1)

    def test_negative_basic_move_raises_even_aquatic(self):
        with pytest.raises(ValueError):
            water_move(-3, aquatic=True)


class TestEffectiveWaterMove:
    def test_no_encumbrance_equals_base(self):
        assert effective_water_move(10) == 2.0

    def test_heavy_encumbrance_book_example(self):
        # water_move(5)=1; 1*0.4(Heavy)=0.4 — the rulebook worked example
        assert effective_water_move(5, encumbrance=Encumbrance.HEAVY) == pytest.approx(0.4)

    def test_all_encumbrance_factors(self):
        # base water_move(10) = 2; factors 1.0/0.8/0.6/0.4/0.2
        assert effective_water_move(10, encumbrance=Encumbrance.NONE) == pytest.approx(2.0)
        assert effective_water_move(10, encumbrance=Encumbrance.LIGHT) == pytest.approx(1.6)
        assert effective_water_move(10, encumbrance=Encumbrance.MEDIUM) == pytest.approx(1.2)
        assert effective_water_move(10, encumbrance=Encumbrance.HEAVY) == pytest.approx(0.8)
        assert effective_water_move(10, encumbrance=Encumbrance.EXTRA_HEAVY) == pytest.approx(0.4)

    def test_fatigued_halves(self):
        # 2 yd/s halved by sub-1/3-FP penalty (B426) = 1.0
        assert effective_water_move(10, fatigued=True) == pytest.approx(1.0)

    def test_fatigue_and_heavy_stack_multiplicatively(self):
        # water_move(10)=2; *0.4 (Heavy) *0.5 (fatigued) = 0.4
        result = effective_water_move(
            10, encumbrance=Encumbrance.HEAVY, fatigued=True
        )
        assert result == pytest.approx(0.4)

    def test_no_clamp_below_one_post_encumbrance(self):
        # base floored to 1, but encumbrance may push effective below 1
        assert effective_water_move(5, encumbrance=Encumbrance.HEAVY) < 1.0

    def test_aquatic_with_encumbrance(self):
        # aquatic full move 12, Medium 0.6 => 7.2
        assert effective_water_move(
            12, encumbrance=Encumbrance.MEDIUM, aquatic=True
        ) == pytest.approx(7.2)

    def test_returns_float(self):
        assert isinstance(effective_water_move(10), float)

    def test_negative_basic_move_raises(self):
        with pytest.raises(ValueError):
            effective_water_move(-1)


class TestSwimDistance:
    def test_heavy_ten_second_scale(self):
        # 0.4 yd/s * 10s = 4 yd; canonical B354 10-second-scale example
        assert swim_distance(5, 10, encumbrance=Encumbrance.HEAVY) == pytest.approx(4.0)

    def test_one_minute_no_encumbrance(self):
        # water_move(10)=2 yd/s * 60s = 120 yd
        assert swim_distance(10, 60) == pytest.approx(120.0)

    def test_zero_seconds(self):
        assert swim_distance(10, 0) == pytest.approx(0.0)

    def test_fractional_duration(self):
        # 2 yd/s * 2.5s = 5.0 yd; fractional durations are valid
        assert swim_distance(10, 2.5) == pytest.approx(5.0)

    def test_fatigued_distance(self):
        # effective 1.0 yd/s * 30s = 30 yd
        assert swim_distance(10, 30, fatigued=True) == pytest.approx(30.0)

    def test_aquatic_distance(self):
        # aquatic move 12 yd/s * 10s = 120 yd
        assert swim_distance(12, 10, aquatic=True) == pytest.approx(120.0)

    def test_returns_float(self):
        assert isinstance(swim_distance(10, 10), float)

    def test_negative_seconds_raises(self):
        with pytest.raises(ValueError):
            swim_distance(10, -1)

    def test_negative_basic_move_raises(self):
        with pytest.raises(ValueError):
            swim_distance(-1, 10)


class TestSwimFatigueSchedule:
    def test_top_speed_three_intervals(self):
        # 180s / 60s = 3 top-speed fatigue rolls owed
        assert swim_fatigue_schedule(180, top_speed=True) == 3

    def test_top_speed_under_one_interval(self):
        # 59s < 60s -> no roll yet (floor)
        assert swim_fatigue_schedule(59, top_speed=True) == 0

    def test_exactly_one_interval(self):
        # seconds == interval -> exactly 1 roll
        assert swim_fatigue_schedule(60, top_speed=True) == 1

    def test_slow_swimming_interval(self):
        # slow swimming uses 1800s (30-min) interval; 3600/1800 = 2
        assert swim_fatigue_schedule(3600, top_speed=False) == 2

    def test_slow_under_one_interval(self):
        # 1799s < 1800s -> 0 rolls
        assert swim_fatigue_schedule(1799, top_speed=False) == 0

    def test_partial_trailing_interval_owes_no_roll(self):
        # 125s top speed -> 2 full intervals (120s), trailing 5s owes nothing
        assert swim_fatigue_schedule(125, top_speed=True) == 2

    def test_zero_seconds(self):
        assert swim_fatigue_schedule(0, top_speed=True) == 0

    def test_returns_int(self):
        assert isinstance(swim_fatigue_schedule(180), int)

    def test_negative_seconds_raises(self):
        with pytest.raises(ValueError):
            swim_fatigue_schedule(-1)


class TestSwimFatigueTarget:
    def test_higher_skill_wins(self):
        # higher of HT(11) or Swimming(14) = 14
        assert swim_fatigue_target(11, 14) == 14

    def test_skill_below_ht_picks_ht(self):
        # skill below HT -> 'higher of' still picks HT(13)
        assert swim_fatigue_target(13, 10) == 13

    def test_none_skill_falls_back_to_ht(self):
        assert swim_fatigue_target(12, None) == 12

    def test_equal_values(self):
        assert swim_fatigue_target(12, 12) == 12

    def test_returns_int(self):
        assert isinstance(swim_fatigue_target(11, 14), int)


class TestSwimEntryTarget:
    def test_intentional_heavy_default_skill(self):
        # base HT-4 = 8; +3 intentional; -2*3 Heavy = -6; 8+3-6 = 5
        assert (
            swim_entry_target(12, None, intentional=True, encumbrance=Encumbrance.HEAVY)
            == 5
        )

    def test_explicit_skill_with_fat_build(self):
        # skill 12 overrides HT-4 default; +0 enc, +0 intentional, +3 Fat -> 15
        assert swim_entry_target(10, 12, build=Build.FAT) == 15

    def test_default_no_modifiers(self):
        # base HT-4 = 6; no modifiers
        assert swim_entry_target(10) == 6

    def test_intentional_bonus_only(self):
        # base HT-4 = 6; +3 intentional = 9
        assert swim_entry_target(10, intentional=True) == 9

    def test_encumbrance_penalty_scaling(self):
        # base HT-4 = 6; LIGHT(level 1) -> -2 -> 4
        assert swim_entry_target(10, encumbrance=Encumbrance.LIGHT) == 4
        # MEDIUM(level 2) -> -4 -> 2
        assert swim_entry_target(10, encumbrance=Encumbrance.MEDIUM) == 2
        # EXTRA_HEAVY(level 4) -> -8 -> -2
        assert swim_entry_target(10, encumbrance=Encumbrance.EXTRA_HEAVY) == -2

    def test_build_bonuses(self):
        # base HT-4 = 6; Overweight +1 / Fat +3 / Very Fat +5
        assert swim_entry_target(10, build=Build.NORMAL) == 6
        assert swim_entry_target(10, build=Build.OVERWEIGHT) == 7
        assert swim_entry_target(10, build=Build.FAT) == 9
        assert swim_entry_target(10, build=Build.VERY_FAT) == 11

    def test_skill_overrides_ht_minus_4(self):
        # explicit skill is the base, not HT-4
        assert swim_entry_target(10, 8) == 8

    def test_all_modifiers_combined(self):
        # skill 14 base; +3 intentional; -2*2 Medium = -4; +5 Very Fat -> 18
        assert (
            swim_entry_target(
                10,
                14,
                intentional=True,
                encumbrance=Encumbrance.MEDIUM,
                build=Build.VERY_FAT,
            )
            == 18
        )

    def test_returns_int(self):
        assert isinstance(swim_entry_target(10), int)


class TestEncumbrance:
    def test_factor_values(self):
        assert Encumbrance.NONE.factor == pytest.approx(1.0)
        assert Encumbrance.LIGHT.factor == pytest.approx(0.8)
        assert Encumbrance.MEDIUM.factor == pytest.approx(0.6)
        assert Encumbrance.HEAVY.factor == pytest.approx(0.4)
        assert Encumbrance.EXTRA_HEAVY.factor == pytest.approx(0.2)

    def test_level_aliases_int_value(self):
        assert Encumbrance.NONE.level == 0
        assert Encumbrance.LIGHT.level == 1
        assert Encumbrance.MEDIUM.level == 2
        assert Encumbrance.HEAVY.level == 3
        assert Encumbrance.EXTRA_HEAVY.level == 4

    def test_is_int_enum(self):
        assert Encumbrance.HEAVY == 3
        assert int(Encumbrance.EXTRA_HEAVY) == 4


class TestBuild:
    def test_swim_bonus_values(self):
        assert Build.NORMAL.swim_bonus == 0
        assert Build.OVERWEIGHT.swim_bonus == 1
        assert Build.FAT.swim_bonus == 3
        assert Build.VERY_FAT.swim_bonus == 5


class TestSwimReport:
    def test_aggregates_fields(self):
        # basic_move 10, 60s, HT 11, Swimming 14, top speed, no encumbrance
        r = swim_report(10, 60, 11, 14)
        assert isinstance(r, SwimResult)
        assert r.basic_move == 10
        assert r.base_water_move == 2
        assert r.effective_water_move == pytest.approx(2.0)
        assert r.duration_seconds == pytest.approx(60.0)
        assert r.distance_yards == pytest.approx(120.0)
        assert r.fatigue_interval_seconds == 60
        assert r.fatigue_rolls == 1  # 60s / 60s
        assert r.fatigue_target == 14  # max(11, 14)

    def test_heavy_encumbrance_report(self):
        # basic_move 5 Heavy: base 1, effective 0.4, 10s -> 4 yd
        r = swim_report(5, 10, 12, encumbrance=Encumbrance.HEAVY)
        assert r.base_water_move == 1
        assert r.effective_water_move == pytest.approx(0.4)
        assert r.distance_yards == pytest.approx(4.0)
        assert r.fatigue_target == 12  # no skill -> HT
        assert r.fatigue_rolls == 0  # 10s < 60s

    def test_slow_speed_interval(self):
        r = swim_report(10, 3600, 11, top_speed=False)
        assert r.fatigue_interval_seconds == 1800
        assert r.fatigue_rolls == 2  # 3600 / 1800

    def test_fatigued_report(self):
        r = swim_report(10, 60, 11, fatigued=True)
        assert r.effective_water_move == pytest.approx(1.0)  # 2 * 0.5
        assert r.distance_yards == pytest.approx(60.0)

    def test_aquatic_report(self):
        r = swim_report(12, 10, 11, aquatic=True)
        assert r.base_water_move == 12
        assert r.effective_water_move == pytest.approx(12.0)
        assert r.distance_yards == pytest.approx(120.0)

    def test_frozen(self):
        r = swim_report(10, 60, 11, 14)
        with pytest.raises((AttributeError, TypeError)):
            r.basic_move = 99  # type: ignore[misc]

    def test_negative_inputs_raise(self):
        with pytest.raises(ValueError):
            swim_report(-1, 60, 11)
        with pytest.raises(ValueError):
            swim_report(10, -1, 11)
