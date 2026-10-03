# numbers and page cites; comments paraphrase, never quote; GURPS is a Steve
# Jackson Games trademark
"""B473-474 New Inventions — the invention procedure as an engine.

Pure functions, no Discord types, no session. The bot facilitates the procedure
and never adjudicates: every call the book hands to the GM arrives here as a
parameter, never as an inference.

Three things worth knowing before editing:

* **The four stages are not variations on one stage.** Each has its own roller,
  its own cadence, its own skill and its own money. ``STAGES`` states that
  explicitly rather than leaving it to the caller to remember.
* **Money is three unlike figures.** A one-off facilities charge per inventor, a
  per-attempt charge equal to the item's retail price, and a per-copy production
  charge. Different payers, different triggers. ``InventionCosts`` deliberately
  has no total.
* **Nothing here is shared with the other crafting domains.** Alchemy, repair,
  enchantment and mundane crafting each disagree with this module on facility
  ladders, on what a batch means, on which skill is rolled, and on what the roll
  even reports. "Assistant" alone means five different things across the five.
  The per-domain scan exists because the obvious abstraction is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gurps_bot.mechanics.dice import DiceSpec

#: B474: each assistant with skill 20+ in a required skill adds +1 to the
#: inventor's roll, capped at +4. That is how invention reads "assistant" — a
#: flat roll bonus. No other crafting domain reads it this way.
ASSISTANT_BONUS_EACH = 1
ASSISTANT_BONUS_CAP = 4
ASSISTANT_MIN_SKILL = 20

#: B474: testing rolls against the device's operation skill, at -3.
TESTING_PENALTY = -3

#: B474 sidebar: a bug nobody found shows up when an operation roll misses by
#: 5 or more.
BUG_SURFACE_MARGIN = -5

#: B474: poor facilities cost -1 to -10, the GM choosing the figure. A range
#: and a ruling, so the engine takes the number instead of deriving a ladder.
FACILITY_PENALTY_RANGE = (-10, 0)

#: B473: a clear or clever description earns +1 or +2 on the invention rolls;
#: an item that varies an existing one earns +1 to +5.
DESCRIPTION_BONUS_RANGE = (0, 2)
VARIANT_BONUS_RANGE = (0, 5)

#: -5 for each TL the device sits above the inventor, counted per step.
#:
#: ⚑ **This is RAW, and the page that prints it is B475, not B474.** B473's New
#: Inventions covers at most one TL in advance and prices that step at a flat
#: -5; B475's Gadgeteering keeps the number but lifts the one-TL cap, so a
#: gadgeteer may aim at any TL and pays the -5 once for every step past his own.
TL_GAP_PENALTY_EACH = -5

#: B474: an invention one TL above the inventor costs three times as much.
#: New Inventions only, and only for the one step it contemplates. Gadgeteering
#: replaces this wholesale with a base-plus-increment table and a doubling
#: accumulation — see ``gadgeteer_facility_cost`` and ``gadgeteer_attempt_cost``.
TL_COST_MULTIPLIER = 3


#: B474: the prototype explosion deals 2d or more — a floor rather than an exact
#: roll, which is why the caller is told it is a minimum.
DISASTER_DAMAGE = DiceSpec(count=2, sides=6, modifier=0)


class Roller(Enum):
    """Who makes a stage's roll. Not decoration — it decides visibility."""

    GM = "GM"
    PLAYER = "player"
    NOBODY = "nobody"


@dataclass(frozen=True, slots=True)
class TimeSpec:
    """A stage's time cost, unrolled. The unit changes down the table."""

    dice: DiceSpec
    unit: str


