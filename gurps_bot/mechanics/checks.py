"""GURPS 3d6 roll-under check engine with critical thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gurps_bot.mechanics.dice import roll_3d6, RollResult


class Outcome(Enum):
    CRITICAL_SUCCESS = "Critical Success"
    SUCCESS = "Success"
    FAILURE = "Failure"
    CRITICAL_FAILURE = "Critical Failure"

    @property
    def succeeded(self) -> bool:
        return self in (Outcome.CRITICAL_SUCCESS, Outcome.SUCCESS)

    @property
    def is_critical(self) -> bool:
        return self in (Outcome.CRITICAL_SUCCESS, Outcome.CRITICAL_FAILURE)


@dataclass(frozen=True, slots=True)
class CheckResult:
    roll_result: RollResult
    target: int
    margin: int
    outcome: Outcome

    @property
    def rolled(self) -> int:
        return self.roll_result.total


def _determine_outcome(rolled: int, target: int) -> Outcome:
    """crit success: 3-4 always, 5 if target >= 15, 6 if >= 16; 17-18 always fail (crit if 18, or 17 at target <= 15), crit failure on any miss by 10+"""
    margin = target - rolled

    if rolled <= 4:
        return Outcome.CRITICAL_SUCCESS
    if rolled == 5 and target >= 15:
        return Outcome.CRITICAL_SUCCESS
    if rolled == 6 and target >= 16:
        return Outcome.CRITICAL_SUCCESS

    if rolled == 18:
        return Outcome.CRITICAL_FAILURE
    if rolled == 17:
        # B347: crit failure at effective skill 15 or less, ordinary failure otherwise
        return Outcome.CRITICAL_FAILURE if target <= 15 else Outcome.FAILURE
    if rolled >= target + 10:
        return Outcome.CRITICAL_FAILURE

    if margin >= 0:
        return Outcome.SUCCESS
    return Outcome.FAILURE


def check(target: int, modifier: int = 0) -> CheckResult:
    """3d6 vs target + modifier"""
    effective = target + modifier
    roll_result = roll_3d6()
    margin = effective - roll_result.total
    outcome = _determine_outcome(roll_result.total, effective)
    return CheckResult(
        roll_result=roll_result,
        target=effective,
        margin=margin,
        outcome=outcome,
    )


def contest(target_a: int, target_b: int) -> tuple[CheckResult, CheckResult, str]:
    """quick contest -> (result_a, result_b, winner); higher margin wins, margin ties go to the higher target"""
    result_a = check(target_a)
    result_b = check(target_b)

    if result_a.margin > result_b.margin:
        winner = "A"
    elif result_b.margin > result_a.margin:
        winner = "B"
    elif target_a > target_b:
        winner = "A"
    elif target_b > target_a:
        winner = "B"
    else:
        winner = "Tie"

    return result_a, result_b, winner
