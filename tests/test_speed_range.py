"""Tests for GURPS Size & Speed/Range calculator (B550, B19).

Covers the build-spec test_cases plus edge cases:
  - Speed/Range step-table lookups (range_modifier / speed_modifier alias).
  - Size Modifier step-table lookups.
  - Combined ranged-to-hit modifier bundle.
  - Round-UP (inclusive >=) boundary behavior, float-equality edges,
    programmatic table extension, and input validation.
"""

import pytest

from gurps_bot.mechanics.speed_range import (
    RangedHitModifier,
    range_modifier,
    ranged_hit_modifier,
    size_modifier,
    speed_modifier,
    speed_range_penalty,
)


class TestSpeedRangePenalty:
    """Core Speed/Range table lookup shared by range and speed."""

    # --- spec test_cases ---
    def test_anchor_2yd_is_zero(self):
        assert speed_range_penalty(2) == 0

    def test_exact_threshold_5_rounds_to_own_row(self):
        # Inclusive >= : D=5 hits the <=5 row (-2), NOT the next row.
        assert speed_range_penalty(5) == -2

    def test_six_rounds_up_to_seven_row(self):
        assert speed_range_penalty(6) == -3

    def test_point_blank_zero_clamps(self):
        assert speed_range_penalty(0) == 0

    def test_last_listed_row_700(self):
        assert speed_range_penalty(700) == -15

    def test_extension_past_listed_rows_1000(self):
        assert speed_range_penalty(1000) == -16

    def test_just_over_100_rounds_to_150(self):
        assert speed_range_penalty(101) == -11

    def test_negative_distance_raises(self):
        with pytest.raises(ValueError):
            speed_range_penalty(-1)

    # --- additional boundary / table coverage ---
    def test_below_anchor_clamps_zero(self):
        assert speed_range_penalty(0.5) == 0
        assert speed_range_penalty(1) == 0
        assert speed_range_penalty(1.5) == 0

    def test_just_over_two_rounds_up(self):
        # Above the anchor but below the next threshold -> rounds up to 3yd (-1).
        # (Uses 2.5, comfortably above the 1/1000-yd fixed-point resolution so it
        # does not collide with the epsilon tolerance that keeps 1.9999999 at 0.)
        assert speed_range_penalty(2.5) == -1

    def test_epsilon_below_anchor_stays_zero(self):
        # Unit-conversion drift just under 2.0 must NOT drop into the -1 row.
        assert speed_range_penalty(1.9999999) == 0

    def test_three_exact_is_minus_one(self):
        assert speed_range_penalty(3) == -1

    def test_seven_float_hits_its_row(self):
        # Float-equality guard: 7.0 must hit the <=7 row (-3), not 10yd row.
        assert speed_range_penalty(7.0) == -3

    def test_full_explicit_row_span(self):
        # Every explicitly-spec'd row, modifiers 0..-21.
        expected = {
            2: 0, 3: -1, 5: -2, 7: -3, 10: -4, 15: -5, 20: -6, 30: -7,
            50: -8, 70: -9, 100: -10, 150: -11, 200: -12, 300: -13,
            500: -14, 700: -15, 1000: -16, 1500: -17, 2000: -18,
            3000: -19, 5000: -20, 7000: -21,
        }
        for dist, mod in expected.items():
            assert speed_range_penalty(dist) == mod, f"D={dist}"

    def test_round_up_between_rows(self):
        assert speed_range_penalty(4) == -2     # ->5 row
        assert speed_range_penalty(8) == -4     # ->10 row
        assert speed_range_penalty(11) == -5    # ->15 row
        assert speed_range_penalty(201) == -13  # ->300 row

    def test_very_large_distance_resolves(self):
        # No hardcoded ceiling: a huge distance must resolve to an int.
        result = speed_range_penalty(1_000_000)
        assert isinstance(result, int)
        assert result < -21

    def test_zero_point_blank_no_error(self):
        # explicit: 0 returns 0, never raises
        assert speed_range_penalty(0.0) == 0

    def test_monotonic_non_increasing(self):
        prev = 1
        for dist in [0, 1, 2, 3, 5, 7, 10, 50, 100, 700, 1000, 5000, 50000]:
            cur = speed_range_penalty(dist)
            assert cur <= prev
            prev = cur


class TestRangeModifierAlias:
    def test_delegates_to_core(self):
        assert range_modifier(10) == speed_range_penalty(10)
        assert range_modifier(5) == -2
        assert range_modifier(0) == 0

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            range_modifier(-3)


class TestSpeedModifierAlias:
    def test_delegates_to_core(self):
        assert speed_modifier(10) == speed_range_penalty(10)
        assert speed_modifier(5) == -2
        assert speed_modifier(0) == 0  # stationary

    def test_stationary_is_zero(self):
        assert speed_modifier(0.0) == 0

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            speed_modifier(-1)


