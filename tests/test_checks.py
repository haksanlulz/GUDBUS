"""Tests for GURPS 3d6 roll-under check engine."""

from unittest.mock import patch

import pytest
from gurps_bot.mechanics.checks import CheckResult, Outcome, check, contest, _determine_outcome
from gurps_bot.mechanics.dice import DiceSpec, RollResult


class TestDetermineOutcome:
    """Test critical threshold logic with known rolls."""

    def test_crit_success_on_3(self):
        assert _determine_outcome(3, 10) == Outcome.CRITICAL_SUCCESS

    def test_crit_success_on_4(self):
        assert _determine_outcome(4, 10) == Outcome.CRITICAL_SUCCESS

    def test_crit_success_5_needs_target_15(self):
        assert _determine_outcome(5, 15) == Outcome.CRITICAL_SUCCESS
        assert _determine_outcome(5, 14) == Outcome.SUCCESS  # not critical

    def test_crit_success_6_needs_target_16(self):
        assert _determine_outcome(6, 16) == Outcome.CRITICAL_SUCCESS
        assert _determine_outcome(6, 15) == Outcome.SUCCESS  # not critical

    def test_crit_failure_on_18(self):
        assert _determine_outcome(18, 18) == Outcome.CRITICAL_FAILURE

    def test_crit_failure_on_17_when_target_15_or_less(self):
        assert _determine_outcome(17, 15) == Outcome.CRITICAL_FAILURE
        assert _determine_outcome(17, 16) == Outcome.FAILURE  # not critical

    def test_17_always_fails_even_at_high_skill(self):
        # B347: a 17 is never a success, however high the effective skill.
        assert _determine_outcome(17, 17) == Outcome.FAILURE
        assert _determine_outcome(17, 18) == Outcome.FAILURE
        assert _determine_outcome(17, 25) == Outcome.FAILURE

    def test_crit_failure_on_10_plus_mof(self):
        # Target 6, rolled 16 -> MoF = 10, so critical
        assert _determine_outcome(16, 6) == Outcome.CRITICAL_FAILURE
        # Target 6, rolled 15 -> MoF = 9, not critical (just failure)
        assert _determine_outcome(15, 6) == Outcome.FAILURE

    def test_normal_success(self):
        assert _determine_outcome(10, 12) == Outcome.SUCCESS

    def test_exact_success(self):
        assert _determine_outcome(12, 12) == Outcome.SUCCESS

    def test_normal_failure(self):
        assert _determine_outcome(13, 12) == Outcome.FAILURE


class TestCheck:
    def test_check_returns_result(self):
        result = check(12)
        assert 3 <= result.rolled <= 18
        assert result.target == 12
        assert result.margin == 12 - result.rolled
        assert isinstance(result.outcome, Outcome)

    def test_check_with_modifier(self):
        result = check(12, modifier=-2)
        assert result.target == 10  # 12 - 2

    def test_check_with_positive_modifier(self):
        result = check(10, modifier=3)
        assert result.target == 13

    def test_outcome_succeeded_property(self):
        assert Outcome.CRITICAL_SUCCESS.succeeded is True
        assert Outcome.SUCCESS.succeeded is True
        assert Outcome.FAILURE.succeeded is False
        assert Outcome.CRITICAL_FAILURE.succeeded is False

    def test_outcome_is_critical_property(self):
        assert Outcome.CRITICAL_SUCCESS.is_critical is True
        assert Outcome.CRITICAL_FAILURE.is_critical is True
        assert Outcome.SUCCESS.is_critical is False
        assert Outcome.FAILURE.is_critical is False


class TestContest:
    def test_contest_returns_three_values(self):
        a, b, winner = contest(12, 12)
        assert isinstance(a.outcome, Outcome)
        assert isinstance(b.outcome, Outcome)
        assert winner in ("A", "B", "Tie")

    def test_contest_higher_margin_wins(self):
        # We can't easily mock random, so just verify the logic is consistent
        for _ in range(50):
            a, b, winner = contest(12, 12)
            if a.margin > b.margin:
                assert winner == "A"
            elif b.margin > a.margin:
                assert winner == "B"
            # Ties resolved by target comparison (both 12 = "Tie")

    def test_tie_break_higher_target_wins(self):
        # Equal margins -> higher target wins (B348); equal target -> Tie.
        # Force equal margins by stubbing check() so only the target differs.
        fixed = CheckResult(
            roll_result=RollResult(spec=DiceSpec(3, 6, 0), dice=(3, 4, 3), total=10),
            target=0, margin=0, outcome=Outcome.SUCCESS,
        )
        with patch("gurps_bot.mechanics.checks.check", return_value=fixed):
            assert contest(15, 10)[2] == "A"
            assert contest(10, 15)[2] == "B"
            assert contest(12, 12)[2] == "Tie"
