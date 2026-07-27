"""damage rolls + wounding multipliers; hit-location to-hit penalties are owned by hit_location.py and sourced from there"""

from __future__ import annotations

from dataclasses import dataclass

from gurps_bot.mechanics.traits import InjuryTolerance
from gurps_bot.mechanics.dice import RollResult, roll
from gurps_bot.mechanics.hit_location import hit_location_names
from gurps_bot.mechanics.hit_location import penalty_for as _loc_penalty

# wounding multipliers by damage type (B378-379)
# B379 lists every type in one sentence: "Small piercing (pi-): x0.5. Burning
# (burn), corrosion (cor), crushing (cr), fatigue (fat), piercing (pi), and
# toxic (tox): x1. Cutting (cut) and large piercing (pi+): x1.5. Impaling (imp)
# and huge piercing (pi++): x2."
WOUNDING_MULTIPLIERS: dict[str, float] = {
    "pi-": 0.5,
    "cr": 1.0,
    "burn": 1.0,
    "pi": 1.0,
    "tox": 1.0,
    "cor": 1.0,
    "fat": 1.0,
    "cut": 1.5,
    "pi+": 1.5,
    "imp": 2.0,
    "pi++": 2.0,
}

#: fatigue damage costs FP, not HP. The multiplier above is the wounding maths;
#: routing the result to FP is the caller's job, and `/combat fp` is where it
#: lands. Flagged here so a caller cannot subtract it from HP by omission.
FATIGUE_DAMAGE_TYPE = "fat"

# per-location wounding overrides (B398-400) — replace the base multiplier.
# type-specific keys beat "all" (B399: skull/eye x4 excludes toxic).
# no tight-beam burn flag in the engine, so the vitals burn x2 case is out of scope.

# B399: pi+/pi++/imp all drop to x1 against a limb or extremity. Typed once.
_LIMB_REDUCTION: dict[str, float] = {"pi+": 1.0, "pi++": 1.0, "imp": 1.0}

#: the impaling/piercing family, which B380's Diffuse rule caps at 1 HP
_PIERCING_FAMILY: frozenset[str] = frozenset({"imp", "pi++", "pi+", "pi", "pi-"})

#: B380 sidebar. Diffuse is absent because it caps finished injury rather than
#: scaling it, and so cannot be expressed as a multiplier.
_INJURY_TOLERANCE_MULTIPLIERS: dict[InjuryTolerance, dict[str, float]] = {
    # "impaling and huge piercing a wounding modifier of x1; large piercing,
    # x1/2; piercing, x1/3; and small piercing, x1/5"
    InjuryTolerance.UNLIVING: {
        "imp": 1.0,
        "pi++": 1.0,
        "pi+": 0.5,
        "pi": 1 / 3,
        "pi-": 0.2,
    },
    # "Impaling and huge piercing have a wounding modifier of x1/2; large
    # piercing, x1/3; piercing, x1/5; and small piercing, x1/10"
    InjuryTolerance.HOMOGENOUS: {
        "imp": 0.5,
        "pi++": 0.5,
        "pi+": 1 / 3,
        "pi": 0.2,
        "pi-": 0.1,
    },
}

