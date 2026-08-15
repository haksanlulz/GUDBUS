"""Sealed probe 3, SPENT 2026-08-15 against the frozen tech-line repair layer.

The layer was built and committed (`tech_level.py` + the `crafting_repair`
additions) with this probe unread, and opened only afterwards. That is the
strongest discipline available here, but it is not a clean held-out result and
this file will not claim one: a prior session read probe 3 on 2026-08-10,
judged it inapplicable to the B484 module, and extracted its workspace ladder
into `mechanics/equipment_quality.py`. So part of its content had already
shaped the code before today. What was genuinely unread this time is every
number below.

VERDICT — the probe describes a repair procedure that is not the Basic Set's,
and now not any tech book's either. Six of its conditions are checkable; the
scoring is in the classes below. One number is positively contradicted by
printed text rather than merely unmatched, and it accounts for the entire
target discrepancy.

⚑ THE WHOLE DELTA IS ONE RULE, AND IT IS A SINGLE VALUE (Rule 23). The probe's
target is 9 and this code's is 5. The gap is exactly 4, it appears once, and
it is the TL penalty: the probe prices one TL above the repairer at -1, where
B168's ladder for IQ-based technological skills prices it at -5. -1 is the
value that rule gives for one TL *below*, and it is also what the flat rule for
non-IQ-based skills gives in either direction. A one-row misread of an
asymmetric table is the most economical explanation, and per Rule 23 a single
dominant delta points at a definition rather than at confabulation.

Why the printed reading is taken as governing, stated so it can be overruled:

* `Armoury/TL†` is **IQ/Average** in the Basic Set skill list, as are
  Electronics Repair/TL† and Mechanic/TL†. Every repair skill is IQ-based, so
  B168's asymmetric ladder is the rule that applies to all of them.
* High-Tech offers an optional rule letting a GM treat a TL penalty as mere
  unfamiliarity — and says in the same breath that the exemption "doesn't
  extend to other skills, or even to IQ-based rolls for DX-based skills". It
  goes out of its way to deny exactly this relief to exactly this case.

⬜ **OPERATOR RULING OWED**, because the code cannot settle it: is the -1 a
house rule, a planted error, or a rule from a book not yet read? The code
follows the printed text and is not changed by this file.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics import crafting_repair as repair
from gurps_bot.mechanics import equipment_quality, tech_level
from gurps_bot.mechanics.crafting_repair import RepairTier
from gurps_bot.mechanics.equipment_quality import EquipmentQuality
from gurps_bot.mechanics.tech_level import SkillClass

#: The probe's inputs, verbatim.
SKILL = 14
SKILL_TL = 9
ITEM_TL = 10
PROBE_TARGET_AT_BASIC = 9


def _modifier(**kwargs):
    """The probe's scenario as this code prices it, minus the price rung.

    B484's price modifier is left out on purpose: the probe names no item
    price, because its model does not have that axis at all. See
    ``TestStructuralDisagreements``.
    """
    gap = tech_level.tl_gap(skill_tl=SKILL_TL, equipment_tl=ITEM_TL)
    return repair.repair_modifier(
        1_500,  # $1,001-$10,000 is B484's zero band, so it contributes nothing
        RepairTier.MAJOR,
        tech_level_gap=gap,
        unfamiliar=True,
        **kwargs,
    )


class TestConditionOneTheTarget:
    """"Target 9 at a basic workspace for the stated inputs." """

    def test_this_code_says_five_not_nine(self):
        basic = equipment_quality.modifier(EquipmentQuality.BASIC, technological=True)
        target = SKILL + _modifier(equipment_modifier=basic).total
        assert target == 5
        assert target != PROBE_TARGET_AT_BASIC

    def test_and_the_difference_is_exactly_four(self):
        basic = equipment_quality.modifier(EquipmentQuality.BASIC, technological=True)
        target = SKILL + _modifier(equipment_modifier=basic).total
        assert PROBE_TARGET_AT_BASIC - target == 4

    def test_which_is_the_tl_rule_and_nothing_else(self):
        """Substituting the probe's own TL penalty reproduces its target
        exactly. Nothing else in the scenario contributes to the gap, which is
        what makes this one delta rather than several."""
        governing = tech_level.tl_gap(skill_tl=SKILL_TL, equipment_tl=ITEM_TL).penalty
        probes = -1
        assert governing == -5
        assert SKILL + probes - 2 - 2 + 0 == PROBE_TARGET_AT_BASIC

    def test_the_probes_value_is_the_ladders_other_direction(self):
        """-1 is what B168 charges for equipment one TL BELOW the skill. The
        probe's item is one TL above."""
        one_below = tech_level.tl_gap(skill_tl=SKILL_TL, equipment_tl=SKILL_TL - 1)
        assert one_below.penalty == -1

    def test_and_also_what_the_wrong_skill_class_would_give(self):
        """The other way to arrive at -1: apply the flat rule that governs
        skills which are not IQ-based. Armoury is IQ/Average, so it does not."""
        flat = tech_level.tl_gap(
            skill_tl=SKILL_TL, equipment_tl=ITEM_TL, skill_class=SkillClass.OTHER
        )
        assert flat.penalty == -1


