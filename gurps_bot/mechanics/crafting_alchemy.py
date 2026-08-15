# numbers only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""GURPS Magic ch. 28 — the alchemy domain.

Third domain, and its own module for the same reason repair has one: it agrees
with the others on almost nothing. What alchemy alone does —

* **the roll has no critical success.** Either the process worked or it did not,
  so ``mechanics/checks.py`` cannot be used unmodified for a brew;
* **critical failure is TWO rolls.** The first disaster is a second technique
  roll; only failing THAT reaches the table;
* **a batch shares one roll.** Repair repeats the whole roll and the whole cost
  per unit; invention has no batch concept at all;
* **mana is an axis.** Nothing else in the family cares where you are standing;
* **the weakest worker rolls.** Invention's assistants each add +1 to the
  inventor's roll; here the lowest-skill alchemist who touched the batch makes
  the final roll, which makes an extra pair of hands a liability.

⚠️ **The elixir catalogue (Magic pp. 213-219) is NOT here and must not be.**
Cost per dose, brewing time and what an elixir DOES are per-elixir data; the
first two arrive as parameters and the third is the arc's hardest non-goal.

⚑ Judgment call worth naming, because it looks inconsistent with the Gadget
Bugs Table this project declined to implement (B476): the alchemical disaster
table IS implemented. The line is what the rows contain. B476's rows describe
what a gadget does wrong — awkward shape, attracts Men in Black, gets too hot —
which is effect prose. These rows carry a radius, a damage roll and whether the
lab survives, and the elixir's actual effect is deferred to the elixir. That is
the same shape as the B556 critical tables already in ``mechanics/tables.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gurps_bot.mechanics.crafting import ModifierBreakdown
from gurps_bot.mechanics.dice import DiceSpec


class Mana(Enum):
    """Where the alchemist is standing. No other crafting domain has this axis."""

    NONE = "No mana"
    LOW = "Low mana"
    NORMAL = "Normal mana"
    HIGH = "High mana"
    VERY_HIGH = "Very high mana"


class LabQuality(Enum):
    """Alchemy's OWN facility ladder — not B345, and not invention's.

    Invention's facility modifier is -1 to -10 at GM discretion; B345's
    equipment ladder bottoms out at -10 for technological skills. This one runs
    -1 / 0 / +1 / +TL/2 and is defined by floor space and dollars of glassware.
    Three ladders, three shapes, which is the per-domain invariant in one
    example.
    """

    MAKESHIFT = "Fire and clean containers"
    BASIC = "Sturdy table, $1,000 of equipment"
    PROFESSIONAL = "100+ sq ft, $5,000 of equipment"
    CUTTING_EDGE = "200+ sq ft, $20,000 of equipment"


_LAB_MODIFIER = {
    LabQuality.MAKESHIFT: -1,
    LabQuality.BASIC: 0,
    LabQuality.PROFESSIONAL: 1,
}

#: "Any attempt to brew an unmastered elixir with neither formulary nor
#: supervision is at -6."
UNMASTERED_PENALTY = -6

#: "every elixir is a Hard technique; most default to Alchemy-1."
TECHNIQUE_DEFAULT = -1

#: Guild gatekeeping, by retail cost per dose.
SECRET_FORMULA_ABOVE = 1_000
GRAND_MASTER_FORMULA_ABOVE = 10_000


def lab_modifier(quality: LabQuality, tech_level: int | None = None) -> int:
    """Magic p.211's laboratory ladder.

    ``CUTTING_EDGE`` is +TL/2 and therefore needs a tech level, so it is asked
    for rather than defaulted — the book notes the top rung "isn't really worth
    it until TL4", which is only true because the value is derived.
    """
    if quality is LabQuality.CUTTING_EDGE:
        if tech_level is None:
            raise ValueError(
                "a cutting-edge lab is +TL/2, so it needs a tech level; there is "
                "no sensible default"
            )
        if tech_level < 0:
            raise ValueError(f"tech_level cannot be negative, got {tech_level}")
        return tech_level // 2
    return _LAB_MODIFIER[quality]


def can_brew(mana: Mana) -> bool:
    """"In no-mana areas, elixirs cannot be made or used."""
    return mana is not Mana.NONE


def brewing_time_multiplier(mana: Mana) -> float:
    """Low mana doubles it; very high mana halves it."""
    if mana is Mana.NONE:
        raise ValueError("elixirs cannot be made in a no-mana area at all")
    if mana is Mana.LOW:
        return 2.0
    if mana is Mana.VERY_HIGH:
        return 0.5
    return 1.0


