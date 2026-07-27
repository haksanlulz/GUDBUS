"""Fatigue (fat) as a wounding type (B379). Operator-ruled into scope 2026-07-27.

B379 names every type in one sentence: "Small piercing (pi-): x0.5. Burning
(burn), corrosion (cor), crushing (cr), fatigue (fat), piercing (pi), and toxic
(tox): x1. Cutting (cut) and large piercing (pi+): x1.5. Impaling (imp) and huge
piercing (pi++): x2."

`fat` was the only listed type the module lacked, so a fatigue attack silently
fell through to the x1.0 default — right answer, wrong reason, and invisible in
the damage-type picker.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics.damage import (
    DAMAGE_TYPE_DISPLAY,
    FATIGUE_DAMAGE_TYPE,
    WOUNDING_MULTIPLIERS,
    parse_gcs_damage,
    wound_from_penetrating,
)


class TestFatigueIsAKnownType:
    def test_present_with_multiplier_one(self):
        assert WOUNDING_MULTIPLIERS["fat"] == 1.0

    def test_has_a_display_name(self):
        assert "fat" in DAMAGE_TYPE_DISPLAY

    def test_display_name_says_it_costs_fp(self):
        """A GM picking it from the list must see it doesn't hit HP."""
        assert "FP" in DAMAGE_TYPE_DISPLAY["fat"]

    def test_constant_matches_the_key(self):
        assert FATIGUE_DAMAGE_TYPE in WOUNDING_MULTIPLIERS


class TestFatigueWounding:
    @pytest.mark.parametrize("raw,expected", [(1, 1), (5, 5), (12, 12)])
    def test_unmodified_at_one_to_one(self, raw, expected):
        assert wound_from_penetrating(raw, "fat")[1] == expected

    def test_no_penetration_no_loss(self):
        assert wound_from_penetrating(0, "fat")[1] == 0

    def test_parses_from_a_gcs_damage_string(self):
        assert parse_gcs_damage("2d fat") == ("2d", "fat")


class TestFullTableMatchesTheBook:
    """Since B379 lists them all in one sentence, pin the whole table."""

    @pytest.mark.parametrize(
        "dtype,expected",
        [
            ("pi-", 0.5),
            ("burn", 1.0), ("cor", 1.0), ("cr", 1.0),
            ("fat", 1.0), ("pi", 1.0), ("tox", 1.0),
            ("cut", 1.5), ("pi+", 1.5),
            ("imp", 2.0), ("pi++", 2.0),
        ],
    )
    def test_every_printed_type(self, dtype, expected):
        assert WOUNDING_MULTIPLIERS[dtype] == expected

    def test_no_unlisted_types(self):
        assert set(WOUNDING_MULTIPLIERS) == {
            "pi-", "burn", "cor", "cr", "fat", "pi", "tox", "cut", "pi+", "imp", "pi++",
        }
