"""B473-474 New Inventions — the slice-1 invention engine.

Red-first per the project's test discipline. Every number here was read off
B473-474 in the operator's own copy; the page cites live beside the constants in
``mechanics/crafting.py``.

⚠️ **Sealed probe 1 is deliberately not consulted while writing this.** It is one
of the two clean held-out checks in the family (ATTACK.md records the provenance
gradient), and reading it during the build would convert it into a differential
— strong as a regression case, worthless as an anti-fabrication rung on code
Claude wrote. Re-verify against it after the engine is frozen.

Two things the extraction could not be trusted for, and how they were resolved:

* B473's two-column layout puts the Concept **modifier list** and its
  once-per-day cadence physically ABOVE the Concept heading, between Required
  Skills and Complexity. They belong to Concept; the Prototype section then says
  "all modifiers listed for Concept rolls" and adds its own two.
* The Testing paragraph is interrupted mid-sentence by the bug-surfacing
  sidebar, and resumes several paragraphs later at "skill (e.g., Driving …)".
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics import crafting
from gurps_bot.mechanics.crafting import (
    Complexity,
    Roller,
    Stage,
)


# --- complexity -------------------------------------------------------------


class TestComplexity:
    """B473's four ratings and the table that suggests them."""

    @pytest.mark.parametrize(
        "complexity,penalty",
        [
            (Complexity.SIMPLE, -6),
            (Complexity.AVERAGE, -10),
            (Complexity.COMPLEX, -14),
            (Complexity.AMAZING, -22),
        ],
    )
    def test_concept_penalty_matches_the_book(self, complexity, penalty):
        assert complexity.concept_penalty == penalty

    @pytest.mark.parametrize(
        "complexity,cost",
        [
            (Complexity.SIMPLE, 50_000),
            (Complexity.AVERAGE, 100_000),
            (Complexity.COMPLEX, 250_000),
            (Complexity.AMAZING, 500_000),
        ],
    )
    def test_facility_cost_matches_the_book(self, complexity, cost):
        assert complexity.facility_cost == cost

    @pytest.mark.parametrize(
        "complexity,notation",
        [
            (Complexity.SIMPLE, "1d-2"),
            (Complexity.AVERAGE, "2d"),
            (Complexity.COMPLEX, "1d"),
            (Complexity.AMAZING, "3d"),
        ],
    )
    def test_prototype_time_dice_match_the_book(self, complexity, notation):
        assert str(complexity.prototype_time.dice) == notation

    def test_time_units_are_days_for_the_cheap_two_and_months_for_the_dear_two(self):
        """The unit changes partway down the table — the easiest cell to lose."""
        assert Complexity.SIMPLE.prototype_time.unit == "days"
        assert Complexity.AVERAGE.prototype_time.unit == "days"
        assert Complexity.COMPLEX.prototype_time.unit == "months"
        assert Complexity.AMAZING.prototype_time.unit == "months"


class TestComputerPrograms:
    """B473 swaps the whole rating scheme out for programs."""

    @pytest.mark.parametrize(
        "rating,expected",
        [
            (1, Complexity.SIMPLE), (3, Complexity.SIMPLE),
            (4, Complexity.AVERAGE), (5, Complexity.AVERAGE),
            (6, Complexity.COMPLEX), (7, Complexity.COMPLEX),
            (8, Complexity.AMAZING), (20, Complexity.AMAZING),
        ],
    )
    def test_rating_maps_to_a_rating_for_cost_and_time(self, rating, expected):
        assert crafting.program_complexity(rating) == expected

    @pytest.mark.parametrize("rating,penalty", [(1, -2), (5, -10), (8, -16), (12, -24)])
    def test_the_concept_penalty_is_twice_the_rating_not_the_table(self, rating, penalty):
        """"apply a penalty equal to twice the Complexity rating instead"."""
        assert crafting.program_concept_penalty(rating) == penalty

    def test_a_high_rating_is_harsher_than_any_table_entry(self):
        """Complexity 12 beats Amazing's -22. The table is not a floor."""
        assert crafting.program_concept_penalty(12) < Complexity.AMAZING.concept_penalty