class Complexity(Enum):
    """B473's four ratings.

    The concept penalty, the facilities price and the prototype time are three
    unrelated ladders that happen to be indexed by the same word — they are
    carried together so a caller cannot pair a Complex penalty with an Average
    price, which is the mistake the table's layout invites.
    """

    SIMPLE = ("Simple", -6, 50_000, DiceSpec(1, 6, -2), "days")
    AVERAGE = ("Average", -10, 100_000, DiceSpec(2, 6, 0), "days")
    COMPLEX = ("Complex", -14, 250_000, DiceSpec(1, 6, 0), "months")
    AMAZING = ("Amazing", -22, 500_000, DiceSpec(3, 6, 0), "months")

    def __init__(self, label: str, penalty: int, facility_cost: int,
                 dice: DiceSpec, unit: str) -> None:
        self.label = label
        self.concept_penalty = penalty
        self.facility_cost = facility_cost
        self.prototype_time = TimeSpec(dice=dice, unit=unit)


class Method(Enum):
    """How an invention is being attempted. NOT interchangeable.

    One domain, three methods, and they disagree on nearly every number that
    matters: the complexity penalty, whether the new-technology penalty exists,
    how far above your TL you may reach, how facilities are priced, how the
    per-attempt charge scales, how long a prototype takes, and whether a major
    bug is even possible. ``tests/test_crafting_methods.py`` asserts the
    disagreements rather than trusting this docstring.

    The gadgeteering methods additionally require an advantage — Gadgeteer
    (B56), or Quick Gadgeteer — so which method applies is a fact about the
    character, not a preference.
    """

    NEW_INVENTIONS = "New Inventions"
    GADGETEERING = "Gadgeteering"
    QUICK_GADGETEERING = "Quick Gadgeteering"


#: B475: a gadgeteer's concept penalty is 0 for Simple, -2 Average, -4 Complex
#: and -8 Amazing. Far milder than B473's -6/-10/-14/-22 — the single biggest
#: difference between the methods.
GADGETEER_CONCEPT_PENALTY = {
    Complexity.SIMPLE: 0,
    Complexity.AVERAGE: -2,
    Complexity.COMPLEX: -4,
    Complexity.AMAZING: -8,
}

#: B475's facilities table. Base Cost matches B474's figures exactly; what is
#: new is the TL Increment, added once per TL above the campaign TL — which is
#: what replaces New Inventions' flat "triple".
GADGETEER_FACILITY_BASE = {
    Complexity.SIMPLE: 50_000,
    Complexity.AVERAGE: 100_000,
    Complexity.COMPLEX: 250_000,
    Complexity.AMAZING: 500_000,
}
GADGETEER_FACILITY_TL_INCREMENT = {
    Complexity.SIMPLE: 100_000,
    Complexity.AVERAGE: 250_000,
    Complexity.COMPLEX: 500_000,
    Complexity.AMAZING: 1_000_000,
}

#: B476, Quick Gadgeteering: the penalty on the **scrounging** roll for parts.
#:
#: ⚠️ Not a Concept or Prototype penalty, despite reading like one. On B476
#: these figures sit a paragraph away from the roll they modify, so the list is
#: easy to file under the wrong heading. Third such layout trap in this
#: chapter; the other two are noted in ``concept_modifier`` and the Testing
#: rules.
QUICK_SCROUNGING_PENALTY = {
    Complexity.SIMPLE: 0,
    Complexity.AVERAGE: -2,
    Complexity.COMPLEX: -6,
    Complexity.AMAZING: -10,
}

#: B476: a quick gadgeteer assembles in minutes or hours, not days or months.
QUICK_ASSEMBLY_TIME = {
    Complexity.SIMPLE: TimeSpec(DiceSpec(2, 6, 0), "minutes"),
    Complexity.AVERAGE: TimeSpec(DiceSpec(1, 6, -2), "hours"),
    Complexity.COMPLEX: TimeSpec(DiceSpec(1, 6, 0), "hours"),
    Complexity.AMAZING: TimeSpec(DiceSpec(4, 6, 0), "hours"),
}

#: B476: a quick gadgeteer who buys parts pays a regular gadgeteer's facilities
#: and prototype figures divided by 100.
QUICK_PURCHASE_DIVISOR = 100

#: Ascending, so "one step easier" is an index step.
_COMPLEXITY_ORDER = (
    Complexity.SIMPLE, Complexity.AVERAGE, Complexity.COMPLEX, Complexity.AMAZING,
)


# --- computer programs ------------------------------------------------------


