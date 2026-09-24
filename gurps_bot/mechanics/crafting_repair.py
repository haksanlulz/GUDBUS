# numbers only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""B484-485 Repairs — the repair domain.

A SEPARATE MODULE from ``mechanics/crafting.py`` on purpose. Repair and
invention are both "crafting" and they agree on almost nothing:

* invention rolls an invention skill; repair rolls a repair skill, and B484
  makes the GM the final judge of which;
* invention's facility modifier is -1 to -10 at GM discretion; repair has no
  facility ladder at all and instead modifies by the **item's price**, on its
  own +1/-1/-2/-3 scale;
* an invention attempt takes 1d-2 days to 3d months by complexity; a repair
  attempt takes half an hour, flat, whatever the item;
* and the roll means a different thing. Invention's Prototype roll succeeds or
  fails. **A repair roll returns a QUANTITY** — HP restored equals the margin —
  which is a third reading again from crafting's "quality".

``ModifierBreakdown`` is imported from the invention module and that is
deliberate: it is a presentation container, not a rule. The rule DATA stays
here. ``tests/test_crafting_domains.py`` asserts the domains disagree.

✅ **The tech-book layer landed 2026-08-15, and the finding is that there is
barely one.** High-Tech and Ultra-Tech were both read for a repair procedure
and neither has one: each points back here by page. High-Tech's Wear and Care
section opens by calling itself an expansion of B483-485 and then routes
repairs to "Repairs, p. B484"; Ultra-Tech's tool-kit entry says to see Repairs
(p. B485) and Breakdowns (p. B486) for the rules on repairing gadgets. What
the tech line actually contributes is **equipment, environment and tech
level** — not a second roll. So this stays one module, and the absence is the
architectural statement.

⚠️ **The rule that a critical failure ESCALATES the damage tier is still not
implemented, and is now known to be printed in none of the four books read.**
It came from a reference scenario, not a book. B485's "critical
failure requires major repairs" belongs to Breakdowns — a *maintenance* roll,
not a repair roll — and Ultra-Tech's repair nanopaste has the only printed
make-it-worse clause in the family (a negative result damages the item), which
is a different mechanism at a different scale. Writing it from memory is
exactly the fabrication this project's book-first rule exists to prevent, so
it is named here and left unbuilt.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gurps_bot.mechanics import tech_level
from gurps_bot.mechanics.crafting import ModifierBreakdown, TimeSpec
from gurps_bot.mechanics.dice import DiceSpec


class RepairTier(Enum):
    """Which set of B484 rules a damaged item falls under."""

    MINOR = "Minor repairs"
    MAJOR = "Major repairs"
    BEYOND_REPAIR = "Beyond repair"


#: B484: "Each attempt … requires half an hour". Flat, and independent of the
#: item — no complexity ladder, unlike every invention time.
MINOR_REPAIR_MINUTES = 30

#: B484: major repairs use the minor rules "except that all rolls are at an
#: extra -2".
MAJOR_REPAIR_PENALTY = -2

#: B484 Hiring Help: "A typical rate is $20/hour", and a hired technician's
#: "Typical skill level is 9 + 1d".
HIRED_TECHNICIAN_RATE_PER_HOUR = 20
HIRED_TECHNICIAN_SKILL_BASE = 9
HIRED_TECHNICIAN_SKILL_DICE = DiceSpec(1, 6, 0)

#: B484's price ladder, as (upper bound inclusive, modifier). The bands are NOT
#: uniform and the gap is real: $1,001-$10,000 gets no modifier at all, because
#: the book names a +1 band, then jumps to $10,001. A ladder written as
#: "every decade is one step" would be wrong in exactly that gap.
_PRICE_LADDER = (
    (1_000, 1),
    (10_000, 0),
    (100_000, -1),
    (1_000_000, -2),
)
_PRICE_LADDER_TOP = -3


