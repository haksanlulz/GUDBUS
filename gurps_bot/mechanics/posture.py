# numbers only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Posture table (B551), signed from the posture-holder's viewpoint."""

from __future__ import annotations

from dataclasses import dataclass

# canonical spelling; callers and tests import this instead of hardcoding it
LYING_DOWN_NAME = "Lying Down"


@dataclass(frozen=True, slots=True)
class Posture:
    """B551 row; ranged_to_hit_you <= 0 (helps you), melee_to_hit_you >= 0 (helps the attacker)."""

    name: str
    attack_penalty: int
    defense_modifier: int
    ranged_to_hit_you: int
    melee_to_hit_you: int
    move_fraction: float
    effect: str


# B551 rows in book order
POSTURES: tuple[Posture, ...] = (
    Posture(
        name="Standing",
        attack_penalty=0,
        defense_modifier=0,
        ranged_to_hit_you=0,
        melee_to_hit_you=0,
        move_fraction=1.0,
        effect="Full Move and no modifiers; the baseline. May sprint.",
    ),
    Posture(
        name="Crouching",
        attack_penalty=-2,
        defense_modifier=0,
        ranged_to_hit_you=-2,
        melee_to_hit_you=0,
        move_fraction=2 / 3,
        effect="Smaller target vs ranged at no defense cost; a free action.",
    ),
    Posture(
        name="Kneeling",
        attack_penalty=-2,
        defense_modifier=-2,
        ranged_to_hit_you=-2,
        melee_to_hit_you=0,
        move_fraction=1 / 3,
        effect="Steadier brace for ranged fire, but defenses suffer.",
    ),
    Posture(
        name="Sitting",
        attack_penalty=-2,
        defense_modifier=-2,
        ranged_to_hit_you=-2,
        melee_to_hit_you=0,
        move_fraction=0.0,
        effect="Cannot move; stand or drop prone before advancing.",
    ),
    Posture(
        name="Crawling",
        attack_penalty=-4,
        defense_modifier=-3,
        ranged_to_hit_you=-2,
        melee_to_hit_you=0,
        move_fraction=1 / 3,
        effect="Low and slow; heavy attack/defense penalties.",
    ),
    Posture(
        name=LYING_DOWN_NAME,
        attack_penalty=-4,
        defense_modifier=-3,
        ranged_to_hit_you=-2,
        melee_to_hit_you=+4,
        move_fraction=1 / 3,
        effect="Prone: hard ranged target, but an easy point-blank melee one.",
    ),
)

_BY_NAME: dict[str, Posture] = {p.name.lower(): p for p in POSTURES}


def posture(name: str) -> Posture:
    try:
        return _BY_NAME[name.strip().lower()]
    except KeyError:
        raise KeyError(f"unknown posture {name!r}") from None


def posture_names() -> list[str]:
    return [p.name for p in POSTURES]
