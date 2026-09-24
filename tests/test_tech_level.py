"""B168 — the two tech-level rules, and the fact that they are two.

Everything here came off the Basic Set: Characters 10th printing, the
"IQ-Based Technological Skills" and "Other Technological Skills" paragraphs and
the table printed between them.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics import tech_level
from gurps_bot.mechanics.tech_level import SkillClass


class TestThePrintedLadder:
    """Every row of the table, as printed, for an IQ-based skill."""

    @pytest.mark.parametrize(
        "steps,expected",
        [
            (3, -15),
            (2, -10),
            (1, -5),
            (0, 0),
            (-1, -1),
            (-2, -3),
            (-3, -5),
            (-4, -7),
        ],
    )
    def test_each_row(self, steps, expected):
        gap = tech_level.tl_gap(skill_tl=9, equipment_tl=9 + steps)
        assert gap.penalty == expected
        assert not gap.impossible

    def test_four_tls_up_is_impossible_not_expensive(self):
        gap = tech_level.tl_gap(skill_tl=9, equipment_tl=13)
        assert gap.impossible

    def test_and_it_stays_impossible_however_far_up(self):
        assert tech_level.tl_gap(skill_tl=3, equipment_tl=12).impossible

    @pytest.mark.parametrize(
        "steps,expected", [(-5, -9), (-6, -11), (-7, -13)]
    )
    def test_below_the_table_it_is_two_per_extra_step(self, steps, expected):
        """"Per extra -1 to TL: -2" — picked up from -7, not restarted."""
        gap = tech_level.tl_gap(skill_tl=9, equipment_tl=9 + steps)
        assert gap.penalty == expected

    def test_the_ladder_is_not_symmetric(self):
        """The whole reason it is a table. One step up is five times one step
        down, and a generated ladder cannot be right on both sides."""
        up = tech_level.tl_gap(skill_tl=9, equipment_tl=10).penalty
        down = tech_level.tl_gap(skill_tl=9, equipment_tl=8).penalty
        assert up == -5
        assert down == -1

    def test_going_up_is_never_cheaper_than_going_down(self):
        for step in range(1, 4):
            up = tech_level.tl_gap(skill_tl=10, equipment_tl=10 + step).penalty
            down = tech_level.tl_gap(skill_tl=10, equipment_tl=10 - step).penalty
            assert up < down


class TestTheOtherRuleIsADifferentRule:
    """The half that would silently replace the other."""

    @pytest.mark.parametrize("steps,expected", [(1, -1), (2, -2), (5, -5)])
    def test_flat_one_per_tl(self, steps, expected):
        gap = tech_level.tl_gap(
            skill_tl=5, equipment_tl=5 + steps, skill_class=SkillClass.OTHER
        )
        assert gap.penalty == expected

    def test_direction_is_irrelevant_here_and_the_book_says_so(self):
        """A TL7 policeman is at -2 with a TL5 revolver exactly as a TL5
        gunman is at -2 with a TL7 one."""
        up = tech_level.tl_gap(
            skill_tl=5, equipment_tl=7, skill_class=SkillClass.OTHER
        ).penalty
        down = tech_level.tl_gap(
            skill_tl=7, equipment_tl=5, skill_class=SkillClass.OTHER
        ).penalty
        assert up == down == -2

    def test_nothing_is_impossible_under_the_flat_rule(self):
        assert not tech_level.tl_gap(
            skill_tl=3, equipment_tl=12, skill_class=SkillClass.OTHER
        ).impossible

    def test_the_two_rules_agree_at_no_gap_and_at_one_tl_down_only(self):
        """Written expecting agreement at zero alone; the ladder's first step
        DOWN is also -1, so they match there too.

        That is the worse fact, not a smaller one: the two common cases where
        picking the wrong rule costs nothing are a perfect match and one TL
        obsolete, so a caller can be wrong for a long time before any table
        notices. One step UP is where it bites, by four points.
        """
        agreements = []
        for equipment_tl in range(4, 13):
            iq = tech_level.tl_gap(skill_tl=9, equipment_tl=equipment_tl)
            other = tech_level.tl_gap(
                skill_tl=9, equipment_tl=equipment_tl, skill_class=SkillClass.OTHER
            )
            if not iq.impossible and iq.penalty == other.penalty:
                agreements.append(equipment_tl - 9)
        assert agreements == [-1, 0]

    def test_and_one_step_up_is_where_the_mix_up_costs_four(self):
        iq = tech_level.tl_gap(skill_tl=9, equipment_tl=10).penalty
        other = tech_level.tl_gap(
            skill_tl=9, equipment_tl=10, skill_class=SkillClass.OTHER
        ).penalty
        assert iq - other == -4


class TestUnfamiliarityIsASeparateModifier:
    def test_it_is_minus_two(self):
        assert tech_level.UNFAMILIAR_PENALTY == -2

    def test_it_is_not_folded_into_the_gap(self):
        """B169: equipment from another TL "gives both TL and familiarity
        modifiers". Folding one into the other would make the practisable half
        unpractisable."""
        gap = tech_level.tl_gap(skill_tl=9, equipment_tl=10)
        assert gap.penalty == -5


class TestGuards:
    @pytest.mark.parametrize(
        "kwargs", [{"skill_tl": -1, "equipment_tl": 9}, {"skill_tl": 9, "equipment_tl": -1}]
    )
    def test_a_negative_tl_is_refused(self, kwargs):
        with pytest.raises(ValueError):
            tech_level.tl_gap(**kwargs)


class TestItAgreesWithInventionWithoutReadingIt:
    """`crafting.TL_GAP_PENALTY_EACH` is -5 per TL above, from B473-474.

    The two are separately printed rules that happen to coincide on the
    ascending side, so neither imports the other — the per-domain scan exists
    to stop exactly that — but the coincidence is worth pinning. If a future
    edit moves one, this test says so instead of leaving two silently
    different answers to the same question.
    """

    @pytest.mark.parametrize("steps", [1, 2, 3])
    def test_the_ascending_side_matches_inventions_per_step(self, steps):
        from gurps_bot.mechanics import crafting

        assert (
            tech_level.tl_gap(skill_tl=8, equipment_tl=8 + steps).penalty
            == crafting.TL_GAP_PENALTY_EACH * steps
        )

    def test_but_the_descending_side_does_not(self):
        """Invention refuses a negative gap outright; B168 prices it. The two
        rules are not the same rule and this is where that shows."""
        from gurps_bot.mechanics import crafting

        assert (
            tech_level.tl_gap(skill_tl=8, equipment_tl=7).penalty
            != crafting.TL_GAP_PENALTY_EACH
        )
