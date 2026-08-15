# numbers only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""B168 — using a technological skill at a tech level that is not its own.

Its own module, owned by no domain, for the same reason ``equipment_quality``
(B345) got one: it is Basic Set rule data that more than one domain needs, and
the alternative is one domain reading another's constants. Repair needs it
because a TL9 technician can be handed TL10 gear; invention needs the same
shape for inventing above your own TL.

⚑ **There are TWO rules here, not one, and they disagree.** The Basic Set
splits technological skills by controlling attribute:

* **IQ-based** ones (Armoury, Electronics Repair, Machinist, Mechanic — i.e.
  every repair skill) represent studied understanding of the methods and tools
  of a particular TL, and take the **asymmetric ladder** below;
* **everything else** — the ones that let you *use* technology without
  understanding it, like a DX-based weapon or vehicle skill — take a **flat -1
  per TL of difference**, and the book says outright that direction is
  irrelevant: a TL7 policeman is at -2 with a TL5 revolver just as a TL5
  gunman is at -2 with a TL7 one.

Getting these two backwards is cheap to do and expensive to notice, because
they agree at exactly one point (no gap at all) and diverge everywhere else.
Repairing a TL10 beam weapon with TL9 skill is **-5** under the ladder that
governs it, and would be **-1** under the rule that does not.

⚠️ The ladder is not symmetric and must not be generated. Above your TL it is
-5 per step; below, it runs -1 / -3 / -5 / -7 and only then settles into -2 per
further step. A single "per step" constant is wrong on one side whichever value
it takes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SkillClass(Enum):
    """Which of B168's two rules a skill answers to."""

    #: Studied technical understanding — the repair skills, and the ones that
    #: build things. Takes the asymmetric ladder.
    IQ_BASED = "IQ-based technological skill"
    #: Skills that operate equipment without explaining it. Flat -1 per TL.
    OTHER = "other technological skill"


#: B168's table, keyed by (equipment TL - skill TL). Written out rather than
#: computed: every attempt to generate it gets one side wrong.
_IQ_LADDER = {
    3: -15,
    2: -10,
    1: -5,
    0: 0,
    -1: -1,
    -2: -3,
    -3: -5,
    -4: -7,
}

#: "Skill's TL+4 or more: Impossible!" — a hard stop, not a large number.
IMPOSSIBLE_AT_OR_ABOVE = 4

#: Below the table's last printed row, "Per extra -1 to TL: -2".
_BEYOND_LADDER_FLOOR = -4
_BEYOND_LADDER_EACH = -2

#: B168's flat rule for the non-IQ-based half.
OTHER_SKILL_PENALTY_EACH = -1

#: B169 Familiarity: "an unfamiliar piece of equipment gives -2 to skill".
#: Separate from and additional to the TL penalty — the book is explicit that
#: equipment from another TL "gives both TL and familiarity modifiers" — and
#: it is the half that practice can remove. Shedding the TL penalty instead
#: requires relearning the skill at the equipment's TL.
UNFAMILIAR_PENALTY = -2


@dataclass(frozen=True, slots=True)
class TechLevelGap:
    """What a TL mismatch costs.

    ``impossible`` is not "a very large penalty". The book stops rather than
    scaling, so a caller must be able to report that the job cannot be
    attempted at all, and ``penalty`` is meaningless when it is set.
    """

    steps: int
    penalty: int
    impossible: bool = False

    @property
    def equipment_is_higher(self) -> bool:
        return self.steps > 0


def tl_gap(
    *,
    skill_tl: int,
    equipment_tl: int,
    skill_class: SkillClass = SkillClass.IQ_BASED,
) -> TechLevelGap:
    """B168, both rules.

    ``skill_class`` defaults to IQ-based because every skill that repairs or
    builds something is IQ-based; the flat rule belongs to the skills that
    merely operate the result.
    """
    if skill_tl < 0:
        raise ValueError(f"skill_tl cannot be negative, got {skill_tl}")
    if equipment_tl < 0:
        raise ValueError(f"equipment_tl cannot be negative, got {equipment_tl}")

    steps = equipment_tl - skill_tl

    if skill_class is SkillClass.OTHER:
        # Direction is explicitly irrelevant here, so the magnitude drives it.
        return TechLevelGap(steps=steps, penalty=abs(steps) * OTHER_SKILL_PENALTY_EACH)

    if steps >= IMPOSSIBLE_AT_OR_ABOVE:
        return TechLevelGap(steps=steps, penalty=0, impossible=True)
    if steps >= _BEYOND_LADDER_FLOOR:
        return TechLevelGap(steps=steps, penalty=_IQ_LADDER[steps])

    extra = _BEYOND_LADDER_FLOOR - steps
    return TechLevelGap(
        steps=steps,
        penalty=_IQ_LADDER[_BEYOND_LADDER_FLOOR] + extra * _BEYOND_LADDER_EACH,
    )
