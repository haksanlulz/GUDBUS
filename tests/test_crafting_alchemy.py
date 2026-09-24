"""GURPS Magic ch. 28 — alchemy.

Everything here came off Magic pp. 210-212 in the operator's own copy.

⚑ Three alchemy specs are closed by this module, and every number that
arrived second-hand turned out to be printed:
the -1/0/+1/+TL/2 lab ladder, the suppressed critical successes, and the
two-stage critical failure. None of them was a house rule.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics import crafting_alchemy as alchemy
from gurps_bot.mechanics.crafting_alchemy import LabQuality, Mana


class TestTheLabLadder:
    """Alchemy's own facility ladder — a third shape in the family."""

    @pytest.mark.parametrize(
        "quality,expected",
        [
            (LabQuality.MAKESHIFT, -1),
            (LabQuality.BASIC, 0),
            (LabQuality.PROFESSIONAL, 1),
        ],
    )
    def test_the_fixed_rungs(self, quality, expected):
        assert alchemy.lab_modifier(quality) == expected

    @pytest.mark.parametrize("tl,expected", [(3, 1), (4, 2), (8, 4), (11, 5)])
    def test_the_top_rung_is_half_the_tech_level(self, tl, expected):
        assert alchemy.lab_modifier(LabQuality.CUTTING_EDGE, tl) == expected

    def test_the_top_rung_is_not_worth_it_below_tl4(self):
        """The book says so, and it is only true because the value is derived:
        at TL3 a $20,000 lab buys the same +1 a $5,000 one does."""
        assert alchemy.lab_modifier(LabQuality.CUTTING_EDGE, 3) == alchemy.lab_modifier(
            LabQuality.PROFESSIONAL
        )
        assert alchemy.lab_modifier(LabQuality.CUTTING_EDGE, 4) > alchemy.lab_modifier(
            LabQuality.PROFESSIONAL
        )

    def test_the_top_rung_refuses_to_guess_a_tech_level(self):
        with pytest.raises(ValueError):
            alchemy.lab_modifier(LabQuality.CUTTING_EDGE)


class TestMana:
    """The axis no other crafting domain has."""

    def test_no_mana_forbids_brewing_outright(self):
        assert not alchemy.can_brew(Mana.NONE)
        for other in (Mana.LOW, Mana.NORMAL, Mana.HIGH, Mana.VERY_HIGH):
            assert alchemy.can_brew(other)

    @pytest.mark.parametrize(
        "mana,multiplier",
        [(Mana.LOW, 2.0), (Mana.NORMAL, 1.0), (Mana.HIGH, 1.0), (Mana.VERY_HIGH, 0.5)],
    )
    def test_brewing_time(self, mana, multiplier):
        assert alchemy.brewing_time_multiplier(mana) == multiplier

    def test_low_mana_also_halves_how_long_the_elixir_WORKS(self):
        """Two separate rules that both fire in low mana, and only one of them
        is about the brewing."""
        assert alchemy.brewing_time_multiplier(Mana.LOW) == 2.0
        assert alchemy.elixir_duration_multiplier(Mana.LOW) == 0.5

    def test_permanent_elixirs_are_exempt_from_the_duration_halving(self):
        assert alchemy.elixir_duration_multiplier(Mana.LOW, permanent=True) == 1.0

    def test_very_high_mana_trades_speed_for_disaster(self):
        """Half the time, but "any failure is critical" — so the ordinary
        ruined-ingredients outcome stops existing."""
        assert alchemy.brewing_time_multiplier(Mana.VERY_HIGH) == 0.5
        assert alchemy.every_failure_is_critical(Mana.VERY_HIGH)
        assert not alchemy.every_failure_is_critical(Mana.HIGH)

    def test_a_plain_failure_in_very_high_mana_reaches_the_disaster_path(self):
        outcome = alchemy.resolve_brew("failure", doses=1, mana=Mana.VERY_HIGH)
        assert outcome.needs_disaster_roll
        normal = alchemy.resolve_brew("failure", doses=1, mana=Mana.NORMAL)
        assert not normal.needs_disaster_roll

    def test_no_mana_refuses_rather_than_returning_a_number(self):
        with pytest.raises(ValueError):
            alchemy.brewing_time_multiplier(Mana.NONE)
        with pytest.raises(ValueError):
            alchemy.elixir_duration_multiplier(Mana.NONE)


