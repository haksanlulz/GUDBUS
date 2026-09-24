"""B475-477 Gadgeteering, and the per-METHOD half of the per-domain invariant.

The crafting invariant is that rules stay per-domain **and per-method**,
"never one shared abstraction", and until now that scan had nothing to bite on:
one method implemented cannot disagree with itself, so a differential written
against it would have been unfalsified rather than passing. Three
methods inside one domain is the first population that can express a
disagreement, so this file asserts the disagreements directly.

The methods are not difficulty settings. Gadgeteering requires the Gadgeteer
advantage (B56) and Quick Gadgeteering requires Quick Gadgeteer, so which one
applies is a fact about the character.

⚠️ B476's **Gadget Bugs Table is deliberately not implemented**. It is eighteen
rows of effect prose, and "no effect prose, ever" is the arc's hardest non-goal
— and the one most likely to erode by accident. The engine says
*whether* the table applies and cites the page; what is on it stays in the book.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics import crafting
from gurps_bot.mechanics.crafting import Complexity, Method


class TestTheBooksOwnWorkedExamples:
    """B475 prints two, and they are the cheapest possible regression class."""

    def test_the_facilities_example_reproduces(self):
        """"a Complex item … three TLs above the campaign TL … $250,000 +
        3 x $500,000 … bringing the total to $1,750,000"."""
        assert crafting.gadgeteer_facility_cost(Complexity.COMPLEX, 3) == 1_750_000

    def test_the_per_attempt_example_reproduces(self):
        """"$4,000 + $8,000 + $16,000 + $32,000 = $60,000!" — every rung paid,
        not just the top one."""
        assert crafting.gadgeteer_attempt_cost(4_000, 3) == 60_000

    def test_at_the_campaign_tl_the_attempt_is_just_retail(self):
        assert crafting.gadgeteer_attempt_cost(4_000, 0) == 4_000

    def test_accumulation_is_not_plain_doubling(self):
        """The distinction bites at the FIRST TL, not the fourth: doubling once
        gives $8,000, accumulating gives $12,000."""
        assert crafting.gadgeteer_attempt_cost(4_000, 1) == 12_000

    def test_production_is_priced_off_the_adjusted_figure(self):
        """"retail price would be $60,000 (not $4,000) for production purposes"."""
        assert crafting.gadgeteer_production_price(4_000, 3) == 60_000


class TestGadgeteerConcept:
    @pytest.mark.parametrize(
        "complexity,penalty",
        [
            (Complexity.SIMPLE, 0),
            (Complexity.AVERAGE, -2),
            (Complexity.COMPLEX, -4),
            (Complexity.AMAZING, -8),
        ],
    )
    def test_the_milder_ladder(self, complexity, penalty):
        assert crafting.GADGETEER_CONCEPT_PENALTY[complexity] == penalty

    def test_the_new_technology_penalty_cannot_be_applied_at_all(self):
        """"Ignore the -5 for a technology that is totally new to the campaign."

        Enforced by the signature rather than by dropping the argument: a caller
        who passes it gets a TypeError, which is a better failure than a value
        silently ignored.
        """
        with pytest.raises(TypeError):
            crafting.gadgeteer_concept_modifier(
                Complexity.SIMPLE, new_technology=True
            )

    def test_the_tl_gap_is_uncapped(self):
        """"not limited to inventions only one TL advanced … any TL, at a flat
        -5 per TL above his own"."""
        mod = crafting.gadgeteer_concept_modifier(Complexity.SIMPLE, tl_gap=6)
        assert mod.total == 0 - 30

    def test_a_program_uses_the_rating_not_twice_it(self):
        """B475 inverts B473 for this exact case."""
        gadget = crafting.gadgeteer_concept_modifier(
            Complexity.AVERAGE, program_complexity=6
        )
        plain = crafting.concept_modifier(Complexity.AVERAGE, program_complexity=6)
        assert gadget.total == -6
        assert plain.total == -12

    def test_the_shared_bonuses_still_apply(self):
        mod = crafting.gadgeteer_concept_modifier(
            Complexity.COMPLEX, working_model=True, variant_bonus=2, description_bonus=1
        )
        assert mod.total == -4 + 5 + 2 + 1


