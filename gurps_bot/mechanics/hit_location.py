"""hit-location to-hit penalties, single owner (B552; deliberate targeting B398-B400) — damage.py sources penalties from here, wounding numbers stay in damage.LOCATION_MULTIPLIERS; effect notes are original summaries, no SJG prose"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HitLocation:
    """penalty = to-hit modifier (Torso 0, rest <= 0); deliberate_only = never rolled on the random table"""

    name: str
    penalty: int
    effect: str
    deliberate_only: bool = False


# random-table locations first (MUST match what damage.HIT_LOCATION_TABLE can
# roll), then the deliberate-only extras (B552)
LOCATIONS: tuple[HitLocation, ...] = (
    # random 3d6 table (B552)
    HitLocation("Skull", -7, "Brain box: x4 wounding and knockdown; DR adds 2."),
    HitLocation("Face", -5, "x1.5 from corrosion; a major wound can blind/stun."),
    HitLocation("Neck", -5, "x1.5 crushing, x2 cutting; a cut here can decapitate."),
    HitLocation("Torso", 0, "The default target; no special penalty or bonus."),
    HitLocation("Groin", -3, "Human males take x2 crushing shock; -5 to knockdown."),
    HitLocation("Right Arm", -2, "pi/imp wound as if pi; >1/2 HP in one blow cripples."),
    HitLocation("Left Arm", -2, "pi/imp wound as if pi; >1/2 HP in one blow cripples."),
    HitLocation("Right Leg", -2, "pi/imp wound as if pi; >1/2 HP in one blow cripples."),
    HitLocation("Left Leg", -2, "pi/imp wound as if pi; >1/2 HP in one blow cripples."),
    HitLocation("Hand", -4, "Reduced large-piercing/impaling; >1/3 HP cripples it."),
    HitLocation("Foot", -4, "Reduced large-piercing/impaling; >1/3 HP cripples it."),
    # deliberate-only (B552 / B398-400)
    HitLocation(
        "Eye",
        -9,
        "Strikes the brain at no DR; >1/10 HP in one blow blinds the eye.",
        deliberate_only=True,
    ),
    HitLocation(
        "Vitals",
        -3,
        "x3 from impaling/any piercing, x2 from a tight-beam burn.",
        deliberate_only=True,
    ),
    HitLocation(
        "Jaw",
        -6,
        "A face hit that can also stun; treated harshly by crushing blows.",
        deliberate_only=True,
    ),
    HitLocation(
        "Spine",
        -8,
        "A neck/torso hit that can cripple the body below the wound.",
        deliberate_only=True,
    ),
    HitLocation(
        "Limb Vein/Artery",
        -5,
        "A limb hit that bleeds; cutting/impaling threaten heavy blood loss.",
        deliberate_only=True,
    ),
    HitLocation(
        "Neck Vein/Artery",
        -8,
        "A neck hit with severe bleeding risk from cutting/impaling.",
        deliberate_only=True,
    ),
)

_BY_NAME: dict[str, HitLocation] = {loc.name.lower(): loc for loc in LOCATIONS}


def _validate() -> None:
    """import-time invariants: unique names, penalties <= 0, torso 0; the cross-module half (random-table coverage) lives in tests — damage.py imports us, so reading its table here would touch a half-initialised module"""
    names = [loc.name for loc in LOCATIONS]
    if len(names) != len(set(names)):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise AssertionError(
            f"duplicate hit-location name(s) {dupes} — a to-hit penalty must have "
            f"exactly one owner (SSoT)"
        )
    for loc in LOCATIONS:
        if loc.penalty > 0:
            raise AssertionError(
                f"{loc.name}: a hit-location to-hit modifier is never a bonus "
                f"(penalty={loc.penalty:+d}); Torso is the easy 0"
            )
        if not loc.effect.strip():
            raise AssertionError(f"{loc.name}: empty effect note")
        if len(loc.effect) > 200:
            raise AssertionError(f"{loc.name}: effect note too long ({len(loc.effect)})")
    if _BY_NAME.get("torso") is None or _BY_NAME["torso"].penalty != 0:
        raise AssertionError("Torso must be owned with penalty 0 (the default target)")


_validate()


def hit_location(name: str) -> HitLocation:
    """case-insensitive lookup; KeyError on unknown names"""
    try:
        return _BY_NAME[name.strip().lower()]
    except KeyError:
        raise KeyError(f"unknown hit location {name!r}") from None


def penalty_for(name: str) -> int:
    """the owned to-hit penalty (B552); damage.py's random table sources through this"""
    return hit_location(name).penalty


def hit_location_names() -> list[str]:
    """display names, table order then the deliberate-only extras"""
    return [loc.name for loc in LOCATIONS]


def deliberate_locations() -> tuple[HitLocation, ...]:
    return tuple(loc for loc in LOCATIONS if loc.deliberate_only)


def gross_targeting_reference() -> list[tuple[str, int, str]]:
    """gross random-table locations as (name, penalty, effect), sided rows collapsed to one entry, roll order; the damage import is deferred to dodge the cycle"""
    from gurps_bot.mechanics.damage import HIT_LOCATION_TABLE

    rows: list[tuple[str, int, str]] = []
    seen: set[str] = set()
    for _rng, name, penalty in HIT_LOCATION_TABLE:
        if name in seen:
            continue
        seen.add(name)
        effect = _BY_NAME[name.lower()].effect
        rows.append((name, penalty, effect))
    return rows
