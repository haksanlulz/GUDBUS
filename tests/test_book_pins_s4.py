"""Book-pin regressions from the S4 ledger burn-down (2026-07-27).

Each test quotes the printed Basic Set clause it pins. These are the four
defects the burn-down found; every other checked module reproduced the book.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics.encumbrance import full_dodge
from gurps_bot.mechanics.knockback import calc_knockback
from gurps_bot.mechanics.posture import LYING_DOWN_NAME, POSTURES, posture


class TestPostureProneHasNoMeleeBonus:
    """B551's Target column is RANGED ONLY, by its own printed legend:

        "Target: The modifier to hit your torso, groin, or legs with a ranged
         attack. No penalty to strike other hit locations, if they are visible
         from that posture."

    B547's Melee Attack Modifiers table has no target-posture row at all — only
    *attacker's* posture. An exhaustive sweep of both volumes finds no melee
    to-hit bonus against a prone target. The B104 Overhead enhancement is
    confirmatory: it "negates attack *penalties* to hit crouching, kneeling,
    sitting, or prone targets" — penalties, never a bonus.
    """

    def test_lying_down_grants_no_melee_to_hit_bonus(self):
        assert posture(LYING_DOWN_NAME).melee_to_hit_you == 0

    def test_no_posture_grants_a_melee_to_hit_bonus(self):
        for p in POSTURES:
            assert p.melee_to_hit_you == 0, (
                f"{p.name}: GURPS Basic Set defines no target-posture melee "
                f"to-hit modifier; B551's Target column is ranged-only"
            )

    def test_ranged_target_penalty_still_applies(self):
        """The real posture advantage — don't over-correct and zero this too."""
        for name in ("Crouching", "Kneeling", "Sitting", "Crawling", LYING_DOWN_NAME):
            assert posture(name).ranged_to_hit_you == -2, name
        assert posture("Standing").ranged_to_hit_you == 0

    def test_prone_defense_penalty_is_the_actual_advantage(self):
        """B551 Defense column: Crawling and Lying Down are both -3."""
        assert posture(LYING_DOWN_NAME).defense_modifier == -3
        assert posture("Crawling").defense_modifier == -3


class TestLyingDownMovesOneYardPerSecond:
    """B551 Movement column prints "1 yard/second" for Lying Down — an absolute
    rate, not a fraction of Move. Crawling is the "1/3 (+2 per hex)" row.
    """

    def test_lying_down_is_an_absolute_rate_not_a_fraction(self):
        ld = posture(LYING_DOWN_NAME)
        assert ld.move_yards_per_second == 1.0
        assert ld.move_fraction is None, (
            "Lying Down has no Move fraction in B551; it is a flat 1 yard/second"
        )

    def test_crawling_keeps_its_one_third_fraction(self):
        crawl = posture("Crawling")
        assert crawl.move_fraction == pytest.approx(1 / 3)
        assert crawl.move_yards_per_second is None

    @pytest.mark.parametrize(
        "name,expected",
        [("Standing", 1.0), ("Crouching", 2 / 3), ("Kneeling", 1 / 3),
         ("Sitting", 0.0), ("Crawling", 1 / 3)],
    )
    def test_other_postures_keep_printed_fractions(self, name, expected):
        assert posture(name).move_fraction == pytest.approx(expected)


class TestDoubleKnockbackDoublesTheResult:
    """B104 Double Knockback (dkb): "twice as much knockback as usual."

    "As usual" is the computed yardage, so the result doubles. Halving the
    ST-2 divisor is a different operation once the floor division is applied,
    and it over-reports whenever basic damage is not an exact multiple of ST-2.
    """

    def test_book_example_st10_damage12(self):
        """ST 10 -> divisor 8. 12 // 8 = 1 yard, doubled = 2 (not 3)."""
        normal = calc_knockback(12, "cr", 10)
        assert normal.yards == 1
        doubled = calc_knockback(12, "cr", 10, double_knockback=True)
        assert doubled.yards == 2

    @pytest.mark.parametrize("damage", [8, 12, 15, 16, 20, 23, 24, 31])
    def test_doubled_is_always_exactly_twice_normal(self, damage):
        normal = calc_knockback(damage, "cr", 10)
        doubled = calc_knockback(damage, "cr", 10, double_knockback=True)
        assert doubled.yards == normal.yards * 2, (
            f"basic damage {damage}: dkb must double the yardage, not halve "
            f"the divisor"
        )

    def test_fall_check_modifier_follows_the_corrected_yardage(self):
        """-1 per yard after the first, computed from the real yard count."""
        doubled = calc_knockback(12, "cr", 10, double_knockback=True)
        assert doubled.yards == 2
        assert doubled.fall_check_modifier == -1


class TestEncumbranceDodgeFloor:
    """B17: "Encumbrance can never reduce Move or Dodge below 1."

    `effective_move` already clamps. `full_dodge` did not, so a low-Speed
    encumbered character was handed an unrollable Dodge of 0 or -1.
    """

    def test_low_speed_extra_heavy_never_drops_below_one(self):
        assert full_dodge(1.0, 4) == 1

    def test_zero_speed_never_goes_negative(self):
        assert full_dodge(0.0, 4) == 1

    @pytest.mark.parametrize("level", [0, 1, 2, 3, 4])
    def test_dodge_is_never_below_one_at_any_book_level(self, level):
        for speed in (0.0, 0.25, 1.0, 2.75, 5.0, 10.0):
            assert full_dodge(speed, level) >= 1, (speed, level)

    def test_unencumbered_dodge_is_still_speed_plus_three(self):
        """Don't let the clamp mask the base formula (B17, fractions dropped)."""
        assert full_dodge(5.25, 0) == 8
        assert full_dodge(5.75, 0) == 8
        assert full_dodge(6.0, 0) == 9

    def test_penalty_still_equals_the_level_where_headroom_exists(self):
        assert full_dodge(10.0, 0) == 13
        assert full_dodge(10.0, 4) == 9
