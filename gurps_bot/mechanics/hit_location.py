"""hit-location to-hit penalties, single owner (B552; deliberate targeting B398-B400) — damage.py sources penalties from here, wounding numbers stay in damage.LOCATION_MULTIPLIERS; effect notes are original summaries, no SJG prose

Four locations are NOT Basic Set content and are marked as such: Jaw, Spine and
the two Vein/Artery entries come from GURPS Martial Arts p.137 "New Hit
Locations". They shipped under a Basic Set cite until 2026-07-27; the penalties
were right, the provenance was not. All four verified against the printed
Martial Arts text. Operator ruling: keep them, cite the book, mark optional.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Cite for locations outside the Basic Set. A GM reading /target must be able
#: to tell core rules from a supplement they may not use at their table.
MARTIAL_ARTS_SOURCE = "GURPS Martial Arts p.137"


@dataclass(frozen=True, slots=True)
class HitLocation:
    """penalty = to-hit modifier (Torso 0, rest <= 0); deliberate_only = never rolled on the random table

    ``source`` is None for Basic Set locations and names the book otherwise.
    ``deliberate_only`` and ``is_optional`` are orthogonal: Eye and Vitals are
    deliberate-only but core (B552 prints "—" for their roll), while the
    Martial Arts four are both.
    """

    name: str
    penalty: int
    effect: str
    deliberate_only: bool = False
    source: str | None = None

    @property
    def is_optional(self) -> bool:
        """True when this location comes from a supplement, not the Basic Set."""
        return self.source is not None


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
    # deliberate-only, Basic Set (B552 / B398-400)
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
    # deliberate-only, GURPS Martial Arts p.137 "New Hit Locations" — optional,
    # not Basic Set. Every penalty verified against the printed text.
    HitLocation(
        "Ear",
        -7,
        "Resolves as a face hit unless a cutting blow is aimed to slice it off; "
        "losing an ear costs a level of Appearance.",
        deliberate_only=True,
        source=MARTIAL_ARTS_SOURCE,
    ),
    HitLocation(
        "Jaw",
        -6,
        "Targetable only from the front; resolves as a face hit, but a crushing "
        "blow adds -1 to the knockdown roll.",
        deliberate_only=True,
        source=MARTIAL_ARTS_SOURCE,
    ),
    HitLocation(
        "Nose",
        -7,
        "Front only; a face hit that breaks past HP/4, costing smell and taste "
        "until it heals.",
        deliberate_only=True,
        source=MARTIAL_ARTS_SOURCE,
    ),
    HitLocation(
        "Limb Joint",
        -5,
        "Arm or leg joint; crushing, cutting, piercing or tight-beam burning "
        "only. Cripples past HP/3 rather than HP/2.",
        deliberate_only=True,
        source=MARTIAL_ARTS_SOURCE,
    ),
    HitLocation(
        "Extremity Joint",
        -7,
        "Hand or foot joint; same attack types. Cripples past HP/4 rather than "
        "HP/3, and recovery rolls are at -2.",
        deliberate_only=True,
        source=MARTIAL_ARTS_SOURCE,
    ),
    HitLocation(
        "Spine",
        -8,
        "Narrow and buried in the torso, with DR 3 over the torso's; injury "
        "past HP cripples it.",
        deliberate_only=True,
        source=MARTIAL_ARTS_SOURCE,
    ),
    HitLocation(
        "Limb Vein/Artery",
        -5,
        "Brachial or femoral vessel; cutting, impaling, piercing or tight-beam "
        "burning only. Bleeds hard.",
        deliberate_only=True,
        source=MARTIAL_ARTS_SOURCE,
    ),
    HitLocation(
        "Neck Vein/Artery",
        -8,
        "Jugular or carotid; cutting, impaling, piercing or tight-beam burning "
        "only. Fastest bleed on the table.",
        deliberate_only=True,
        source=MARTIAL_ARTS_SOURCE,
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