def program_complexity(rating: int) -> Complexity:
    """B473: a program's numerical Complexity, mapped for cost and time only.

    Ratings 1-3 count as Simple, 4-5 Average, 6-7 Complex, 8+ Amazing. The
    mapping is explicitly NOT used for the concept penalty, which stays on the
    rating itself.
    """
    if rating < 1:
        raise ValueError(f"program Complexity starts at 1, got {rating}")
    if rating <= 3:
        return Complexity.SIMPLE
    if rating <= 5:
        return Complexity.AVERAGE
    if rating <= 7:
        return Complexity.COMPLEX
    return Complexity.AMAZING


def program_concept_penalty(rating: int) -> int:
    """B473: a program's concept penalty is double its Complexity rating.

    Unbounded on purpose — a Complexity 12 program is harsher than Amazing, and
    capping it at the table's -22 would be an invention.
    """
    if rating < 1:
        raise ValueError(f"program Complexity starts at 1, got {rating}")
    return -2 * rating


def reinvented_complexity(base: Complexity, tl_advantage: int) -> Complexity:
    """B473 sidebar: each TL of hindsight drops complexity one step, never
    below Simple."""
    if tl_advantage < 0:
        raise ValueError(
            "tl_advantage is how far the inventor's TL EXCEEDS the invention's; "
            "inventing above your own TL is a -5 modifier, not a complexity step"
        )
    index = max(0, _COMPLEXITY_ORDER.index(base) - tl_advantage)
    return _COMPLEXITY_ORDER[index]


# --- modifiers --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModifierBreakdown:
    """Every term named, so the guided flow can show its work.

    A bare integer cannot be audited at the table, and the invention modifiers
    are numerous enough that "-27" tells a player nothing about which of the
    GM's calls to argue with.
    """

    terms: tuple[tuple[str, int], ...]

    @property
    def total(self) -> int:
        return sum(value for _, value in self.terms)


def _check_range(name: str, value: int, bounds: tuple[int, int]) -> None:
    low, high = bounds
    if not low <= value <= high:
        raise ValueError(f"{name} must be {low}..{high}, got {value}")


def concept_modifier(
    complexity: Complexity,
    *,
    program_complexity: int | None = None,
    working_model: bool = False,
    device_exists: bool = False,
    variant_bonus: int = 0,
    new_technology: bool = False,
    tl_gap: int = 0,
    description_bonus: int = 0,
) -> ModifierBreakdown:
    """B473's modifier list for the Concept roll.

    ⚠️ On B473 this list sits before the Concept heading, between Required
    Skills and Complexity. It belongs to Concept, and B474 then inherits it
    wholesale for the Prototype roll.
    """
    _check_range("variant_bonus", variant_bonus, VARIANT_BONUS_RANGE)
    _check_range("description_bonus", description_bonus, DESCRIPTION_BONUS_RANGE)
    if tl_gap < 0:
        raise ValueError(
            f"tl_gap is how far the invention is ABOVE the inventor's TL, got "
            f"{tl_gap}; inventing BELOW your TL reduces complexity instead "
            f"(see reinvented_complexity)"
        )

    terms: list[tuple[str, int]] = []

    if program_complexity is not None:
        terms.append((
            f"Complexity {program_complexity} program",
            program_concept_penalty(program_complexity),
        ))
    else:
        terms.append((f"{complexity.label} invention", complexity.concept_penalty))

    # B473: +5 with a working model to copy, +2 when the device exists but no
    # model is at hand. The second is the weaker case of the first, so having a
    # model does not also earn the no-model bonus.
    if working_model:
        terms.append(("working model to copy", 5))
    elif device_exists:
        terms.append(("device exists, no model", 2))

    if variant_bonus:
        terms.append(("variant on an existing item", variant_bonus))
    if new_technology:
        # B473: -5 whatever the TL — this is about the campaign, not the
        # inventor, so it stacks with the TL penalty below rather than
        # replacing it.
        terms.append(("new core technology for this campaign", -5))
    if tl_gap:
        label = (
            "device is one TL above the inventor"
            if tl_gap == 1
            else f"device is {tl_gap} TLs above the inventor"
        )
        terms.append((label, tl_gap * TL_GAP_PENALTY_EACH))
    if description_bonus:
        terms.append(("clear or clever description", description_bonus))

    return ModifierBreakdown(terms=tuple(terms))


