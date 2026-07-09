# formulas/numbers only, no SJG text reproduced; GURPS is a trademark of
# Steve Jackson Games — unofficial fan calculator
"""encumbrance & move (B15/B17): Basic Lift, bands, Move/Dodge penalties"""

from __future__ import annotations

import math
from dataclasses import dataclass

# B15 move multipliers; 5 = overloaded sentinel (weight > 10*BL, cannot move);
# dodge penalty equals the level number
_MOVE_MULTIPLIERS: dict[int, float] = {
    0: 1.0,  # None
    1: 0.8,  # Light
    2: 0.6,  # Medium
    3: 0.4,  # Heavy
    4: 0.2,  # Extra-Heavy
    5: 0.0,  # Overloaded (cannot move under load)
}

# index = level 0..5 (B15)
_LEVEL_NAMES: tuple[str, ...] = (
    "None",
    "Light",
    "Medium",
    "Heavy",
    "Extra-Heavy",
    "Overloaded",
)

# inclusive BL multiples for None..Extra-Heavy (B15); overloaded = past the last
_THRESHOLD_MULTIPLES: tuple[int, ...] = (1, 2, 3, 6, 10)


@dataclass(frozen=True, slots=True)
class EncumbranceThreshold:
    """One real encumbrance band (None..Extra-Heavy) for UI/embeds (B15)."""

    level: int  # encumbrance level 0..4 (None..Extra-Heavy)
    name: str  # level display name ("None".."Extra-Heavy")
    max_weight: float  # inclusive maximum carried weight (lbs) still in band
    move_multiplier: float  # Basic Move multiplier (1.0/0.8/0.6/0.4/0.2)
    dodge_penalty: int  # penalty subtracted from full Dodge (equals level)


@dataclass(frozen=True, slots=True)
class EncumbranceResult:
    """Full encumbrance evaluation for one carried weight (B15/B17)."""

    basic_lift: float  # computed Basic Lift in lbs
    carried_weight: float  # the W that was evaluated (echoed for display)
    level: int  # encumbrance level 0..5 (5 = overloaded)
    level_name: str  # display name ("None".."Extra-Heavy" or "Overloaded")
    move_multiplier: float  # Basic Move multiplier applied (0.0 if overloaded)
    effective_move: int  # final Move (0 if overloaded, min 1 when BM>=1)
    dodge: int  # full Dodge after encumbrance penalty
    overloaded: bool  # True when W > 10*BL (cannot move under load)


def basic_lift(st: int) -> float:
    """B15: BL = ST*ST/5, whole lbs from 10 up; ST*ST/5 never ends in .5, so banker's round() is exact here — don't 'fix' it to half-up"""
    if st < 0:
        raise ValueError("ST must be non-negative")
    bl_raw = (st * st) / 5.0
    if bl_raw >= 10:
        return float(round(bl_raw))
    return bl_raw


def encumbrance_level(weight: float, bl: float) -> int:
    """band 0..5 with inclusive upper bounds (B15); bl 0 = any positive weight overloads"""
    if weight < 0:
        raise ValueError("weight must be non-negative")
    if bl < 0:
        raise ValueError("bl must be non-negative")
    for level, multiple in enumerate(_THRESHOLD_MULTIPLES):
        if weight <= multiple * bl:
            return level
    return 5


def move_multiplier(level: int) -> float:
    """B15/B17 multiplier table owner — hiking.py derives from here"""
    if level not in _MOVE_MULTIPLIERS:
        raise ValueError("level must be in 0..5")
    return _MOVE_MULTIPLIERS[level]


def effective_move(basic_move: int, level: int) -> int:
    """floor(move * mult), min 1 while Basic Move >= 1; overloaded forces 0 (B15/B17)"""
    if basic_move < 0:
        raise ValueError("basic_move must be non-negative")
    if level not in _MOVE_MULTIPLIERS:
        raise ValueError("level must be in 0..5")
    if level == 5:
        return 0
    eff = math.floor(basic_move * _MOVE_MULTIPLIERS[level])
    if basic_move >= 1 and eff < 1:
        return 1
    return eff


def full_dodge(basic_speed: float, level: int) -> int:
    """dodge = floor(Basic Speed) + 3 - level (B17)"""
    if basic_speed < 0:
        raise ValueError("basic_speed must be non-negative")
    if level not in _MOVE_MULTIPLIERS:
        raise ValueError("level must be in 0..5")
    return math.floor(basic_speed) + 3 - level


def encumbrance_thresholds(bl: float) -> tuple[EncumbranceThreshold, ...]:
    """the 5 real bands for UI (B15); overloaded is a region past the last threshold, not a band — excluded"""
    if bl < 0:
        raise ValueError("bl must be non-negative")
    return tuple(
        EncumbranceThreshold(
            level=level,
            name=_LEVEL_NAMES[level],
            max_weight=multiple * bl,
            move_multiplier=_MOVE_MULTIPLIERS[level],
            dodge_penalty=level,
        )
        for level, multiple in enumerate(_THRESHOLD_MULTIPLES)
    )


def encumbrance_report(
    st: int, basic_move: int, basic_speed: float, weight: float
) -> EncumbranceResult:
    """one-call bundle: BL, band, effective Move, full Dodge"""
    bl = basic_lift(st)
    level = encumbrance_level(weight, bl)
    eff = effective_move(basic_move, level)
    dodge = full_dodge(basic_speed, level)
    return EncumbranceResult(
        basic_lift=bl,
        carried_weight=weight,
        level=level,
        level_name=_LEVEL_NAMES[level],
        move_multiplier=_MOVE_MULTIPLIERS[level],
        effective_move=eff,
        dodge=dodge,
        overloaded=(level == 5),
    )
