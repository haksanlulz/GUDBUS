"""GURPS Magic pp. 16-18 — enchantment.

Everything came off the book, and the book is the authority here.

⚑ The book's two worked examples are the regression class, and between them
they exercise the assistant penalty, the bystander penalty, the min() over two
skills, and the derived headcount cap.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics import crafting_enchantment as ench
from gurps_bot.mechanics.crafting_enchantment import (
    CeremonialOutcome,
    Mana,
    Method,
)


class TestTheBooksWorkedExamples:
    """Two enchanters, printed start to finish."""

    def test_the_powerstone_sitting(self):
        """Hawthorne has Powerstone 16 and Enchant 17; Tubbs assists. The book
        says Hawthorne "does the actual casting" and rolls against an effective
        skill of 15."""
        assert (
            ench.effective_skill(enchant_skill=17, spell_skill=16, assistants=1) == 15
        )

    def test_the_better_enchanter_casts(self):
        """Tubbs has 15 in both, Hawthorne 16 and 17. Whoever casts, the base
        is the lower of their own two skills — so Hawthorne's 16 beats Tubbs's
        15 and he is the one who should hold the chalk."""
        hawthorne = ench.enchanting_skill(17, 16)
        tubbs = ench.enchanting_skill(15, 15)
        assert hawthorne > tubbs

    def test_the_staff_sitting(self):
        """Staff spell 17, Enchant 17, one assistant and one customer who will
        not leave the room: 17 - 1 - 1 = 15."""
        assert (
            ench.effective_skill(
                enchant_skill=17, spell_skill=17, assistants=1, bystanders=True
            )
            == 15
        )

    def test_neither_example_can_distinguish_the_min_from_the_spell_alone(self):
        """Worth recording rather than glossing: in both sittings Enchant is at
        or above the other spell, so "the lower of both" and "the enchanted
        spell" give the same answer. The general statement on p. 17 is what
        settles it, not these."""
        both_ways_agree = ench.enchanting_skill(17, 16) == 16
        assert both_ways_agree

    def test_and_here_is_a_case_that_does_distinguish_them(self):
        """A superb spell and a shaky Enchant. If the rule were "the enchanted
        spell", this would be 18."""
        assert ench.enchanting_skill(enchant_skill=15, spell_skill=18) == 15


class TestPowerIsTheRollIsTheSkill:
    def test_power_equals_effective_skill(self):
        effective = ench.effective_skill(enchant_skill=18, spell_skill=18, assistants=2)
        assert ench.item_power(effective) == 16

    def test_a_weak_second_spell_caps_the_item(self):
        """"whichever is lower" — no averaging, so being superb at Enchant
        buys nothing if the spell going in is shaky."""
        assert ench.effective_skill(enchant_skill=25, spell_skill=15) == 15

    def test_rolling_well_does_not_make_a_better_item(self):
        """A fourth reading of what a craft roll MEANS, after success (invention),
        quantity (repair) and quality (mundane): here the roll only says whether
        it worked, and the item's quality was fixed before the dice were picked
        up."""
        import inspect

        params = inspect.signature(ench.item_power).parameters
        assert "margin" not in params
        assert "rolled" not in params


class TestTheItemHasToWorkWhereItIsUsed:
    def test_fifteen_is_the_floor(self):
        assert ench.item_works(15)
        assert not ench.item_works(14)

    def test_low_mana_makes_the_real_floor_twenty(self):
        """The book states the derived number outright, which makes it a check
        on the derivation rather than a restatement of it."""
        assert not ench.item_works(19, Mana.LOW)
        assert ench.item_works(20, Mana.LOW)

    def test_no_magic_item_works_in_a_no_mana_region(self):
        assert not ench.item_works(100, Mana.NONE)

    def test_no_mana_is_not_the_same_as_power_zero(self):
        """Collapsing them would let a big enough item work anywhere."""
        assert ench.power_in_play(30, Mana.NONE) is None
        assert ench.power_in_play(30, Mana.LOW) == 25


class TestTheAssistantCapIsDerivedNotPrinted:
    @pytest.mark.parametrize(
        "skill,cap", [(15, 0), (16, 1), (18, 3), (20, 5)]
    )
    def test_you_may_bring_as_many_as_leave_you_at_fifteen(self, skill, cap):
        assert ench.assistant_cap(skill) == cap

    def test_the_cap_is_exactly_where_effective_skill_hits_fifteen(self):
        """Stated as a property rather than a table, because that is how the
        book states it — the cap is a consequence of the -1 each, not a
        separate number to get wrong."""
        for skill in range(15, 25):
            cap = ench.assistant_cap(skill)
            assert (
                ench.effective_skill(skill, skill, assistants=cap)
                == ench.MINIMUM_EFFECTIVE_SKILL
            )

    def test_one_more_would_break_it(self):
        cap = ench.assistant_cap(18)
        assert (
            ench.effective_skill(18, 18, assistants=cap + 1)
            < ench.MINIMUM_EFFECTIVE_SKILL
        )

    def test_a_bare_minimum_caster_works_alone(self):
        assert ench.assistant_cap(15) == 0

    def test_an_unqualified_helper_cannot_contribute_at_all(self):
        """"Unskilled spectators cannot contribute energy" — not a weaker
        assistant, no assistant."""
        assert not ench.everyone_is_qualified(16, 14)
        assert ench.everyone_is_qualified(16, 15)