def prototype_modifier(
    complexity: Complexity,
    *,
    skilled_assistants: int = 0,
    facility_penalty: int = 0,
    **concept_kwargs,
) -> ModifierBreakdown:
    """B474: every Concept modifier carries over, plus two of Prototype's own."""
    _check_range("facility_penalty", facility_penalty, FACILITY_PENALTY_RANGE)
    if skilled_assistants < 0:
        raise ValueError(f"skilled_assistants cannot be negative: {skilled_assistants}")

    terms = list(concept_modifier(complexity, **concept_kwargs).terms)

    if skilled_assistants:
        counted = min(skilled_assistants, ASSISTANT_BONUS_CAP)
        terms.append((
            f"{skilled_assistants} assistant(s) at skill {ASSISTANT_MIN_SKILL}+",
            counted * ASSISTANT_BONUS_EACH,
        ))
    if facility_penalty:
        terms.append(("facilities below the best available", facility_penalty))

    return ModifierBreakdown(terms=tuple(terms))


def gadgeteer_concept_modifier(
    complexity: Complexity,
    *,
    tl_gap: int = 0,
    program_complexity: int | None = None,
    working_model: bool = False,
    device_exists: bool = False,
    variant_bonus: int = 0,
    description_bonus: int = 0,
) -> ModifierBreakdown:
    """B475 Concept, for a character with the Gadgeteer advantage.

    Three departures from B473, and each is a rule rather than a discount:

    * the complexity penalty is its own much milder ladder;
    * the -5 for technology new to the campaign **does not apply** —
      so this function takes no ``new_technology`` argument at all, rather than
      accepting one and quietly dropping it;
    * software takes the plain Complexity rating, **not double it** — the exact
      inverse of B473's rule for the same case.

    The TL gap is uncapped here: B473's one-step ceiling is a New Inventions
    limit, and B475 removes it.
    """
    if tl_gap < 0:
        raise ValueError(f"tl_gap cannot be negative, got {tl_gap}")
    _check_range("variant_bonus", variant_bonus, VARIANT_BONUS_RANGE)
    _check_range("description_bonus", description_bonus, DESCRIPTION_BONUS_RANGE)

    terms: list[tuple[str, int]] = []

    if program_complexity is not None:
        if program_complexity < 1:
            raise ValueError(f"program Complexity starts at 1, got {program_complexity}")
        # B475: the rating itself, where B473 doubles it.
        terms.append((
            f"Complexity {program_complexity} program", -program_complexity,
        ))
    else:
        terms.append((
            f"{complexity.label} gadget", GADGETEER_CONCEPT_PENALTY[complexity],
        ))

    if working_model:
        terms.append(("working model to copy", 5))
    elif device_exists:
        terms.append(("device exists, no model", 2))
    if variant_bonus:
        terms.append(("variant on an existing item", variant_bonus))
    if tl_gap:
        terms.append((
            f"{tl_gap} TL(s) above the gadgeteer", tl_gap * TL_GAP_PENALTY_EACH,
        ))
    if description_bonus:
        terms.append(("clear or clever description", description_bonus))

    return ModifierBreakdown(terms=tuple(terms))


def gadgeteer_facility_cost(
    complexity: Complexity, tl_gap: int = 0, *, reuses_facilities: bool = False
) -> int:
    """B475: the Base Cost prices a device at the campaign's own TL; every TL
    past that layers on one TL Increment.

    Additive, not multiplicative — which is what New Inventions' flat "triple"
    is replaced by. B475's own worked example is a Complex gadget three TLs up:
    $250,000 + 3 x $500,000 = **$1,750,000**.

    The reuse discount is narrower here than in B474: it wants a prior project
    of equal or higher complexity **and tech level**, where New Inventions asks
    only for complexity. The caller decides whether it applies; this applies it.
    """
    if tl_gap < 0:
        raise ValueError(f"tl_gap cannot be negative, got {tl_gap}")
    cost = (
        GADGETEER_FACILITY_BASE[complexity]
        + GADGETEER_FACILITY_TL_INCREMENT[complexity] * tl_gap
    )
    return cost // 10 if reuses_facilities else cost