class TestReinventingTheWheel:
    """B473 sidebar: one step easier per TL of hindsight, floor at Simple."""

    @pytest.mark.parametrize(
        "base,tl_advantage,expected",
        [
            (Complexity.AMAZING, 0, Complexity.AMAZING),
            (Complexity.AMAZING, 1, Complexity.COMPLEX),
            (Complexity.AMAZING, 2, Complexity.AVERAGE),
            (Complexity.AMAZING, 3, Complexity.SIMPLE),
            (Complexity.AMAZING, 9, Complexity.SIMPLE),
            (Complexity.SIMPLE, 4, Complexity.SIMPLE),
        ],
    )
    def test_complexity_steps_down_to_a_floor(self, base, tl_advantage, expected):
        assert crafting.reinvented_complexity(base, tl_advantage) == expected

    def test_a_negative_tl_advantage_is_not_a_way_to_climb(self):
        """Inventing ABOVE your TL is a -5 modifier, never a complexity bump."""
        with pytest.raises(ValueError):
            crafting.reinvented_complexity(Complexity.SIMPLE, -1)


# --- concept ----------------------------------------------------------------


class TestConceptModifier:
    """B473's modifier list, which the extraction prints above its own heading."""

    def test_bare_complexity_is_the_whole_modifier(self):
        mod = crafting.concept_modifier(Complexity.AVERAGE)
        assert mod.total == -10

    def test_every_book_modifier_is_reachable(self):
        mod = crafting.concept_modifier(
            Complexity.SIMPLE,
            working_model=True,          # +5
            variant_bonus=3,             # +1 to +5
            description_bonus=2,         # GM, +1 or +2
        )
        assert mod.total == -6 + 5 + 3 + 2

    def test_a_model_and_mere_existence_do_not_stack(self):
        """+5 "if you have a working model", +2 "if the device already exists
        but you don't have a model" — the second is the weaker case of the
        first, not an addition to it."""
        mod = crafting.concept_modifier(
            Complexity.SIMPLE, working_model=True, device_exists=True
        )
        assert mod.total == -6 + 5

    def test_penalties_are_reachable_too(self):
        mod = crafting.concept_modifier(
            Complexity.COMPLEX,
            new_technology=True,   # -5
            one_tl_above=True,     # -5
        )
        assert mod.total == -14 - 5 - 5

    def test_new_technology_is_independent_of_tech_level(self):
        """"regardless of TL" — the two -5s are different rules and both apply."""
        both = crafting.concept_modifier(
            Complexity.SIMPLE, new_technology=True, one_tl_above=True
        ).total
        only_new = crafting.concept_modifier(Complexity.SIMPLE, new_technology=True).total
        assert both == only_new - 5

    @pytest.mark.parametrize("bonus", [-1, 6])
    def test_the_variant_bonus_is_bounded_by_its_own_rule(self, bonus):
        """"+1 to +5 if the item is a variant on an existing one"."""
        with pytest.raises(ValueError):
            crafting.concept_modifier(Complexity.SIMPLE, variant_bonus=bonus)

    @pytest.mark.parametrize("bonus", [-1, 3])
    def test_the_description_bonus_is_bounded_by_its_own_rule(self, bonus):
        """"+1 or +2 to all invention-related skill rolls"."""
        with pytest.raises(ValueError):
            crafting.concept_modifier(Complexity.SIMPLE, description_bonus=bonus)

    def test_the_breakdown_names_every_term(self):
        """The guided flow shows its work; a bare integer cannot be audited."""
        mod = crafting.concept_modifier(
            Complexity.AVERAGE, working_model=True, one_tl_above=True
        )
        labels = [label for label, _ in mod.terms]
        assert any("Average" in label for label in labels)
        assert any("working model" in label for label in labels)
        assert any("TL above" in label for label in labels)
        assert sum(value for _, value in mod.terms) == mod.total

    def test_a_program_uses_its_rating_instead_of_the_table(self):
        mod = crafting.concept_modifier(Complexity.AMAZING, program_complexity=9)
        assert mod.total == -18
        assert not any("Amazing" in label for label, _ in mod.terms)