def elixir_duration_multiplier(mana: Mana, permanent: bool = False) -> float:
    """Low mana halves how long an elixir WORKS — a separate rule from how long
    it takes to make, and one that exempts permanent-effect elixirs."""
    if mana is Mana.NONE:
        raise ValueError("elixirs cannot be used in a no-mana area at all")
    if mana is Mana.LOW and not permanent:
        return 0.5
    return 1.0


def every_failure_is_critical(mana: Mana) -> bool:
    """Very high mana's trade: half the brewing time, "any failure is critical".

    The cost of speed is that the ordinary failure — ruined ingredients — is
    replaced by the two-stage disaster path.
    """
    return mana is Mana.VERY_HIGH


def batch_penalty(doses: int) -> int:
    """"the final roll is at -1 for every EXTRA dose of elixir produced".

    Extra, so one dose is unmodified and three doses is -2.
    """
    if doses < 1:
        raise ValueError(f"a batch is at least one dose, got {doses}")
    return -(doses - 1)


def batch_materials_cost(cost_per_dose: int, doses: int) -> int:
    """"multiplying the cost for materials by the number of doses produced".

    The other half of the same rule. Probe-2 elicitation caught this pair being
    applied one clause at a time, which is why both live in one module with
    tests that assert they move together.
    """
    if cost_per_dose < 0:
        raise ValueError(f"cost_per_dose cannot be negative, got {cost_per_dose}")
    if doses < 1:
        raise ValueError(f"a batch is at least one dose, got {doses}")
    return cost_per_dose * doses


def disaster_roll_penalty(doses: int) -> int:
    """"make a second technique roll at -1 for EACH dose of elixir in the batch".

    ⚑ Each, not each extra — so this is NOT ``batch_penalty``. A three-dose
    batch rolls its brew at -2 and its disaster-avoidance roll at -3. The two
    sentences are four lines apart and differ by one word; reusing one for the
    other is the obvious mistake and it is off by exactly one every time.
    """
    if doses < 1:
        raise ValueError(f"a batch is at least one dose, got {doses}")
    return -doses


def default_technique_level(alchemy_skill: int) -> int:
    """Where an unbought elixir technique sits: Alchemy-1, Hard."""
    return alchemy_skill + TECHNIQUE_DEFAULT


def is_mastered(technique: int, alchemy_skill: int) -> bool:
    """A technique bought up to its base skill is mastered.

    ⚑ This is a DERIVATION, and it has to stay one. The -6 for brewing blind
    is conditional on not having mastered the elixir, and mastery is already
    on the character sheet — a bot that asks "have you mastered it?" is asking
    the user to restate two numbers it was given.
    """
    return technique >= alchemy_skill


def blind_brewing_penalty(
    technique: int,
    alchemy_skill: int,
    *,
    formulary: bool = False,
    teacher: bool = False,
) -> int:
    """-6, and the three separate ways out of it.

    Mastery, a formulary, or supervision — any one is enough, which is why
    the mastered case never needs to know whether a book was present.
    """
    if is_mastered(technique, alchemy_skill) or formulary or teacher:
        return 0
    return UNMASTERED_PENALTY


def brewing_modifier(
    *,
    alchemy_skill: int,
    technique: int | None = None,
    lab: LabQuality = LabQuality.BASIC,
    tech_level: int | None = None,
    doses: int = 1,
    formulary: bool = False,
    teacher: bool = False,
) -> ModifierBreakdown:
    """What modifies the final Alchemy roll, relative to base Alchemy skill.

    ⚠️ ``unmastered=`` used to be a parameter here and is deliberately gone.
    Handing the module its own conclusion is the same defect as a ``quality=``
    argument on a craft call: the rule lives here, so the verdict does too.
    Sealed probe 2 caught it on re-verify — everything else in the domain
    passed, and this one condition had no implementation at all.
    """
    if technique is None:
        technique = default_technique_level(alchemy_skill)

    terms: list[tuple[str, int]] = []

    step = technique - alchemy_skill
    if step:
        terms.append(("elixir technique", step))

    modifier = lab_modifier(lab, tech_level)
    if modifier:
        terms.append((lab.value, modifier))

    blind = blind_brewing_penalty(
        technique, alchemy_skill, formulary=formulary, teacher=teacher
    )
    if blind:
        terms.append(("brewing blind: no mastery, no book, no teacher", blind))

    if doses > 1:
        terms.append((f"{doses} doses in the batch", batch_penalty(doses)))

    return ModifierBreakdown(terms=tuple(terms))


