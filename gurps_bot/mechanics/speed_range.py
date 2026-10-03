# formulas only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Size and Speed/Range tables (B550, B19): round up to the first row >= input, never interpolate."""

from __future__ import annotations

from dataclasses import dataclass

# compare distances as integer thousandths of a yard so unit-conversion float
# dust (1.9999999 from 6ft/3) can't drift across a row boundary
_SCALE = 1000


def _scaled(value: float) -> int:
    return int(round(value * _SCALE))


# B550 speed/range: 2yd -> 0, one worse per row; thresholds cycle [2,3,5,7,10,15]
# times ascending powers of 10, extended programmatically so there's no ceiling
_SPEED_RANGE_MANTISSA: tuple[float, ...] = (2.0, 3.0, 5.0, 7.0, 10.0, 15.0)

_SPEED_RANGE_MIN_THRESHOLD = 2.0


def _speed_range_threshold(index: int) -> float:
    mantissa = _SPEED_RANGE_MANTISSA[index % 6]
    decade = 10 ** (index // 6)
    return mantissa * decade


# B550/B19 size: 2yd -> SM 0, +1 per row up, -1 per row down. Below the smallest
# row clamp at -10; above 150yd extend by the same mantissa cycle
_SIZE_TABLE: tuple[tuple[float, int], ...] = (
    (0.05, -10),
    (0.07, -9),
    (0.1, -8),
    (0.15, -7),
    (0.2, -6),
    (0.3, -5),
    (0.5, -4),
    (0.7, -3),
    (1.0, -2),
    (1.5, -1),
    (2.0, 0),
    (3.0, 1),
    (5.0, 2),
    (7.0, 3),
    (10.0, 4),
    (15.0, 5),
    (20.0, 6),
    (30.0, 7),
    (50.0, 8),
    (70.0, 9),
    (100.0, 10),
    (150.0, 11),
)

_SIZE_TABLE_SCALED: tuple[tuple[int, int], ...] = tuple(
    (_scaled(threshold), sm) for threshold, sm in _SIZE_TABLE
)

_SIZE_MIN_THRESHOLD, _SIZE_MIN_SM = _SIZE_TABLE[0]
_SIZE_MAX_THRESHOLD, _SIZE_MAX_SM = _SIZE_TABLE[-1]

# the large side shares the speed/range cycle with SM == cycle index (150yd = idx 11)
_SIZE_MAX_CYCLE_INDEX = 11


@dataclass(frozen=True, slots=True)
class RangedHitModifier:
    """Net to-hit bundle (B550); total is deliberately unclamped."""

    distance_yards: float
    target_size_yards: float
    target_speed_yards_per_second: float
    speed_range_modifier: int  # one lookup of speed+range summed (B550)
    size_modifier: int
    total: int
    # informational single-axis breakdown; NOT summed into total (B550 combines them)
    range_modifier: int
    speed_modifier: int

    def __str__(self) -> str:
        return (
            f"speed/range {self.speed_range_modifier:+d} "
            f"+ size {self.size_modifier:+d} "
            f"= {self.total:+d}"
        )


def speed_range_penalty(distance_yards: float) -> int:
    """Speed/Range penalty (<= 0) for yards (B550); shared core for range and speed."""
    if distance_yards < 0:
        raise ValueError(f"distance_yards must be >= 0, got {distance_yards}")

    target = _scaled(distance_yards)

    if target <= _scaled(_SPEED_RANGE_MIN_THRESHOLD):
        return 0

    # row 0 is the 2yd anchor, so the modifier for row index is -index
    index = 1
    while True:
        threshold = _speed_range_threshold(index)
        if _scaled(threshold) >= target:
            return -index
        index += 1


def range_modifier(yards: float) -> int:
    """Alias of speed_range_penalty for shooter-to-target distance (B550)."""
    return speed_range_penalty(yards)


def speed_modifier(yards_per_second: float) -> int:
    """Alias of speed_range_penalty keyed on target speed in yards/second (B550)."""
    return speed_range_penalty(yards_per_second)


def size_modifier(longest_dimension_yards: float) -> int:
    """Signed SM for a longest dimension (B550, B19); clamps at -10 below 0.05yd, extends past 150yd."""
    if longest_dimension_yards <= 0:
        raise ValueError(
            f"longest_dimension_yards must be > 0, got {longest_dimension_yards}"
        )

    target = _scaled(longest_dimension_yards)

    if target <= _SIZE_TABLE_SCALED[0][0]:
        return _SIZE_MIN_SM

    for threshold_scaled, sm in _SIZE_TABLE_SCALED:
        if threshold_scaled >= target:
            return sm

    # past 150yd: continue the cycle, +1 SM per row
    index = _SIZE_MAX_CYCLE_INDEX + 1
    sm = _SIZE_MAX_SM + 1
    while True:
        threshold = _speed_range_threshold(index)
        if _scaled(threshold) >= target:
            return sm
        index += 1
        sm += 1


def ranged_hit_modifier(
    distance_yards: float,
    target_longest_dimension_yards: float,
    target_speed_yards_per_second: float = 0.0,
) -> RangedHitModifier:
    """speed/range + size in one bundle (B550); caller feeds the unclamped total to checks.check."""
    # B550: sum range and speed in yards FIRST, then take ONE speed/range lookup
    size_mod = size_modifier(target_longest_dimension_yards)
    sr_mod = speed_range_penalty(distance_yards + target_speed_yards_per_second)
    total = sr_mod + size_mod

    return RangedHitModifier(
        distance_yards=distance_yards,
        target_size_yards=target_longest_dimension_yards,
        target_speed_yards_per_second=target_speed_yards_per_second,
        speed_range_modifier=sr_mod,
        size_modifier=size_mod,
        total=total,
        range_modifier=range_modifier(distance_yards),
        speed_modifier=speed_modifier(target_speed_yards_per_second),
    )