def price_modifier(price: int) -> int:
    """B484: "+1" up to $1,000, then -1/-2/-3 as the price climbs.

    Repair's answer to "how hard is this?" — the item's price, where invention
    asks about facilities and complexity. Same question, unrelated axis.
    """
    if price < 0:
        raise ValueError(f"price cannot be negative, got {price}")
    for bound, modifier in _PRICE_LADDER:
        if price <= bound:
            return modifier
    return _PRICE_LADDER_TOP


def repair_tier(current_hp: int, max_hp: int, destroyed: bool = False) -> RepairTier:
    """B484-485: which tier an item is in.

    "An artifact reduced to zero or negative HP requires spare parts", and
    "If a device is destroyed (failed a HT roll to avoid destruction, or went
    to -5xHP or less), it is beyond repair."
    """
    if max_hp <= 0:
        raise ValueError(f"max_hp must be positive, got {max_hp}")
    if destroyed or current_hp <= -5 * max_hp:
        return RepairTier.BEYOND_REPAIR
    if current_hp <= 0:
        return RepairTier.MAJOR
    return RepairTier.MINOR


class EmpDamage(Enum):
    """High-Tech: what an EMP leaves behind, for repair purposes.

    The only environmental repair modifier the tech books print as a number
    rather than as a GM call, and the split is the rule: solid-state gear is
    "likely to be permanently damaged" and far worse off than everything else.
    """

    NONE = "Undamaged by EMP"
    SOLID_STATE = "EMP-damaged solid-state electronics"
    OTHER_DEVICE = "EMP-damaged, not solid-state"


#: High-Tech: after an EMP, "all repair rolls are at -10. Repairs on other
#: devices are at only -4."
EMP_SOLID_STATE_PENALTY = -10
EMP_OTHER_DEVICE_PENALTY = -4

_EMP_PENALTY = {
    EmpDamage.NONE: 0,
    EmpDamage.SOLID_STATE: EMP_SOLID_STATE_PENALTY,
    EmpDamage.OTHER_DEVICE: EMP_OTHER_DEVICE_PENALTY,
}


def repair_modifier(
    price: int,
    tier: RepairTier,
    *,
    equipment_modifier: int = 0,
    time_spent_modifier: int = 0,
    tech_level_gap: tech_level.TechLevelGap | None = None,
    unfamiliar: bool = False,
    emp: EmpDamage = EmpDamage.NONE,
) -> ModifierBreakdown:
    """The repair roll's modifiers.

    ``equipment_modifier`` and ``time_spent_modifier`` are B345 and B346, which
    B484 cites rather than restates — they are GM-supplied here for the same
    reason every other adjudication is.

    ``tech_level_gap`` is the tech-line layer, and it is B168 rather than any
    tech book: repair skills are IQ-based, so a mismatch costs -5 for the first
    step **up** and -1 for the first step down. Build it with
    ``mechanics.tech_level.tl_gap``; an impossible gap is refused here rather
    than priced, because the book stops instead of scaling.
    """
    if tier is RepairTier.BEYOND_REPAIR:
        raise ValueError(
            "a destroyed item is beyond repair — B484 says replace it at full "
            "cost, so there is no roll to modify"
        )
    if tech_level_gap is not None and tech_level_gap.impossible:
        raise ValueError(
            "B168 stops at four TLs above the skill: the job is impossible, "
            "not merely very hard, so there is no roll to modify"
        )

    terms: list[tuple[str, int]] = []
    modifier = price_modifier(price)
    if modifier:
        terms.append((f"item price ${price:,}", modifier))
    if tier is RepairTier.MAJOR:
        terms.append(("major repair", MAJOR_REPAIR_PENALTY))
    if tech_level_gap is not None and tech_level_gap.penalty:
        direction = "above" if tech_level_gap.equipment_is_higher else "below"
        terms.append((
            f"{abs(tech_level_gap.steps)} TL {direction} your skill (B168)",
            tech_level_gap.penalty,
        ))
    if unfamiliar:
        # B169 is explicit that this stacks with the TL penalty rather than
        # replacing it, and that only this half can be practised away.
        terms.append(("unfamiliar equipment (B169)", tech_level.UNFAMILIAR_PENALTY))
    if _EMP_PENALTY[emp]:
        terms.append((emp.value, _EMP_PENALTY[emp]))
    if equipment_modifier:
        terms.append(("equipment (B345)", equipment_modifier))
    if time_spent_modifier:
        terms.append(("time spent (B346)", time_spent_modifier))
    return ModifierBreakdown(terms=tuple(terms))


