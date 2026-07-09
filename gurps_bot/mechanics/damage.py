"""damage rolls + wounding multipliers; hit-location to-hit penalties are owned by hit_location.py and sourced from there"""

from __future__ import annotations

from dataclasses import dataclass

from gurps_bot.mechanics.dice import RollResult, roll
from gurps_bot.mechanics.hit_location import hit_location_names
from gurps_bot.mechanics.hit_location import penalty_for as _loc_penalty

# wounding multipliers by damage type (B378-379)
WOUNDING_MULTIPLIERS: dict[str, float] = {
    "pi-": 0.5,
    "cr": 1.0,
    "burn": 1.0,
    "pi": 1.0,
    "tox": 1.0,
    "cor": 1.0,
    "cut": 1.5,
    "pi+": 1.5,
    "imp": 2.0,
    "pi++": 2.0,
}

# per-location wounding overrides (B398-400) — replace the base multiplier.
# type-specific keys beat "all" (B399: skull/eye x4 excludes toxic).
# no tight-beam burn flag in the engine, so the vitals burn x2 case is out of scope.
LOCATION_MULTIPLIERS: dict[str, dict[str, float]] = {
    "skull": {"all": 4.0, "tox": 1.0},
    "eye": {"all": 4.0, "tox": 1.0},
    "vitals": {"imp": 3.0, "pi": 3.0, "pi+": 3.0, "pi++": 3.0},
    "neck": {"cr": 1.5, "cor": 1.5, "cut": 2.0},
    "face": {"cor": 1.5},  # B399: otherwise torso wounding; cor major wound also blinds an eye (GM call)
    "groin": {},  # B399: torso wounding; cr doubles SHOCK on males, not injury
}

# display names for UI choices
DAMAGE_TYPE_DISPLAY: dict[str, str] = {
    "cr": "Crushing (cr)",
    "cut": "Cutting (cut)",
    "imp": "Impaling (imp)",
    "pi": "Piercing (pi)",
    "pi-": "Sm. Piercing (pi-)",
    "pi+": "Lg. Piercing (pi+)",
    "pi++": "Huge Piercing (pi++)",
    "burn": "Burning (burn)",
    "tox": "Toxic (tox)",
    "cor": "Corrosion (cor)",
}

# 3d6 -> location (B552); this owns the roll ranges only, penalties come from
# hit_location.py so no number is typed twice
_HIT_LOCATION_RANGES: list[tuple[range, str]] = [
    (range(3, 5), "Skull"),
    (range(5, 6), "Face"),
    (range(6, 7), "Right Leg"),
    (range(7, 8), "Right Leg"),
    (range(8, 9), "Right Arm"),
    (range(9, 11), "Torso"),
    (range(11, 12), "Groin"),
    (range(12, 13), "Left Arm"),
    (range(13, 14), "Left Leg"),
    (range(14, 15), "Left Leg"),
    (range(15, 16), "Hand"),
    (range(16, 17), "Foot"),
    (range(17, 19), "Neck"),
]

#: back-compat (range, location, penalty) rows, penalty pulled from the owner
HIT_LOCATION_TABLE: list[tuple[range, str, int]] = [
    (rng, loc, _loc_penalty(loc)) for rng, loc in _HIT_LOCATION_RANGES
]

# derived from hit_location.py — random-table locations plus the deliberate-only
# extras, no separately-maintained list
HIT_LOCATION_NAMES: list[str] = hit_location_names()


@dataclass(frozen=True, slots=True)
class DamageResult:
    roll_result: RollResult
    damage_type: str
    raw_damage: int
    wounding_multiplier: float
    wound: int
    location: str | None

    def __str__(self) -> str:
        loc = f" to {self.location}" if self.location else ""
        return (
            f"{self.roll_result.spec} {self.damage_type} = "
            f"{self.raw_damage} raw (x{self.wounding_multiplier}) = "
            f"{self.wound} wound{loc}"
        )


@dataclass(frozen=True, slots=True)
class HitLocationResult:
    rolled: int
    location: str
    hit_penalty: int


def parse_gcs_damage(damage_str: str) -> tuple[str, str]:
    """'8d burn' -> ('8d', 'burn'); no recognized suffix -> 'cr'"""
    damage_str = damage_str.strip()
    for suffix in WOUNDING_MULTIPLIERS:
        if damage_str.lower().endswith(f" {suffix}"):
            dice = damage_str[:-(len(suffix) + 1)].strip()
            return dice, suffix
    return damage_str, "cr"


def roll_damage(
    dice_expr: str,
    damage_type: str,
    dr: int = 0,
    location: str | None = None,
) -> DamageResult:
    """roll dice_expr (pure dice, no type suffix) against DR with the wounding multiplier for type/location"""
    damage_type = damage_type.lower().strip()
    if not damage_type:
        damage_type = "cr"

    dr = max(0, dr)  # DR is never negative; unclamped it would inflate the wound
    result = roll(dice_expr)
    raw = max(0, result.total - dr)

    mult = WOUNDING_MULTIPLIERS.get(damage_type, 1.0)
    if location:
        loc_key = location.lower()
        loc_overrides = LOCATION_MULTIPLIERS.get(loc_key, {})
        if damage_type in loc_overrides:
            mult = loc_overrides[damage_type]
        elif "all" in loc_overrides:
            mult = loc_overrides["all"]

    # B379: any attack that penetrates DR inflicts at least 1 HP
    wound = max(1, int(raw * mult)) if raw > 0 else 0

    return DamageResult(
        roll_result=result,
        damage_type=damage_type,
        raw_damage=raw,
        wounding_multiplier=mult,
        wound=wound,
        location=location,
    )


def roll_hit_location() -> HitLocationResult:
    from gurps_bot.mechanics.dice import roll_3d6

    result = roll_3d6()
    rolled = result.total

    for roll_range, location, penalty in HIT_LOCATION_TABLE:
        if rolled in roll_range:
            return HitLocationResult(
                rolled=rolled, location=location, hit_penalty=penalty
            )

    # unreachable with 3d6
    return HitLocationResult(rolled=rolled, location="Torso", hit_penalty=0)