class TestImpossibleTargetsAreReportedHonestly:
    """SPEC impossible-targets-are-reported-honestly (B347).

    An Amazing invention at -22 puts almost every real inventor below 3. The
    engine must say so rather than clamp, and a natural 3-4 must still succeed.
    """

    def test_the_effective_target_goes_negative_without_a_floor(self):
        mod = crafting.concept_modifier(Complexity.AMAZING, new_technology=True)
        assert crafting.effective_target(skill=14, modifier=mod) == 14 - 22 - 5

    def test_the_engine_does_not_refuse_a_negative_target(self):
        from gurps_bot.mechanics.checks import Outcome, check_against

        result = check_against(rolled=3, target=-13)
        assert result is Outcome.CRITICAL_SUCCESS

    def test_an_ordinary_roll_against_a_negative_target_still_fails(self):
        from gurps_bot.mechanics.checks import Outcome, check_against

        assert check_against(rolled=10, target=-13) is Outcome.CRITICAL_FAILURE


# --- prototype --------------------------------------------------------------


class TestPrototypeModifier:
    """B474: everything Concept had, plus assistants and facilities."""

    def test_it_inherits_the_concept_modifiers(self):
        concept = crafting.concept_modifier(Complexity.COMPLEX, working_model=True)
        proto = crafting.prototype_modifier(Complexity.COMPLEX, working_model=True)
        assert proto.total == concept.total

    @pytest.mark.parametrize("assistants,bonus", [(0, 0), (1, 1), (4, 4), (5, 4), (20, 4)])
    def test_assistants_give_one_each_to_a_cap_of_four(self, assistants, bonus):
        """"+1 per assistant with skill 20+ …, to a maximum of +4"."""
        proto = crafting.prototype_modifier(Complexity.SIMPLE, skilled_assistants=assistants)
        assert proto.total == -6 + bonus

    def test_an_assistant_here_means_plus_one_to_the_roll(self):
        """Invention's reading of "assistant". Four other domains disagree —
        see the per-domain scan; this asserts THIS one rather than a shared
        abstraction."""
        assert crafting.ASSISTANT_BONUS_EACH == 1
        assert crafting.ASSISTANT_BONUS_CAP == 4

    @pytest.mark.parametrize("penalty", [0, -1, -10])
    def test_the_facility_penalty_is_a_gm_parameter_within_the_books_range(self, penalty):
        """"-1 to -10 (GM's discretion)". The book states a range and hands the
        call to the GM, so the engine takes it rather than deriving a ladder."""
        proto = crafting.prototype_modifier(Complexity.SIMPLE, facility_penalty=penalty)
        assert proto.total == -6 + penalty

    @pytest.mark.parametrize("penalty", [1, -11])
    def test_a_facility_penalty_outside_the_books_range_is_refused(self, penalty):
        with pytest.raises(ValueError):
            crafting.prototype_modifier(Complexity.SIMPLE, facility_penalty=penalty)


class TestPrototypeTime:
    """B474 Time Required."""

    def test_workers_divide_the_time(self):
        """"Divide time required by the number of skilled people"."""
        rolled = crafting.prototype_elapsed(Complexity.AVERAGE, rolled_dice=8, workers=4)
        assert rolled.amount == 2

    def test_a_lone_inventor_divides_by_one(self):
        rolled = crafting.prototype_elapsed(Complexity.AVERAGE, rolled_dice=8, workers=1)
        assert rolled.amount == 8  # undivided

    def test_the_floor_is_one_day_not_zero(self):
        """"Minimum time is always one day." A 1d-2 Simple roll of 1 is -1."""
        rolled = crafting.prototype_elapsed(Complexity.SIMPLE, rolled_dice=-1, workers=1)
        assert rolled.amount == 1
        assert rolled.unit == "days"

    def test_the_floor_survives_division_by_a_crowd(self):
        rolled = crafting.prototype_elapsed(Complexity.COMPLEX, rolled_dice=3, workers=99)
        assert rolled.amount == 1

    def test_the_floor_is_one_DAY_even_when_the_unit_is_months(self):
        """The book's floor is stated in days; a Complex project floored by a
        crowd is one day, not one month."""
        rolled = crafting.prototype_elapsed(Complexity.COMPLEX, rolled_dice=3, workers=99)
        assert rolled.unit == "days"

    def test_zero_workers_is_refused_rather_than_dividing_by_zero(self):
        with pytest.raises(ValueError):
            crafting.prototype_elapsed(Complexity.SIMPLE, rolled_dice=3, workers=0)


