# formulas/constants only, no SJG prose; GURPS is a trademark of Steve Jackson
# Games — unofficial, unaffiliated
"""explosion math (B414-415): concussion falloff + fragmentation; pure — callers roll the dice"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

# per-yard divisor (B414 normal, B415 variants); collateral =
# floor(basic / (divisor * distance)) at distance >= 1
_ENVIRONMENT_DIVISORS: dict[str, int] = {
    "normal": 3,
    "underwater": 1,
    "vacuum": 10,
}

# base fragment attack skill before the three allowed modifiers (B414)
_FRAGMENT_BASE_SKILL = 15

# B414: danger radius = 5 * frag_dice yards
_RADIUS_PER_FRAG_DIE = 5


@dataclass(frozen=True, slots=True)
class CollateralAtRange:
    distance: int  # yards from blast center (0 = the directly-struck target)
    damage: int  # floored collateral damage (>= 0; equals basic_damage at distance 0)


@dataclass(frozen=True, slots=True)
class FragmentationAttack:
    distance: int  # yards from blast center
    danger_radius: int  # 5 * frag_dice, the outer edge of fragment vulnerability
    in_radius: bool  # whether distance <= danger_radius (fragments can reach)
    auto_hit: bool  # True only when distance == 0 (direct strike, automatic hit)
    effective_skill: int  # 15 + range_penalty + posture_mod + size_mod (B414)
    frag_dice: int  # number of fragmentation dice; each hit rolls this many d6 cutting


@dataclass(frozen=True, slots=True)
class ExplosionResult:
    basic_damage: int  # the pre-rolled basic explosion damage fed in
    environment: str  # 'normal' | 'underwater' | 'vacuum' (selects per-yard divisor)
    collateral: tuple[CollateralAtRange, ...]  # one entry per requested distance
    frag_dice: int | None  # None if the weapon has no fragmentation; else dice count
    danger_radius: int | None  # 5 * frag_dice, or None when frag_dice is None
    fragmentation: tuple[FragmentationAttack, ...]  # per-distance attacks; () if none


def explosion_collateral(
    basic_damage: int,
    distances: Sequence[int],
    *,
    environment: str = "normal",
) -> tuple[CollateralAtRange, ...]:
    """B414-415: distance 0 takes full basic damage, else floor(basic / (divisor * distance)); no armor-divisor param — it never applies to collateral"""
    divisor_per_yard = _resolve_divisor(environment)

    results: list[CollateralAtRange] = []
    for distance in distances:
        if distance < 0:
            raise ValueError(f"distance cannot be negative: {distance}")
        if distance == 0:
            damage = max(0, basic_damage)
        else:
            damage = max(0, basic_damage // (divisor_per_yard * distance))
        results.append(CollateralAtRange(distance=distance, damage=damage))

    return tuple(results)


def fragmentation_radius(frag_dice: int) -> int:
    """danger radius = 5 * frag_dice yards (B414); no-frag weapons signal with None at the caller, never 0"""
    if frag_dice < 1:
        raise ValueError(f"frag_dice must be at least 1: {frag_dice}")
    return _RADIUS_PER_FRAG_DIE * frag_dice


def fragmentation_attack(
    frag_dice: int,
    distance: int,
    *,
    posture_mod: int = 0,
    size_mod: int = 0,
    range_penalty: int = 0,
) -> FragmentationAttack:
    """fragment attack at one distance (B414): skill 15 + range/posture/SM only; caller rolls the 3d6 and supplies the B550 range penalty"""
    if distance < 0:
        raise ValueError(f"distance cannot be negative: {distance}")

    radius = fragmentation_radius(frag_dice)  # validates frag_dice >= 1
    effective_skill = _FRAGMENT_BASE_SKILL + range_penalty + posture_mod + size_mod

    return FragmentationAttack(
        distance=distance,
        danger_radius=radius,
        in_radius=distance <= radius,
        auto_hit=distance == 0,
        effective_skill=effective_skill,
        frag_dice=frag_dice,
    )


def fragments_hitting(margin_of_success: int) -> int:
    """hits = 1 + margin // 3 (B414), 0 on a miss; uncapped by design"""
    if margin_of_success < 0:
        return 0
    return 1 + margin_of_success // 3


def explosion_report(
    basic_damage: int,
    distances: Sequence[int],
    *,
    frag_dice: int | None = None,
    environment: str = "normal",
) -> ExplosionResult:
    """collateral + optional fragmentation in one bundle; frag mods zeroed — use fragmentation_attack for per-target modifiers"""
    # fail on a bad environment even with no distances
    _resolve_divisor(environment)

    collateral = explosion_collateral(
        basic_damage, distances, environment=environment
    )

    danger_radius: int | None = None
    fragmentation: tuple[FragmentationAttack, ...] = ()
    if frag_dice is not None:
        danger_radius = fragmentation_radius(frag_dice)  # validates frag_dice >= 1
        fragmentation = tuple(
            fragmentation_attack(frag_dice, c.distance) for c in collateral
        )

    return ExplosionResult(
        basic_damage=basic_damage,
        environment=environment,
        collateral=collateral,
        frag_dice=frag_dice,
        danger_radius=danger_radius,
        fragmentation=fragmentation,
    )


def _resolve_divisor(environment: str) -> int:
    try:
        return _ENVIRONMENT_DIVISORS[environment]
    except KeyError:
        valid = ", ".join(sorted(_ENVIRONMENT_DIVISORS))
        raise ValueError(
            f"unknown environment {environment!r}; expected one of: {valid}"
        ) from None