class TestSizeModifier:
    """Size Modifier table lookup — signed, anchor 0 at ~2yd."""

    # --- spec test_cases ---
    def test_anchor_2yd_is_zero(self):
        assert size_modifier(2) == 0

    def test_one_yard_is_minus_two(self):
        assert size_modifier(1) == -2

    def test_smallest_listed_small_row(self):
        assert size_modifier(0.05) == -10

    def test_small_side_round_up(self):
        # 0.4 rounds UP to the 0.5yd row -> -4
        assert size_modifier(0.4) == -4

    def test_first_positive_row(self):
        assert size_modifier(3) == 1

    def test_largest_listed_row(self):
        assert size_modifier(150) == 11

    def test_large_exact_threshold_own_row(self):
        # 10 resolves to its OWN row (+4), not +5.
        assert size_modifier(10) == 4

    def test_zero_size_raises(self):
        with pytest.raises(ValueError):
            size_modifier(0)

    # --- additional coverage ---
    def test_negative_size_raises(self):
        with pytest.raises(ValueError):
            size_modifier(-2)

    def test_full_small_side_span(self):
        expected = {
            0.05: -10, 0.07: -9, 0.1: -8, 0.15: -7, 0.2: -6, 0.3: -5,
            0.5: -4, 0.7: -3, 1: -2, 1.5: -1, 2: 0,
        }
        for length, sm in expected.items():
            assert size_modifier(length) == sm, f"L={length}"

    def test_full_large_side_span(self):
        expected = {
            3: 1, 5: 2, 7: 3, 10: 4, 15: 5, 20: 6, 30: 7, 50: 8,
            70: 9, 100: 10, 150: 11,
        }
        for length, sm in expected.items():
            assert size_modifier(length) == sm, f"L={length}"

    def test_large_extension_above_listed(self):
        # Programmatic upward extension by the [2,3,5,7,10,15] cycle.
        assert size_modifier(200) == 12
        assert size_modifier(300) == 13
        assert size_modifier(500) == 14
        assert size_modifier(700) == 15
        assert size_modifier(1000) == 16

    def test_below_smallest_clamps_at_minus_ten(self):
        # Documented choice: clamp at -10 below the smallest listed row.
        assert size_modifier(0.01) == -10
        assert size_modifier(0.001) == -10

    def test_feet_to_yards_anchor_no_drift(self):
        # 6 ft = 2 yd exactly -> SM 0; division artifacts must not drop a row.
        assert size_modifier(6 / 3) == 0       # 2.0
        assert size_modifier(3 / 3) == -2      # 1.0

    def test_round_up_large_between_rows(self):
        assert size_modifier(4) == 2    # ->5 row
        assert size_modifier(8) == 4    # ->10 row
        assert size_modifier(101) == 11  # ->150 row

    def test_just_over_two_rounds_up(self):
        # Above the anchor but below the next row -> rounds up to 3yd (+1).
        assert size_modifier(2.5) == 1

    def test_epsilon_below_anchor_stays_zero(self):
        # 1.9999999 (e.g. 6ft/3 drift) must hit the 2yd anchor (SM 0), not -1.
        assert size_modifier(1.9999999) == 0

    def test_monotonic_non_decreasing(self):
        prev = -99
        for length in [0.05, 0.1, 0.5, 1, 2, 3, 10, 100, 1000]:
            cur = size_modifier(length)
            assert cur >= prev
            prev = cur


class TestB550PrintedExamples:
    """The four worked examples printed on B550 — the authoritative oracle.

    B550: "for fast targets ... add speed in yards/second to range BEFORE
    looking it up in the Linear Measurement column." One combined lookup, not
    a range lookup plus a speed lookup.
    """

    def test_man_at_8_yards_is_minus_4(self):
        # "A man 8 yards away is -4 to hit." (8 rounds up to the 10yd row.)
        assert speed_range_penalty(8) == -4

    def test_motorcycle_40yd_at_30yps_is_minus_9(self):
        # "a motorcycle rider 40 yards away, traveling at 30 yards/second ...
        #  has a speed/range of 40 + 30 = 70 yards, which gives -9 to hit."
        r = ranged_hit_modifier(
            distance_yards=40,
            target_longest_dimension_yards=2,   # SM 0, isolates speed/range
            target_speed_yards_per_second=30,
        )
        assert r.speed_range_modifier == -9
        # separate lookups would give range(40)=-8 plus speed(30)=-7 = -15
        assert r.speed_range_modifier != range_modifier(40) + speed_modifier(30)

    def test_missile_5yd_at_1000yps_is_minus_17(self):
        # "a missile passing within 5 yards while moving 1,000 yards/second has
        #  a speed/range of 5 + 1,000 = 1,005 yards, for -17 to hit."
        assert speed_range_penalty(5 + 1000) == -17

    def test_erin_and_the_dragon_nets_minus_6(self):
        # "It is 40 yards away and flying at Move 15: 40 + 15 = 55 yards. Erin
        #  rounds up to 70 yards, for a speed/range modifier of -9. The dragon
        #  is 6 yards long, which rounds up to 7 yards, for SM +3. Erin's final
        #  modifier to hit is -6."
        r = ranged_hit_modifier(
            distance_yards=40,
            target_longest_dimension_yards=6,
            target_speed_yards_per_second=15,
        )
        assert r.speed_range_modifier == -9
        assert r.size_modifier == 3
        assert r.total == -6