class TestTheBatchRuleHasTwoClauses:
    """The exact rule most easily applied by halves."""

    @pytest.mark.parametrize("doses,penalty", [(1, 0), (2, -1), (3, -2), (6, -5)])
    def test_the_roll_takes_minus_one_per_EXTRA_dose(self, doses, penalty):
        assert alchemy.batch_penalty(doses) == penalty

    @pytest.mark.parametrize("doses,cost", [(1, 50), (3, 150), (10, 500)])
    def test_the_materials_cost_multiplies_by_the_whole_batch(self, doses, cost):
        assert alchemy.batch_materials_cost(50, doses) == cost

    def test_both_clauses_move_together(self):
        """Applying one without the other is the failure mode: a bigger batch
        must get both harder AND dearer."""
        small = (alchemy.batch_penalty(1), alchemy.batch_materials_cost(50, 1))
        large = (alchemy.batch_penalty(5), alchemy.batch_materials_cost(50, 5))
        assert large[0] < small[0]
        assert large[1] > small[1]

    def test_a_batch_of_zero_is_refused(self):
        with pytest.raises(ValueError):
            alchemy.batch_penalty(0)
        with pytest.raises(ValueError):
            alchemy.batch_materials_cost(50, 0)


class TestTheTwoBatchPenaltiesAreNotTheSame:
    """⚑ The subtlety most likely to be got wrong: the brew roll is -1 per EXTRA dose, the disaster-avoidance roll
    is -1 per dose. Four lines apart, one word different."""

    @pytest.mark.parametrize("doses", [1, 2, 3, 7])
    def test_they_differ_by_exactly_one_at_every_batch_size(self, doses):
        assert alchemy.disaster_roll_penalty(doses) == alchemy.batch_penalty(doses) - 1

    def test_a_single_dose_shows_it_most_clearly(self):
        """One dose: the brew roll is unmodified, the disaster roll is -1."""
        assert alchemy.batch_penalty(1) == 0
        assert alchemy.disaster_roll_penalty(1) == -1

    def test_the_worked_case(self):
        """Three doses: brew at -2, disaster-avoidance at -3."""
        assert alchemy.batch_penalty(3) == -2
        assert alchemy.disaster_roll_penalty(3) == -3


class TestThereAreNoCriticalSuccesses:
    """SPEC alchemy-has-no-critical-successes."""

    def test_a_reported_critical_success_is_refused_not_downgraded(self):
        """Returning a plain success would hide the real problem — that the
        caller used the unmodified core engine, which returns CRITICAL_SUCCESS
        on any 3 or 4 regardless of target."""
        with pytest.raises(ValueError):
            alchemy.resolve_brew("critical_success")

    def test_the_core_engine_would_have_produced_one(self):
        """Shows the reuse this domain forbids is a real hazard, not theory."""
        from gurps_bot.mechanics.checks import Outcome, check_against

        assert check_against(rolled=3, target=12) is Outcome.CRITICAL_SUCCESS

    def test_a_success_is_just_a_success(self):
        outcome = alchemy.resolve_brew("success")
        assert outcome.succeeded
        assert not outcome.ingredients_ruined
        assert not outcome.needs_disaster_roll


class TestFailure:
    def test_an_ordinary_failure_ruins_the_ingredients_and_stops_there(self):
        outcome = alchemy.resolve_brew("failure", doses=3)
        assert not outcome.succeeded
        assert outcome.ingredients_ruined
        assert not outcome.needs_disaster_roll

    def test_a_critical_failure_is_two_rolls_not_one(self):
        """SPEC an-alchemy-disaster-takes-two-rolls-to-reach-the-table."""
        outcome = alchemy.resolve_brew("critical_failure", doses=4)
        assert outcome.needs_disaster_roll
        assert outcome.disaster_roll_modifier == -4

    def test_the_second_roll_can_avert_the_table_entirely(self):
        """The engine reports that a roll is owed; success on it is the
        averted case, which is why this returns a modifier rather than a row."""
        outcome = alchemy.resolve_brew("critical_failure")
        assert outcome.needs_disaster_roll
        assert not hasattr(outcome, "disaster")