class TestGadgeteerBugs:
    def test_a_gadgeteer_can_never_produce_a_major_bug(self):
        """"There is no chance at all of a major bug." No margin, no critical."""
        for margin in range(0, 12):
            assert crafting.gadgeteer_bugs_from_prototype(margin).major_dice is None
        assert (
            crafting.gadgeteer_bugs_from_prototype(0, critical_success=True).major_dice
            is None
        )

    def test_success_by_three_is_clean(self):
        assert crafting.gadgeteer_bugs_from_prototype(margin=3).is_clean

    def test_a_lesser_success_gives_halved_minor_bugs(self):
        bugs = crafting.gadgeteer_bugs_from_prototype(margin=2)
        assert str(bugs.minor_dice) == "1d"
        assert bugs.minor_halved is True

    def test_a_failure_has_no_bug_load(self):
        with pytest.raises(ValueError):
            crafting.gadgeteer_bugs_from_prototype(margin=-1)

    @pytest.mark.parametrize(
        "gadgeteer_tl,gadget_tl,applies", [(8, 9, True), (8, 8, False), (10, 9, False)]
    )
    def test_the_bugs_table_applies_only_above_the_gadgeteers_tl(
        self, gadgeteer_tl, gadget_tl, applies
    ):
        assert (
            crafting.gadget_bugs_are_rolled_on_the_table(gadgeteer_tl, gadget_tl)
            is applies
        )

    def test_the_bugs_table_itself_is_not_in_the_repo(self):
        """The arc's hardest non-goal, asserted rather than trusted.

        B476's table is eighteen rows of what a bug DOES. Shipping it would be
        effect prose, so the engine only says whether the table applies.
        """
        import inspect

        source = inspect.getsource(crafting)
        for phrase in ("Men in Black", "brownouts", "shower of sparks", "self-destruct"):
            assert phrase.lower() not in source.lower(), (
                f"{phrase!r} reads like B476 Gadget Bugs Table text — that table "
                f"is effect prose and must stay in the book"
            )


class TestQuickGadgeteering:
    @pytest.mark.parametrize(
        "complexity,notation,unit",
        [
            (Complexity.SIMPLE, "2d", "minutes"),
            (Complexity.AVERAGE, "1d-2", "hours"),
            (Complexity.COMPLEX, "1d", "hours"),
            (Complexity.AMAZING, "4d", "hours"),
        ],
    )
    def test_assembly_times(self, complexity, notation, unit):
        spec = crafting.quick_assembly_time(complexity)
        assert (str(spec.dice), spec.unit) == (notation, unit)

    @pytest.mark.parametrize("rolled,expected", [(1, True), (2, True), (3, False)])
    def test_the_average_row_has_a_printed_exception(self, rolled, expected):
        """"1d-2 hours (a roll of 1 or 2 indicates a 30-minute assembly time)".

        Without this the dice render "0 hours" or "-1 hours" for a third of all
        rolls, which is not what the book says and looks like a bug.
        """
        assert (
            crafting.quick_assembly_is_half_an_hour(Complexity.AVERAGE, rolled)
            is expected
        )

    def test_the_exception_belongs_to_the_average_row_only(self):
        assert not crafting.quick_assembly_is_half_an_hour(Complexity.COMPLEX, 1)

    @pytest.mark.parametrize(
        "rolled,cost", [(1, 0), (2, 100), (3, 200), (6, 500)]
    )
    def test_the_scrounged_project_cost(self, rolled, cost):
        """"(1d-1) x $100, with a roll of 1 indicating no cost"."""
        assert crafting.quick_scrounged_project_cost(rolled) == cost

    def test_buying_the_parts_divides_by_a_hundred(self):
        facilities, attempt = crafting.quick_purchased_costs(
            Complexity.COMPLEX, retail_price=4_000, tl_gap=3
        )
        assert facilities == 1_750_000 // 100
        assert attempt == 60_000 // 100

    def test_the_scrounging_penalties_are_not_the_concept_penalties(self):
        """The column-scramble trap: "These rolls are at no [modifier for a
        Simple gadget, -2 …]" is the PARTS roll, not the Concept roll, and the
        two ladders differ at Complex and Amazing."""
        assert crafting.QUICK_SCROUNGING_PENALTY[Complexity.COMPLEX] == -6
        assert crafting.GADGETEER_CONCEPT_PENALTY[Complexity.COMPLEX] == -4
        assert crafting.QUICK_SCROUNGING_PENALTY[Complexity.AMAZING] == -10
        assert crafting.GADGETEER_CONCEPT_PENALTY[Complexity.AMAZING] == -8


