# numbers and own-words summaries; no SJG text reproduced; GURPS is a Steve Jackson Games trademark
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
Power is min(effective Enchant, effective skill in the spell being placed)
(Magic p. 17). So a superb enchanter with a shaky grasp of the spell makes a
weak item, and there is no averaging.

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


#: Magic p. 17: 15 is the qualifying effective skill, in both Enchant and the
#: spell being placed, for the caster and every assistant alike.
#: Also the floor a working item's Power must clear, which is not a coincidence
#: — Power IS that effective skill.
MINIMUM_EFFECTIVE_SKILL = 15

#: Magic pp. 16-18: low mana costs an item 5 Power while it is there, so below
#: Power 20 it stops working in such a zone.
LOW_MANA_POWER_PENALTY = -5

#: Magic p. 17: every assistant costs the caster 1 point of skill. The rule sits
#: inside Quick and Dirty's energy paragraphs and is scoped to it — Slow and Sure
#: restates its own assistant rules on p. 18 and no skill penalty is among them.
ASSISTANT_PENALTY_EACH = -1

#: Magic p. 17: each HP the caster burns for energy is -1 to his effective skill.
HP_PENALTY_EACH = -1

#: Magic p. 17: one more -1 when someone outside the circle is within 10 yards.
BYSTANDER_PENALTY = -1
BYSTANDER_RADIUS_YARDS = 10

#: Ceremonial thresholds — these are the rule, not a clamp.
CEREMONIAL_AUTOMATIC_FAILURE = 16
CEREMONIAL_CRITICAL_FAILURE_FROM = 17

#: Magic pp. 16-18: rolling a critical success bumps Power upward by 2d, on top
#: of whatever the caster and spell skills would otherwise set.
CRITICAL_SUCCESS_POWER_BONUS = DiceSpec(2, 6, 0)
#: Magic pp. 16-18: on a natural 3 the GM may grant the item something extra —
#: flagged, never invented.
FURTHER_ENHANCEMENT_ON = 3

#: Magic p. 17, Quick and Dirty: each started block of 100 energy takes an hour.
QUICK_AND_DIRTY_ENERGY_PER_HOUR = 100
#: Magic p. 18, Slow and Sure: each energy point takes one mage-day, i.e. one
#: caster working a full eight-hour day.
MAGE_DAY_HOURS = 8
#: Magic p. 18: losing a day to the calendar, for any reason, sets the timeline
#: back by two days, not one.
INTERRUPTED_DAY_COST = 2


def enchanting_skill(enchant_skill: int, spell_skill: int) -> int:
    """The lower of the two, and the whole rule in one line.

    ⚑ Not an average and not the Enchant skill alone. Both of the book's own
    worked examples happen to have Enchant at or above the other spell, so
    neither of them can tell "the lower of both" from "the enchanted spell" —
    the general statement on p. 17 is what settles it, and it takes the lower
    of the two.
    """
    if enchant_skill < 0 or spell_skill < 0:
        raise ValueError("skills cannot be negative")
    return min(enchant_skill, spell_skill)


def everyone_is_qualified(*effective_skills: int) -> bool:
    """Magic p. 17: everyone in the circle needs 15+ effective skill in both
    spells. An unqualified assistant is not a weaker assistant; they
    cannot contribute energy at all."""
    return all(skill >= MINIMUM_EFFECTIVE_SKILL for skill in effective_skills)


def assistant_cap(base_skill: int) -> int:
    """How many assistants the caster may bring, DERIVED rather than printed.

    Magic p. 17: the headcount is capped where the -1 per assistant would
    bring the caster down to 15; past that the enchantment fails. So a
    skill-15 caster may bring none, and each further point of skill buys
    exactly one more pair of hands.

    ⚠️ Quick and Dirty only — the cap is derived FROM the -1, which Slow and
    Sure does not take. A slow circle has no headcount cap; p. 19's
    Disorganization sidebar openly allows for enchanting at large scale.
    """
    if base_skill < MINIMUM_EFFECTIVE_SKILL:
        return 0
    return base_skill - MINIMUM_EFFECTIVE_SKILL


