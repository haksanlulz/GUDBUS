"""Low-Tech Companion 3 ch. 5 — making a mundane item.

Everything here came off LTC3 pp. 22-25, and the book is the authority in
this file.

⚑ The book's own worked example — the 9' ladder — is the regression class.
It is the only end-to-end figure in the chapter that the text computes itself,
so it checks the whole chain rather than any one constant.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics import crafting_mundane as mundane
from gurps_bot.mechanics.crafting_mundane import (
    ItemClass,
    LaborKind,
    MaterialMultiplier,
    Quality,
)


class TestTheBooksOwnLadder:
    """LTC3's worked example, reproduced end to end.

    A 9' ladder: $90, 22.5 lbs, 1" planks at $2.70/lb, made by a TL4 carpenter
    who earns $790 a month.
    """

    LIST_PRICE = 90
    WEIGHT = 22.5
    PER_LB = 2.70
    MONTHLY = 790

    def test_materials_are_sixty_seventy_five(self):
        assert mundane.materials_cost(self.WEIGHT, self.PER_LB) == pytest.approx(60.75)

    def test_labor_is_the_remainder(self):
        materials = mundane.materials_cost(self.WEIGHT, self.PER_LB)
        assert mundane.labor_cost(self.LIST_PRICE, materials) == pytest.approx(29.25)

    def test_the_hourly_rate_is_two_seventeen(self):
        rate = mundane.hourly_labor_rate(self.MONTHLY, LaborKind.ROUTINE)
        assert rate == pytest.approx(2.17, abs=0.005)

    def test_it_takes_thirteen_and_a_half_man_hours(self):
        materials = mundane.materials_cost(self.WEIGHT, self.PER_LB)
        labor = mundane.labor_cost(self.LIST_PRICE, materials)
        rate = mundane.hourly_labor_rate(self.MONTHLY, LaborKind.ROUTINE)
        assert mundane.active_hours(labor, rate) == pytest.approx(13.5, abs=0.05)

    def test_a_carpenter_and_five_assistants_take_just_over_two_hours(self):
        """"A carpenter and five assistants could make one from lumber in just
        over two hours" — six people, which is also the cap."""
        materials = mundane.materials_cost(self.WEIGHT, self.PER_LB)
        labor = mundane.labor_cost(self.LIST_PRICE, materials)
        rate = mundane.hourly_labor_rate(self.MONTHLY, LaborKind.ROUTINE)
        active = mundane.active_hours(labor, rate)
        elapsed = mundane.elapsed_hours(active, workers=6)
        assert 2.0 < elapsed < 2.5


class TestMaterialsComeFromWeightNotListPrice:
    """SPEC materials-come-from-weight-not-from-list-price.

    The tempting wrong answer, and the reason it survives review: a
    percentage of list price also produces a plausible number.
    """

    def test_it_is_weight_times_the_table(self):
        assert mundane.materials_cost(10, 5) == 50

    def test_list_price_is_not_an_argument_to_it(self):
        import inspect

        params = inspect.signature(mundane.materials_cost).parameters
        assert "list_price" not in params
        assert "price" not in params

    def test_two_items_of_one_price_can_differ_in_materials(self):
        """The structural consequence: if materials were a fraction of price,
        these would be equal. They are not."""
        light = mundane.materials_cost(2, 5)
        heavy = mundane.materials_cost(20, 5)
        assert light != heavy


class TestTheRawMaterialMultipliers:
    @pytest.mark.parametrize(
        "multiplier,expected",
        [
            (MaterialMultiplier.NONE, 100),
            (MaterialMultiplier.LONGBOW_OR_CROSSBOW, 200),
            (MaterialMultiplier.COMPOSITE_BOW, 300),
            (MaterialMultiplier.SWORD_OR_PLATE, 200),
        ],
    )
    def test_each_printed_multiplier(self, multiplier, expected):
        assert mundane.materials_cost(10, 10, multiplier) == expected

    def test_swords_and_bows_share_a_number_and_not_a_reason(self):
        """Both x2, for unrelated causes — bows need better wood, swords need
        more charcoal. Collapsing them into one constant would lose the fact
        that composite bows then go to x3 and swords do not."""
        assert (
            MaterialMultiplier.SWORD_OR_PLATE.value
            == MaterialMultiplier.LONGBOW_OR_CROSSBOW.value
        )
        assert MaterialMultiplier.COMPOSITE_BOW.value == 3


