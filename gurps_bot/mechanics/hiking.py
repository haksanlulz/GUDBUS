# formulas/numbers only (B351, FP costs B426), no SJG prose; GURPS is a
# trademark of Steve Jackson Games
"""daily march distance (B351) + forced-march FP (B426); the once-a-day Hiking roll is the caller's — B351 defines no footwear modifier, its absence is deliberate"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from gurps_bot.mechanics import encumbrance as _enc


class Encumbrance(enum.Enum):
    """B17 levels; .value is the Move multiplier (sourced from encumbrance.py), declaration order gives the 0-4 index"""

    NONE = _enc.move_multiplier(0)
    LIGHT = _enc.move_multiplier(1)
    MEDIUM = _enc.move_multiplier(2)
    HEAVY = _enc.move_multiplier(3)
    EXTRA_HEAVY = _enc.move_multiplier(4)

    @property
    def level(self) -> int:
        """0-4 index of this level in declaration order (None=0 ... X-Heavy=4)."""
        return list(Encumbrance).index(self)


class Terrain(enum.Enum):
    """B351 terrain band; the caller folds road + weather into the band choice (dirt road in rain = VERY_BAD)"""

    VERY_BAD = "very_bad"
    BAD = "bad"
    AVERAGE = "average"
    GOOD = "good"

    @property
    def mult(self) -> float:
        return _TERRAIN_MULT[self]


class Weather(enum.Enum):
    """B351 weather; SNOW_DEEP is the 'divide by 4 or more' floor — going lower is GM territory"""

    CLEAR = "clear"
    RAIN = "rain"
    SNOW_ANKLE = "snow_ankle"
    SNOW_DEEP = "snow_deep"
    ICE = "ice"

    @property
    def mult(self) -> float:
        return _WEATHER_MULT[self]


# terrain multipliers (B351)
_TERRAIN_MULT: dict[Terrain, float] = {
    Terrain.VERY_BAD: 0.20,
    Terrain.BAD: 0.50,
    Terrain.AVERAGE: 1.00,
    Terrain.GOOD: 1.25,
}

# weather multipliers (B351)
_WEATHER_MULT: dict[Weather, float] = {
    Weather.CLEAR: 1.0,
    Weather.RAIN: 0.5,
    Weather.SNOW_ANKLE: 0.5,
    Weather.SNOW_DEEP: 0.25,
    Weather.ICE: 0.5,
}

# per-hour forced-march FP by level index 0-4 (B426)
_FP_PER_HOUR_BASE: tuple[int, ...] = (1, 2, 3, 4, 5)


@dataclass(frozen=True, slots=True)
class HikingResult:
    basic_move: int
    effective_move: int
    encumbrance: Encumbrance
    terrain: Terrain
    weather: Weather
    hiking_success: bool
    base_miles: int
    terrain_mult: float
    weather_mult: float
    skill_mult: float
    enhanced_move_mult: float
    miles_per_day: int
    fp_per_hour: int
    fp_note: str

    def __str__(self) -> str:
        skill = " (Hiking +20%)" if self.hiking_success else ""
        em = (
            f" x{self.enhanced_move_mult:g} Enhanced Move"
            if self.enhanced_move_mult != 1.0
            else ""
        )
        return (
            f"Move {self.effective_move} -> {self.base_miles} mi ideal x"
            f"{self.terrain_mult:g} ({self.terrain.name.lower()}) x"
            f"{self.weather_mult:g} ({self.weather.name.lower()}){skill}{em} = "
            f"{self.miles_per_day} mi/day; {self.fp_per_hour} FP/hr march"
        )


def encumbrance_move_multiplier(level: Encumbrance) -> float:
    return _enc.move_multiplier(level.level)


def effective_move(basic_move: int, encumbrance: Encumbrance) -> int:
    """delegates to encumbrance.effective_move (hiking has no overloaded band)"""
    return _enc.effective_move(basic_move, encumbrance.level)


def fp_cost_per_hour(
    encumbrance: Encumbrance,
    hot_day: bool = False,
    heavy_garb: bool = False,
) -> int:
    """B426: base 1-5 by encumbrance; hot day +1, or +2 with plate/heavy garb (replaces the +1, irrelevant on a temperate day)"""
    cost = _FP_PER_HOUR_BASE[encumbrance.level]
    if hot_day:
        cost += 2 if heavy_garb else 1
    return cost


def calc_hiking(
    basic_move: int,
    encumbrance: Encumbrance = Encumbrance.NONE,
    terrain: Terrain = Terrain.AVERAGE,
    weather: Weather = Weather.CLEAR,
    hiking_success: bool = False,
    enhanced_move_mult: float = 1.0,
) -> HikingResult:
    """miles/day = round(10 * move * terrain * weather * 1.2-if-skill * em), rounded once at the very end (B351; B426); enhanced_move_mult only multiplies up (>= 1.0)"""
    if enhanced_move_mult < 1.0:
        raise ValueError("enhanced_move_mult must be >= 1.0 (Enhanced Move only multiplies up)")

    eff = effective_move(basic_move, encumbrance)  # validates basic_move >= 0
    base_miles = 10 * eff
    terrain_mult = terrain.mult
    weather_mult = weather.mult
    skill_mult = 1.2 if hiking_success else 1.0

    distance = base_miles * terrain_mult * weather_mult * skill_mult * enhanced_move_mult
    miles_per_day = max(0, round(distance))

    fp_per_hour = fp_cost_per_hour(encumbrance)
    fp_note = (
        f"Forced march costs {fp_per_hour} FP/hour at {encumbrance.name.lower()} "
        f"encumbrance (+1/hour on a hot day, +2 for plate/heavy garb); B426."
    )

    return HikingResult(
        basic_move=basic_move,
        effective_move=eff,
        encumbrance=encumbrance,
        terrain=terrain,
        weather=weather,
        hiking_success=hiking_success,
        base_miles=base_miles,
        terrain_mult=terrain_mult,
        weather_mult=weather_mult,
        skill_mult=skill_mult,
        enhanced_move_mult=enhanced_move_mult,
        miles_per_day=miles_per_day,
        fp_per_hour=fp_per_hour,
        fp_note=fp_note,
    )
