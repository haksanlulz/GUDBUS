"""B345 Equipment Modifiers.

Found while re-verifying a repair reference scenario: its workspace ladder
(improvised -5 / basic 0 / shop +1 / factory +2) is four fifths of B345, and
B484's repair rules cite B345 explicitly — so the repair module was passing an
opaque GM integer where the book has a printed table. This is that table.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics import equipment_quality as eq
from gurps_bot.mechanics.equipment_quality import EquipmentQuality


class TestTheLadder:
    @pytest.mark.parametrize(
        "quality,expected",
        [
            (EquipmentQuality.NONE, -10),
            (EquipmentQuality.IMPROVISED, -5),
            (EquipmentQuality.BASIC, 0),
            (EquipmentQuality.GOOD, 1),
            (EquipmentQuality.FINE, 2),
        ],
    )
    def test_technological_skills(self, quality, expected):
        assert eq.modifier(quality, technological=True) == expected

    @pytest.mark.parametrize(
        "quality,expected",
        [
            (EquipmentQuality.NONE, -5),
            (EquipmentQuality.IMPROVISED, -2),
            (EquipmentQuality.BASIC, 0),
            (EquipmentQuality.GOOD, 1),
            (EquipmentQuality.FINE, 2),
        ],
    )
    def test_non_technological_skills(self, quality, expected):
        assert eq.modifier(quality, technological=False) == expected

    def test_the_split_is_five_points_on_the_skills_a_crafting_bot_serves(self):
        """The cell most likely to be collapsed, asserted as a difference.

        Armoury and Mechanic are technological; a bot that ignores the split
        under-penalises improvised tools by 3 and no equipment by 5.
        """
        for quality in (EquipmentQuality.NONE, EquipmentQuality.IMPROVISED):
            tech = eq.modifier(quality, technological=True)
            other = eq.modifier(quality, technological=False)
            assert tech < other
        assert eq.modifier(EquipmentQuality.NONE, technological=True) == -10
        assert eq.modifier(EquipmentQuality.NONE, technological=False) == -5

    def test_the_middle_rungs_do_not_care_what_kind_of_skill_it_is(self):
        for quality in (EquipmentQuality.BASIC, EquipmentQuality.GOOD, EquipmentQuality.FINE):
            assert eq.modifier(quality, technological=True) == eq.modifier(
                quality, technological=False
            )

    def test_only_the_bottom_two_rungs_are_kind_sensitive(self):
        assert eq.is_worse_than_basic(EquipmentQuality.NONE)
        assert eq.is_worse_than_basic(EquipmentQuality.IMPROVISED)
        assert not eq.is_worse_than_basic(EquipmentQuality.BASIC)
        assert not eq.is_worse_than_basic(EquipmentQuality.BEST)


class TestBestEquipment:
    """"+TL/2, round down (minimum +2)" — the only rung that is computed."""

    @pytest.mark.parametrize(
        "tl,expected",
        [(0, 2), (3, 2), (4, 2), (5, 2), (6, 3), (9, 4), (10, 5), (12, 6)],
    )
    def test_it_is_half_the_tech_level_with_a_floor(self, tl, expected):
        assert eq.modifier(EquipmentQuality.BEST, tech_level=tl) == expected

    def test_the_floor_binds_below_tl5(self):
        """TL4/2 = 2 exactly, so the floor only actually bites below that — and
        it is what keeps a TL1 smith's best tools from being worth +0."""
        assert eq.modifier(EquipmentQuality.BEST, tech_level=1) == 2

    def test_it_beats_fine_only_from_tl6(self):
        fine = eq.modifier(EquipmentQuality.FINE)
        assert eq.modifier(EquipmentQuality.BEST, tech_level=5) == fine
        assert eq.modifier(EquipmentQuality.BEST, tech_level=6) > fine

    def test_it_refuses_to_guess_a_tech_level(self):
        """A default here would hand back a confidently wrong +2."""
        with pytest.raises(ValueError):
            eq.modifier(EquipmentQuality.BEST)

    def test_a_negative_tech_level_is_refused(self):
        with pytest.raises(ValueError):
            eq.modifier(EquipmentQuality.BEST, tech_level=-1)


class TestPricing:
    def test_good_and_fine_are_priced(self):
        assert eq.price_multiplier(EquipmentQuality.GOOD) == 5
        assert eq.price_multiplier(EquipmentQuality.FINE) == 20

    def test_the_rest_are_not_priced_and_say_so(self):
        """BEST is "not usually for sale"; the two below basic are what you have
        when you have nothing. None is the honest answer, not 0."""
        for quality in (
            EquipmentQuality.NONE,
            EquipmentQuality.IMPROVISED,
            EquipmentQuality.BASIC,
            EquipmentQuality.BEST,
        ):
            assert eq.price_multiplier(quality) is None