class TestMoneyIsNeverSummedIntoOneNumber:
    """SPEC money-is-never-summed-into-one-number.

    B474 keeps three unlike figures apart: a one-off facilities charge per
    inventor, a per-attempt charge equal to the item's retail price, and a
    per-copy production charge. They have different payers, different cadences
    and different triggers, so a single "cost" is a lie in every direction.
    """

    def test_the_three_figures_are_separate_fields(self):
        costs = crafting.invention_costs(Complexity.COMPLEX, retail_price=5_000)
        assert costs.facilities == 250_000
        assert costs.per_attempt == 5_000
        assert costs.per_copy_parts_only == 1_000  # 20% of retail

    def test_there_is_no_total(self):
        costs = crafting.invention_costs(Complexity.SIMPLE, retail_price=100)
        for banned in ("total", "sum", "grand_total"):
            assert not hasattr(costs, banned), (
                f"InventionCosts grew a {banned!r} — the three figures have "
                f"different payers and cadences; collapsing them is the lie the "
                f"spec forbids"
            )

    def test_a_tl_advance_triples_both_the_facilities_and_the_attempt(self):
        """"Triple these costs" (facilities) and "Triple this cost" (attempt)
        are two separate sentences applying to the same condition."""
        plain = crafting.invention_costs(Complexity.AVERAGE, retail_price=2_000)
        ahead = crafting.invention_costs(
            Complexity.AVERAGE, retail_price=2_000, one_tl_above=True
        )
        assert ahead.facilities == plain.facilities * 3
        assert ahead.per_attempt == plain.per_attempt * 3

    def test_a_tl_advance_does_not_triple_the_copies(self):
        """Production is priced off retail and the book tripes only the two
        figures above — a shared multiplier would be a fabrication."""
        plain = crafting.invention_costs(Complexity.AVERAGE, retail_price=2_000)
        ahead = crafting.invention_costs(
            Complexity.AVERAGE, retail_price=2_000, one_tl_above=True
        )
        assert ahead.per_copy_parts_only == plain.per_copy_parts_only

    def test_leftover_facilities_divide_by_ten(self):
        """"Divide costs by 10 if the inventor has appropriate facilities left
        over from a related project of equal or higher complexity"."""
        costs = crafting.invention_costs(
            Complexity.COMPLEX, retail_price=100, reuses_facilities=True
        )
        assert costs.facilities == 25_000

    def test_reuse_and_a_tl_advance_compose(self):
        costs = crafting.invention_costs(
            Complexity.COMPLEX, retail_price=100, reuses_facilities=True, one_tl_above=True
        )
        assert costs.facilities == 250_000 * 3 // 10

    def test_reuse_does_not_touch_the_per_attempt_charge(self):
        """The discount is about facilities. The attempt still buys an item."""
        costs = crafting.invention_costs(
            Complexity.SIMPLE, retail_price=800, reuses_facilities=True
        )
        assert costs.per_attempt == 800

    def test_facilities_are_charged_per_inventor_not_per_project(self):
        """"Each inventor who wishes to attempt a Prototype roll must pay the
        facilities cost 'up front'" — assistants are not inventors."""
        costs = crafting.invention_costs(Complexity.AVERAGE, retail_price=10, inventors=3)
        assert costs.facilities == 100_000 * 3


# --- testing and bugs -------------------------------------------------------


class TestBugsFromThePrototypeRoll:
    """B474: the prototype roll's QUALITY decides the bug load."""

    def test_a_critical_success_is_a_clean_prototype(self):
        bugs = crafting.bugs_from_prototype(margin=0, critical_success=True)
        assert bugs.major_dice is None
        assert bugs.minor_dice is None
        assert bugs.is_clean

    def test_success_by_three_or_more_gives_only_minor_bugs(self):
        bugs = crafting.bugs_from_prototype(margin=3)
        assert bugs.major_dice is None
        assert str(bugs.minor_dice) == "1d"
        assert bugs.minor_halved is True

    def test_a_bare_success_gives_major_bugs_too(self):
        bugs = crafting.bugs_from_prototype(margin=2)
        assert str(bugs.major_dice) == "1d"
        assert bugs.major_halved is True
        assert str(bugs.minor_dice) == "1d"
        assert bugs.minor_halved is False

    def test_the_boundary_is_three_not_two(self):
        assert crafting.bugs_from_prototype(margin=3).major_dice is None
        assert crafting.bugs_from_prototype(margin=2).major_dice is not None

    def test_a_failed_prototype_has_no_bug_load_because_it_has_no_prototype(self):
        with pytest.raises(ValueError):
            crafting.bugs_from_prototype(margin=-1)


