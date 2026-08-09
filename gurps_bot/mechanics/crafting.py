# numbers only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
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

#: B474: "+1 per assistant with skill 20+ in one of the skills required for the
#: invention, to a maximum of +4". Invention's reading of "assistant" — a flat
#: bonus to the inventor's roll. No other crafting domain reads it this way.
ASSISTANT_BONUS_EACH = 1
ASSISTANT_BONUS_CAP = 4
ASSISTANT_MIN_SKILL = 20

#: B474: testing rolls are made "vs. operation skill … at -3".
TESTING_PENALTY = -3

#: B474 sidebar: an unfound bug "surface[s] on any operation skill roll that
#: fails by 5 or more".
BUG_SURFACE_MARGIN = -5

#: B474: the facility modifier is "-1 to -10 (GM's discretion)". A range and a
#: ruling, so the engine takes the number instead of deriving a ladder.
FACILITY_PENALTY_RANGE = (-10, 0)

#: B473: "+1 or +2 to all invention-related skill rolls" for a clear or clever
#: description, and "+1 to +5 if the item is a variant on an existing one".
DESCRIPTION_BONUS_RANGE = (0, 2)
VARIANT_BONUS_RANGE = (0, 5)

#: B473: "-5 if the device is one TL above the inventor's TL", applied per step.
#:
#: ⚠️ RAW covers ONE step and says so — the rules "cover realistic innovation at
#: the inventor's tech level – or one TL in advance of that, at most", and past
#: that B473 hands off to Gadgeteering. The per-step extension is the operator's,
#: from sealed probe 1: a TL+3 superscience item at effective skill 16 targets
#: **-18**, which is 16 - 14 (Complex) - 15 (three steps) - 5 (new tech). It was
#: confirmed twice in one probe — the prototype target -14 carries the identical
#: gap — so the linear reading is measured rather than assumed.
TL_GAP_PENALTY_EACH = -5

#: B474: "Triple these costs if the invention is one TL above the inventor's TL."
#: Same one-step caveat, and unlike the roll penalty this one does NOT extend
#: cleanly: probe 1's own figures need x7 on facilities and x5 on the attempt,
#: which no single multiplier produces. So the multiplier stays the book's 3 and
#: is a GM-supplied parameter past one step, rather than a curve fitted to two
#: points. See GAUNTLET §5 — an operator ruling is owed.
TL_COST_MULTIPLIER = 3

#: B474: the prototype explosion. "at least 2d damage" — a floor, not a roll to
#: be taken literally, which is why the caller is told it is a minimum.
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


#: Ascending, so "one step easier" is an index step.
_COMPLEXITY_ORDER = (
    Complexity.SIMPLE, Complexity.AVERAGE, Complexity.COMPLEX, Complexity.AMAZING,
)


# --- computer programs ------------------------------------------------------


def program_complexity(rating: int) -> Complexity:
    """B473: a program's numerical Complexity, mapped for cost and time only.

    "treat Complexity 1-3 as Simple, 4-5 as Average, 6-7 as Complex, and 8+ as
    Amazing" — and note this mapping is explicitly NOT used for the concept
    penalty, which stays on the rating itself.
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
    """B473: "a penalty equal to twice the Complexity rating instead".

    Unbounded on purpose — a Complexity 12 program is harsher than Amazing, and
    capping it at the table's -22 would be an invention.
    """
    if rating < 1:
        raise ValueError(f"program Complexity starts at 1, got {rating}")
    return -2 * rating


def reinvented_complexity(base: Complexity, tl_advantage: int) -> Complexity:
    """B473 sidebar: "Reduce complexity by one step per TL … to a minimum of
    Simple"."""
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

    ⚠️ The extraction prints this list ABOVE the Concept heading, between
    Required Skills and Complexity — a two-column artifact. It belongs to
    Concept, and B474 then inherits it wholesale for the Prototype roll.
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

    # "+5 if you have a working model you're trying to copy, or +2 if the device
    # already exists but you don't have a model" — the second is the weaker case
    # of the first, so having a model does not also earn the no-model bonus.
    if working_model:
        terms.append(("working model to copy", 5))
    elif device_exists:
        terms.append(("device exists, no model", 2))

    if variant_bonus:
        terms.append(("variant on an existing item", variant_bonus))
    if new_technology:
        # "regardless of TL" — this is about the campaign, not the inventor, so
        # it stacks with the TL penalty below rather than replacing it.
        terms.append(("basic technology new to the campaign", -5))
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
    """B474: "All modifiers listed for Concept rolls", plus two of its own."""
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
        terms.append(("less than the best tools and facilities", facility_penalty))

    return ModifierBreakdown(terms=tuple(terms))


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
    ONE-step gap and probe 1's TL+3 figures do not follow from any single
    multiplier — fitting one to two points would be the fabrication this engine
    is meant to avoid, so the GM supplies it instead.
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
        # "Divide costs by 10 if the inventor has appropriate facilities left
        # over from a related project of equal or higher complexity."
        facilities //= 10
    # "Each inventor who wishes to attempt a Prototype roll must pay the
    # facilities cost 'up front'" — assistants are not inventors.
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
    """B474: after an explosion the facilities "must be rebuilt at full cost".

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

    "Divide time required by the number of skilled people working on the
    project. Minimum time is always one day." The floor is stated in DAYS, so a
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
    """B474: "Each success finds one bug; a critical success finds all bugs"."""
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
            # "alternatively, the tester is convinced, erroneously, that no bugs
            # remain" — the book offers the GM a choice, so both are reported
            # and neither is taken.
            gm_alternative="the tester is convinced, erroneously, that no bugs remain",
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
    """B474: "To set up a production line costs 20 times the retail price"."""
    return retail_price * 20


def copy_time(prototype_days: int) -> int:
    """B474: "Time required to produce each copy is half that required for a
    Prototype roll"."""
    return prototype_days // 2


def line_copy_hours(prototype_days: int, retail_price: int) -> int:
    """B474: "1/7 the time it took to build a prototype or in (retail
    price/100) hours, whichever is less"."""
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
        # "may try again the next day at no additional penalty"
        return ConceptOutcome(advances=False, flawed_theory=False, retry_penalty=0)
    return ConceptOutcome(advances=True, flawed_theory=False)


def prototype_possible(flawed_theory: bool, outcome: str) -> bool:
    """B474: "If the inventor was working with a flawed theory, he will never
    create a working prototype"."""
    if flawed_theory:
        return False
    return outcome in ("success", "critical_success")


def flaw_revealed(flawed_theory: bool, outcome: str) -> bool:
    """B474: "a critical success on the Prototype roll lets him realize that
    his theory was bad" — the only exit from a flawed theory."""
    return flawed_theory and outcome == "critical_success"


@dataclass(frozen=True, slots=True)
class PrototypeDisaster:
    victims: int
    damage: DiceSpec
    damage_is_a_minimum: bool
    facilities_destroyed: bool


def prototype_disaster(assistants: int) -> PrototypeDisaster:
    """B474: "an explosion or accident occurs … at least 2d damage to the
    inventor and each assistant – and destroys the facilities"."""
    if assistants < 0:
        raise ValueError(f"assistants cannot be negative: {assistants}")
    return PrototypeDisaster(
        victims=assistants + 1,
        damage=DISASTER_DAMAGE,
        damage_is_a_minimum=True,
        facilities_destroyed=True,
    )
