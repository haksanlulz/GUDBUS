# formulas only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Swimming movement, distance, and fatigue-timing math (B354)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum

# B17/B354: Move multiplier by encumbrance level, NONE..EXTRA_HEAVY order
_ENCUMBRANCE_FACTORS: tuple[float, ...] = (1.0, 0.8, 0.6, 0.4, 0.2)

# B354: Swimming entry-roll bonus by Build (B18)
_BUILD_SWIM_BONUS: dict[str, int] = {
    "NORMAL": 0,
    "OVERWEIGHT": 1,
    "FAT": 3,
    "VERY_FAT": 5,
}

# B354: fatigue-roll cadence in seconds, top speed vs slow/floating
_FATIGUE_INTERVAL_TOP: int = 60
_FATIGUE_INTERVAL_SLOW: int = 1800

# B354: Swimming defaults to HT-4
_SWIMMING_DEFAULT_PENALTY: int = 4

# B426: below 1/3 FP, Move is halved
_FATIGUE_MOVE_FACTOR: float = 0.5


class Encumbrance(IntEnum):
    """Int value is the encumbrance level in the -2*level entry penalty (B354)."""

    NONE = 0
    LIGHT = 1
    MEDIUM = 2
    HEAVY = 3
    EXTRA_HEAVY = 4

    @property
    def factor(self) -> float:
        """Move multiplier for this level: 1.0/0.8/0.6/0.4/0.2 (B17/B354)."""
        return _ENCUMBRANCE_FACTORS[self.value]

    @property
    def level(self) -> int:
        """The enum's int value, used for the -2*level entry-roll penalty."""
        return self.value


class Build(Enum):
    """Body Build affecting the Swimming entry roll (B18)."""

    NORMAL = "Normal"
    OVERWEIGHT = "Overweight"
    FAT = "Fat"
    VERY_FAT = "Very Fat"

    @property
    def swim_bonus(self) -> int:
        """Entry-roll modifier: 0/+1/+3/+5 (Normal/Overweight/Fat/Very Fat). B354."""
        return _BUILD_SWIM_BONUS[self.name]


@dataclass(frozen=True, slots=True)
class SwimResult:
    """Bundled swimming readout the cog renders in one shot. Pure — no rolls."""

    basic_move: int
    base_water_move: int
    effective_water_move: float
    duration_seconds: float
    distance_yards: float
    fatigue_interval_seconds: int
    fatigue_rolls: int
    fatigue_target: int

    def __str__(self) -> str:
        return (
            f"water Move {self.effective_water_move:g} yd/s "
            f"(base {self.base_water_move}); "
            f"{self.distance_yards:g} yd over {self.duration_seconds:g}s; "
            f"{self.fatigue_rolls} fatigue roll(s) vs {self.fatigue_target}"
        )


def water_move(basic_move: int, *, aquatic: bool = False) -> int:
    """Base water Move in yd/s (B354): max(1, Move // 5); aquatic = full Move, no divisor or floor."""
    if basic_move < 0:
        raise ValueError("basic_move must be non-negative")
    if aquatic:
        return basic_move
    return max(1, basic_move // 5)


def effective_water_move(
    basic_move: int,
    *,
    encumbrance: Encumbrance = Encumbrance.NONE,
    aquatic: bool = False,
    fatigued: bool = False,
) -> float:
    """Encumbrance- and fatigue-adjusted water Move (B17/B354, B426); deliberately not re-clamped to 1 — the floor lives in water_move, so Move 1 at Heavy = 0.4 yd/s per the book."""
    base = water_move(basic_move, aquatic=aquatic)
    effective = base * encumbrance.factor
    if fatigued:
        effective *= _FATIGUE_MOVE_FACTOR
    return effective


def swim_distance(
    basic_move: int,
    seconds: float,
    *,
    encumbrance: Encumbrance = Encumbrance.NONE,
    aquatic: bool = False,
    fatigued: bool = False,
) -> float:
    """Yards covered over seconds of swimming (B354); float on purpose, display rounding is the cog's problem."""
    if seconds < 0:
        raise ValueError("seconds must be non-negative")
    rate = effective_water_move(
        basic_move, encumbrance=encumbrance, aquatic=aquatic, fatigued=fatigued
    )
    return rate * seconds


def swim_fatigue_schedule(seconds: float, *, top_speed: bool = True) -> int:
    """Fatigue rolls owed over seconds (B354): completed intervals only — the roll count, not FP lost."""
    if seconds < 0:
        raise ValueError("seconds must be non-negative")
    interval = _FATIGUE_INTERVAL_TOP if top_speed else _FATIGUE_INTERVAL_SLOW
    return int(seconds // interval)


def swim_fatigue_target(ht: int, swimming_skill: int | None = None) -> int:
    """Per-roll fatigue target: higher of HT or Swimming (B354)."""
    if swimming_skill is None:
        return ht
    return max(ht, swimming_skill)


def swim_entry_target(
    ht: int,
    swimming_skill: int | None = None,
    *,
    encumbrance: Encumbrance = Encumbrance.NONE,
    intentional: bool = False,
    build: Build = Build.NORMAL,
) -> int:
    """Entry-roll target (B354): Swimming (default HT-4), +3 intentional, -2 per encumbrance level, plus Build bonus; roll cadence is the caller's concern."""
    base = swimming_skill if swimming_skill is not None else ht - _SWIMMING_DEFAULT_PENALTY
    modifier = (
        (3 if intentional else 0)
        - 2 * encumbrance.level
        + build.swim_bonus
    )
    return base + modifier


def swim_report(
    basic_move: int,
    seconds: float,
    ht: int,
    swimming_skill: int | None = None,
    *,
    encumbrance: Encumbrance = Encumbrance.NONE,
    aquatic: bool = False,
    fatigued: bool = False,
    top_speed: bool = True,
) -> SwimResult:
    """Full swimming readout in one SwimResult (B354); pure, no rolls."""
    base = water_move(basic_move, aquatic=aquatic)
    effective = effective_water_move(
        basic_move, encumbrance=encumbrance, aquatic=aquatic, fatigued=fatigued
    )
    distance = swim_distance(
        basic_move,
        seconds,
        encumbrance=encumbrance,
        aquatic=aquatic,
        fatigued=fatigued,
    )
    interval = _FATIGUE_INTERVAL_TOP if top_speed else _FATIGUE_INTERVAL_SLOW
    rolls = swim_fatigue_schedule(seconds, top_speed=top_speed)
    target = swim_fatigue_target(ht, swimming_skill)

    return SwimResult(
        basic_move=basic_move,
        base_water_move=base,
        effective_water_move=effective,
        duration_seconds=float(seconds),
        distance_yards=distance,
        fatigue_interval_seconds=interval,
        fatigue_rolls=rolls,
        fatigue_target=target,
    )
