"""Trait-reading helper (mechanics/traits.py).

Every number here is quoted from the printed Basic Set in the test that pins it.
The parsing tests exist because GCS names carry parentheticals and trailing
levels, and because several trait pairs differ only by a prefix — a substring
match returns the wrong sign rather than failing loudly.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics.traits import (
    InjuryTolerance,
    fright_will_modifier,
    has_reduced_parry,
    has_trait,
    injury_tolerance,
    is_unfazeable,
    pain_threshold_knockdown_modifier,
    parse_trait,
    trait_level,
)


class TestParsing:
    def test_plain_name(self):
        p = parse_trait("Unfazeable")
        assert p.base == "unfazeable" and p.parenthetical is None and p.level is None

    def test_parenthetical_is_split_out(self):
        p = parse_trait("Injury Tolerance (Unliving)")
        assert p.base == "injury tolerance"
        assert p.parenthetical == "Unliving"

    def test_trailing_level_is_split_out(self):
        p = parse_trait("Fearlessness 3")
        assert p.base == "fearlessness"
        assert p.level == 3

    def test_both_at_once(self):
        p = parse_trait("Damage Resistance (Tough Skin) 2")
        assert p.base == "damage resistance"
        assert p.parenthetical == "Tough Skin"
        assert p.level == 2

    def test_matching_is_case_insensitive_and_whitespace_tolerant(self):
        assert has_trait(["  high pain THRESHOLD "], "High Pain Threshold")


class TestMatchingIsNotSubstring:
    """The failure mode this module exists to prevent."""

    def test_fearfulness_is_not_fearlessness(self):
        assert has_trait(["Fearfulness 2"], "Fearlessness") is False
        assert has_trait(["Fearlessness 2"], "Fearfulness") is False

    def test_low_pain_threshold_is_not_high(self):
        assert has_trait(["Low Pain Threshold"], "High Pain Threshold") is False

    def test_opposite_traits_produce_opposite_signs(self):
        assert fright_will_modifier(["Fearlessness 3"]) == 3
        assert fright_will_modifier(["Fearfulness 3"]) == -3


class TestPainThresholdKnockdown:
    """B420: "+3 for High Pain Threshold, or -4 for Low Pain Threshold." """

    def test_high(self):
        assert pain_threshold_knockdown_modifier(["High Pain Threshold"]) == 3

    def test_low(self):
        assert pain_threshold_knockdown_modifier(["Low Pain Threshold"]) == -4

    def test_neither(self):
        assert pain_threshold_knockdown_modifier(["Combat Reflexes"]) == 0

    def test_both_resolves_to_the_penalty(self):
        """Mutually exclusive by RAW; if a sheet carries both, never hand out a
        bonus the rules can't justify."""
        assert pain_threshold_knockdown_modifier(
            ["High Pain Threshold", "Low Pain Threshold"]
        ) == -4


class TestFrightTraits:
    """Fearlessness (B55): "Add your level of Fearlessness to your Will whenever
    you make a Fright Check." Fearfulness: "Subtract your Fearfulness from your
    Will." Unfazeable (B95): "You are exempt from Fright Checks." """

    def test_unfazeable_detected(self):
        assert is_unfazeable(["Unfazeable"]) is True
        assert is_unfazeable(["Fearlessness 2"]) is False

    @pytest.mark.parametrize("level", [1, 2, 5])
    def test_fearlessness_adds_its_level(self, level):
        assert fright_will_modifier([f"Fearlessness {level}"]) == level

    @pytest.mark.parametrize("level", [1, 2, 5])
    def test_fearfulness_subtracts_its_level(self, level):
        assert fright_will_modifier([f"Fearfulness {level}"]) == -level

    def test_level_column_wins_over_the_name(self):
        names = ["Fearlessness"]
        assert fright_will_modifier(names, levels={"Fearlessness": 4}) == 4

    def test_unlevelled_trait_counts_as_one(self):
        assert trait_level(["Fearlessness"], "Fearlessness") == 1

    def test_absent_trait_is_zero(self):
        assert fright_will_modifier(["Combat Reflexes"]) == 0


class TestInjuryTolerance:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Injury Tolerance (Unliving)", InjuryTolerance.UNLIVING),
            ("Injury Tolerance (Homogenous)", InjuryTolerance.HOMOGENOUS),
            ("Injury Tolerance (Diffuse)", InjuryTolerance.DIFFUSE),
        ],
    )
    def test_recognised_variants(self, name, expected):
        assert injury_tolerance([name]) is expected

    def test_case_insensitive(self):
        assert injury_tolerance(["injury tolerance (UNLIVING)"]) is InjuryTolerance.UNLIVING

    def test_other_variants_return_none_rather_than_guessing(self):
        """Injury Tolerance has parentheticals that don't change wounding."""
        for other in ("No Blood", "No Neck", "No Brain", "Damage Reduction"):
            assert injury_tolerance([f"Injury Tolerance ({other})"]) is None

    def test_absent_returns_none(self):
        assert injury_tolerance(["Combat Reflexes", "Fearlessness 2"]) is None

    def test_bare_injury_tolerance_returns_none(self):
        assert injury_tolerance(["Injury Tolerance"]) is None

    def test_found_among_many(self):
        names = ["Combat Reflexes", "Injury Tolerance (Diffuse)", "Fearlessness 1"]
        assert injury_tolerance(names) is InjuryTolerance.DIFFUSE


class TestReducedParry:
    """B376: the -2 step comes from Trained By A Master or Weapon Master."""

    @pytest.mark.parametrize("name", ["Trained By A Master", "Weapon Master"])
    def test_granting_traits(self, name):
        assert has_reduced_parry([name]) is True

    def test_weapon_master_with_a_specialty(self):
        assert has_reduced_parry(["Weapon Master (Broadsword)"]) is True

    def test_absent(self):
        assert has_reduced_parry(["Combat Reflexes"]) is False
