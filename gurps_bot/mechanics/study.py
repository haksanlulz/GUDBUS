# formulas only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Study-hour accrual (B292-294): 200 learning-hours buys 1 character point."""

from __future__ import annotations

import math
from dataclasses import dataclass

POINT_HOURS: float = 200.0

# real hours -> learning hours (B292-294); 'adventuring' has no fixed rate, the GM sets it
METHOD_MULTIPLIERS: dict[str, float] = {
    "self_teaching": 0.5,  # study alone w/ book: 2 real hrs -> 1 learning-hr
    "on_the_job": 0.25,    # learn while working: 4 work hrs -> 1 learning-hr
    "education": 1.0,      # instructor (Teaching-12+): 1 real hr -> 1 learning-hr
    "intensive": 2.0,      # expert teacher + materials: 1 real hr -> 2 learning-hrs
}

# B293: at most 8 work-hours per session/day count toward on-the-job study
ON_THE_JOB_DAILY_CAP_HOURS: float = 8.0


@dataclass(frozen=True, slots=True)
class StudyProgress:
    """Aggregated study progress for one (user, character?, skill) bucket."""

    total_learning_hours: float
    points_earned: int
    remainder: float
    hours_to_next: float


def _reject_nan(value: float, label: str) -> None:
    """Raise ValueError if value is NaN (NaN slips past >= 0 comparisons)."""
    if isinstance(value, float) and math.isnan(value):
        raise ValueError(f"{label} must not be NaN")


def study_multiplier(method: str, gm_multiplier: float | None = None) -> float:
    """Learning-hours per real hour; the on-the-job cap is hour-based and lives in learning_hours_for."""
    key = method.strip().lower()

    if key in METHOD_MULTIPLIERS:
        return METHOD_MULTIPLIERS[key]

    if key == "adventuring":
        if gm_multiplier is None:
            raise ValueError(
                "adventuring requires an explicit gm_multiplier (no default)"
            )
        _reject_nan(gm_multiplier, "gm_multiplier")
        if gm_multiplier < 0:
            raise ValueError("gm_multiplier must be >= 0")
        return float(gm_multiplier)

    raise ValueError(f"unknown study method: {method!r}")


def learning_hours_for(
    method: str, real_hours: float, gm_multiplier: float | None = None,
) -> float:
    """Learning-hours for one session; the only place the on-the-job 8-hour cap (B293) applies."""
    _reject_nan(real_hours, "real_hours")
    if real_hours < 0:
        raise ValueError("real_hours must be >= 0")

    key = method.strip().lower()
    if key == "on_the_job":
        effective_real = min(real_hours, ON_THE_JOB_DAILY_CAP_HOURS)
    else:
        effective_real = real_hours

    return effective_real * study_multiplier(method, gm_multiplier)


def study_progress(total_learning_hours: float) -> StudyProgress:
    """Points earned + banked remainder; hours_to_next is exactly 200.0 on a boundary, never 0."""
    _reject_nan(total_learning_hours, "total_learning_hours")
    if total_learning_hours < 0:
        raise ValueError("total_learning_hours must be >= 0")

    total = total_learning_hours

    # clamp float drift so many x0.25/x0.5 sessions can't yield 199.99999999
    nearest_boundary = round(total / POINT_HOURS) * POINT_HOURS
    if abs(total - nearest_boundary) < 1e-9:
        total = nearest_boundary

    points_earned = int(total // POINT_HOURS)
    remainder = total - points_earned * POINT_HOURS
    hours_to_next = POINT_HOURS - remainder

    return StudyProgress(
        total_learning_hours=total_learning_hours,
        points_earned=points_earned,
        remainder=remainder,
        hours_to_next=hours_to_next,
    )