class TestFindingBugs:
    """B474: once per week, vs the OPERATION skill, at -3."""

    def test_the_testing_penalty_is_minus_three(self):
        assert crafting.TESTING_PENALTY == -3

    def test_testing_is_weekly(self):
        assert Stage.TESTING.cadence == "once per week"

    def test_the_roller_is_the_operator_not_the_inventor(self):
        """"roll vs. operation skill (e.g., Driving for a car …)" — the skill
        that USES the device, which is a different skill and often a different
        person from the one that invented it."""
        assert Stage.TESTING.skill_kind == "operation"
        assert Stage.TESTING.roller is Roller.PLAYER

    @pytest.mark.parametrize(
        "outcome,found",
        [("critical_success", "all"), ("success", 1), ("failure", 0), ("critical_failure", 0)],
    )
    def test_what_each_outcome_finds(self, outcome, found):
        assert crafting.bugs_found_by(outcome) == found

    def test_a_failure_triggers_a_major_bug_if_one_is_present(self):
        result = crafting.testing_result("failure", major_bugs_remaining=1)
        assert result.triggers_major_bug is True

    def test_a_failure_with_no_major_bug_left_merely_finds_nothing(self):
        result = crafting.testing_result("failure", major_bugs_remaining=0)
        assert result.triggers_major_bug is False
        assert result.bugs_found == 0

    def test_a_critical_failure_hurts_without_touching_a_real_bug(self):
        """"causes a problem similar to a major bug without encountering any
        real bugs" — the bug count must not go down."""
        result = crafting.testing_result("critical_failure", major_bugs_remaining=2)
        assert result.bugs_found == 0
        assert result.simulates_major_bug is True

    def test_the_critical_failure_alternative_is_offered_not_chosen(self):
        """The book gives the GM an either/or: a fake major bug, OR a false
        clean bill of health. Choosing one silently would be an adjudication."""
        result = crafting.testing_result("critical_failure", major_bugs_remaining=0)
        assert result.gm_alternative is not None
        assert "no bugs remain" in result.gm_alternative


class TestBugsSurfaceInPlay:
    """B474 sidebar: what an unfound bug does at the table."""

    @pytest.mark.parametrize("margin,surfaces", [(-4, False), (-5, True), (-9, True)])
    def test_a_lingering_bug_surfaces_on_a_miss_by_five(self, margin, surfaces):
        assert crafting.bug_surfaces(margin=margin, critical_failure=False) is surfaces

    def test_a_major_bug_always_surfaces_on_a_critical_failure(self):
        assert crafting.bug_surfaces(margin=-1, critical_failure=True) is True


# --- production -------------------------------------------------------------


class TestProduction:
    """B474: two ways to make copies, priced and timed differently."""

    def test_a_hand_built_copy_is_a_fifth_for_parts_or_full_for_labour(self):
        assert crafting.copy_cost(retail_price=1_000, parts_only=True) == 200
        assert crafting.copy_cost(retail_price=1_000, parts_only=False) == 1_000

    def test_a_production_line_copy_is_half_retail_with_labour_not_full(self):
        """The two ladders differ in exactly one cell — 100% by hand vs 50% on
        the line — and the parts-only figure is 20% for both."""
        assert crafting.copy_cost(retail_price=1_000, parts_only=False, from_line=True) == 500
        assert crafting.copy_cost(retail_price=1_000, parts_only=True, from_line=True) == 200

    def test_setting_up_a_line_costs_twenty_times_retail(self):
        assert crafting.production_line_setup_cost(retail_price=1_000) == 20_000

    def test_a_hand_built_copy_takes_half_the_prototype_time(self):
        assert crafting.copy_time(prototype_days=30) == 15

    def test_a_line_copy_takes_the_lesser_of_a_seventh_and_retail_over_a_hundred(self):
        """"in 1/7 the time it took to build a prototype or in (retail
        price/100) hours, whichever is less"."""
        # 70 days = 1680 hours; a seventh is 240 hours, retail/100 is 50 hours.
        assert crafting.line_copy_hours(prototype_days=70, retail_price=5_000) == 50

    def test_the_other_side_of_the_whichever_is_less(self):
        # A cheap item off a fast prototype: the seventh wins.
        assert crafting.line_copy_hours(prototype_days=7, retail_price=100_000) == 24


