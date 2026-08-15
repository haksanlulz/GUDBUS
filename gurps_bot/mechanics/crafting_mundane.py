# numbers only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Low-Tech Companion 3 ch. 5 — making a mundane item.

The fourth crafting domain, and the one that forced the arc's central API
decision. Everything else in this family rolls to find out **whether** it
worked; this rolls to find out **how well**. A crafting attempt cannot fail
into "nothing happened" — it fails into *cheap* or into *junk*, and both are
outcomes with an item at the end of them.

⚑ **So quality is a RETURN VALUE and a ``quality=`` argument would be wrong at
the API level.** The books' price table is only coherent this way: a fine blade
costs the same materials and the same hours as a good one, and its x4 price is
amortization across the blades that missed. You do not decide to make a fine
sword. You make a sword and find out.

⚑ **The highest skill present rolls.** Three domains looked like a rule —
alchemy hands the roll to the *weakest* worker, and repair and invention both
have their own answers — and then this one takes the best craftsman in the
room. Four domains, four readings of "who rolls", and the shared abstraction
that seemed safe at three-for-three does not exist.

⚠️ **The Crafting Table extraction is column-scrambled and this module does not
use it as extracted.** pdftotext shifts every row label up by one: the printed
"Failure by 4+" row loses its label to the header, so the extracted table
appears to say that a failure by 1-3 gives *Good* armor. The prose above the
table states each band in words and disambiguates all five rows, and the
alignment used here agrees with the prose in all three columns simultaneously.
This is the third column-scramble trap in this project (cf. B473's Concept
list, and the Testing paragraph cut by a sidebar).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Quality(Enum):
    """A crafting result. Ordered worst to best within each ladder."""

    JUNK = "Junk"
    CHEAP = "Cheap"
    BASIC = "Basic"
    GOOD = "Good"
    FINE = "Fine"
    VERY_FINE = "Very fine"
    #: Failure by 1-3 on a tool: it works, badly, and hands its user the
    #: improvised-equipment penalty from B345.
    POOR = "Poor (improvised)"


class ItemClass(Enum):
    """Which quality ladder an item reads.

    One roll, one margin, three different answers — which is why the class is
    an input to the *reading* rather than to the roll.
    """

    GENERAL = "General goods"
    ARMS_OR_ARMOR = "Weapon or armor"
    TOOL = "Tool"


class LaborKind(Enum):
    """LTC3: what fraction of a craftsman's pay the work actually costs."""

    #: "most undecorated, utilitarian goods", less-skilled workers under
    #: supervision.
    ROUTINE = "Routine work"
    #: "arms manufacture and the decorative options" — more master involvement.
    ARTISTIC = "Artistic or high-performance work"


_LABOR_FACTOR = {LaborKind.ROUTINE: 0.55, LaborKind.ARTISTIC: 0.75}

#: LTC3: "Divide monthly rates by 25 for daily rates, by 200 for hourly rates."
MONTH_TO_DAY = 25
MONTH_TO_HOUR = 200

#: "divide active time by the number of craftsmen and assistants involved, to a
#: maximum of six people." A fifth reading of "assistant" in this family, and
#: unlike the other four it touches no roll at all — it only divides the clock.
MAX_WORKERS = 6

#: "add up to 5 to effective margin of success ... if the roll succeeds."
MAX_FINE_MATERIALS_MARGIN = 5

#: Plate armor: "-1 per Armoury skill level below 14".
PLATE_ARMOUR_FULL_SKILL = 14


class MaterialMultiplier(Enum):
    """Items whose raw materials cost more than their weight suggests.

    Each is printed with its reason, and the reasons are not the same: bows
    need better wood, while swords and plate need more charcoal to work the
    metal. Same multiplier, unrelated causes.
    """

    NONE = 1
    #: "double raw materials costs for longbows and crossbows"
    LONGBOW_OR_CROSSBOW = 2
    #: "triple them for composite bows"
    COMPOSITE_BOW = 3
    #: "Swords and plate armor ... double raw materials costs to account for
    #: the large quantities of additional charcoal necessary."
    SWORD_OR_PLATE = 2