class TestAssistantsMeanFiveDifferentThings:
    def test_this_domain_alone_holds_two_of_them(self):
        """Quick and Dirty: -1 to the roll each. Slow and Sure: they divide the
        mage-days and touch no roll."""
        penalised = ench.enchanting_modifier(assistants=3).total
        assert penalised == -3
        assert ench.slow_and_sure_days(100, mages=4) == 25

    def test_and_it_contradicts_invention_and_alchemy_and_crafting(self):
        from gurps_bot.mechanics import crafting as invention
        from gurps_bot.mechanics import crafting_alchemy as alchemy
        from gurps_bot.mechanics import crafting_mundane as mundane

        # invention: an assistant HELPS the roll
        assert invention.ASSISTANT_BONUS_EACH > 0
        # enchantment: an assistant HURTS it
        assert ench.ASSISTANT_PENALTY_EACH < 0
        # alchemy: the weakest hand rolls; mundane: the strongest does
        assert alchemy.final_roller_skill([12, 18]) == 12
        assert mundane.rolling_skill([12, 18]) == 18

    def test_mundane_caps_the_headcount_and_this_does_not(self):
        """Six is a hard cap on crafting workers. Here a big team is allowed
        and simply makes the roll unwinnable, which is a different constraint
        reached from a different direction."""
        from gurps_bot.mechanics import crafting_mundane as mundane

        assert mundane.elapsed_hours(60, 100) == mundane.elapsed_hours(60, 6)
        assert ench.slow_and_sure_days(100, 100) < ench.slow_and_sure_days(100, 6)


class TestTheCeremonialThresholds:
    """The third check variant in the arc."""

    def test_sixteen_always_fails(self):
        assert ench.ceremonial_outcome(16, target=20) is CeremonialOutcome.FAILURE

    @pytest.mark.parametrize("rolled", [17, 18])
    def test_seventeen_and_eighteen_are_always_critical(self, rolled):
        assert (
            ench.ceremonial_outcome(rolled, target=25)
            is CeremonialOutcome.CRITICAL_FAILURE
        )

    def test_a_high_skill_caster_still_fails_on_sixteen(self):
        """The whole reason this cannot reuse the core engine: on B347 a 16
        against a target of 20 is an ordinary success."""
        assert ench.ceremonial_outcome(16, target=20) is CeremonialOutcome.FAILURE
        assert ench.ceremonial_outcome(15, target=20) is CeremonialOutcome.SUCCESS

    def test_the_core_engine_disagrees_which_is_the_point(self):
        from gurps_bot.mechanics.checks import Outcome, _determine_outcome

        assert _determine_outcome(16, 20) is Outcome.SUCCESS
        assert ench.ceremonial_outcome(16, 20) is CeremonialOutcome.FAILURE

    def test_a_bad_roll_is_still_bounded(self):
        with pytest.raises(ValueError):
            ench.ceremonial_outcome(19, target=15)


class TestWhatAFailureCosts:
    def test_quick_and_dirty_burns_the_energy_either_way(self):
        """"Succeed or fail, all the energy is spent when the GM rolls."""
        result = ench.resolve(CeremonialOutcome.FAILURE, Method.QUICK_AND_DIRTY)
        assert result.energy_spent

    def test_slow_and_sure_wastes_the_time_and_the_materials(self):
        result = ench.resolve(CeremonialOutcome.FAILURE, Method.SLOW_AND_SURE)
        assert not result.energy_spent
        assert result.materials_lost

    def test_a_critical_failure_destroys_the_item_on_either_method(self):
        for method in Method:
            result = ench.resolve(CeremonialOutcome.CRITICAL_FAILURE, method)
            assert result.item_destroyed
            assert result.materials_lost

    def test_an_ordinary_failure_never_destroys_the_item(self):
        for method in Method:
            assert not ench.resolve(CeremonialOutcome.FAILURE, method).item_destroyed

    def test_a_critical_success_adds_two_dice_of_power(self):
        result = ench.resolve(CeremonialOutcome.CRITICAL_SUCCESS, Method.SLOW_AND_SURE)
        assert result.power_bonus == ench.CRITICAL_SUCCESS_POWER_BONUS
        assert result.power_bonus.count == 2

    def test_a_natural_three_is_flagged_and_never_invented(self):
        """"the item might have some further enhancement (GM's discretion)" —
        so the bot says the GM has a call to make and stops there."""
        flagged = ench.resolve(
            CeremonialOutcome.CRITICAL_SUCCESS, Method.SLOW_AND_SURE, rolled_3d=3
        )
        plain = ench.resolve(
            CeremonialOutcome.CRITICAL_SUCCESS, Method.SLOW_AND_SURE, rolled_3d=4
        )
        assert flagged.may_have_further_enhancement
        assert not plain.may_have_further_enhancement


