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

⬜ **The tech-book layer is NOT implemented and this module does not pretend
otherwise.** GAUNTLET's ledger row names Low/High/Ultra-Tech for repair, and
what is here is only the Basic Set core. In particular the rule that a critical
failure ESCALATES the damage tier — recorded in ATTACK.md from probe-3
elicitation — is *not* printed on B484-485 and is not implemented; B485's
"critical failure requires major repairs" belongs to the Breakdowns rules, a
different roll. Implementing it from memory is exactly the fabrication the
sealed probe exists to catch.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

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


def repair_modifier(
    price: int,
    tier: RepairTier,
    *,
    equipment_modifier: int = 0,
    time_spent_modifier: int = 0,
) -> ModifierBreakdown:
    """The repair roll's modifiers.

    ``equipment_modifier`` and ``time_spent_modifier`` are B345 and B346, which
    B484 cites rather than restates — they are GM-supplied here for the same
    reason every other adjudication is.
    """
    if tier is RepairTier.BEYOND_REPAIR:
        raise ValueError(
            "a destroyed item is beyond repair — B484 says replace it at full "
            "cost, so there is no roll to modify"
        )

    terms: list[tuple[str, int]] = []
    modifier = price_modifier(price)
    if modifier:
        terms.append((f"item price ${price:,}", modifier))
    if tier is RepairTier.MAJOR:
        terms.append(("major repair", MAJOR_REPAIR_PENALTY))
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

    ⚠️ The 10th-printing markdown renders this as "1d — 10%", an em-dash where
    a multiplication sign belongs. Read as ``1d x 10%`` — i.e. 10% to 60% — on
    two grounds: it is the only reading that produces a cost, and the same
    extraction mangles "-5xHP" and "1dx10 minutes" identically in the same
    chapter. **Confirm against the PDF before this figure is trusted at a
    table**; it is the one number in this module inferred from a damaged glyph.
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


def maintenance_ht_repairs(ht_points_lost: int) -> int:
    """B485: "Treat each point of HT restored as a separate major repair."

    So restoring 3 HT is three major repairs — three rolls at -2, three sets of
    spare parts — not one repair of size 3. The distinction is the whole rule.
    """
    if ht_points_lost < 0:
        raise ValueError(f"ht_points_lost cannot be negative, got {ht_points_lost}")
    return ht_points_lost
