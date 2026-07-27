# numbers only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Reading character traits at a mechanics call site.

Mechanics modules never had a way to ask "does this character have High Pain
Threshold?", so every trait-driven rule was either unimplemented or exposed as a
manual toggle. This is the single place that answers such questions, and it is
pure: callers pass trait names (and levels), never a session or a model.

GCS trait names arrive with parentheticals and sometimes a trailing level, e.g.
"Injury Tolerance (Unliving)" or "Fearlessness 3". Matching is therefore on a
normalised base name, and never on a substring — "Fearlessness" and
"Fearfulness" are opposite traits that a naive `in` test would conflate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

#: B420 knockdown-and-stunning modifiers: "+3 for High Pain Threshold, or -4 for
#: Low Pain Threshold."
HIGH_PAIN_THRESHOLD_KNOCKDOWN = 3
LOW_PAIN_THRESHOLD_KNOCKDOWN = -4

#: B: Fearfulness "may not reduce your Will roll below 3."
FEARFULNESS_WILL_FLOOR = 3

_PARENTHETICAL = re.compile(r"\s*\(([^)]*)\)\s*")
_TRAILING_LEVEL = re.compile(r"\s+(\d+)\s*$")


class InjuryTolerance(str, Enum):
    """B380 sidebar variants that change wounding multipliers."""

    UNLIVING = "Unliving"
    HOMOGENOUS = "Homogenous"
    DIFFUSE = "Diffuse"


@dataclass(frozen=True, slots=True)
class ParsedTrait:
    """One trait split into the parts a rule cares about."""

    base: str  # normalised base name, lowercased
    parenthetical: str | None  # text inside (), original case
    level: int | None  # trailing integer level, if the name carried one


def parse_trait(name: str) -> ParsedTrait:
    """Split a GCS trait name into base / parenthetical / trailing level."""
    raw = name.strip()
    paren: str | None = None
    match = _PARENTHETICAL.search(raw)
    if match:
        paren = match.group(1).strip() or None
        raw = _PARENTHETICAL.sub(" ", raw).strip()
    level: int | None = None
    level_match = _TRAILING_LEVEL.search(raw)
    if level_match:
        level = int(level_match.group(1))
        raw = _TRAILING_LEVEL.sub("", raw).strip()
    return ParsedTrait(base=raw.casefold(), parenthetical=paren, level=level)


def _matches(name: str, target: str) -> bool:
    """Exact base-name match, never a substring test.

    Fearlessness and Fearfulness differ by three characters and mean opposite
    things; High and Low Pain Threshold share a suffix. Substring matching on
    any of these silently returns the wrong sign.
    """
    return parse_trait(name).base == target.casefold()


def has_trait(names: list[str], target: str) -> bool:
    return any(_matches(n, target) for n in names)


def trait_level(names: list[str], target: str, *, levels: dict[str, int] | None = None) -> int:
    """Level of ``target``, or 0 if absent.

    A level may arrive either in the name ("Fearlessness 3") or in the DB's
    ``level`` column, passed as ``levels``. An explicit ``levels`` entry wins;
    a trait present with no level at all counts as level 1, since a levelled
    trait cannot be taken at level 0.
    """
    for name in names:
        if not _matches(name, target):
            continue
        if levels is not None and name in levels and levels[name] is not None:
            return int(levels[name])
        parsed = parse_trait(name)
        return parsed.level if parsed.level is not None else 1
    return 0


def pain_threshold_knockdown_modifier(names: list[str]) -> int:
    """B420: "+3 for High Pain Threshold, or -4 for Low Pain Threshold."

    They are mutually exclusive traits; if a sheet somehow carries both, the
    penalty wins — the bot must not hand out a bonus it cannot justify.
    """
    low = has_trait(names, "Low Pain Threshold")
    high = has_trait(names, "High Pain Threshold")
    if low:
        return LOW_PAIN_THRESHOLD_KNOCKDOWN
    if high:
        return HIGH_PAIN_THRESHOLD_KNOCKDOWN
    return 0


def is_unfazeable(names: list[str]) -> bool:
    """B95 Unfazeable: "You are exempt from Fright Checks." No roll happens."""
    return has_trait(names, "Unfazeable")


def fright_will_modifier(
    names: list[str], *, levels: dict[str, int] | None = None
) -> int:
    """Fearlessness adds its level to Will on a Fright Check; Fearfulness
    subtracts its level. B says the two are mutually exclusive."""
    return (
        trait_level(names, "Fearlessness", levels=levels)
        - trait_level(names, "Fearfulness", levels=levels)
    )


def injury_tolerance(names: list[str]) -> InjuryTolerance | None:
    """B380 variant carried by Injury Tolerance (...), or None.

    Only the three variants that change wounding are recognised; Injury
    Tolerance has other parentheticals (No Blood, No Neck, ...) that this
    deliberately ignores, returning None rather than guessing.
    """
    for name in names:
        parsed = parse_trait(name)
        if parsed.base != "injury tolerance" or not parsed.parenthetical:
            continue
        for variant in InjuryTolerance:
            if parsed.parenthetical.casefold() == variant.value.casefold():
                return variant
    return None


#: display labels for the three wounding-relevant variants, so a command surface
#: does not re-type the list and drift from the enum
INJURY_TOLERANCE_LABELS: dict[InjuryTolerance, str] = {
    InjuryTolerance.UNLIVING: "Unliving (machines, most corporeal undead)",
    InjuryTolerance.HOMOGENOUS: "Homogenous (statues, blobs, solid objects)",
    InjuryTolerance.DIFFUSE: "Diffuse (swarms, air elementals, nets)",
}


def parse_injury_tolerance(value: str | None) -> InjuryTolerance | None:
    """Enum for a command-surface value, or None. Unknown input is None, never
    a guess — a wrong tolerance silently changes every wound."""
    if not value:
        return None
    wanted = value.strip().casefold()
    for variant in InjuryTolerance:
        if wanted == variant.value.casefold():
            return variant
    return None


def has_reduced_parry(names: list[str]) -> bool:
    """B376: the -2 parry step is granted by Trained By A Master or Weapon
    Master. (A fencing weapon also grants it, but that is equipment, not a
    trait, so it stays a caller-supplied flag.)"""
    return has_trait(names, "Trained By A Master") or has_trait(names, "Weapon Master")