def gadgeteer_attempt_cost(retail_price: int, tl_gap: int = 0) -> int:
    """B475: start from the retail price at the device's own TL, then double
    once per TL of separation, keeping every doubled step in the total rather
    than just the last.

    Accumulate, not merely double: the book's example spends $4,000 + $8,000 +
    $16,000 + $32,000 = $60,000 for three TLs, i.e. every rung is paid, not just
    the top one. That is ``retail x (2**(tl_gap + 1) - 1)``, and it grows fast
    enough that the distinction matters at the first TL rather than the fourth.
    """
    if retail_price < 0:
        raise ValueError(f"retail_price cannot be negative, got {retail_price}")
    if tl_gap < 0:
        raise ValueError(f"tl_gap cannot be negative, got {tl_gap}")
    return retail_price * (2 ** (tl_gap + 1) - 1)


def gadgeteer_bugs_from_prototype(margin: int, critical_success: bool = False) -> BugLoad:
    """B475 Testing and Bugs, for a gadgeteer.

    A margin of 3+ leaves the prototype clean; a narrower success still leaves
    1d/2 minor bugs. A major bug is off the table entirely. That last point is
    the whole difference and it is absolute — a gadgeteer's prototype cannot
    carry the catastrophic kind, so no margin, and no critical, produces one.

    Above the gadgeteer's own TL the minor bugs are then rolled on B476's Gadget
    Bugs Table. That table is deliberately NOT reproduced here: it is effect
    prose, which is the arc's hardest non-goal. Cite the page and let the reader
    own the book.
    """
    if margin < 0:
        raise ValueError(
            "a failed Prototype roll produces no prototype, so it has no bug load"
        )
    if critical_success or margin >= 3:
        return BugLoad(major_dice=None, minor_dice=None)
    return BugLoad(major_dice=None, minor_dice=DiceSpec(1, 6, 0), minor_halved=True)


def gadget_bugs_are_rolled_on_the_table(gadgeteer_tl: int, gadget_tl: int) -> bool:
    """B475: a device built above the gadgeteer's own tech level gets one roll
    per minor bug on the Gadget Bugs Table.

    Returns whether the table applies. What is ON the table stays in the book —
    see the note in ``gadgeteer_bugs_from_prototype``.
    """
    return gadget_tl > gadgeteer_tl


def gadgeteer_production_price(retail_price: int, tl_gap: int = 0) -> int:
    """B475 Production: every production figure uses the TL-adjusted retail
    price.

    The book is explicit that this is the accumulated figure and not the native
    one — B475's worked example prices production at $60,000, not $4,000 — so
    a copy of a TL+3 gadget is priced off $60,000.
    """
    return gadgeteer_attempt_cost(retail_price, tl_gap)


def quick_assembly_time(complexity: Complexity) -> TimeSpec:
    """B476: minutes and hours, where every other method deals in days.

    ⚠️ The Average entry carries a printed exception the dice cannot express:
    1d-2 hours, except that a roll of 1 or 2 means **30 minutes**. The
    spec returned here is the dice; :func:`quick_assembly_is_half_an_hour`
    answers the exception, because a caller that only reads the dice would
    render "0 hours" or "-1 hours" for a third of all rolls.
    """
    return QUICK_ASSEMBLY_TIME[complexity]


def quick_assembly_is_half_an_hour(complexity: Complexity, rolled: int) -> bool:
    """B476's parenthetical on the Average row, as a rule rather than a note."""
    return complexity is Complexity.AVERAGE and rolled in (1, 2)