class TestTheMethodsDisagree:
    """The invariant's per-METHOD half. The scan the arc has been owed.

    Each test names one rule and asserts the methods give different answers to
    it. A shared abstraction would make one of these pass by accident; all of
    them passing means the split is real.
    """

    def test_there_are_three_methods_and_they_are_named(self):
        """FAIL CLOSED: with fewer than two, nothing below can disagree."""
        assert len(Method) >= 3

    def test_the_complexity_penalty_differs(self):
        for complexity in Complexity:
            raw = complexity.concept_penalty
            gadget = crafting.GADGETEER_CONCEPT_PENALTY[complexity]
            assert raw != gadget, (
                f"{complexity.label}: New Inventions and Gadgeteering agree at "
                f"{raw}, which the book does not"
            )

    def test_the_new_technology_penalty_exists_in_one_method_and_not_the_other(self):
        raw = crafting.concept_modifier(Complexity.SIMPLE, new_technology=True).total
        assert raw == -6 - 5
        with pytest.raises(TypeError):
            crafting.gadgeteer_concept_modifier(Complexity.SIMPLE, new_technology=True)

    def test_the_facilities_price_scales_differently(self):
        """Multiplicative vs additive — but NOT at the first step, for three of
        the four ratings.

        B475's TL Increment is exactly twice the Base Cost for Simple, Complex
        and Amazing, so ``base + 1 x increment`` is arithmetically B474's
        "triple" and the two methods agree at one TL. **Average is the
        exception**: its increment is 2.5x base, so it diverges immediately.

        Written this way deliberately. Asserting blanket divergence looked
        right, passed review, and failed on the first run at Complex — the
        methods are different rules that happen to collide on a subset of one
        parameter, which is exactly the coincidence a shared abstraction would
        be built on by someone who checked one cell.
        """
        # The collision, at one TL:
        for complexity in (Complexity.SIMPLE, Complexity.COMPLEX, Complexity.AMAZING):
            raw = crafting.invention_costs(complexity, 0, tl_gap=1).facilities
            assert raw == crafting.gadgeteer_facility_cost(complexity, 1)

        # Average breaks it even there:
        assert crafting.invention_costs(
            Complexity.AVERAGE, 0, tl_gap=1
        ).facilities != crafting.gadgeteer_facility_cost(Complexity.AVERAGE, 1)

        # And past one TL nothing collides, because B474 does not scale at all:
        for complexity in Complexity:
            raw = crafting.invention_costs(complexity, 0, tl_gap=3).facilities
            assert raw != crafting.gadgeteer_facility_cost(complexity, 3)

    def test_the_attempt_charge_scales_differently(self):
        raw = crafting.invention_costs(Complexity.COMPLEX, 4_000, tl_gap=1).per_attempt
        gadget = crafting.gadgeteer_attempt_cost(4_000, 1)
        assert raw == 12_000  # x3
        assert gadget == 12_000  # 4,000 + 8,000
        # ⚑ They coincide at exactly one TL — a numerological accident, not a
        # shared rule — and diverge at every other gap. Asserted so a future
        # reader who spots the equality does not conclude the rules are one.
        assert (
            crafting.invention_costs(Complexity.COMPLEX, 4_000, tl_gap=2).per_attempt
            != crafting.gadgeteer_attempt_cost(4_000, 2)
        )

    def test_only_one_method_can_produce_a_major_bug(self):
        raw = crafting.bugs_from_prototype(margin=0)
        gadget = crafting.gadgeteer_bugs_from_prototype(margin=0)
        assert raw.major_dice is not None
        assert gadget.major_dice is None

    def test_the_prototype_time_is_a_different_order_of_magnitude(self):
        for complexity in Complexity:
            slow = complexity.prototype_time
            quick = crafting.quick_assembly_time(complexity)
            assert slow.unit != quick.unit, (
                f"{complexity.label}: New Inventions and Quick Gadgeteering both "
                f"measure in {slow.unit}"
            )

    def test_only_one_method_prices_the_whole_project_as_one_figure(self):
        """Quick Gadgeteering's scrounged cost is a single number for
        everything, where every other method keeps facilities and attempts
        apart. That is a structural difference, not a cheaper number."""
        assert isinstance(crafting.quick_scrounged_project_cost(4), int)
        costs = crafting.invention_costs(Complexity.SIMPLE, 100)
        assert not hasattr(costs, "total")

    def test_the_tl_ceiling_differs(self):
        """B473 caps New Inventions at one TL in advance; B475 removes the cap.

        The engine cannot enforce a ceiling it is not told about — the campaign
        TL is a GM fact — so this asserts the documented asymmetry stays
        documented, which is the honest version of the check.
        """
        source = crafting.__doc__ or ""
        import inspect

        module_source = inspect.getsource(crafting)
        assert "not limited to inventions only one TL advanced" in module_source