def enchanting_modifier(
    *,
    method: Method = Method.QUICK_AND_DIRTY,
    assistants: int = 0,
    hp_spent: int = 0,
    bystanders: bool = False,
) -> ModifierBreakdown:
    """What modifies the enchanting roll — and every term is Quick and Dirty's.

    All three penalties are printed inside Quick and Dirty Enchantment's
    energy paragraphs (p. 17). Under Slow and Sure, assistants divide the
    mage-days and touch no roll, disturbance is the Interruptions box's
    business, and spending HP is impossible — p. 18 charges the enchanters
    no FP or HP at all — so it is refused rather than silently dropped, the
    B475-gadgeteer precedent. Assistants and bystanders stay legal arguments
    there (both can be present; they just carry no penalty).

    ⚠️ ``hp_spent`` is the caster's own. Assistants may also spend HP and take
    the same -1 each, but an assistant's skill only has to stay at 15 or
    better and never sets Power (p. 17) — so an assistant's HP cost
    never reaches this breakdown, and folding it in would quietly weaken every
    item made by a bleeding helper.
    """
    if assistants < 0:
        raise ValueError(f"assistants cannot be negative, got {assistants}")
    if hp_spent < 0:
        raise ValueError(f"hp_spent cannot be negative, got {hp_spent}")
    if method is Method.SLOW_AND_SURE:
        if hp_spent:
            raise ValueError(
                "Slow and Sure costs no FP or HP, so hp_spent must be 0"
            )
        return ModifierBreakdown(terms=())

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
    method: Method = Method.QUICK_AND_DIRTY,
    assistants: int = 0,
    hp_spent: int = 0,
    bystanders: bool = False,
) -> int:
    """The number rolled against, which is also the item's Power.

    Under Slow and Sure this is the bare min() — the penalties are Quick and
    Dirty's, so a big slow circle makes a big item slowly rather than badly.
    """
    base = enchanting_skill(enchant_skill, spell_skill)
    return base + enchanting_modifier(
        method=method, assistants=assistants, hp_spent=hp_spent,
        bystanders=bystanders,
    ).total


def item_power(effective: int) -> int:
    """See effective_skill() (Magic p. 17): the item's Power is that figure —
    the min() from enchanting_skill() after its modifiers — not a separate
    roll result.

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
    """Magic pp. 16-18: an item below Power 15 does nothing.

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

    Magic pp. 16-18, following the ceremonial-magic rule: 16 is an automatic
    failure and 17-18 a critical one, at any effective skill.
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
        # Magic pp. 16-18: any critical failure wrecks the item and all materials.
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

    # An ordinary failure. Quick and Dirty (p. 17): the energy is gone the
    # moment the dice are rolled, whatever they show, and the enchantment
    # perverts rather than failing to happen. Slow and Sure (p. 18): nothing
    # is enchanted, and both the time and the materials are forfeit.
    return EnchantmentResult(
        outcome=outcome,
        energy_spent=method is Method.QUICK_AND_DIRTY,
        materials_lost=method is Method.SLOW_AND_SURE,
    )


def quick_and_dirty_hours(energy: int) -> int:
    """Magic p. 17: hours = energy / 100, rounded up."""
    if energy < 1:
        raise ValueError(f"an enchantment costs at least 1 energy, got {energy}")
    return math.ceil(energy / QUICK_AND_DIRTY_ENERGY_PER_HOUR)


def slow_and_sure_days(energy: int, mages: int = 1) -> float:
    """Magic p. 18: days = energy / mages, each point costing one mage-day —
    100 energy is one mage for 100 days, or two mages for 50.

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
    """Magic p. 18: every missed or broken-off day is repaid with two.
    So an interruption costs double, not the day itself."""
    if days_missed < 0:
        raise ValueError(f"days_missed cannot be negative, got {days_missed}")
    return days_missed * INTERRUPTED_DAY_COST


def costs_fatigue(method: Method) -> bool:
    """Magic p. 18: Slow and Sure charges no FP or HP, because the energy
    goes in a little at a time over the whole project.

    Which is why the HP-for-skill trade only exists on the other method: there
    is no HP being spent here to take a penalty for.
    """
    return method is Method.QUICK_AND_DIRTY