def quick_scrounged_project_cost(rolled_1d: int) -> int:
    """B476: a scrounged project costs (1d-1) x $100 in total, so a roll of 1
    is free.

    One figure for the WHOLE project, where every other method bills facilities
    and attempts separately — which is why this returns a bare int rather than
    an ``InventionCosts``: there is nothing to keep apart.
    """
    if not 1 <= rolled_1d <= 6:
        raise ValueError(f"a 1d roll is 1..6, got {rolled_1d}")
    return (rolled_1d - 1) * 100


def quick_purchased_costs(
    complexity: Complexity, retail_price: int, tl_gap: int = 0
) -> tuple[int, int]:
    """B476: bought parts cost a regular gadgeteer's facilities and prototype
    figures, divided by 100.

    Returns ``(facilities, per_attempt)`` — still two figures, still not summed.
    """
    facilities = gadgeteer_facility_cost(complexity, tl_gap)
    attempt = gadgeteer_attempt_cost(retail_price, tl_gap)
    return facilities // QUICK_PURCHASE_DIVISOR, attempt // QUICK_PURCHASE_DIVISOR


def effective_target(skill: int, modifier: ModifierBreakdown) -> int:
    """Skill plus modifiers, with no floor.

    B347 has no minimum effective skill, and an Amazing invention at -22 puts
    most inventors well below 3. A natural 3 or 4 still succeeds, so a clamp
    here would forbid the only outcome that makes the attempt worth rolling.
    """
    return skill + modifier.total


# --- money ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InventionCosts:
    """B474's three figures, kept apart.

    There is deliberately no total. The facilities charge is one-off and per
    inventor; the attempt charge recurs per prototype roll; the copy charge
    applies only after there is something to copy. A caller that wants a number
    to show a player has to say WHICH one, which is the point.
    """

    facilities: int
    per_attempt: int
    per_copy_parts_only: int
    per_copy_with_labour: int


def invention_costs(
    complexity: Complexity,
    retail_price: int,
    *,
    tl_gap: int = 0,
    tl_cost_multiplier: int | None = None,
    reuses_facilities: bool = False,
    inventors: int = 1,
) -> InventionCosts:
    """B474 Cost.

    The TL surcharge is two separate sentences applying to the same condition —
    facilities and the per-attempt charge both triple. Production is priced off
    retail and is not among them.

    ``tl_cost_multiplier`` defaults to the book's 3 whenever the invention is
    above the inventor's TL at all. It is a parameter because B474 only prices a
    ONE-step gap, and no single multiplier is printed for larger gaps —
    inventing one would be a rule the book does not have, so the GM supplies
    it instead.
    """
    if inventors < 1:
        raise ValueError(f"an invention needs at least one inventor, got {inventors}")
    if tl_gap < 0:
        raise ValueError(f"tl_gap cannot be negative, got {tl_gap}")
    if tl_cost_multiplier is not None and tl_cost_multiplier < 1:
        raise ValueError(
            f"tl_cost_multiplier must be at least 1, got {tl_cost_multiplier}"
        )

    multiplier = 1
    if tl_gap:
        multiplier = (
            TL_COST_MULTIPLIER if tl_cost_multiplier is None else tl_cost_multiplier
        )

    facilities = complexity.facility_cost * multiplier
    if reuses_facilities:
        # B474: this cost falls to one tenth when the inventor already has
        # facilities standing from an earlier project at the same complexity
        # or harder.
        facilities //= 10
    # B474: every inventor rolling Prototype pays facilities in advance;
    # assistants are not inventors.
    facilities *= inventors

    per_attempt = retail_price * multiplier

    return InventionCosts(
        facilities=facilities,
        per_attempt=per_attempt,
        per_copy_parts_only=retail_price // 5,
        per_copy_with_labour=retail_price,
    )


def rebuild_facilities_cost(
    complexity: Complexity,
    *,
    tl_gap: int = 0,
    tl_cost_multiplier: int | None = None,
    reuses_facilities: bool = False,
) -> int:
    """B474: facilities lost to an explosion are rebuilt at the full price.

    ``reuses_facilities`` is accepted and ignored on purpose: the leftover-
    facilities discount describes equipment that survives, and this is the case
    where it did not. Silently honouring it would refund a disaster.
    """
    cost = complexity.facility_cost
    if not tl_gap:
        return cost
    multiplier = (
        TL_COST_MULTIPLIER if tl_cost_multiplier is None else tl_cost_multiplier
    )
    return cost * multiplier