def effective_target(
    *,
    alchemy_skill: int,
    technique: int | None = None,
    lab: LabQuality = LabQuality.BASIC,
    tech_level: int | None = None,
    doses: int = 1,
    formulary: bool = False,
    teacher: bool = False,
) -> int:
    """The number the final roll is made against — a return value, not an ask."""
    return alchemy_skill + brewing_modifier(
        alchemy_skill=alchemy_skill,
        technique=technique,
        lab=lab,
        tech_level=tech_level,
        doses=doses,
        formulary=formulary,
        teacher=teacher,
    ).total


def final_roller_skill(skills: list[int]) -> int:
    """"the lowest-skill alchemist who worked on the elixir makes the final roll".

    Alchemy's reading of "assistant", and it is the opposite of invention's:
    there, each skilled assistant is +1 to the inventor's roll; here, bringing
    in a weaker pair of hands LOWERS the roll that decides the batch.
    """
    if not skills:
        raise ValueError("someone has to brew it")
    return min(skills)


def is_secret_formula(retail_per_dose: int) -> bool:
    return retail_per_dose > SECRET_FORMULA_ABOVE


def needs_grand_master(retail_per_dose: int) -> bool:
    return retail_per_dose > GRAND_MASTER_FORMULA_ABOVE


@dataclass(frozen=True, slots=True)
class Disaster:
    """One row of the 3d disaster table, as mechanics.

    ``elixir_radius_yards`` means everyone inside it suffers the elixir's own
    effect or its reverse, even odds — what that effect IS stays in the book.
    """

    low: int
    high: int
    elixir_radius_yards: int | None = None
    reversed_is_even_odds: bool = False
    lab_destroyed: bool = False
    alchemist_damage: DiceSpec | None = None


DISASTER_TABLE: tuple[Disaster, ...] = (
    Disaster(3, 5, elixir_radius_yards=100, reversed_is_even_odds=True),
    Disaster(6, 9, elixir_radius_yards=10, reversed_is_even_odds=True),
    Disaster(10, 12, lab_destroyed=True),
    Disaster(13, 15, lab_destroyed=True, alchemist_damage=DiceSpec(3, 6, 0)),
    Disaster(16, 18, lab_destroyed=True, alchemist_damage=DiceSpec(6, 6, 0)),
)


def disaster_for(rolled_3d: int) -> Disaster:
    if not 3 <= rolled_3d <= 18:
        raise ValueError(f"a 3d roll is 3..18, got {rolled_3d}")
    for row in DISASTER_TABLE:
        if row.low <= rolled_3d <= row.high:
            return row
    raise AssertionError("the disaster table has a gap")  # pragma: no cover


@dataclass(frozen=True, slots=True)
class BrewOutcome:
    succeeded: bool
    ingredients_ruined: bool
    needs_disaster_roll: bool
    disaster_roll_modifier: int = 0


def resolve_brew(outcome: str, doses: int = 1, mana: Mana = Mana.NORMAL) -> BrewOutcome:
    """What a finished brewing roll means.

    ⚠️ ``critical_success`` is refused rather than handled. "There are no
    critical successes in alchemy" is a rule about the roll itself, so a caller
    reporting one has used the core 3d6 engine unmodified — which is exactly the
    reuse this domain does not permit, and returning a plain success would hide
    it.
    """
    if doses < 1:
        raise ValueError(f"a batch is at least one dose, got {doses}")

    if outcome == "critical_success":
        raise ValueError(
            "alchemy has no critical successes — either the process worked or it "
            "did not. A caller seeing one is using the unmodified core engine."
        )
    if outcome == "success":
        return BrewOutcome(
            succeeded=True, ingredients_ruined=False, needs_disaster_roll=False
        )

    critical = outcome == "critical_failure" or every_failure_is_critical(mana)
    if not critical:
        # "A failure ruins the ingredients, wasting the money spent on them."
        return BrewOutcome(
            succeeded=False, ingredients_ruined=True, needs_disaster_roll=False
        )
    return BrewOutcome(
        succeeded=False,
        ingredients_ruined=True,
        needs_disaster_roll=True,
        disaster_roll_modifier=disaster_roll_penalty(doses),
    )
