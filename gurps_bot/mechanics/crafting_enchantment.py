# numbers only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""GURPS Magic pp. 16-18 — enchantment, the fifth crafting domain.

The last of the five, and the one that finally breaks the "assistant"
abstraction beyond repair. Across this family the word now means five
unrelated things, two of which live in this module alone:

* invention: each skilled assistant adds to the inventor's roll;
* alchemy: the weakest hand present makes the roll;
* mundane crafting: the strongest hand makes it, and extra hands only divide
  the clock, capped at six;
* enchantment, Quick and Dirty: each assistant is **-1 to the caster's skill**,
  and the headcount cap is therefore *derived* rather than printed — you may
  bring as many as would leave the caster at 15;
* enchantment, Slow and Sure: assistants divide the elapsed mage-days, must be
  present every single day, and **losing one ends the project outright**.

⚑ **The roll and the item's Power are the same number, and it is a min().**
Power equals the caster's effective skill with either Enchant or the spell
going into the item, whichever is lower. So a superb enchanter with a shaky
grasp of the spell makes a weak item, and there is no averaging.

⚑ **Ceremonial thresholds, the third check variant in this arc.** A 16 always
fails and a 17-18 is always a critical failure, at any effective skill — so
``mechanics/checks.py`` cannot serve this unmodified any more than it can serve
alchemy. Where alchemy suppresses critical successes and mundane crafting
ignores criticals entirely, this one moves the failure line.

⚠️ **The spell catalogue is NOT here and must not be.** What each enchantment
DOES, and its energy cost, are per-spell data; energy arrives as a parameter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from gurps_bot.mechanics.crafting import ModifierBreakdown
from gurps_bot.mechanics.dice import DiceSpec


class Method(Enum):
    """The two ways to enchant, and they share almost nothing."""

    QUICK_AND_DIRTY = "Quick and Dirty"
    SLOW_AND_SURE = "Slow and Sure"


class Mana(Enum):
    """Enchantment's own mana axis. Alchemy has one too and they differ."""

    NONE = "No mana"
    LOW = "Low mana"
    NORMAL = "Normal mana"


#: "the caster and any assistants must know both the Enchant spell and the
#: specific spell being put on the item at an effective skill of 15 or better."
#: Also the floor a working item's Power must clear, which is not a coincidence
#: — Power IS that effective skill.
MINIMUM_EFFECTIVE_SKILL = 15

#: "Apply a temporary -5 to Power in a low-mana area; thus, an item with less
#: than Power 20 will not work at all in a low-mana zone."
LOW_MANA_POWER_PENALTY = -5

#: "The caster is at -1 to skill for each assistant."
ASSISTANT_PENALTY_EACH = -1

#: "If the caster uses HP to cast the spell, his effective skill is at -1 for
#: every HP used."
HP_PENALTY_EACH = -1

#: "If anyone but the caster and his assistants is within 10 yards, the spell
#: is at a further -1."
BYSTANDER_PENALTY = -1
BYSTANDER_RADIUS_YARDS = 10

#: Ceremonial thresholds — these are the rule, not a clamp.
CEREMONIAL_AUTOMATIC_FAILURE = 16
CEREMONIAL_CRITICAL_FAILURE_FROM = 17

#: "On a critical success, increase the Power of the item by 2d."
CRITICAL_SUCCESS_POWER_BONUS = DiceSpec(2, 6, 0)
#: "if the success roll was a natural 3, the item might have some further
#: enhancement (GM's discretion)" — flagged, never invented.
FURTHER_ENHANCEMENT_ON = 3

#: Quick and Dirty: "one hour per 100 points of energy required (round up)".
QUICK_AND_DIRTY_ENERGY_PER_HOUR = 100
#: Slow and Sure: "one mage-day per point of energy required", a mage-day being
#: a full eight-hour workday.
MAGE_DAY_HOURS = 8
#: "If a day's work is skipped or interrupted, it takes two days to make it up."
INTERRUPTED_DAY_COST = 2


def enchanting_skill(enchant_skill: int, spell_skill: int) -> int:
    """The lower of the two, and the whole rule in one line.

    ⚑ Not an average and not the Enchant skill alone. Both of the book's own
    worked examples happen to have Enchant at or above the other spell, so
    neither of them can tell "the lower of both" from "the enchanted spell" —
    the general statement on p. 17 is what settles it, and it says *whichever
    is lower*.
    """
    if enchant_skill < 0 or spell_skill < 0:
        raise ValueError("skills cannot be negative")
    return min(enchant_skill, spell_skill)


