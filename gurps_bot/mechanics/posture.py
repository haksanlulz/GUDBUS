# numbers only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Posture table (B551), signed from the posture-holder's viewpoint."""

from __future__ import annotations

from dataclasses import dataclass

# canonical spelling; callers and tests import this instead of hardcoding it
LYING_DOWN_NAME = "Lying Down"


@dataclass(frozen=True, slots=True)
class Posture:
    """B551 row.

    Column meanings are the book's own legend, and they are narrower than they
    look: ``attack_penalty`` applies to a MELEE attack made from this posture
    ("There is no effect on ranged attacks"), ``defense_modifier`` to all active
    defenses, and ``ranged_to_hit_you`` is the Target column — "the modifier to
    hit your torso, groin, or legs with a RANGED attack."

    ``melee_to_hit_you`` is retained as an explicit zero across every posture.
    GURPS Basic Set defines no target-posture melee modifier at all: B547's
    melee table carries only the *attacker's* posture, and B104's Overhead
    enhancement speaks of negating attack *penalties* against prone targets.
    The field stays so callers can render "no melee modifier" rather than
    silently omitting the question.

    Movement is one of two shapes, never both: most rows are a fraction of Move
    (``move_fraction``), but Lying Down prints a flat "1 yard/second"
    (``move_yards_per_second``), which no fraction of Move can express.
    """

    name: str
    attack_penalty: int
    defense_modifier: int
    ranged_to_hit_you: int
    melee_to_hit_you: int
    move_fraction: float | None
    effect: str
    move_yards_per_second: float | None = None


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
        melee_to_hit_you=0,
        move_fraction=None,
        move_yards_per_second=1.0,
        effect="Prone: a hard ranged target, but defenses drop by 3.",
    ),
)

def move_label(p: Posture) -> str:
    """Compact Move label for one posture — single owner, both surfaces use it.

    Lying Down is the reason this exists: B551 gives it a flat "1 yard/second"
    while every other row is a fraction of Move, so no single numeric field
    renders the column correctly.
    """
    if p.move_yards_per_second is not None:
        rate = p.move_yards_per_second
        whole = int(rate) if float(rate).is_integer() else rate
        return f"{whole} yard/second" if rate == 1 else f"{whole} yards/second"
    fraction = p.move_fraction
    if fraction is None:  # neither shape set — a malformed row, caught by _validate
        return "-"
    if fraction >= 1.0:
        return "full"
    if fraction <= 0.0:
        return "none (cannot move)"
    if abs(fraction - 2 / 3) < 1e-6:
        return "x2/3"
    if abs(fraction - 1 / 3) < 1e-6:
        return "x1/3"
    return f"x{fraction:.2g}"


def _validate() -> None:
    """Import-time invariant: every row carries exactly one movement shape."""
    for p in POSTURES:
        has_fraction = p.move_fraction is not None
        has_rate = p.move_yards_per_second is not None
        if has_fraction == has_rate:
            raise AssertionError(
                f"{p.name}: a B551 row is either a Move fraction or an absolute "
                f"yards/second, never both and never neither "
                f"(fraction={p.move_fraction!r}, rate={p.move_yards_per_second!r})"
            )
        if p.melee_to_hit_you != 0:
            raise AssertionError(
                f"{p.name}: GURPS Basic Set defines no target-posture melee "
                f"to-hit modifier (B551's Target column is ranged-only); "
                f"got {p.melee_to_hit_you:+d}"
            )


_validate()


_BY_NAME: dict[str, Posture] = {p.name.lower(): p for p in POSTURES}


def posture(name: str) -> Posture:
    try:
        return _BY_NAME[name.strip().lower()]
    except KeyError:
        raise KeyError(f"unknown posture {name!r}") from None


def posture_names() -> list[str]:
    return [p.name for p in POSTURES]
