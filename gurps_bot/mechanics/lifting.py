# formulas only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""ST -> lifting/moving capacities (B353); everything is a multiple of Basic Lift."""

from __future__ import annotations

from dataclasses import dataclass

# B353 action times, exposed on LiftCapacities
_ONE_HANDED_LIFT_SECONDS = 2
_TWO_HANDED_LIFT_SECONDS = 4


@dataclass(frozen=True, slots=True)
class LiftCapacities:
    """All weights in lbs, unrounded; display rounding is the cog's problem."""

    st: int
    basic_lift: float
    one_handed_lift: float
    two_handed_lift: float
    shove: float
    shove_running: float
    carry_on_back: float
    drag: float
    shift_slightly: float
    one_handed_lift_seconds: int
    two_handed_lift_seconds: int


def basic_lift(st: int) -> float:
    """BL = ST^2 / 5 lbs, deliberately unrounded (B353); rejects bool and non-int ST."""
    if isinstance(st, bool) or not isinstance(st, int):
        raise TypeError(f"ST must be an int, got {type(st).__name__}")
    if st <= 0:
        raise ValueError(f"ST must be positive, got {st}")
    return (st * st) / 5


def one_handed_lift(st: int) -> float:
    """2 x BL, takes 2 seconds (B353)."""
    return 2 * basic_lift(st)


def two_handed_lift(st: int) -> float:
    """8 x BL, takes 4 seconds (B353)."""
    return 8 * basic_lift(st)


def shove(st: int, *, running_start: bool = False) -> float:
    """Shove and Knock Over: 12 x BL; a running start (B520 slam) doubles it (B353)."""
    base = 12 * basic_lift(st)
    return 2 * base if running_start else base


def carry_on_back(st: int) -> float:
    """15 x BL (B353); anything over 10 x BL is Extra-Heavy encumbrance (1 FP/sec)."""
    return 15 * basic_lift(st)


def drag(st: int) -> float:
    """15 x BL (B353); same coefficient as carry_on_back by RAW, not a copy-paste bug."""
    return 15 * basic_lift(st)


def shift_slightly(st: int) -> float:
    """50 x BL when braced (B353)."""
    return 50 * basic_lift(st)


def lifting_capacities(st: int) -> LiftCapacities:
    bl = basic_lift(st)
    standing_shove = shove(st)
    return LiftCapacities(
        st=st,
        basic_lift=bl,
        one_handed_lift=one_handed_lift(st),
        two_handed_lift=two_handed_lift(st),
        shove=standing_shove,
        shove_running=shove(st, running_start=True),
        carry_on_back=carry_on_back(st),
        drag=drag(st),
        shift_slightly=shift_slightly(st),
        one_handed_lift_seconds=_ONE_HANDED_LIFT_SECONDS,
        two_handed_lift_seconds=_TWO_HANDED_LIFT_SECONDS,
    )