class TestRangedHitModifier:
    """Combined helper: total = speed/range (one lookup) + size."""

    # --- spec test_cases ---
    def test_stationary_man_at_10yd(self):
        r = ranged_hit_modifier(
            distance_yards=10,
            target_longest_dimension_yards=2,
            target_speed_yards_per_second=0,
        )
        assert r.total == -4  # range -4 + size 0 + speed 0

    def test_speed_and_range_combine_before_lookup(self):
        r = ranged_hit_modifier(
            distance_yards=10,
            target_longest_dimension_yards=2,
            target_speed_yards_per_second=10,
        )
        assert r.speed_range_modifier == speed_range_penalty(20)
        assert r.speed_range_modifier != range_modifier(10) + speed_modifier(10)
        assert r.total == speed_range_penalty(20) + r.size_modifier

    def test_all_components(self):
        r = ranged_hit_modifier(
            distance_yards=100,
            target_longest_dimension_yards=10,
            target_speed_yards_per_second=5,
        )
        # 100 + 5 = 105 -> rounds up to the 150yd row (-11); size +4 -> -7
        assert r.total == speed_range_penalty(105) + size_modifier(10)
        assert r.total == -7

    def test_default_speed_arg(self):
        r = ranged_hit_modifier(
            distance_yards=2,
            target_longest_dimension_yards=1,
        )
        # range 0 + size -2 + speed 0
        assert r.total == -2

    # --- structure / field coverage ---
    def test_returns_dataclass_with_components(self):
        r = ranged_hit_modifier(
            distance_yards=100,
            target_longest_dimension_yards=10,
            target_speed_yards_per_second=5,
        )
        assert isinstance(r, RangedHitModifier)
        assert r.size_modifier == 4
        assert r.total == r.speed_range_modifier + r.size_modifier
        # The breakdown fields are informational and must NOT sum to the total.
        assert r.range_modifier == -10
        assert r.speed_modifier == -2

    def test_records_inputs(self):
        r = ranged_hit_modifier(
            distance_yards=50,
            target_longest_dimension_yards=3,
            target_speed_yards_per_second=7,
        )
        assert r.distance_yards == 50
        assert r.target_size_yards == 3
        assert r.target_speed_yards_per_second == 7

    def test_is_frozen(self):
        r = ranged_hit_modifier(
            distance_yards=10, target_longest_dimension_yards=2
        )
        with pytest.raises((AttributeError, Exception)):
            r.total = 0  # type: ignore[misc]

    def test_does_not_clamp_strongly_negative(self):
        # Long range + tiny + fast target -> deeply negative, must NOT clamp.
        r = ranged_hit_modifier(
            distance_yards=1000,
            target_longest_dimension_yards=0.05,   # SM -10
            target_speed_yards_per_second=1000,    # 1000 + 1000 = 2000yd
        )
        assert r.total == speed_range_penalty(2000) + size_modifier(0.05)
        assert r.total < -20

    def test_propagates_distance_validation(self):
        with pytest.raises(ValueError):
            ranged_hit_modifier(
                distance_yards=-1, target_longest_dimension_yards=2
            )

    def test_propagates_size_validation(self):
        with pytest.raises(ValueError):
            ranged_hit_modifier(
                distance_yards=10, target_longest_dimension_yards=0
            )

    def test_propagates_speed_validation(self):
        with pytest.raises(ValueError):
            ranged_hit_modifier(
                distance_yards=10,
                target_longest_dimension_yards=2,
                target_speed_yards_per_second=-5,
            )

    def test_size_helps_sign(self):
        # Bigger target -> positive SM -> raises (helps) the total.
        small = ranged_hit_modifier(
            distance_yards=50, target_longest_dimension_yards=2
        )
        big = ranged_hit_modifier(
            distance_yards=50, target_longest_dimension_yards=50
        )
        assert big.total > small.total
