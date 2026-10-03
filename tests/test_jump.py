"""Jump calculator (B352)."""

import pytest
from gurps_bot.mechanics.jump import (
    JumpResult,
    effective_move,
    high_jump,
    long_jump,
)


class TestEffectiveMove:
    def test_standing_is_basic_move(self):
        assert effective_move(6) == 6.0

    def test_running_adds_yards(self):
        assert effective_move(6, running_start=True, yards_run=4) == 10.0

    def test_enhanced_move_multiplies(self):
        # Horse example: Move 6, Enhanced Move (Ground) 1 -> x2 -> 12
        assert effective_move(6, running_start=True, enhanced_move=2.0) == 12.0

    def test_enhanced_move_precedence_over_yards(self):
        # enhanced_move wins; yards_run must NOT also be added.
        m = effective_move(6, running_start=True, yards_run=20, enhanced_move=2.0)
        assert m == 12.0

    def test_enhanced_move_ignored_when_standing(self):
        # Enhanced Move only applies WITH a running start.
        assert effective_move(6, running_start=False, enhanced_move=2.0) == 6.0

    def test_yards_ignored_when_standing(self):
        assert effective_move(6, running_start=False, yards_run=20) == 6.0

    def test_jumping_skill_substitutes_when_better(self):
        # floor(20/2) = 10 beats Move 6.
        assert effective_move(6, jumping_skill=20) == 10.0

    def test_jumping_skill_ignored_when_worse(self):
        # floor(10/2) = 5 does not beat Move 6.
        assert effective_move(6, jumping_skill=10) == 6.0

    def test_jumping_skill_floor_division(self):
        # floor(15/2) = 7.
        assert effective_move(6, jumping_skill=15) == 7.0

    def test_st_jump_substitutes_when_enabled_and_better(self):
        # floor(40/4) = 10 beats Move 6.
        assert effective_move(6, st=40, use_st_jump=True) == 10.0

    def test_st_jump_ignored_when_disabled(self):
        assert effective_move(6, st=40, use_st_jump=False) == 6.0

    def test_st_jump_ignored_when_not_better(self):
        # floor(20/4) = 5 does not beat Move 6.
        assert effective_move(6, st=20, use_st_jump=True) == 6.0

    def test_skill_and_st_both_take_best(self):
        # base 6, st 40 -> 10, skill 30 -> 15: best is 15.
        m = effective_move(6, st=40, use_st_jump=True, jumping_skill=30)
        assert m == 15.0

    def test_running_then_skill_take_best(self):
        # running 6+4=10, skill 16 -> 8: running wins.
        m = effective_move(6, running_start=True, yards_run=4, jumping_skill=16)
        assert m == 10.0

    def test_fractional_basic_move_flows_through(self):
        assert effective_move(5.25) == 5.25


class TestHighJump:
    def test_standing_worked_example(self):
        # Book: Basic Move 6 -> 26 inches. (6*6)-10 = 26.
        result = high_jump(6)
        assert result.kind == "high"
        assert result.value == 26.0
        assert result.capped is False
        assert result.super_jump_multiplier == 1
        assert result.encumbrance_factor == 1.0
        assert result.effective_move == 6.0

    def test_feet_field_is_inches_over_twelve(self):
        result = high_jump(6)
        assert result.feet == pytest.approx(26.0 / 12.0)

    def test_running_under_cap(self):
        # M=10 -> 60-10=50; standing=26 so cap=52; 50<=52 ok.
        result = high_jump(6, running_start=True, yards_run=4)
        assert result.value == 50.0
        assert result.capped is False

    def test_running_hits_cap(self):
        # M=26 -> 146 raw, capped at 2x standing (2*26=52).
        result = high_jump(6, running_start=True, yards_run=20)
        assert result.value == 52.0
        assert result.capped is True

    def test_jumping_skill_substitution(self):
        # M=max(6,10)=10 -> (6*10)-10 = 50.
        result = high_jump(6, jumping_skill=20)
        assert result.value == 50.0
        assert result.effective_move == 10.0

    def test_negative_clamped_to_zero(self):
        # (6*1)-10 = -4 inches -> clamped to 0.0.
        result = high_jump(1)
        assert result.value == 0.0
        assert result.feet == 0.0

    def test_super_jump_doubles_per_level(self):
        # Standing high 26, Super Jump L1 -> 52.
        result = high_jump(6, super_jump=1)
        assert result.value == 52.0
        assert result.super_jump_multiplier == 2

    def test_super_jump_two_levels(self):
        # 26 * 2^2 = 104.
        result = high_jump(6, super_jump=2)
        assert result.value == 104.0
        assert result.super_jump_multiplier == 4

    def test_super_jump_after_running_cap_exceeds_2x_standing(self):
        # Running cap = 52, Super Jump L1 doubles the capped value -> 104.
        result = high_jump(6, running_start=True, yards_run=20, super_jump=1)
        assert result.capped is True
        assert result.value == 104.0

    def test_encumbrance_scales_final(self):
        # 26 * 0.6 = 15.6.
        result = high_jump(6, encumbrance=0.6)
        assert result.value == pytest.approx(15.6)
        assert result.encumbrance_factor == 0.6

    def test_running_start_zero_contribution_equals_standing(self):
        # running_start but no yards/enhanced -> equals standing, cap non-binding.
        result = high_jump(6, running_start=True)
        assert result.value == 26.0
        assert result.capped is False

    def test_st_jump_substitution(self):
        # floor(40/4)=10 beats Move 6 -> (6*10)-10 = 50.
        result = high_jump(6, st=40, use_st_jump=True)
        assert result.value == 50.0

    def test_returns_jumpresult(self):
        assert isinstance(high_jump(6), JumpResult)


