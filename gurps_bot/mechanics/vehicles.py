# formulas only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Vehicle movement / control / crash math (B462-470); vehicle stat tables are SJG content and not shipped — stats are inputs."""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass

from gurps_bot.mechanics.dice import DiceSpec
from gurps_bot.mechanics.fall import fall_damage_dice

PAGE = "B462-470"

_YPS_TO_MPH = 2.0  # "double yards/second to get mph" (B462)
_CRASH_HP_MULTIPLIER = 2  # immovable object = hard surface, 2x HP (B430/B431)
_SKID_FRACTION = 3  # a ground crash skids 1/3 of its velocity (B469)
_ROAD_BOUND_OFFROAD_ACCEL_FACTOR = 4  # off-road cap = min(top, 4 x Accel) (B466)
_DECEL_WHEELED = 5  # powered wheeled decel per turn (B468)
_DECEL_HEAVY = 10  # animal / tracked / walking decel per turn (B468)
_DECEL_AIR_WATER_BASE = 5  # air & water decel = 5 + Handling, min 1 (B468)
_CRUISING_ROUND_DP = 4  # round mph to kill float dust from 0.1/0.15/0.2 mults


class Terrain(enum.Enum):
    """Travel terrain band for a vehicle (B463/466)."""

    VERY_BAD = "very_bad"  # deep snow, swamp
    BAD = "bad"  # hills, woods
    AVERAGE = "average"  # dirt road, plains
    GOOD = "good"  # paved road, salt flats


class Locomotion(enum.Enum):
    """How a vehicle moves over ground (sets the terrain multiplier column)."""

    WHEELS = "wheels"
    RUNNERS = "runners"  # sleds/skids: like wheels only on Very Bad terrain
    TRACKS = "tracks"
    LEGS = "legs"
    OTHER = "other"  # any non-wheeled drivetrain not broken out above


class VehicleKind(enum.Enum):
    """Drivetrain class for the deceleration rule (B468)."""

    WHEELED_POWERED = "wheeled_powered"
    ANIMAL_TRACKED_WALKING = "animal_tracked_walking"
    AIR_WATER = "air_water"


# B463/466: mph per yd/s of Top Speed, by terrain x locomotion; the yd/s->mph
# conversion is folded in. NOT the hiking.py terrain table (B351) — same word,
# distinct rules, not shared
_CRUISING_MULT: dict[Terrain, dict[Locomotion, float]] = {
    Terrain.VERY_BAD: {
        Locomotion.WHEELS: 0.1,
        Locomotion.RUNNERS: 0.1,
        Locomotion.TRACKS: 0.15,
        Locomotion.LEGS: 0.2,
        Locomotion.OTHER: 0.2,
    },
    Terrain.BAD: {
        Locomotion.WHEELS: 0.25,
        Locomotion.RUNNERS: 0.5,
        Locomotion.TRACKS: 0.5,
        Locomotion.LEGS: 0.5,
        Locomotion.OTHER: 0.5,
    },
    Terrain.AVERAGE: {
        Locomotion.WHEELS: 0.5,
        Locomotion.RUNNERS: 1.0,
        Locomotion.TRACKS: 1.0,
        Locomotion.LEGS: 1.0,
        Locomotion.OTHER: 1.0,
    },
    Terrain.GOOD: {
        Locomotion.WHEELS: 1.25,
        Locomotion.RUNNERS: 1.25,
        Locomotion.TRACKS: 1.25,
        Locomotion.LEGS: 1.25,
        Locomotion.OTHER: 1.25,
    },
}

_DAMAGE_SCALE_DIVISORS = {"D": 10, "C": 100}


@dataclass(frozen=True, slots=True)
class VehicleCrashResult:
    """A vehicle crash / ram / bail-out: impact damage + ground skid (B468/430)."""

    velocity: int
    hp: int
    dice_float: float  # canonical fractional figure, (2 x HP x velocity)/100
    dice: DiceSpec  # whole crushing dice (rounded up)
    damage_type: str  # always 'cr'
    skid_yards: int  # ground crash skids 1/3 of velocity before stopping
    dr: int
    flying: bool  # if True, add falling damage from altitude separately (B467)

    def __str__(self) -> str:
        note = " +altitude fall" if self.flying else ""
        return (
            f"crash @ {self.velocity} yd/s -> {self.dice_float:g}d ({self.dice})"
            f" {self.damage_type}, skid {self.skid_yards} yd{note}"
        )