# --- the four stages --------------------------------------------------------


class TestInventionWalksItsFourStages:
    """SPEC invention-walks-its-four-stages."""

    def test_there_are_exactly_four_and_they_are_ordered(self):
        assert [s.name for s in crafting.STAGES] == [
            "Concept", "Prototype", "Testing", "Production",
        ]

    def test_each_stage_states_its_own_roller(self):
        assert Stage.CONCEPT.roller is Roller.GM
        assert Stage.PROTOTYPE.roller is Roller.GM
        assert Stage.TESTING.roller is Roller.PLAYER
        assert Stage.PRODUCTION.roller is Roller.NOBODY

    def test_each_stage_states_its_own_cadence(self):
        assert Stage.CONCEPT.cadence == "once per day"
        assert Stage.TESTING.cadence == "once per week"
        assert Stage.PROTOTYPE.cadence != Stage.CONCEPT.cadence

    def test_no_two_stages_share_a_whole_profile(self):
        """If two stages agree on everything, one of them is not a stage."""
        profiles = {(s.roller, s.cadence, s.skill_kind) for s in crafting.STAGES}
        assert len(profiles) == len(crafting.STAGES)


class TestGmRollsStayWithTheGm:
    """SPEC gm-rolls-stay-with-the-gm.

    B473 says the Concept roll is secret and B474 says the Prototype roll is
    too, and gives the reason: a flawed theory must stay invisible or the
    player knows the prototype is doomed before building it.
    """

    def test_the_two_secret_stages_are_marked_secret(self):
        assert Stage.CONCEPT.secret is True
        assert Stage.PROTOTYPE.secret is True

    def test_the_stages_a_player_drives_are_not_secret(self):
        assert Stage.TESTING.secret is False
        assert Stage.PRODUCTION.secret is False

    def test_secrecy_and_roller_agree(self):
        """A stage the GM rolls is secret; one the player rolls is not. Stated
        as a property so a new stage cannot be added inconsistently."""
        for stage in crafting.STAGES:
            assert stage.secret == (stage.roller is Roller.GM)


class TestFlawedTheory:
    """B473-474's reason for the secrecy, as a rule rather than a note."""

    def test_a_critical_failure_on_concept_still_advances_to_prototype(self):
        """"go on to the next step, but note that it is doomed to failure"."""
        outcome = crafting.concept_outcome("critical_failure")
        assert outcome.advances is True
        assert outcome.flawed_theory is True

    def test_an_ordinary_failure_does_not_advance(self):
        outcome = crafting.concept_outcome("failure")
        assert outcome.advances is False
        assert outcome.flawed_theory is False
        assert outcome.retry_penalty == 0  # "may try again … at no additional penalty"

    def test_a_flawed_theory_can_never_yield_a_prototype(self):
        assert crafting.prototype_possible(flawed_theory=True, outcome="success") is False

    def test_only_a_critical_success_reveals_the_flaw(self):
        """"a critical success on the Prototype roll lets him realize that his
        theory was bad" — the single escape hatch."""
        assert crafting.flaw_revealed(flawed_theory=True, outcome="critical_success") is True
        assert crafting.flaw_revealed(flawed_theory=True, outcome="success") is False

    def test_nothing_is_revealed_when_there_was_no_flaw(self):
        assert crafting.flaw_revealed(flawed_theory=False, outcome="critical_success") is False


class TestPrototypeCriticalFailure:
    """B474: the explosion, which is the one place invention deals damage."""

    def test_it_damages_the_inventor_and_every_assistant(self):
        blast = crafting.prototype_disaster(assistants=3)
        assert blast.victims == 4
        assert str(blast.damage) == "2d"
        assert blast.damage_is_a_minimum is True

    def test_it_destroys_the_facilities(self):
        blast = crafting.prototype_disaster(assistants=0)
        assert blast.facilities_destroyed is True

    def test_rebuilding_is_at_full_cost_ignoring_the_reuse_discount(self):
        """"destroys the facilities, which must be rebuilt at full cost" — the
        ÷10 leftover-facilities discount cannot apply to a rebuild."""
        rebuilt = crafting.rebuild_facilities_cost(
            Complexity.COMPLEX, reuses_facilities=True
        )
        assert rebuilt == 250_000
