"""collision & slam damage (B430, B431, B371) — formulas only, no SJG prose"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from gurps_bot.mechanics.dice import DiceSpec

# mirror dice.py's 100-die ceiling
_MAX_DICE = 100


class CollisionAngle(Enum):
    """B431 collision geometry — selects how closing velocity is computed (see collision_velocity)"""

    HEAD_ON = "head-on"
    REAR_END = "rear-end"
    SIDE_ON = "side-on"


@dataclass(frozen=True, slots=True)
class CollisionParty:
    """HP drives damage (it already encodes mass/structure); weight is advisory only"""

    hp: int
    velocity: int
    weight: float | None = None
    streamlined: bool = False
    damage_type: str = "cr"
    size_modifier: int = 0


@dataclass(frozen=True, slots=True)
class CollisionResult:
    collision_velocity: int
    striker_damage: DiceSpec
    struck_damage: DiceSpec
    striker_type: str
    struck_type: str
    struck_dice_capped: bool
    overrun_thrust_st: int | None


def collision_dice(
    hp: int,
    velocity: int,
    *,
    half_damage: bool = False,
    hard_multiplier: int = 1,
) -> DiceSpec:
    """B430: x = hp * velocity * hard_mult / 100 (halved if streamlined); x < 1 maps to 1d-3 / 1d-2 / 1d-1, else round half-up to whole dice"""
    if velocity <= 0:
        raise ValueError("Collision velocity must be positive (no closing = no collision)")
    if hp <= 0:
        raise ValueError("Collision HP must be positive")

    # B430's printed text renders the operation oddly; the worked examples
    # confirm multiplication (60-HP car at 20 yd/s = 12d)
    x = hp * velocity * hard_multiplier / 100
    if half_damage:
        x *= 0.5

    if x < 1.0:
        if x <= 0.25:
            modifier = -3
        elif x <= 0.5:
            modifier = -2
        else:
            modifier = -1
        return DiceSpec(count=1, sides=6, modifier=modifier)

    # floor(x + 0.5) = round half-up; round() would banker's-round
    count = math.floor(x + 0.5)
    if count > _MAX_DICE:
        raise ValueError(
            f"Collision dice count {count} exceeds the maximum of {_MAX_DICE} (dice.py limit)"
        )
    return DiceSpec(count=count, sides=6, modifier=0)


def collision_velocity(v_striker: int, v_struck: int, angle: CollisionAngle) -> int:
    """B431: head-on sums both speeds, rear-end subtracts (min 0), side-on counts only the striker's"""
    if angle is CollisionAngle.HEAD_ON:
        return v_striker + v_struck
    if angle is CollisionAngle.REAR_END:
        return max(0, v_striker - v_struck)
    # SIDE_ON / moving-vs-stationary / fall
    return v_striker


def resolve_collision(
    striker: CollisionParty,
    struck: CollisionParty,
    angle: CollisionAngle = CollisionAngle.SIDE_ON,
) -> CollisionResult:
    """mutual collision (B430-B432): shared closing velocity, each side's own HP; overrun thrust ST is surfaced, not rolled — no thrust table lives in mechanics"""
    v = collision_velocity(striker.velocity, struck.velocity, angle)

    striker_damage = collision_dice(
        striker.hp, v, half_damage=striker.streamlined, hard_multiplier=1
    )
    struck_damage = collision_dice(
        struck.hp, v, half_damage=struck.streamlined, hard_multiplier=1
    )

    # B431: struck can't out-dice the striker; sub-1d bands are all count 1, so
    # the cap only bites a strictly greater whole-die count
    struck_dice_capped = False
    if struck_damage.count > striker_damage.count:
        struck_damage = DiceSpec(
            count=striker_damage.count, sides=6, modifier=struck_damage.modifier
        )
        struck_dice_capped = True

    striker_type = striker.damage_type if striker.streamlined else "cr"
    struck_type = struck.damage_type if struck.streamlined else "cr"

    # B432 overrun: SM diff >= 2 -> bonus thrust at ST = HP/2
    overrun_thrust_st: int | None = None
    if striker.size_modifier - struck.size_modifier >= 2:
        overrun_thrust_st = striker.hp // 2

    return CollisionResult(
        collision_velocity=v,
        striker_damage=striker_damage,
        struck_damage=struck_damage,
        striker_type=striker_type,
        struck_type=struck_type,
        struck_dice_capped=struck_dice_capped,
        overrun_thrust_st=overrun_thrust_st,
    )


def resolve_slam(
    attacker_hp: int,
    attacker_move: int,
    target_hp: int,
    target_move_toward: int = 0,
) -> CollisionResult:
    """B371 slam via the collision engine; velocity = yards moved this turn plus the foe's move toward you"""
    # velocity is already the summed closing speed; SIDE_ON passes it through —
    # HEAD_ON would re-sum and double-count
    velocity = attacker_move + target_move_toward
    return resolve_collision(
        striker=CollisionParty(hp=attacker_hp, velocity=velocity),
        struck=CollisionParty(hp=target_hp, velocity=velocity),
        angle=CollisionAngle.SIDE_ON,
    )


def immovable_collision(
    hp: int,
    velocity: int,
    *,
    hard: bool = False,
    obstacle_hp_plus_dr: int | None = None,
) -> DiceSpec:
    """B431 immovable obstacle: hard doubles the mover's HP; a breakable obstacle clamps the die COUNT to HP+DR — a guaranteed-break bound, deliberately not a cap on the rolled total"""
    spec = collision_dice(hp, velocity, hard_multiplier=2 if hard else 1)

    if obstacle_hp_plus_dr is not None:
        # each die rolls at least 1, so count > HP+DR is guaranteed overkill;
        # floor of 1 keeps the spec legal
        max_count = max(1, obstacle_hp_plus_dr)
        if spec.count > max_count:
            spec = DiceSpec(count=max_count, sides=6, modifier=spec.modifier)

    return spec