class TestConditionTwoSeparateModifiers:
    """"TL mismatch and unfamiliarity as separate modifiers, not folded."""

    def test_they_are_two_terms(self):
        labels = [label for label, _ in _modifier().terms]
        assert any("B168" in label for label in labels)
        assert any("B169" in label for label in labels)

    def test_the_structure_passes_even_though_the_value_does_not(self):
        """The probe's shape is right and its number is not — worth separating,
        because a scoring pass that collapsed them would report a design
        failure where there is only an arithmetic disagreement."""
        terms = dict((label, value) for label, value in _modifier().terms)
        unfamiliar = next(v for k, v in terms.items() if "B169" in k)
        assert unfamiliar == -2


class TestConditionThreeTheTierIsItsOwnModifier:
    def test_major_is_minus_two_on_top(self):
        """The one number the two rule sets have always agreed on."""
        assert repair.MAJOR_REPAIR_PENALTY == -2
        labels = [label for label, _ in _modifier().terms]
        assert any("major" in label.lower() for label in labels)


class TestConditionFourTheEscalationIsStillUnsourced:
    """"Critical failure escalates the tier, and it persists."

    The probe's distinctive rule, and the reason it was worth holding back.
    It is printed in none of the four books read for this domain: B484-485,
    High-Tech, Ultra-Tech. B485's "critical failure requires major repairs"
    belongs to Breakdowns, which is a maintenance roll rather than a repair
    roll. Ultra-Tech's repair nanopaste can damage an item on a negative
    result, which is the only printed make-it-worse clause in the family and a
    different mechanism at a different scale.
    """

    def test_it_is_not_implemented(self):
        assert not hasattr(repair, "escalate_damage_tier")
        assert not hasattr(repair, "critical_failure_tier")

    def test_there_is_no_severe_tier_to_escalate_into(self):
        assert {t.name for t in RepairTier} == {"MINOR", "MAJOR", "BEYOND_REPAIR"}

    def test_the_module_says_so_rather_than_staying_quiet(self):
        doc = repair.__doc__ or ""
        assert "escalat" in doc.lower()


class TestConditionSixNoBatching:
    """"No batch behavior at all here." The one condition that passes
    outright, and it passes by construction."""

    def test_nothing_in_the_domain_takes_a_batch(self):
        import inspect

        for name, fn in vars(repair).items():
            if not callable(fn) or name.startswith("_"):
                continue
            try:
                params = inspect.signature(fn).parameters
            except (TypeError, ValueError):  # pragma: no cover - builtins
                continue
            assert "doses" not in params, name
            assert "batch" not in params, name
            assert "units" not in params, name


class TestWhatTheProbeBoughtTheWorkspaceLadderIsNowFullySourced:
    """The 2026-08-10 pass found the probe's five-rung ladder to be
    four-fifths of B345 and left the fifth rung unexplained. Reading
    Ultra-Tech for the tech layer supplied it.

    improvised -5 · portable -2 · basic 0 · shop +1 · factory +2
    """

    @pytest.mark.parametrize(
        "quality,expected",
        [
            (EquipmentQuality.IMPROVISED, -5),
            (EquipmentQuality.BASIC, 0),
            (EquipmentQuality.GOOD, 1),
            (EquipmentQuality.FINE, 2),
        ],
    )
    def test_four_rungs_are_b345(self, quality, expected):
        assert equipment_quality.modifier(quality, technological=True) == expected

    def test_and_the_fifth_is_ultra_techs_mini_toolkit(self):
        """Ultra-Tech gives a belt-sized kit a -2 (quality) modifier for the
        very skill it is built for, and gives a full portable kit the same -2
        when used on another specialization within its skill. Either reading
        supplies a printed -2 rung for a technological repair skill, which
        B345's technological column does not have — its improvised rung is -5.
        """
        assert equipment_quality.modifier(
            EquipmentQuality.IMPROVISED, technological=True
        ) == -5
        assert equipment_quality.modifier(
            EquipmentQuality.IMPROVISED, technological=False
        ) == -2


class TestStructuralDisagreements:
    """Beyond the one number: the probe and B484 do not model the same thing.

    Recorded rather than reconciled. Each is a place where a future session
    could mistake one rule set for the other.
    """

    def test_b484s_primary_difficulty_axis_is_absent_from_the_probe(self):
        """B484 asks what the item COSTS and modifies by price. The probe's
        difficulty comes from the workspace and never mentions a price, which
        is why the scenario cannot be scored without choosing one."""
        assert repair.price_modifier(500) == 1
        assert repair.price_modifier(50_000) == -1

    def test_parts_are_rolled_in_the_book_and_flat_in_the_probe(self):
        """B484: 1d x 10% of original price, so a range. The probe states a
        single figure of $180 with no roll."""
        low = repair.major_repair_parts_cost(1_800, 1)
        high = repair.major_repair_parts_cost(1_800, 6)
        assert low != high
        assert (low, high) == (180, 1_080)

    def test_time_is_flat_in_the_book_and_rolled_in_the_probe(self):
        """B484: half an hour per attempt, whatever the item, never divided.
        The probe: 3d hours divided by workers — which is invention's shape,
        not repair's."""
        spec = repair.minor_repair_time()
        assert spec.dice.count == 0
        assert spec.dice.modifier == 30
        assert spec.unit == "minutes"