def materials_cost(
    weight_lbs: float,
    cost_per_lb: float,
    multiplier: MaterialMultiplier = MaterialMultiplier.NONE,
) -> float:
    """LTC3: weight x the Raw Materials Table, not a fraction of list price.

    ⚑ This is the number sealed probe 5 got wrong twice before anyone opened
    the book, and it passed unchallenged both times because a percentage of
    list price produces a plausible figure. It is derived from the item's
    WEIGHT and its material, and list price never enters it.
    """
    if weight_lbs < 0:
        raise ValueError(f"weight cannot be negative, got {weight_lbs}")
    if cost_per_lb < 0:
        raise ValueError(f"cost per lb cannot be negative, got {cost_per_lb}")
    return weight_lbs * cost_per_lb * multiplier.value


def labor_cost(list_price: float, materials: float) -> float:
    """LTC3: "An item's labor cost is its list price minus the materials cost."

    A residual, not a rate — so it is whatever the price does not explain, and
    the book notes it usually lands between one and four times materials.
    """
    if list_price < 0:
        raise ValueError(f"list price cannot be negative, got {list_price}")
    return list_price - materials


def hourly_labor_rate(monthly_pay: float, kind: LaborKind = LaborKind.ROUTINE) -> float:
    """(monthly pay x the work's factor) / 200."""
    if monthly_pay < 0:
        raise ValueError(f"monthly pay cannot be negative, got {monthly_pay}")
    return monthly_pay * _LABOR_FACTOR[kind] / MONTH_TO_HOUR


def daily_labor_rate(monthly_pay: float, kind: LaborKind = LaborKind.ROUTINE) -> float:
    if monthly_pay < 0:
        raise ValueError(f"monthly pay cannot be negative, got {monthly_pay}")
    return monthly_pay * _LABOR_FACTOR[kind] / MONTH_TO_DAY


def active_hours(labor: float, hourly_rate: float) -> float:
    """LTC3: "divide the labor portion of its cost by the labor pay rate"."""
    if hourly_rate <= 0:
        raise ValueError("a labor rate must be positive to divide by")
    if labor < 0:
        raise ValueError(f"labor cost cannot be negative, got {labor}")
    return labor / hourly_rate


def elapsed_hours(active: float, workers: int = 1) -> float:
    """Man-hours become wall-clock hours, and only up to six people.

    ⚠️ The cap is a rule, not a sanity check: a seventh pair of hands makes an
    item no faster, so silently dividing by 7 would invent a speed-up the book
    refuses.
    """
    if active < 0:
        raise ValueError(f"active time cannot be negative, got {active}")
    if workers < 1:
        raise ValueError(f"someone has to make it, got {workers} workers")
    return active / min(workers, MAX_WORKERS)


def rolling_skill(skills: list[int]) -> int:
    """LTC3: "using the highest craft skill among the workers involved".

    ⚑ The exact opposite of alchemy, where the lowest-skilled hand takes the
    roll. Here an extra worker can only help; there, an extra worker is a
    liability. Same word, contradictory rules, and no shared helper can serve
    both without being told which domain it is in — which is the argument for
    keeping them in separate modules.
    """
    if not skills:
        raise ValueError("someone has to make it")
    return max(skills)


def plate_armour_effective_skill(armoury_skill: int) -> int:
    """LTC3: "-1 per Armoury skill level below 14".

    So the penalty grows as the smith gets worse, and the book's own worked
    cases are 13 working as 12 and 12 working as 10. Skill 14+ is untouched.
    """
    if armoury_skill < 0:
        raise ValueError(f"skill cannot be negative, got {armoury_skill}")
    if armoury_skill >= PLATE_ARMOUR_FULL_SKILL:
        return armoury_skill
    return armoury_skill - (PLATE_ARMOUR_FULL_SKILL - armoury_skill)


def effective_margin(
    margin: int,
    *,
    fine_materials: int = 0,
    crucible_steel: bool = False,
) -> int:
    """Margin bonuses, which is the only place superior materials apply.

    ⚑ **They add to the MARGIN, on a success — never to the skill.** A better
    ingot does not make the smith likelier to succeed; it makes a successful
    piece better. Adding it to skill would let fine materials rescue a failed
    roll, which is precisely what the book withholds.
    """
    if fine_materials < 0:
        raise ValueError(f"fine materials bonus cannot be negative, got {fine_materials}")
    if fine_materials > MAX_FINE_MATERIALS_MARGIN:
        raise ValueError(
            f"the book allows up to +{MAX_FINE_MATERIALS_MARGIN} for superior "
            f"materials, got +{fine_materials}"
        )
    if margin < 0:
        # "if the roll succeeds" — a failure gets nothing.
        return margin
    bonus = fine_materials
    if crucible_steel:
        bonus += CRUCIBLE_STEEL_MARGIN
    return margin + bonus