class TestQualityIsAReturnValue:
    """SPEC quality-is-a-return-value-never-a-parameter."""

    def test_you_cannot_ask_for_a_quality(self):
        import inspect

        params = inspect.signature(mundane.craft_quality).parameters
        assert "quality" not in params

    def test_no_entry_point_in_the_module_takes_one(self):
        """Functions only. ``CraftResult`` carries a ``quality`` field and must
        — it is the return value, which is the entire point; the rule is that
        nothing ASKS for one."""
        import inspect

        for name, fn in vars(mundane).items():
            if name.startswith("_") or not inspect.isfunction(fn):
                continue
            params = inspect.signature(fn).parameters
            assert "quality" not in params, name

    def test_the_result_type_carries_it_because_that_is_the_point(self):
        import inspect

        assert "quality" in inspect.signature(mundane.CraftResult).parameters

    def test_the_margin_decides_it(self):
        assert mundane.craft_quality(0).quality is Quality.BASIC
        assert mundane.craft_quality(20).quality is Quality.FINE


class TestTheCraftingTableReadFromTheProse:
    """⚠️ The extracted table is shifted up by one row.

    As extracted it appears to say a failure by 1-3 yields GOOD armor, which
    would make a botched sword better than a competent one. The prose states
    every band in words; this alignment matches it in all three columns at
    once, which the shifted one cannot do.
    """

    @pytest.mark.parametrize(
        "margin,general,arms,tool",
        [
            (-4, Quality.JUNK, Quality.JUNK, Quality.JUNK),
            (-10, Quality.JUNK, Quality.JUNK, Quality.JUNK),
            (-1, Quality.CHEAP, Quality.CHEAP, Quality.POOR),
            (-3, Quality.CHEAP, Quality.CHEAP, Quality.POOR),
            (0, Quality.BASIC, Quality.GOOD, Quality.BASIC),
            (11, Quality.BASIC, Quality.GOOD, Quality.BASIC),
            (12, Quality.GOOD, Quality.FINE, Quality.GOOD),
            (17, Quality.GOOD, Quality.FINE, Quality.GOOD),
            (18, Quality.FINE, Quality.VERY_FINE, Quality.FINE),
            (30, Quality.FINE, Quality.VERY_FINE, Quality.FINE),
        ],
    )
    def test_every_band_of_every_ladder(self, margin, general, arms, tool):
        assert mundane.craft_quality(margin, ItemClass.GENERAL).quality is general
        assert mundane.craft_quality(margin, ItemClass.ARMS_OR_ARMOR).quality is arms
        assert mundane.craft_quality(margin, ItemClass.TOOL).quality is tool

    def test_quality_never_decreases_as_the_margin_rises(self):
        """A general sanity property, and NOT the guard against the scramble.

        Checked by mutation: feeding the shifted reading in leaves this test
        green, because promoting the flawed band to Good is still monotonic.
        The parametrized band test above is what actually reddens, and this
        docstring said otherwise until it was probed.
        """
        order = [
            Quality.JUNK,
            Quality.CHEAP,
            Quality.GOOD,
            Quality.FINE,
            Quality.VERY_FINE,
        ]
        seen = [
            order.index(mundane.craft_quality(m, ItemClass.ARMS_OR_ARMOR).quality)
            for m in range(-10, 25)
        ]
        assert seen == sorted(seen)

    def test_a_failure_still_leaves_you_holding_something(self):
        """The domain's whole shape: you cannot fail into nothing."""
        flawed = mundane.craft_quality(-2)
        assert not flawed.is_junk
        assert flawed.sells_for_at_most_half

    def test_junk_costs_the_materials(self):
        assert mundane.craft_quality(-4).materials_lost

    def test_a_flawed_piece_does_not(self):
        assert not mundane.craft_quality(-3).materials_lost

    def test_there_is_no_succeeded_flag(self):
        """A boolean would have to answer a question this domain does not ask."""
        assert not hasattr(mundane.craft_quality(5), "succeeded")

    def test_critical_success_is_not_a_band(self):
        """"Critical success doesn't impact quality beyond margin of success" —
        so this family's third check variant is one that IGNORES criticals,
        where alchemy suppresses them and ceremonial magic shifts thresholds.

        Asserted behaviourally rather than by grepping the source: the first
        draft of this test searched for the word "critical" and failed on its
        own docstring, which is a test of the comments rather than the code.
        """
        import inspect

        params = inspect.signature(mundane.craft_quality).parameters
        assert "critical" not in params
        assert "outcome" not in params
        # Quality is a pure function of margin and class: same margin in, same
        # quality out, with no way for a caller to say how the roll was made.
        assert set(params) == {"margin", "item_class"}