LOCATION_MULTIPLIERS: dict[str, dict[str, float]] = {
    "skull": {"all": 4.0, "tox": 1.0},
    "eye": {"all": 4.0, "tox": 1.0},
    # B399 "an impaling or ANY piercing attack" — pi- is small piercing, still piercing
    "vitals": {"imp": 3.0, "pi-": 3.0, "pi": 3.0, "pi+": 3.0, "pi++": 3.0},
    "neck": {"cr": 1.5, "cor": 1.5, "cut": 2.0},
    "face": {"cor": 1.5},  # B399: otherwise torso wounding; cor major wound also blinds an eye (GM call)
    "groin": {},  # B399: torso wounding; cr doubles SHOCK on males, not injury
    "right arm": dict(_LIMB_REDUCTION),
    "left arm": dict(_LIMB_REDUCTION),
    "right leg": dict(_LIMB_REDUCTION),
    "left leg": dict(_LIMB_REDUCTION),
    "arm": dict(_LIMB_REDUCTION),
    "leg": dict(_LIMB_REDUCTION),
    "hand": dict(_LIMB_REDUCTION),
    "foot": dict(_LIMB_REDUCTION),
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
    "fat": "Fatigue (fat) - costs FP",
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
    injury_tolerance: InjuryTolerance | None = None

    def __str__(self) -> str:
        loc = f" to {self.location}" if self.location else ""
        # Diffuse caps finished injury rather than scaling it, so the multiplier
        # alone would not explain the number — name the tolerance when set.
        tol = f" [{self.injury_tolerance.value}]" if self.injury_tolerance else ""
        return (
            f"{self.roll_result.spec} {self.damage_type} = "
            f"{self.raw_damage} raw (x{self.wounding_multiplier}) = "
            f"{self.wound} wound{loc}{tol}"
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


def wound_from_penetrating(
    raw: int,
    damage_type: str,
    *,
    location: str | None = None,
    injury_tolerance: InjuryTolerance | None = None,
) -> tuple[float, int]:
    """(wounding multiplier, injury) for ``raw`` points that already beat DR.

    Split out of roll_damage so the wounding rules can be checked against the
    book without a die roll in the way — the dice notation has no zero-dice
    form, so every multiplier test through roll_damage would be stochastic.
    """
    damage_type = damage_type.lower().strip() or "cr"
    raw = max(0, raw)

    mult = WOUNDING_MULTIPLIERS.get(damage_type, 1.0)
    if location:
        loc_overrides = LOCATION_MULTIPLIERS.get(location.lower(), {})
        if damage_type in loc_overrides:
            mult = loc_overrides[damage_type]
        elif "all" in loc_overrides:
            mult = loc_overrides["all"]

    # B380: Unliving/Homogenous replace the type multiplier. Both this and the
    # location override are damage-reducing, and the book does not say which
    # wins when a limb hit lands on an undead; take the more protective, so
    # neither can be bypassed by invoking the other. Diffuse is a cap on the
    # finished injury, not a multiplier, so it lands after the floor below.
    if injury_tolerance is not None:
        tolerance_mult = _INJURY_TOLERANCE_MULTIPLIERS.get(injury_tolerance, {}).get(
            damage_type
        )
        if tolerance_mult is not None:
            mult = min(mult, tolerance_mult)

    # B379: any attack that penetrates DR inflicts at least 1 HP
    wound = max(1, int(raw * mult)) if raw > 0 else 0

    if injury_tolerance is InjuryTolerance.DIFFUSE and wound > 0:
        # "Impaling and piercing attacks (of any size) never do more than 1 HP
        # of injury ... Other attacks can never do more than 2 HP of injury."
        wound = min(wound, 1 if damage_type in _PIERCING_FAMILY else 2)

    return mult, wound


def roll_damage(
    dice_expr: str,
    damage_type: str,
    dr: int = 0,
    location: str | None = None,
    injury_tolerance: InjuryTolerance | None = None,
) -> DamageResult:
    """roll dice_expr (pure dice, no type suffix) against DR with the wounding multiplier for type/location

    ``injury_tolerance`` applies the B380 sidebar for Unliving, Homogenous and
    Diffuse targets — machines, corporeal undead, swarms.
    """
    damage_type = damage_type.lower().strip()
    if not damage_type:
        damage_type = "cr"

    dr = max(0, dr)  # DR is never negative; unclamped it would inflate the wound
    result = roll(dice_expr)
    raw = max(0, result.total - dr)

    mult, wound = wound_from_penetrating(
        raw, damage_type, location=location, injury_tolerance=injury_tolerance
    )

    return DamageResult(
        roll_result=result,
        damage_type=damage_type,
        raw_damage=raw,
        wounding_multiplier=mult,
        wound=wound,
        location=location,
        injury_tolerance=injury_tolerance,
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