class TestTheDisasterTable:
    @pytest.mark.parametrize(
        "rolled,radius,lab,damage",
        [
            (3, 100, False, None),
            (5, 100, False, None),
            (6, 10, False, None),
            (9, 10, False, None),
            (10, None, True, None),
            (12, None, True, None),
            (13, None, True, "3d"),
            (15, None, True, "3d"),
            (16, None, True, "6d"),
            (18, None, True, "6d"),
        ],
    )
    def test_the_rows(self, rolled, radius, lab, damage):
        row = alchemy.disaster_for(rolled)
        assert row.elixir_radius_yards == radius
        assert row.lab_destroyed is lab
        if damage is None:
            assert row.alchemist_damage is None
        else:
            assert str(row.alchemist_damage) == damage

    def test_the_table_covers_every_3d_result(self):
        for rolled in range(3, 19):
            assert alchemy.disaster_for(rolled) is not None

    def test_an_impossible_roll_is_refused(self):
        for rolled in (2, 19):
            with pytest.raises(ValueError):
                alchemy.disaster_for(rolled)

    def test_the_bad_rows_do_not_destroy_the_lab(self):
        """The two elixir-radius rows are dangerous to bystanders and leave the
        lab standing; the explosion rows are the reverse."""
        assert not alchemy.disaster_for(4).lab_destroyed
        assert alchemy.disaster_for(11).lab_destroyed

    def test_the_elixir_effect_itself_is_not_in_the_repo(self):
        """The rows say WHO is affected and how far; WHAT happens to them is
        the elixir's own entry, which stays in the book."""
        row = alchemy.disaster_for(4)
        assert row.elixir_radius_yards == 100
        assert row.reversed_is_even_odds is True
        assert not hasattr(row, "effect")
        assert not hasattr(row, "description")


class TestTheWeakestWorkerRolls:
    """Alchemy's reading of "assistant", and it inverts invention's."""

    def test_the_lowest_skill_alchemist_makes_the_final_roll(self):
        assert alchemy.final_roller_skill([18, 12, 15]) == 12

    def test_bringing_in_help_can_make_it_WORSE(self):
        """Invention: +1 per skilled assistant. Alchemy: a weaker pair of hands
        lowers the roll that decides the batch."""
        alone = alchemy.final_roller_skill([18])
        helped = alchemy.final_roller_skill([18, 10])
        assert helped < alone

        from gurps_bot.mechanics import crafting as invention

        assert invention.ASSISTANT_BONUS_EACH > 0

    def test_someone_has_to_brew_it(self):
        with pytest.raises(ValueError):
            alchemy.final_roller_skill([])


class TestMasteryIsDerivedAndNeverAsked:
    """The reference scenario's mastery condition — and it failed on re-verify 2026-08-15.

    ``brewing_modifier`` took ``unmastered: bool``: the caller handed the
    module its conclusion. That is the same disease as a ``quality=``
    argument — the module owns the rule, so it must own the verdict. A
    technique bought up to its base skill is mastered, so the -6 cannot
    apply, and nothing should have to be asked to know that.
    """

    def test_a_technique_at_base_skill_is_mastered(self):
        assert alchemy.is_mastered(technique=12, alchemy_skill=12)

    def test_a_technique_at_default_is_not(self):
        assert not alchemy.is_mastered(technique=11, alchemy_skill=12)

    def test_mastery_alone_retires_the_penalty_with_no_book_in_sight(self):
        assert (
            alchemy.blind_brewing_penalty(
                technique=12, alchemy_skill=12, formulary=False, teacher=False
            )
            == 0
        )

    @pytest.mark.parametrize("formulary,teacher", [(True, False), (False, True)])
    def test_either_a_book_or_a_teacher_also_retires_it(self, formulary, teacher):
        assert (
            alchemy.blind_brewing_penalty(
                technique=11, alchemy_skill=12, formulary=formulary, teacher=teacher
            )
            == 0
        )

    def test_unmastered_and_alone_is_the_minus_six(self):
        assert alchemy.UNMASTERED_PENALTY == -6
        assert (
            alchemy.blind_brewing_penalty(
                technique=11, alchemy_skill=12, formulary=False, teacher=False
            )
            == -6
        )

    def test_the_conclusion_cannot_be_passed_in(self):
        """The regression guard. If ``unmastered=`` ever comes back as a
        parameter, the caller can assert a rule the module is supposed to
        decide, and the mastery condition silently reopens."""
        import inspect

        params = inspect.signature(alchemy.brewing_modifier).parameters
        assert "unmastered" not in params
        assert "mastered" not in params


