# formulas/constants only (B431), no SJG prose; GURPS is a trademark of
# Steve Jackson Games
"""fall damage (B431): velocity -> crushing dice, with acrobatics/catfall/surface/blunt-trauma handling"""

from __future__ import annotations

import math
from dataclasses import dataclass

from gurps_bot.mechanics.dice import DiceSpec, RollResult, roll

_FEET_PER_YARD = 3.0
_VELOCITY_K = 21.4  # GURPS falling-velocity constant (B431).
_DICE_DIVISOR = 100  # (hp_mult * HP * v) / 100 -> dice.
_BLUNT_TRAUMA_PER = 5  # 1 HP injury per full 5 points stopped (B379).
_CATFALL_REDUCTION = 5  # yards subtracted for Catfall (B41).
_ACROBATICS_REDUCTION = 5  # yards subtracted on a controlled-fall success.


@dataclass(frozen=True, slots=True)
class FallResult:
    distance_yards: float
    effective_distance_yards: float
    velocity: int
    hp: int
    surface: str
    hp_multiplier: int
    dice_float: float
    dice: DiceSpec
    damage_type: str
    acrobatics_success: bool
    has_catfall: bool
    total_dr: int
    roll_result: RollResult | None
    penetrating_damage: int | None
    blunt_trauma: int | None

    def __str__(self) -> str:
        base = (
            f"fall {self.distance_yards:g}yd"
            f" (eff {self.effective_distance_yards:g}yd)"
            f" -> v{self.velocity} -> {self.dice_float:g}d"
            f" = {self.dice} {self.damage_type}"
        )
        if self.roll_result is not None:
            base += (
                f" | rolled {self.roll_result.total},"
                f" {self.penetrating_damage} pen"
            )
            if self.blunt_trauma:
                base += f", {self.blunt_trauma} blunt"
        return base


def feet_to_yards(feet: float) -> float:
    return feet / _FEET_PER_YARD


def fall_velocity(
    distance_yards: float,
    gravity: float = 1.0,
    terminal_velocity: int | None = 60,
) -> int:
    """B431: v = round(sqrt(21.4 * g * yd)), capped at terminal (60 spread-eagle, 100 dive, None uncapped); diverges ~1 yd/s from the printed table's midpoint rounding at some boundaries — the formula is the source of truth here"""
    product = _VELOCITY_K * gravity * distance_yards
    if product <= 0:
        return 0
    velocity = round(math.sqrt(product))
    if terminal_velocity is not None and velocity > terminal_velocity:
        return terminal_velocity
    return velocity


def fall_damage_dice(
    hp: int,
    velocity: int,
    hp_multiplier: int = 2,
) -> tuple[float, DiceSpec]:
    """B431: (mult * hp * v) / 100 -> (dice_float, spec); spec ceils to whole dice, the float is kept for the canonical fractional display (3.8d)"""
    dice_float = (hp_multiplier * hp * velocity) / _DICE_DIVISOR
    count = math.ceil(dice_float) if dice_float > 0 else 0
    return dice_float, DiceSpec(count=count, sides=6, modifier=0)


def compute_fall(
    *,
    distance_yards: float | None = None,
    distance_feet: float | None = None,
    hp: int,
    dr: int = 0,
    gravity: float = 1.0,
    surface: str = "hard",
    surface_dr: int = 0,
    acrobatics_success: bool = False,
    has_catfall: bool = False,
    terminal_velocity: int | None = 60,
    roll_damage: bool = False,
) -> FallResult:
    """full fall pipeline (B431): acrobatics/catfall each shave 5 yd (they stack), catfall then halves the damage; blunt trauma (B379) needs dr = WORN armor only, innate DR must not count"""
    if (distance_yards is None) == (distance_feet is None):
        raise ValueError(
            "Provide exactly one of distance_yards or distance_feet."
        )

    yards = (
        float(distance_yards)
        if distance_yards is not None
        else feet_to_yards(float(distance_feet))  # type: ignore[arg-type]
    )

    effective = yards
    if acrobatics_success:
        effective -= _ACROBATICS_REDUCTION
    if has_catfall:
        effective -= _CATFALL_REDUCTION
    effective = max(0.0, effective)

    velocity = fall_velocity(effective, gravity, terminal_velocity)

    hp_mult = 2 if surface == "hard" else 1

    dice_float, spec = fall_damage_dice(hp, velocity, hp_mult)

    # catfall halves, then re-ceil the halved float (B41 worked case:
    # 4.6d -> 2.3d -> 3d)
    if has_catfall:
        dice_float = dice_float / 2
        halved_count = math.ceil(dice_float) if dice_float > 0 else 0
        spec = DiceSpec(count=halved_count, sides=6, modifier=0)

    total_dr = dr + surface_dr

    roll_result: RollResult | None = None
    penetrating: int | None = None
    blunt_trauma: int | None = None
    if roll_damage and spec.count > 0:
        roll_result = roll(spec)
        rolled_total = roll_result.total
        penetrating = max(0, rolled_total - total_dr)
        # B379: blunt trauma only when armor fully stops penetration
        blunt_trauma = (
            rolled_total // _BLUNT_TRAUMA_PER if penetrating == 0 else 0
        )

    return FallResult(
        distance_yards=yards,
        effective_distance_yards=effective,
        velocity=velocity,
        hp=hp,
        surface=surface,
        hp_multiplier=hp_mult,
        dice_float=dice_float,
        dice=spec,
        damage_type="cr",
        acrobatics_success=acrobatics_success,
        has_catfall=has_catfall,
        total_dr=total_dr,
        roll_result=roll_result,
        penetrating_damage=penetrating,
        blunt_trauma=blunt_trauma,
    )