#: Crucible Steel: an ingot "improves margin of success by 5 when determining
#: that item's quality".
CRUCIBLE_STEEL_MARGIN = 5
#: "$20 worth of materials per pound of steel to be produced."
CRUCIBLE_STEEL_COST_PER_LB = 20
#: "five man-days per batch; there's no bonus for taking additional time."
CRUCIBLE_STEEL_MAN_DAYS = 5
#: "at -1 per full 3 lbs. of steel in the batch."
CRUCIBLE_STEEL_LBS_PER_PENALTY = 3


def crucible_steel_penalty(pounds: float) -> int:
    """-1 per FULL 3 lbs, so 5 lbs is -1 and 6 lbs is -2."""
    if pounds < 0:
        raise ValueError(f"pounds cannot be negative, got {pounds}")
    return -int(pounds // CRUCIBLE_STEEL_LBS_PER_PENALTY)


def crucible_steel_materials(pounds: float) -> float:
    if pounds < 0:
        raise ValueError(f"pounds cannot be negative, got {pounds}")
    return pounds * CRUCIBLE_STEEL_COST_PER_LB


#: The Crafting Table, read from the prose rather than from the scrambled
#: extraction. Each row is (lowest margin in the band, quality by item class).
#: A failure is a negative margin here, so the bands run from -4 downward.
_JUNK_FAILURE_BY = 4

_BANDS: tuple[tuple[int, dict[ItemClass, Quality]], ...] = (
    (18, {
        ItemClass.GENERAL: Quality.FINE,
        ItemClass.ARMS_OR_ARMOR: Quality.VERY_FINE,
        ItemClass.TOOL: Quality.FINE,
    }),
    (12, {
        ItemClass.GENERAL: Quality.GOOD,
        ItemClass.ARMS_OR_ARMOR: Quality.FINE,
        ItemClass.TOOL: Quality.GOOD,
    }),
    (0, {
        ItemClass.GENERAL: Quality.BASIC,
        ItemClass.ARMS_OR_ARMOR: Quality.GOOD,
        ItemClass.TOOL: Quality.BASIC,
    }),
)

_FLAWED = {
    ItemClass.GENERAL: Quality.CHEAP,
    ItemClass.ARMS_OR_ARMOR: Quality.CHEAP,
    ItemClass.TOOL: Quality.POOR,
}


@dataclass(frozen=True, slots=True)
class CraftResult:
    """What a crafting roll produced.

    There is no ``succeeded`` field on purpose. Every band except junk leaves
    the craftsman holding an item, so a boolean would have to answer a question
    the domain does not ask.
    """

    quality: Quality
    margin: int
    materials_lost: bool = False
    sells_for_at_most_half: bool = False

    @property
    def is_junk(self) -> bool:
        return self.quality is Quality.JUNK


def craft_quality(
    margin: int, item_class: ItemClass = ItemClass.GENERAL
) -> CraftResult:
    """The whole domain in one call: a margin in, a quality out.

    ⚑ **Critical success is deliberately absent.** LTC3 says outright that it
    "doesn't impact quality beyond margin of success", so this is the third
    check variant in the family: alchemy suppresses critical successes,
    ceremonial magic shifts the thresholds, and here a critical success is
    simply a success whose margin already said everything.
    """
    if margin <= -_JUNK_FAILURE_BY:
        # "Failure by 4+ gives junk! At least half of the raw materials are lost."
        return CraftResult(
            quality=Quality.JUNK, margin=margin, materials_lost=True
        )
    if margin < 0:
        # "Failure by 1-3 indicates a functional-but-flawed finished piece."
        return CraftResult(
            quality=_FLAWED[item_class],
            margin=margin,
            sells_for_at_most_half=True,
        )
    for floor, qualities in _BANDS:
        if margin >= floor:
            return CraftResult(quality=qualities[item_class], margin=margin)
    raise AssertionError("the crafting table has a gap")  # pragma: no cover