class TestFormulariesAndSecrets:

    def test_most_elixirs_default_to_alchemy_minus_one(self):
        assert alchemy.TECHNIQUE_DEFAULT == -1

    @pytest.mark.parametrize(
        "price,secret,grand",
        [(500, False, False), (1_001, True, False), (10_001, True, True)],
    )
    def test_the_guild_thresholds(self, price, secret, grand):
        assert alchemy.is_secret_formula(price) is secret
        assert alchemy.needs_grand_master(price) is grand

    def test_the_thresholds_are_exclusive(self):
        """"more than $1,000 per dose" — exactly $1,000 is not secret."""
        assert not alchemy.is_secret_formula(1_000)
        assert not alchemy.needs_grand_master(10_000)


class TestTheBrewingModifier:
    def test_it_assembles_the_terms(self):
        mod = alchemy.brewing_modifier(
            alchemy_skill=12, lab=LabQuality.PROFESSIONAL, doses=3, formulary=True
        )
        # professional lab +1, technique sits at its Alchemy-1 default, two
        # extra doses -2. The formulary is what keeps the -6 out of it, and
        # this test had to be told so: written against the old signature it
        # expected -2 and got -8, because a defaulted technique with no book
        # really is brewing blind.
        assert mod.total == 1 - 1 - 2
        labels = [label for label, _ in mod.terms]
        assert any("doses" in label for label in labels)

    def test_a_basic_lab_contributes_nothing_and_says_nothing(self):
        mod = alchemy.brewing_modifier(alchemy_skill=12, technique=12)
        assert mod.total == 0
        assert mod.terms == ()


class TestTheReferenceScenarioEndToEnd:
    """The alchemy reference scenario, run as one call.

    Alchemy 12 · elixir technique raised to 12 · basic lab · formulary in
    hand · 2 doses · standard mana · $200/dose · 1 week.
    """

    def test_the_effective_target_is_eleven(self):
        assert (
            alchemy.effective_target(
                alchemy_skill=12,
                technique=12,
                lab=LabQuality.BASIC,
                doses=2,
                formulary=True,
            )
            == 11
        )

    def test_the_formulary_was_never_needed(self):
        """Mastery already covers it, so the answer must not move when the
        book is taken away — condition 4's whole point."""
        with_book = alchemy.effective_target(
            alchemy_skill=12, technique=12, lab=LabQuality.BASIC, doses=2,
            formulary=True,
        )
        without = alchemy.effective_target(
            alchemy_skill=12, technique=12, lab=LabQuality.BASIC, doses=2,
            formulary=False,
        )
        assert with_book == without == 11

    def test_the_materials_are_four_hundred(self):
        assert alchemy.batch_materials_cost(200, 2) == 400

    def test_the_batch_takes_one_week_not_two(self):
        """Batch time does not multiply. Asserted by signature, because the
        durable version of this rule is that there is nowhere to put the
        doses — a number that cannot be passed cannot be multiplied by."""
        import inspect

        assert "doses" not in inspect.signature(
            alchemy.brewing_time_multiplier
        ).parameters
        assert alchemy.brewing_time_multiplier(Mana.NORMAL) == 1.0

    def test_an_unmastered_brewer_without_the_book_is_ten_worse(self):
        """The same scenario with the -6 live — pins that the derivation is
        actually reachable, not merely present."""
        assert (
            alchemy.effective_target(
                alchemy_skill=12,
                technique=11,
                lab=LabQuality.BASIC,
                doses=2,
                formulary=False,
            )
            == 4
        )