def hp_restored(margin: int) -> int:
    """B484: "Success restores 1 HP times the margin of success (minimum 1)."

    ⚑ The repair roll's RETURN VALUE is a quantity, not an outcome. A margin of
    0 is a success and still restores 1 HP, which is why the floor is part of
    the rule and not a guard against a silly number.
    """
    if margin < 0:
        raise ValueError(
            "a failed repair roll restores nothing; the attempt costs the half "
            "hour and the item is unchanged"
        )
    return max(1, margin)


def minor_repair_time() -> TimeSpec:
    """B484: half an hour per attempt, flat.

    Returned as a TimeSpec for symmetry with the invention times, but note it
    carries no dice — repair time is not rolled, which is itself a difference
    between the domains.
    """
    return TimeSpec(dice=DiceSpec(0, 6, MINOR_REPAIR_MINUTES), unit="minutes")


def major_repair_parts_cost(original_price: int, rolled_1d: int) -> int:
    """B484: spare parts "cost 1dx10% of its original price".

    ✅ **Confirmed against the PDF 2026-08-15; this docstring used to ask for
    exactly that check.** The 10th-printing markdown renders it "1d — 10%", an
    em-dash where a multiplication sign belongs, and the reading was inferred.
    The PDF's text layer encodes the character as the byte 0xA5, and every
    unambiguous occurrence of that byte in the same volume is a multiplication
    sign: "(150 + 30) x (1.2 - 1) = 36 lbs", "x0.50", "2xBL cubic feet per
    hour", "30x gives +5". One glyph, one meaning, checked where the arithmetic
    could speak for itself rather than where it was in doubt.
    """
    if original_price < 0:
        raise ValueError(f"original_price cannot be negative, got {original_price}")
    if not 1 <= rolled_1d <= 6:
        raise ValueError(f"a 1d roll is 1..6, got {rolled_1d}")
    return original_price * rolled_1d * 10 // 100


def replacement_cost(original_price: int) -> int:
    """B484: "Replace it at 100% of its original cost." No discount, no salvage."""
    if original_price < 0:
        raise ValueError(f"original_price cannot be negative, got {original_price}")
    return original_price


@dataclass(frozen=True, slots=True)
class HiredTechnician:
    rate_per_hour: int
    skill_dice: DiceSpec
    skill_base: int

    def skill_for(self, rolled_1d: int) -> int:
        if not 1 <= rolled_1d <= 6:
            raise ValueError(f"a 1d roll is 1..6, got {rolled_1d}")
        return self.skill_base + rolled_1d


def hired_technician() -> HiredTechnician:
    """B484 Hiring Help. The rate rises "if unusual skills are required" — a GM
    call, so the typical figure is what is returned and the raise is not
    guessed at."""
    return HiredTechnician(
        rate_per_hour=HIRED_TECHNICIAN_RATE_PER_HOUR,
        skill_dice=HIRED_TECHNICIAN_SKILL_DICE,
        skill_base=HIRED_TECHNICIAN_SKILL_BASE,
    )


#: Ultra-Tech's robotic workshop: "skill 13 in whatever skill and specialty the
#: workshop is designed for; add +1 per TL over TL10."
ROBOTIC_WORKSHOP_SKILL = 13
ROBOTIC_WORKSHOP_TL = 10

#: "If a human technician is directing a robotic workshop, it is as good as a
#: portable workshop, with an additional +1" — so the machine stops being a
#: substitute technician and becomes equipment plus an assistant.
ROBOTIC_WORKSHOP_ASSISTANT_BONUS = 1