class TestLongJump:
    def test_standing_worked_example(self):
        # Book: Basic Move 6 -> 9 feet broad jump = 3.0 yards.
        result = long_jump(6)
        assert result.kind == "long"
        assert result.value == 3.0
        assert result.feet == 9.0
        assert result.capped is False
        assert result.effective_move == 6.0

    def test_running_hits_cap(self):
        # Raw feet=(2*26)-3=49, capped at 2x standing broad (2*9=18) = 6.0 yd.
        result = long_jump(6, running_start=True, yards_run=20)
        assert result.value == 6.0
        assert result.feet == 18.0
        assert result.capped is True

    def test_enhanced_move_path_with_cap(self):
        # M=12 -> feet=21, standing=9 so cap=18 -> 18 ft = 6.0 yd.
        result = long_jump(6, running_start=True, enhanced_move=2.0)
        assert result.effective_move == 12.0
        assert result.feet == 18.0
        assert result.value == 6.0
        assert result.capped is True

    def test_super_jump_doubles_final(self):
        # Standing broad 9 ft, Super Jump L1 -> 18 ft = 6.0 yd.
        result = long_jump(6, super_jump=1)
        assert result.value == 6.0
        assert result.feet == 18.0
        assert result.super_jump_multiplier == 2

    def test_negative_clamped_to_zero(self):
        # (2*1)-3 = -1 ft -> clamped to 0.0.
        result = long_jump(1)
        assert result.value == 0.0
        assert result.feet == 0.0

    def test_encumbrance_scales_final(self):
        # 9 ft * 0.6 = 5.4 ft -> 1.8 yd.
        result = long_jump(6, encumbrance=0.6)
        assert result.feet == pytest.approx(5.4)
        assert result.value == pytest.approx(1.8)
        assert result.encumbrance_factor == 0.6

    def test_running_under_cap(self):
        # M=10 -> feet=17; standing=9 so cap=18; 17<=18 ok.
        result = long_jump(6, running_start=True, yards_run=4)
        assert result.feet == 17.0
        assert result.value == pytest.approx(17.0 / 3.0)
        assert result.capped is False

    def test_super_jump_after_running_cap(self):
        # Running cap = 18 ft, Super Jump L1 -> 36 ft = 12.0 yd.
        result = long_jump(6, running_start=True, yards_run=20, super_jump=1)
        assert result.capped is True
        assert result.feet == 36.0
        assert result.value == 12.0

    def test_yards_is_feet_over_three(self):
        result = long_jump(9)
        # (2*9)-3 = 15 ft -> 5.0 yd.
        assert result.feet == 15.0
        assert result.value == pytest.approx(5.0)

    def test_returns_jumpresult(self):
        assert isinstance(long_jump(6), JumpResult)


class TestJumpResultShape:
    def test_high_result_fields(self):
        result = high_jump(6)
        assert hasattr(result, "kind")
        assert hasattr(result, "value")
        assert hasattr(result, "feet")
        assert hasattr(result, "effective_move")
        assert hasattr(result, "capped")
        assert hasattr(result, "super_jump_multiplier")
        assert hasattr(result, "encumbrance_factor")

    def test_frozen(self):
        result = high_jump(6)
        with pytest.raises((AttributeError, Exception)):
            result.value = 999.0


class TestJumpRendering:
    """JumpResult.__str__ — both unit branches (display-layer smoke)."""

    def test_high_jump_str_uses_inches(self):
        s = str(high_jump(6))
        assert "high jump:" in s and " in" in s

    def test_long_jump_str_uses_yards(self):
        s = str(long_jump(6))
        assert "long jump:" in s and " yd" in s
