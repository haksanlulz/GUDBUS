# formulas only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Standard-magic spell math (B234-242): energy cost, casting time, ceremonial pooling, range penalties, missile damage."""

from __future__ import annotations

import math
from dataclasses import dataclass

from gurps_bot.mechanics.dice import DiceSpec

PAGE = "B234-242"

# B236 energy reduction, keyed on base skill (only low mana modifies it):
# 0 below 15, 1 at 15-19, 2 at 20-24, +1 per full 5 beyond 20
_REDUCTION_FIRST_TIER = 15
_REDUCTION_SECOND_TIER = 20
_LOW_MANA_PENALTY = 5  # -5 to base skill in a low-mana area (B235)

# Casting-time tiers (B236-237).
_TIME_DOUBLE_AT_OR_BELOW = 9  # base skill <= 9 doubles casting time
_TIME_HALVE_FROM = 20  # base skill >= 20 starts halving (then /4, /8, ...)
_CEREMONIAL_TIME_MULTIPLIER = 10  # ceremonial magic multiplies time by 10 (B238)

# Ceremonial assistant contribution caps (B238).
_CAPPED_ASSISTANT_CONTRIB = 3  # non-mage 15+ / mage <=14: up to 3 points each
_SUPPORTER_CONTRIB = 1  # each supporting spectator: +1 ...
_SUPPORTER_CAP = 100  # ... to a maximum of +100 from all spectators
_OPPOSER_PENALTY = 5  # each opposing spectator: -5 ...
_OPPOSER_CAP = 100  # ... to a maximum of -100 from all opposers

# Extra-energy skill-bonus table (B238): surplus energy as a fraction of cost.
_EXTRA_ENERGY_TIERS = ((0.2, 1), (0.4, 2), (0.6, 3))  # below 100%
# At >= 100% surplus the bonus is +4, then +1 per additional full +100%.
_EXTRA_ENERGY_BASE_BONUS = 4

# Long-distance modifier table (B241): (inclusive max distance in miles, penalty).
_YARDS_PER_MILE = 1760
_LONG_DISTANCE_BRACKETS = (
    (200 / _YARDS_PER_MILE, 0),  # up to 200 yards
    (0.5, -1),
    (1, -2),
    (3, -3),
    (10, -4),
    (30, -5),
    (100, -6),
    (300, -7),
    (1000, -8),
)
_LD_BEYOND_BASE = -8  # penalty at 1,000 miles
_LD_BEYOND_BASE_MILES = 1000  # ... and -2 per additional factor of 10
_LD_BEYOND_PER_DECADE = 2

_CANT_SEE_OR_TOUCH_PENALTY = 5  # extra -5 for a Regular spell (B240)


def _effective_skill(skill: int, low_mana: bool) -> int:
    return skill - (_LOW_MANA_PENALTY if low_mana else 0)


def spell_energy_reduction(skill: int, *, low_mana: bool = False) -> int:
    """High-skill energy reduction (B236); applies to casting and maintenance alike."""
    effective_skill = _effective_skill(skill, low_mana)
    if effective_skill < _REDUCTION_FIRST_TIER:
        return 0
    if effective_skill < _REDUCTION_SECOND_TIER:
        return 1
    return 2 + (effective_skill - _REDUCTION_SECOND_TIER) // 5


@dataclass(frozen=True, slots=True)
class SpellCostResult:
    """Energy cost of one casting, scaled for size/area then reduced (B236-240)."""

    base_cost: float
    scaled_cost: int  # after size/area multiplier, before high-skill reduction
    reduction: int  # high-skill energy reduction subtracted
    final_cost: int  # max(0, scaled - reduction)
    size_modifier: int
    area_radius: int
    low_mana: bool

    def __str__(self) -> str:
        shape = (
            f" area r{self.area_radius}" if self.area_radius > 0
            else f" SM+{self.size_modifier}" if self.size_modifier > 0
            else ""
        )
        return (
            f"cost {self.base_cost:g}{shape} -> {self.scaled_cost}"
            f" - {self.reduction} (skill) = {self.final_cost} FP"
        )


def effective_spell_cost(
    base_cost: float,
    skill: int,
    *,
    size_modifier: int = 0,
    area_radius: int = 0,
    low_mana: bool = False,
) -> SpellCostResult:
    """Casting cost (B236-240): scale for SM or area first, then subtract the high-skill reduction."""
    if size_modifier > 0 and area_radius > 0:
        raise ValueError("A spell is Regular (size_modifier) xor Area (area_radius), not both")
    if base_cost < 0:
        raise ValueError("base_cost must be non-negative")
    if area_radius < 0:
        raise ValueError("area_radius must be non-negative")

    multiplier = (
        area_radius if area_radius > 0
        else 1 + size_modifier if size_modifier > 0
        else 1
    )
    # B240's minimum-1-energy for fractional bases needs no guard: multiplier is an
    # int >= 1, so ceil of a positive product is already >= 1
    scaled = math.ceil(base_cost * multiplier)

    reduction = spell_energy_reduction(skill, low_mana=low_mana)
    final = max(0, scaled - reduction)
    return SpellCostResult(
        base_cost=base_cost,
        scaled_cost=scaled,
        reduction=reduction,
        final_cost=final,
        size_modifier=size_modifier,
        area_radius=area_radius,
        low_mana=low_mana,
    )


def maintenance_cost(base_maintain: int, skill: int, *, low_mana: bool = False) -> int:
    """Maintenance cost (B237): same high-skill reduction as casting; 0 = maintainable forever."""
    return max(0, base_maintain - spell_energy_reduction(skill, low_mana=low_mana))