class TestTheTwoMethodsDisagreeOnEverything:
    @pytest.mark.parametrize(
        "energy,hours", [(1, 1), (100, 1), (101, 2), (250, 3), (1_000, 10)]
    )
    def test_quick_and_dirty_is_an_hour_per_hundred_rounded_up(self, energy, hours):
        assert ench.quick_and_dirty_hours(energy) == hours

    def test_slow_and_sure_is_a_mage_day_per_point(self):
        """The book's own arithmetic: 100 energy is one mage for 100 days or
        two for 50."""
        assert ench.slow_and_sure_days(100, 1) == 100
        assert ench.slow_and_sure_days(100, 2) == 50

    def test_the_ratio_between_them_is_enormous_and_that_is_the_trade(self):
        assert ench.quick_and_dirty_hours(1_000) == 10
        assert ench.slow_and_sure_days(1_000, 1) == 1_000

    def test_only_one_of_them_costs_fatigue(self):
        """"There is no FP or HP cost to the enchanters" on Slow and Sure —
        which is also why the HP-for-skill trade only exists on the other."""
        assert ench.costs_fatigue(Method.QUICK_AND_DIRTY)
        assert not ench.costs_fatigue(Method.SLOW_AND_SURE)

    def test_a_missed_day_costs_two(self):
        assert ench.make_up_days(1) == 2
        assert ench.make_up_days(3) == 6


class TestHpBuysEnergyAndCostsSkill:
    def test_each_hp_is_minus_one(self):
        assert ench.enchanting_modifier(hp_spent=4).total == -4

    def test_it_stacks_with_assistants_and_bystanders(self):
        assert (
            ench.enchanting_modifier(assistants=2, hp_spent=3, bystanders=True).total
            == -6
        )

    def test_an_assistants_hp_is_not_in_this_breakdown(self):
        """"their skill does not affect the item's power, as long as their
        effective skill is at least 15" — so folding an assistant's HP cost in
        here would quietly weaken every item made by a bleeding helper."""
        import inspect

        params = inspect.signature(ench.enchanting_modifier).parameters
        assert "assistant_hp" not in params
        assert set(params) == {"method", "assistants", "hp_spent", "bystanders"}


class TestThePenaltiesAreQuickAndDirtyOnly:
    """Settled against the printed page 2026-08-15: the -1 per assistant, the
    HP-spend -1, the bystander -1 and the derived cap are all printed INSIDE
    Quick and Dirty Enchantment, continuing its energy paragraphs ("A lone
    caster is limited to the energy provided by his FP, HP, and one
    Powerstone..."). Both worked sittings are Quick and Dirty. Slow and Sure
    (p. 18) restates its own assistant rules — present every day, a missed day
    costs two, loss of a mage ends the project — has "no FP or HP cost", and
    restates no skill penalty. The module's own header said this from the
    start; the code applied the penalties to both methods anyway."""

    def test_slow_and_sure_assistants_touch_no_roll(self):
        total = ench.enchanting_modifier(
            method=Method.SLOW_AND_SURE, assistants=3, bystanders=True
        ).total
        assert total == 0

    def test_quick_and_dirty_keeps_every_penalty(self):
        total = ench.enchanting_modifier(
            method=Method.QUICK_AND_DIRTY, assistants=3, bystanders=True
        ).total
        assert total == -4

    def test_quick_and_dirty_is_the_default_the_sittings_run_on(self):
        assert ench.enchanting_modifier(assistants=1).total == -1

    def test_slow_and_sure_cannot_spend_hp(self):
        """"There is no FP or HP cost to the enchanters – they invested the
        energy gradually as the spell progressed." Refused, not dropped."""
        with pytest.raises(ValueError, match="no FP or HP"):
            ench.enchanting_modifier(method=Method.SLOW_AND_SURE, hp_spent=2)

    def test_effective_skill_is_bare_under_slow_and_sure(self):
        bare = ench.effective_skill(
            enchant_skill=17, spell_skill=16, method=Method.SLOW_AND_SURE,
            assistants=3,
        )
        assert bare == 16