class TestSuperiorMaterialsAddToMarginNotSkill:
    def test_fine_materials_cap_at_five(self):
        assert mundane.effective_margin(3, fine_materials=5) == 8
        with pytest.raises(ValueError):
            mundane.effective_margin(3, fine_materials=6)

    def test_a_failed_roll_gets_nothing(self):
        """"if the roll succeeds" — superior materials cannot rescue a failure,
        which is exactly what adding them to skill would have let them do."""
        assert mundane.effective_margin(-2, fine_materials=5) == -2

    def test_it_can_promote_a_basic_piece_to_good(self):
        plain = mundane.craft_quality(11, ItemClass.GENERAL).quality
        helped = mundane.craft_quality(
            mundane.effective_margin(11, fine_materials=5), ItemClass.GENERAL
        ).quality
        assert plain is Quality.BASIC
        assert helped is Quality.GOOD


class TestCrucibleSteel:
    def test_the_ingot_is_worth_five_margin(self):
        assert mundane.CRUCIBLE_STEEL_MARGIN == 5
        assert mundane.effective_margin(4, crucible_steel=True) == 9

    def test_it_stacks_with_fine_materials(self):
        assert mundane.effective_margin(0, fine_materials=5, crucible_steel=True) == 10

    @pytest.mark.parametrize(
        "pounds,penalty", [(2, 0), (3, -1), (5, -1), (6, -2), (9, -3)]
    )
    def test_minus_one_per_FULL_three_pounds(self, pounds, penalty):
        assert mundane.crucible_steel_penalty(pounds) == penalty

    def test_twenty_dollars_a_pound(self):
        assert mundane.crucible_steel_materials(4) == 80

    def test_five_man_days_and_no_haste_bonus(self):
        assert mundane.CRUCIBLE_STEEL_MAN_DAYS == 5


class TestWhoRolls:
    def test_the_highest_skill_present(self):
        assert mundane.rolling_skill([10, 18, 12]) == 18

    def test_which_is_the_opposite_of_alchemy(self):
        """Four domains, four readings of "assistant". This one and alchemy's
        are direct contradictions, which is why no shared helper serves both."""
        from gurps_bot.mechanics import crafting_alchemy as alchemy

        workers = [10, 18]
        assert mundane.rolling_skill(workers) == 18
        assert alchemy.final_roller_skill(workers) == 10

    def test_someone_has_to_make_it(self):
        with pytest.raises(ValueError):
            mundane.rolling_skill([])


class TestPlateArmourIsItsOwnCase:
    @pytest.mark.parametrize(
        "skill,effective", [(14, 14), (15, 15), (13, 12), (12, 10), (11, 8)]
    )
    def test_minus_one_per_level_below_fourteen(self, skill, effective):
        """The book prints two of these: 13 works as 12, and 12 as 10. The
        penalty compounds, so it is not a flat -1."""
        assert mundane.plate_armour_effective_skill(skill) == effective


class TestWorkersOnlyDivideTheClock:
    def test_six_is_the_cap(self):
        assert mundane.elapsed_hours(60, workers=6) == 10

    def test_a_seventh_pair_of_hands_changes_nothing(self):
        """A rule, not a sanity check — dividing by 7 would invent a speed-up
        the book refuses."""
        assert mundane.elapsed_hours(60, workers=7) == mundane.elapsed_hours(
            60, workers=6
        )
        assert mundane.elapsed_hours(60, workers=100) == 10

    def test_they_touch_no_roll_at_all(self):
        """The fifth reading of "assistant" in this family, and the only one
        that is purely a divisor."""
        import inspect

        params = inspect.signature(mundane.elapsed_hours).parameters
        assert set(params) == {"active", "workers"}


class TestLaborKinds:
    def test_routine_is_fifty_five_percent(self):
        assert mundane.hourly_labor_rate(200, LaborKind.ROUTINE) == pytest.approx(0.55)

    def test_artistic_is_seventy_five(self):
        assert mundane.hourly_labor_rate(200, LaborKind.ARTISTIC) == pytest.approx(0.75)

    def test_arms_manufacture_is_the_artistic_rate(self):
        """Named in the book alongside decorative work, which is worth pinning
        because "artistic" does not obviously include making swords."""
        assert mundane.hourly_labor_rate(
            1_000, LaborKind.ARTISTIC
        ) > mundane.hourly_labor_rate(1_000, LaborKind.ROUTINE)

    def test_daily_is_the_month_over_twenty_five(self):
        assert mundane.daily_labor_rate(2_500, LaborKind.ROUTINE) == pytest.approx(55)