# --- time -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Elapsed:
    amount: int
    unit: str


def prototype_elapsed(complexity: Complexity, rolled_dice: int, workers: int) -> Elapsed:
    """B474 Time Required, once the dice are known.

    The time is split across the skilled workers, never dropping below one
    day. The floor is stated in DAYS, so a
    Complex project driven to zero by a crowd is one day, not one month.
    """
    if workers < 1:
        raise ValueError(f"a project needs at least one worker, got {workers}")
    amount = rolled_dice // workers
    if amount < 1:
        return Elapsed(amount=1, unit="days")
    return Elapsed(amount=amount, unit=complexity.prototype_time.unit)


# --- bugs -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BugLoad:
    """What a prototype came out carrying.

    Counts are dice, not numbers, and two of them are halved — "1d/2". GURPS
    rounds this kind of result down, so a 1 becomes none: a lucky prototype with
    no major bugs is a legal outcome of a bare success.
    """

    major_dice: DiceSpec | None
    minor_dice: DiceSpec | None
    major_halved: bool = False
    minor_halved: bool = False

    @property
    def is_clean(self) -> bool:
        return self.major_dice is None and self.minor_dice is None


def bugs_from_prototype(margin: int, critical_success: bool = False) -> BugLoad:
    """B474 Testing and Bugs — the prototype roll's QUALITY sets the bug load."""
    if margin < 0:
        raise ValueError(
            "a failed Prototype roll produces no prototype, so it has no bug "
            "load; the inventor retries instead"
        )
    if critical_success:
        return BugLoad(major_dice=None, minor_dice=None)
    if margin >= 3:
        return BugLoad(
            major_dice=None, minor_dice=DiceSpec(1, 6, 0), minor_halved=True,
        )
    return BugLoad(
        major_dice=DiceSpec(1, 6, 0),
        minor_dice=DiceSpec(1, 6, 0),
        major_halved=True,
        minor_halved=False,
    )


def bugs_found_by(outcome: str) -> int | str:
    """B474: one bug per successful test; a critical success finds every bug."""
    return {
        "critical_success": "all",
        "success": 1,
        "failure": 0,
        "critical_failure": 0,
    }[outcome]


@dataclass(frozen=True, slots=True)
class TestingResult:
    bugs_found: int | str
    triggers_major_bug: bool = False
    simulates_major_bug: bool = False
    gm_alternative: str | None = None


def testing_result(outcome: str, major_bugs_remaining: int) -> TestingResult:
    """B474: one week of testing, resolved.

    The two failure rows are different in a way that matters to state: a plain
    failure sets off a real bug that is still there afterwards, while a critical
    failure produces the symptoms of one without touching the count. Neither
    reduces the bug tally.
    """
    if major_bugs_remaining < 0:
        raise ValueError(f"bug counts cannot be negative: {major_bugs_remaining}")

    if outcome == "critical_failure":
        return TestingResult(
            bugs_found=0,
            simulates_major_bug=True,
            # B474 lets the GM instead rule that the tester wrongly believes the
            # device is bug-free. That is a choice, so both are reported and
            # neither is taken.
            gm_alternative="the tester wrongly believes no bugs remain",
        )
    if outcome == "failure":
        return TestingResult(
            bugs_found=0,
            triggers_major_bug=major_bugs_remaining > 0,
        )
    return TestingResult(bugs_found=bugs_found_by(outcome))


def bug_surfaces(margin: int, critical_failure: bool) -> bool:
    """B474 sidebar: when a bug the testers missed shows up in play."""
    if critical_failure:
        return True
    return margin <= BUG_SURFACE_MARGIN


# --- production -------------------------------------------------------------