def everyone_is_qualified(*effective_skills: int) -> bool:
    """"the caster and any assistants must know both ... at an effective skill
    of 15 or better". An unqualified assistant is not a weaker assistant; they
    cannot contribute energy at all."""
    return all(skill >= MINIMUM_EFFECTIVE_SKILL for skill in effective_skills)


def assistant_cap(base_skill: int) -> int:
    """How many assistants the caster may bring, DERIVED rather than printed.

    "the number of assistants allowed is the number that would reduce the
    caster's effective skill to 15. With more assistants, the enchantment
    won't work." So a skill-15 caster may bring none, and each further point
    of skill buys exactly one more pair of hands.
    """
    if base_skill < MINIMUM_EFFECTIVE_SKILL:
        return 0
    return base_skill - MINIMUM_EFFECTIVE_SKILL


def enchanting_modifier(
    *,
    assistants: int = 0,
    hp_spent: int = 0,
    bystanders: bool = False,
) -> ModifierBreakdown:
    """What modifies the enchanting roll.

    ⚠️ ``hp_spent`` is the caster's own. Assistants may also spend HP and take
    the same -1 each, but "their skill does not affect the item's power, as
    long as their effective skill is at least 15" — so an assistant's HP cost
    never reaches this breakdown, and folding it in would quietly weaken every
    item made by a bleeding helper.
    """
    if assistants < 0:
        raise ValueError(f"assistants cannot be negative, got {assistants}")
    if hp_spent < 0:
        raise ValueError(f"hp_spent cannot be negative, got {hp_spent}")

    terms: list[tuple[str, int]] = []
    if assistants:
        terms.append((
            f"{assistants} assistant{'s' if assistants > 1 else ''}",
            assistants * ASSISTANT_PENALTY_EACH,
        ))
    if hp_spent:
        terms.append((f"{hp_spent} HP spent by the caster", hp_spent * HP_PENALTY_EACH))
    if bystanders:
        terms.append((
            f"someone else within {BYSTANDER_RADIUS_YARDS} yards", BYSTANDER_PENALTY
        ))
    return ModifierBreakdown(terms=tuple(terms))


def effective_skill(
    enchant_skill: int,
    spell_skill: int,
    *,
    assistants: int = 0,
    hp_spent: int = 0,
    bystanders: bool = False,
) -> int:
    """The number rolled against, which is also the item's Power."""
    base = enchanting_skill(enchant_skill, spell_skill)
    return base + enchanting_modifier(
        assistants=assistants, hp_spent=hp_spent, bystanders=bystanders
    ).total


def item_power(effective: int) -> int:
    """"An item's Power equals the caster's effective skill ... whichever is
    lower."

    ⚑ The roll and the item's quality are one number. Rolling well does not
    make a better item — being better makes a better item, and the roll only
    says whether it worked. That is a fourth reading of what a craft roll
    MEANS, after success, quantity and quality.
    """
    return effective


def power_in_play(power: int, mana: Mana = Mana.NORMAL) -> int | None:
    """What an item's Power is worth where it is being used.

    Returns ``None`` where no magic item functions at all, which is not the
    same as Power 0 and must not be collapsed into it.
    """
    if mana is Mana.NONE:
        return None
    if mana is Mana.LOW:
        return power + LOW_MANA_POWER_PENALTY
    return power


def item_works(power: int, mana: Mana = Mana.NORMAL) -> bool:
    """"An item's Power must be 15 or more for the item to work."

    In low mana the -5 bites, so the real threshold there is 20 — a derived
    number the book states outright, which makes it a good check on the
    derivation.
    """
    effective_power = power_in_play(power, mana)
    if effective_power is None:
        return False
    return effective_power >= MINIMUM_EFFECTIVE_SKILL


class CeremonialOutcome(Enum):
    CRITICAL_SUCCESS = "critical success"
    SUCCESS = "success"
    FAILURE = "failure"
    CRITICAL_FAILURE = "critical failure"