def robotic_workshop_skill(tech_level_of_workshop: int) -> int:
    """What a robotic workshop can do unattended.

    ⚑ This is the family's fourth reading of "assistant", and it is unlike the
    other three: invention's assistants add to the inventor's roll, alchemy's
    weakest hand takes the roll over, enchantment's cost the caster — and this
    one **rolls in place of a person entirely**, with its own flat skill, when
    nobody is directing it.
    """
    if tech_level_of_workshop < ROBOTIC_WORKSHOP_TL:
        raise ValueError(
            f"robotic workshops start at TL{ROBOTIC_WORKSHOP_TL}, got "
            f"TL{tech_level_of_workshop}"
        )
    return ROBOTIC_WORKSHOP_SKILL + (tech_level_of_workshop - ROBOTIC_WORKSHOP_TL)


@dataclass(frozen=True, slots=True)
class PasteResult:
    """What an application of repair nanopaste did.

    ``hp`` is signed on purpose. Ultra-Tech's paste is the one printed repair
    mechanism in the family that can leave the item worse than it found it —
    "if the result is negative, the nano botched the job, inflicting damage
    instead of repairing it" — so collapsing it to a non-negative "HP healed"
    would delete the rule.
    """

    hp: int
    hours: float

    @property
    def made_it_worse(self) -> bool:
        return self.hp < 0


#: Ultra-Tech: an application "repairs 1d-2 HP after an hour".
PASTE_HP = DiceSpec(1, 6, -2)
PASTE_HOURS = 1.0

#: "If the wrong repair paste is sprayed on an item, it will take an hour to
#: inflict 1d-1 HP damage." Always damage, never a repair.
WRONG_PASTE_DAMAGE = DiceSpec(1, 6, -1)

#: "A successful roll made against an appropriate repair skill + 2 will halve
#: the time required for repair paste to work, and add +1 to the HP that it
#: heals." The skill roll is a bonus on top, not a requirement — the paste
#: "does not require any skill to use".
PASTE_SKILL_BONUS = 2
PASTE_ASSISTED_EXTRA_HP = 1
PASTE_ASSISTED_TIME_MULTIPLIER = 0.5


def repair_paste(rolled_1d: int, *, skilled_success: bool = False) -> PasteResult:
    """One application of dedicated, programmable or universal repair paste."""
    if not 1 <= rolled_1d <= 6:
        raise ValueError(f"a 1d roll is 1..6, got {rolled_1d}")

    hp = rolled_1d + PASTE_HP.modifier
    hours = PASTE_HOURS
    if skilled_success:
        hp += PASTE_ASSISTED_EXTRA_HP
        hours *= PASTE_ASSISTED_TIME_MULTIPLIER
    return PasteResult(hp=hp, hours=hours)


def wrong_repair_paste(rolled_1d: int, *, sealed: bool = False) -> PasteResult:
    """The wrong paste on the wrong item.

    Sealed objects are exempt — "It cannot damage sealed objects" — which is a
    real out, not a rounding case, so it is a parameter rather than a footnote.
    """
    if not 1 <= rolled_1d <= 6:
        raise ValueError(f"a 1d roll is 1..6, got {rolled_1d}")
    if sealed:
        return PasteResult(hp=0, hours=PASTE_HOURS)
    return PasteResult(hp=-(rolled_1d + WRONG_PASTE_DAMAGE.modifier), hours=PASTE_HOURS)


def maintenance_ht_repairs(ht_points_lost: int) -> int:
    """B485: "Treat each point of HT restored as a separate major repair."

    So restoring 3 HT is three major repairs — three rolls at -2, three sets of
    spare parts — not one repair of size 3. The distinction is the whole rule.
    """
    if ht_points_lost < 0:
        raise ValueError(f"ht_points_lost cannot be negative, got {ht_points_lost}")
    return ht_points_lost