def casting_time(
    base_seconds: int,
    skill: int,
    *,
    low_mana: bool = False,
    ceremonial: bool = False,
) -> int:
    """Casting seconds (B236-238): skill <= 9 doubles, 20+ halves per 5 levels; ceremonial = x10, no reduction."""
    if base_seconds < 1:
        raise ValueError("base_seconds must be at least 1")
    if ceremonial:
        return base_seconds * _CEREMONIAL_TIME_MULTIPLIER

    effective_skill = _effective_skill(skill, low_mana)
    if effective_skill <= _TIME_DOUBLE_AT_OR_BELOW:
        return base_seconds * 2
    if effective_skill < _TIME_HALVE_FROM:
        return base_seconds
    divisor = 2 ** ((effective_skill - _TIME_HALVE_FROM) // 5 + 1)
    return max(1, math.ceil(base_seconds / divisor))


def _extra_energy_bonus(ratio: float) -> int:
    if ratio < _EXTRA_ENERGY_TIERS[0][0]:
        return 0
    if ratio >= 1.0:
        return _EXTRA_ENERGY_BASE_BONUS + math.floor(ratio - 1.0)
    # below +100%: highest tier met; the early return above guarantees at least one
    return max(bonus for threshold, bonus in _EXTRA_ENERGY_TIERS if ratio >= threshold)


@dataclass(frozen=True, slots=True)
class CeremonialResult:
    """Pooled energy + skill bonus from a ceremonial casting (B238)."""

    spell_cost: int
    total_energy: int
    extra_energy: int  # total - spell_cost (0 if the pool fell short)
    skill_bonus: int
    time_multiplier: int  # always 10 for ceremonial magic
    coordination_note: str

    def __str__(self) -> str:
        return (
            f"ceremonial: {self.total_energy} energy vs cost {self.spell_cost}"
            f" -> +{self.skill_bonus} skill (x{self.time_multiplier} time)"
        )


def ceremonial_energy(
    spell_cost: int,
    *,
    caster_energy: int = 0,
    mage_energy: int = 0,
    skilled_nonmages: int = 0,
    low_skill_mages: int = 0,
    supporters: int = 0,
    opposers: int = 0,
) -> CeremonialResult:
    """Pool ceremonial energy (B238); mage_energy is pre-summed by the caller, surplus over cost buys a skill bonus."""
    if spell_cost < 1:
        raise ValueError("spell_cost must be at least 1")
    for name, value in (
        ("caster_energy", caster_energy),
        ("mage_energy", mage_energy),
        ("skilled_nonmages", skilled_nonmages),
        ("low_skill_mages", low_skill_mages),
        ("supporters", supporters),
        ("opposers", opposers),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")

    # floored at 0 so heavy opposition can't drive the pool negative
    total = max(
        0,
        caster_energy
        + mage_energy
        + _CAPPED_ASSISTANT_CONTRIB * (skilled_nonmages + low_skill_mages)
        + min(_SUPPORTER_CAP, _SUPPORTER_CONTRIB * supporters)
        - min(_OPPOSER_CAP, _OPPOSER_PENALTY * opposers),
    )

    extra = total - spell_cost
    skill_bonus = _extra_energy_bonus(extra / spell_cost) if extra > 0 else 0
    note = (
        "Ceremonial: casting time x10; high skill gives no cost/time reduction; "
        "a roll of 16 always fails and 17-18 always critically fails."
    )
    return CeremonialResult(
        spell_cost=spell_cost,
        total_energy=total,
        extra_energy=max(0, extra),
        skill_bonus=skill_bonus,
        time_multiplier=_CEREMONIAL_TIME_MULTIPLIER,
        coordination_note=note,
    )


def long_distance_modifier(
    *, yards: float | None = None, miles: float | None = None
) -> int:
    """Long-distance penalty for Information/Seek spells (B241); between rows use the worse bracket."""
    if (yards is None) == (miles is None):
        raise ValueError("Provide exactly one of yards or miles.")
    distance_miles = (yards / _YARDS_PER_MILE) if yards is not None else float(miles)
    if distance_miles < 0:
        raise ValueError("distance must be non-negative")

    for bound_miles, penalty in _LONG_DISTANCE_BRACKETS:
        if distance_miles <= bound_miles:
            return penalty
    # past 1,000 mi: -2 per factor of 10, partial decades round up (worse bracket)
    decades = math.ceil(math.log10(distance_miles / _LD_BEYOND_BASE_MILES))
    return _LD_BEYOND_BASE - _LD_BEYOND_PER_DECADE * decades


def regular_spell_distance_penalty(
    yards: float, *, can_touch: bool = False, can_see: bool = True
) -> int:
    """Regular-spell range penalty (B240): free if touching, else -1/yard, -5 more if unseen and untouched."""
    if yards < 0:
        raise ValueError("yards must be non-negative")
    if can_touch:
        return 0
    surcharge = _CANT_SEE_OR_TOUCH_PENALTY if not can_see else 0
    return -math.ceil(yards) - surcharge


def missile_spell_damage(
    magery: int, *, seconds: int = 1, energy: int | None = None
) -> DiceSpec:
    """Missile-spell dice (B240): 1d per energy point, capped at magery * min(seconds, 3)."""
    if magery < 0:
        raise ValueError("magery must be non-negative")
    if seconds < 1:
        raise ValueError("seconds must be at least 1")
    max_energy = magery * min(seconds, 3)
    invested = max(0, max_energy if energy is None else min(energy, max_energy))
    return DiceSpec(count=invested, sides=6, modifier=0)