def ceremonial_outcome(rolled_3d: int, target: int) -> CeremonialOutcome:
    """Enchantment's check variant. The thresholds move, so the core engine
    cannot be reused unmodified.

    "a roll of 16 fails automatically and a roll of 17-18 is a critical
    failure" — *as with other ceremonial magic*, and at any effective skill.
    A caster at 20 still fails on a 16.
    """
    if not 3 <= rolled_3d <= 18:
        raise ValueError(f"a 3d roll is 3..18, got {rolled_3d}")
    if rolled_3d >= CEREMONIAL_CRITICAL_FAILURE_FROM:
        return CeremonialOutcome.CRITICAL_FAILURE
    if rolled_3d == CEREMONIAL_AUTOMATIC_FAILURE:
        return CeremonialOutcome.FAILURE
    if rolled_3d <= 4:
        return CeremonialOutcome.CRITICAL_SUCCESS
    if rolled_3d <= target:
        return CeremonialOutcome.SUCCESS
    return CeremonialOutcome.FAILURE


@dataclass(frozen=True, slots=True)
class EnchantmentResult:
    """What a finished enchanting roll costs and destroys.

    ``item_destroyed`` is separate from ``materials_lost`` because Slow and
    Sure's ordinary failure loses the materials and spares an already-enchanted
    item, while any critical failure destroys both.
    """

    outcome: CeremonialOutcome
    energy_spent: bool
    item_destroyed: bool = False
    materials_lost: bool = False
    power_bonus: DiceSpec | None = None
    may_have_further_enhancement: bool = False


def resolve(
    outcome: CeremonialOutcome,
    method: Method,
    rolled_3d: int | None = None,
) -> EnchantmentResult:
    """What the roll did, by method.

    The two methods disagree on what a plain failure costs, which is the
    reason to pick one: Quick and Dirty burns the energy either way, while
    Slow and Sure burns the calendar and the materials but never FP or HP.
    """
    if outcome is CeremonialOutcome.CRITICAL_FAILURE:
        # "A critical failure always destroys the item and all materials used."
        return EnchantmentResult(
            outcome=outcome,
            energy_spent=True,
            item_destroyed=True,
            materials_lost=True,
        )

    if outcome is CeremonialOutcome.CRITICAL_SUCCESS:
        return EnchantmentResult(
            outcome=outcome,
            energy_spent=True,
            power_bonus=CRITICAL_SUCCESS_POWER_BONUS,
            may_have_further_enhancement=rolled_3d == FURTHER_ENHANCEMENT_ON,
        )

    if outcome is CeremonialOutcome.SUCCESS:
        return EnchantmentResult(outcome=outcome, energy_spent=True)

    # An ordinary failure. Quick and Dirty: "Succeed or fail, all the energy is
    # spent when the GM rolls the dice", and the enchantment perverts rather
    # than failing to happen. Slow and Sure: "the enchantment didn't work. The
    # time was wasted, and any materials used in the spell are lost."
    return EnchantmentResult(
        outcome=outcome,
        energy_spent=method is Method.QUICK_AND_DIRTY,
        materials_lost=method is Method.SLOW_AND_SURE,
    )


def quick_and_dirty_hours(energy: int) -> int:
    """"one hour per 100 points of energy required (round up)"."""
    if energy < 1:
        raise ValueError(f"an enchantment costs at least 1 energy, got {energy}")
    return math.ceil(energy / QUICK_AND_DIRTY_ENERGY_PER_HOUR)


def slow_and_sure_days(energy: int, mages: int = 1) -> float:
    """"one mage-day per point of energy required" — 100 energy is one mage
    for 100 days, or two mages for 50.

    ⚠️ There is no cap here, unlike mundane crafting's six workers. The limit
    is the assistant cap on the ROLL, which is a different constraint reached
    from a different direction — so a large team is possible and simply makes
    the roll harder.
    """
    if energy < 1:
        raise ValueError(f"an enchantment costs at least 1 energy, got {energy}")
    if mages < 1:
        raise ValueError(f"someone has to cast it, got {mages}")
    return energy / mages


def make_up_days(days_missed: int) -> int:
    """"If a day's work is skipped or interrupted, it takes two days to make
    it up." So an interruption costs double, not the day itself."""
    if days_missed < 0:
        raise ValueError(f"days_missed cannot be negative, got {days_missed}")
    return days_missed * INTERRUPTED_DAY_COST


def costs_fatigue(method: Method) -> bool:
    """Slow and Sure has "no FP or HP cost to the enchanters - they invested
    the energy gradually as the spell progressed".

    Which is why the HP-for-skill trade only exists on the other method: there
    is no HP being spent here to take a penalty for.
    """
    return method is Method.QUICK_AND_DIRTY