def yards_per_sec_to_mph(yps: float) -> float:
    """yd/s -> mph, the x2 RAW approximation (B462); single owner of the conversion."""
    return yps * _YPS_TO_MPH


def cruising_speed(
    top_speed: float,
    terrain: Terrain,
    *,
    locomotion: Locomotion = Locomotion.WHEELS,
    road_bound: bool = False,
    off_road: bool = False,
    acceleration: float | None = None,
) -> float:
    """Cruising mph over terrain (B463/466); road-bound off-road caps at min(top, 4*Accel), so acceleration is required there."""
    if top_speed < 0:
        raise ValueError("top_speed must be non-negative")

    effective_top = top_speed
    if road_bound and off_road:
        if acceleration is None:
            raise ValueError(
                "A road-bound vehicle off-road needs acceleration for the cap."
            )
        effective_top = min(top_speed, _ROAD_BOUND_OFFROAD_ACCEL_FACTOR * acceleration)

    mult = _CRUISING_MULT[terrain][locomotion]
    return round(effective_top * mult, _CRUISING_ROUND_DP)


def endurance(range_miles: float, cruising_mph: float) -> float:
    """Endurance in hours: Range / cruising speed (B463)."""
    if range_miles < 0:
        raise ValueError("range_miles must be non-negative")
    if cruising_mph <= 0:
        raise ValueError("cruising_mph must be positive")
    return round(range_miles / cruising_mph, _CRUISING_ROUND_DP)


def vehicle_dodge(control_skill: int, handling: int) -> int:
    """Vehicle Dodge: control_skill // 2 + Handling (B470)."""
    if control_skill < 0:
        raise ValueError("control_skill must be non-negative")
    return math.floor(control_skill / 2) + handling


def control_effective_skill(
    control_skill: int, handling: int, visibility: int = 0
) -> int:
    """Control-roll skill (B466): skill + Handling + visibility (0 to -10 for darkness/fog); caller rolls via checks."""
    return control_skill + handling + visibility


def classify_control_failure(
    margin_of_failure: int, sr: int, critical: bool = False
) -> str:
    """Failed control roll: minor if margin <= SR, else major; criticals always major (B466-467)."""
    if margin_of_failure < 0:
        raise ValueError("margin_of_failure must be non-negative")
    if sr < 0:
        raise ValueError("sr must be non-negative")
    if critical:
        return "major"
    return "minor" if margin_of_failure <= sr else "major"


def deceleration(handling: int, kind: VehicleKind = VehicleKind.WHEELED_POWERED) -> int:
    """Safe decel in yd/s per turn (B468): wheeled 5, animal/tracked/walking 10, air/water 5 + Handling min 1; braking harder needs a control roll."""
    if kind is VehicleKind.WHEELED_POWERED:
        return _DECEL_WHEELED
    if kind is VehicleKind.ANIMAL_TRACKED_WALKING:
        return _DECEL_HEAVY
    return max(1, _DECEL_AIR_WATER_BASE + handling)


def crash(velocity: int, hp: int, *, dr: int = 0, flying: bool = False) -> VehicleCrashResult:
    """Crash = fall at velocity onto a hard surface, 2x HP (B468/430), via fall.fall_damage_dice; skid velocity//3 (B469)."""
    if velocity < 0:
        raise ValueError("velocity must be non-negative")
    if hp <= 0:
        raise ValueError("hp must be positive")
    if dr < 0:
        raise ValueError("dr must be non-negative")

    dice_float, spec = fall_damage_dice(hp, velocity, _CRASH_HP_MULTIPLIER)
    return VehicleCrashResult(
        velocity=velocity,
        hp=hp,
        dice_float=dice_float,
        dice=spec,
        damage_type="cr",
        skid_yards=velocity // _SKID_FRACTION,
        dr=dr,
        flying=flying,
    )


def damage_scale(value: float, scale: str = "D") -> int:
    """Big-vehicle damage scale (B470): D /10, C /100, 0.5 rounds up; the sub-1d dice exception is the caller's problem."""
    divisor = _DAMAGE_SCALE_DIVISORS.get(scale.upper())
    if divisor is None:
        raise ValueError("scale must be 'D' (decade) or 'C' (century)")
    return math.floor(value / divisor + 0.5)