def copy_cost(retail_price: int, parts_only: bool, from_line: bool = False) -> int:
    """B474 Production.

    The two ladders differ in exactly one cell. Parts-only is 20% either way;
    parts-and-labour is full retail by hand and half retail off a line, which is
    what the line is for.
    """
    if parts_only:
        return retail_price // 5
    return retail_price // 2 if from_line else retail_price


def production_line_setup_cost(retail_price: int) -> int:
    """B474: a production line costs 20x retail to set up."""
    return retail_price * 20


def copy_time(prototype_days: int) -> int:
    """B474: a hand-built copy takes half the prototype's time."""
    return prototype_days // 2


def line_copy_hours(prototype_days: int, retail_price: int) -> int:
    """B474: a line copy takes the shorter of one seventh of the prototype time
    and retail/100 hours."""
    seventh_in_hours = prototype_days * 24 // 7
    by_price = retail_price // 100
    return min(seventh_in_hours, by_price)


# --- the stages -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StageSpec:
    name: str
    roller: Roller
    cadence: str
    skill_kind: str | None
    secret: bool


class Stage:
    """B473-474's four stages, each with its own everything.

    Secrecy is not a UI preference. B473 makes the Concept roll secret and B474
    makes the Prototype roll secret for a stated reason: a flawed theory has to
    stay invisible, or the player knows the prototype is doomed before paying to
    build it.
    """

    CONCEPT = StageSpec(
        name="Concept",
        roller=Roller.GM,
        cadence="once per day",
        skill_kind="invention",
        secret=True,
    )
    PROTOTYPE = StageSpec(
        name="Prototype",
        roller=Roller.GM,
        cadence="once per attempt",
        skill_kind="invention",
        secret=True,
    )
    TESTING = StageSpec(
        name="Testing",
        roller=Roller.PLAYER,
        cadence="once per week",
        skill_kind="operation",
        secret=False,
    )
    PRODUCTION = StageSpec(
        name="Production",
        roller=Roller.NOBODY,
        cadence="per copy",
        skill_kind=None,
        secret=False,
    )


STAGES: tuple[StageSpec, ...] = (
    Stage.CONCEPT, Stage.PROTOTYPE, Stage.TESTING, Stage.PRODUCTION,
)


# --- concept and prototype outcomes ----------------------------------------


@dataclass(frozen=True, slots=True)
class ConceptOutcome:
    advances: bool
    flawed_theory: bool
    retry_penalty: int = 0


def concept_outcome(outcome: str) -> ConceptOutcome:
    """B473: what a Concept roll leaves behind.

    A critical failure advances — that is the whole trap. The inventor gets a
    theory that looks good, proceeds to spend facilities money on it, and can
    never build the thing.
    """
    if outcome == "critical_failure":
        return ConceptOutcome(advances=True, flawed_theory=True)
    if outcome == "failure":
        # B473: retry the following day with no added penalty.
        return ConceptOutcome(advances=False, flawed_theory=False, retry_penalty=0)
    return ConceptOutcome(advances=True, flawed_theory=False)


def prototype_possible(flawed_theory: bool, outcome: str) -> bool:
    """B474: a flawed theory can never yield a working prototype."""
    if flawed_theory:
        return False
    return outcome in ("success", "critical_success")


def flaw_revealed(flawed_theory: bool, outcome: str) -> bool:
    """B474: a critical success on Prototype shows the inventor his theory is
    unsound — the only exit from a flawed theory."""
    return flawed_theory and outcome == "critical_success"


@dataclass(frozen=True, slots=True)
class PrototypeDisaster:
    victims: int
    damage: DiceSpec
    damage_is_a_minimum: bool
    facilities_destroyed: bool


def prototype_disaster(assistants: int) -> PrototypeDisaster:
    """B474: a disaster hits the inventor and every helper for 2d or more and
    leaves the facilities in ruins."""
    if assistants < 0:
        raise ValueError(f"assistants cannot be negative: {assistants}")
    return PrototypeDisaster(
        victims=assistants + 1,
        damage=DISASTER_DAMAGE,
        damage_is_a_minimum=True,
        facilities_destroyed=True,
    )
