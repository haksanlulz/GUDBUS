# formulas only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Throwing distance + damage (B355) and thrust-by-ST (B16); returns dice specs, never rolls."""

from __future__ import annotations

from dataclasses import dataclass

from gurps_bot.mechanics.dice import DiceSpec

_MIN_ST = 1
_MAX_ST = 40

# B16 thrust column: ST -> (dice, modifier); sides always 6, table stops at ST 40
_THRUST_BY_ST: dict[int, tuple[int, int]] = {
    1: (1, -6),
    2: (1, -6),
    3: (1, -5),
    4: (1, -5),
    5: (1, -4),
    6: (1, -4),
    7: (1, -3),
    8: (1, -3),
    9: (1, -2),
    10: (1, -2),
    11: (1, -1),
    12: (1, -1),
    13: (1, 0),
    14: (1, 0),
    15: (1, 1),
    16: (1, 1),
    17: (1, 2),
    18: (1, 2),
    19: (2, -1),
    20: (2, -1),
    21: (2, 0),
    22: (2, 0),
    23: (2, 1),
    24: (2, 1),
    25: (2, 2),
    26: (2, 2),
    27: (3, -1),
    28: (3, -1),
    29: (3, 0),
    30: (3, 0),
    31: (3, 1),
    32: (3, 1),
    33: (3, 2),
    34: (3, 2),
    35: (4, -1),
    36: (4, -1),
    37: (4, 0),
    38: (4, 0),
    39: (4, 1),
    40: (4, 1),
}

# B355: weight/BL ratio -> distance modifier; round the ratio UP to the next key
_DISTANCE_MODIFIERS: dict[float, float] = {
    0.05: 3.5,
    0.10: 2.5,
    0.15: 2.0,
    0.20: 1.5,
    0.25: 1.2,
    0.30: 1.1,
    0.40: 1.0,
    0.50: 0.8,
    0.75: 0.7,
    1.00: 0.6,
    1.50: 0.4,
    2.0: 0.30,
    2.5: 0.25,
    3.0: 0.20,
    4.0: 0.15,
    5.0: 0.12,
    6.0: 0.10,
    7.0: 0.09,
    8.0: 0.08,
    9.0: 0.07,
    10.0: 0.06,
    12.0: 0.05,
}

_RATIO_KEYS: tuple[float, ...] = tuple(sorted(_DISTANCE_MODIFIERS))
_SMALLEST_RATIO_KEY = _RATIO_KEYS[0]


@dataclass(frozen=True, slots=True)
class ThrowResult:
    """Distance + reachability detail for a thrown object (B355)."""

    st: int
    weight_lbs: float
    basic_lift: float
    weight_ratio: float
    distance_modifier: float
    distance_yards: float
    throwable: bool
    one_handed: bool


@dataclass(frozen=True, slots=True)
class ThrowEstimate:
    """Convenience aggregate of distance + damage for one throw."""

    result: ThrowResult
    damage: DiceSpec | None
    damage_type: str


def _basic_lift(st: int) -> float:
    """Basic Lift in lbs: (ST * ST) / 5 (B15)."""
    return (st * st) / 5


def thrust_for_st(st: int) -> DiceSpec:
    """Thrust dice for ST 1..40 (B16); the ST 40 cap is this table's range, not a rules limit."""
    if st < _MIN_ST or st > _MAX_ST:
        raise ValueError(
            f"ST {st} outside supported thrust range {_MIN_ST}..{_MAX_ST}"
        )
    count, modifier = _THRUST_BY_ST[st]
    return DiceSpec(count=count, sides=6, modifier=modifier)


def throw_distance(st: int, weight_lbs: float) -> ThrowResult:
    """Throw distance + reachability (B355): >8*BL is unthrowable; ST range 1..40 matches throw_damage so distance and damage agree."""
    if st < _MIN_ST or st > _MAX_ST:
        raise ValueError(
            f"ST {st} outside supported throw range {_MIN_ST}..{_MAX_ST}"
        )
    if weight_lbs < 0:
        raise ValueError(f"weight_lbs must be >= 0, got {weight_lbs}")

    bl = _basic_lift(st)
    ratio = weight_lbs / bl
    one_handed = weight_lbs <= 2 * bl

    if weight_lbs > 8 * bl:
        return ThrowResult(
            st=st,
            weight_lbs=weight_lbs,
            basic_lift=bl,
            weight_ratio=ratio,
            distance_modifier=0.0,
            distance_yards=0.0,
            throwable=False,
            one_handed=one_handed,
        )

    modifier = _distance_modifier_for_ratio(ratio)
    distance_yards = round(st * modifier, 2)

    return ThrowResult(
        st=st,
        weight_lbs=weight_lbs,
        basic_lift=bl,
        weight_ratio=ratio,
        distance_modifier=modifier,
        distance_yards=distance_yards,
        throwable=True,
        one_handed=one_handed,
    )


def _distance_modifier_for_ratio(ratio: float) -> float:
    if ratio <= _SMALLEST_RATIO_KEY:
        return _DISTANCE_MODIFIERS[_SMALLEST_RATIO_KEY]
    for key in _RATIO_KEYS:
        if ratio <= key:
            return _DISTANCE_MODIFIERS[key]
    # unreachable for throwable weights; fall back to the last row rather than raise
    return _DISTANCE_MODIFIERS[_RATIO_KEYS[-1]]


def throw_damage(st: int, weight_lbs: float) -> DiceSpec:
    """Thrown-object damage (B355): thrust adjusted per-die by weight band vs BL; negative modifiers not clamped — min-1 injury is the wounding layer's job."""
    if weight_lbs < 0:
        raise ValueError(f"weight_lbs must be >= 0, got {weight_lbs}")

    base = thrust_for_st(st)  # raises for out-of-range ST
    bl = _basic_lift(st)

    if weight_lbs > 8 * bl:
        raise ValueError(
            f"weight {weight_lbs} exceeds 8*BL ({8 * bl}); object cannot be thrown"
        )

    count = base.count
    modifier = base.modifier

    # ascending bands, first match wins
    if weight_lbs <= bl / 8:
        new_mod = modifier + (-2 * count)
    elif weight_lbs <= bl / 4:
        new_mod = modifier + (-1 * count)
    elif weight_lbs <= bl / 2:
        new_mod = modifier  # straight thrust
    elif weight_lbs <= bl:
        new_mod = modifier + (1 * count)
    elif weight_lbs <= 2 * bl:
        new_mod = modifier  # straight thrust
    elif weight_lbs <= 4 * bl:
        new_mod = modifier - (count // 2)  # -1/2 per die, rounded DOWN
    else:  # weight_lbs <= 8 * bl
        new_mod = modifier + (-1 * count)

    return DiceSpec(count=count, sides=6, modifier=new_mod)


def throw(st: int, weight_lbs: float, damage_type: str = "cr") -> ThrowEstimate:
    """Distance + damage for one throw (B355); damage is None when unthrowable; cr by default, GM may rule cut/imp/pi."""
    result = throw_distance(st, weight_lbs)
    damage = throw_damage(st, weight_lbs) if result.throwable else None
    return ThrowEstimate(result=result, damage=damage, damage_type=damage_type)
