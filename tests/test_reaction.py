"""Tests for the GURPS reaction roll calculator (B560)."""

from unittest.mock import patch

import pytest
from gurps_bot.mechanics.dice import DiceSpec, RollResult
from gurps_bot.mechanics.reaction import (
    REACTION_BANDS,
    ReactionBand,
    ReactionResult,
    reaction_band,
    roll_reaction,
)


def _forced_roll(total: int) -> RollResult:
    """Build a RollResult whose .total is exactly `total` (dice irrelevant here)."""
    spec = DiceSpec(count=3, sides=6, modifier=0)
    return RollResult(spec=spec, dice=(total, 0, 0), total=total)


class TestReactionBand:
    """Pure lookup — no RNG. Open-ended at both ends, contiguous 3-wide buckets."""

    def test_zero_is_disastrous(self):
        # Upper edge of the open Disastrous band ("0 or less").
        assert reaction_band(0).name == "Disastrous"

    def test_negative_seven_is_disastrous(self):
        # Open-ended below 0 must not raise or clamp.
        assert reaction_band(-7).name == "Disastrous"

    def test_three_is_very_bad(self):
        # Upper boundary of Very Bad (1 to 3).
        assert reaction_band(3).name == "Very Bad"

    def test_four_is_bad(self):
        # Lower boundary of Bad (4 to 6) — off-by-one guard vs Very Bad.
        assert reaction_band(4).name == "Bad"

    def test_ten_is_neutral(self):
        # Lower edge of Neutral (10 to 12); 9->Poor must not bleed in.
        assert reaction_band(10).name == "Neutral"

    def test_twelve_is_neutral(self):
        # Upper edge of Neutral; 13->Good must not bleed in.
        assert reaction_band(12).name == "Neutral"

    def test_fifteen_is_good(self):
        # Upper boundary of Good (13 to 15).
        assert reaction_band(15).name == "Good"

    def test_eighteen_is_very_good(self):
        # Upper boundary of Very Good (16 to 18); 19 flips to Excellent.
        assert reaction_band(18).name == "Very Good"

    def test_nineteen_is_excellent(self):
        # Lower edge of the open Excellent band ("19 or better").
        assert reaction_band(19).name == "Excellent"

    def test_ninetynine_is_excellent(self):
        # Open-ended above 19 must not raise or clamp.
        assert reaction_band(99).name == "Excellent"

    def test_boundary_zero_one(self):
        assert reaction_band(0).name == "Disastrous"
        assert reaction_band(1).name == "Very Bad"

    def test_boundary_three_four(self):
        assert reaction_band(3).name == "Very Bad"
        assert reaction_band(4).name == "Bad"

    def test_boundary_six_seven(self):
        assert reaction_band(6).name == "Bad"
        assert reaction_band(7).name == "Poor"

    def test_boundary_nine_ten(self):
        assert reaction_band(9).name == "Poor"
        assert reaction_band(10).name == "Neutral"

    def test_boundary_twelve_thirteen(self):
        assert reaction_band(12).name == "Neutral"
        assert reaction_band(13).name == "Good"

    def test_boundary_fifteen_sixteen(self):
        assert reaction_band(15).name == "Good"
        assert reaction_band(16).name == "Very Good"

    def test_boundary_eighteen_nineteen(self):
        assert reaction_band(18).name == "Very Good"
        assert reaction_band(19).name == "Excellent"

    def test_every_value_three_to_eighteen(self):
        expected = {
            **{n: "Very Bad" for n in (1, 2, 3)},
            **{n: "Bad" for n in (4, 5, 6)},
            **{n: "Poor" for n in (7, 8, 9)},
            **{n: "Neutral" for n in (10, 11, 12)},
            **{n: "Good" for n in (13, 14, 15)},
            **{n: "Very Good" for n in (16, 17, 18)},
        }
        for total, name in expected.items():
            assert reaction_band(total).name == name, f"total={total}"

    def test_open_lower_sweep(self):
        for total in (0, -1, -5, -50, -1000):
            assert reaction_band(total).name == "Disastrous", f"total={total}"

    def test_open_upper_sweep(self):
        for total in (19, 20, 50, 1000):
            assert reaction_band(total).name == "Excellent", f"total={total}"

    def test_returns_reaction_band_instance(self):
        assert isinstance(reaction_band(11), ReactionBand)

    def test_ranks_are_monotonic_with_total(self):
        prev = reaction_band(-20).rank
        for total in range(-20, 40):
            cur = reaction_band(total).rank
            assert cur >= prev, f"rank dropped at total={total}"
            prev = cur

    def test_rank_values(self):
        assert reaction_band(-5).rank == -3  # Disastrous
        assert reaction_band(2).rank == -2   # Very Bad
        assert reaction_band(5).rank == -1   # Bad
        assert reaction_band(8).rank == 0    # Poor
        assert reaction_band(11).rank == 1   # Neutral
        assert reaction_band(14).rank == 2   # Good
        assert reaction_band(17).rank == 3   # Very Good
        assert reaction_band(25).rank == 4   # Excellent

    def test_neutral_is_rank_one(self):
        # Neutral is the unmodified-average outcome (3d6 averages 10.5).
        assert reaction_band(11).name == "Neutral"
        assert reaction_band(11).rank == 1

    def test_band_bounds_contain_total(self):
        for total in range(-30, 40):
            band = reaction_band(total)
            assert band.lower <= total <= band.upper, f"total={total} not in band"

    def test_band_is_frozen(self):
        band = reaction_band(11)
        with pytest.raises((AttributeError, TypeError)):
            band.name = "Hacked"  # type: ignore[misc]


class TestReactionBandsTable:
    """The module-constant ordered table is the single source of truth."""

    def test_table_is_ordered_by_rank(self):
        ranks = [b.rank for b in REACTION_BANDS]
        assert ranks == sorted(ranks)

    def test_table_is_contiguous_and_gapless(self):
        for prev, nxt in zip(REACTION_BANDS, REACTION_BANDS[1:]):
            assert nxt.lower == prev.upper + 1, f"gap between {prev.name} and {nxt.name}"

    def test_table_covers_eight_bands(self):
        assert len(REACTION_BANDS) == 8
        names = [b.name for b in REACTION_BANDS]
        assert names == [
            "Disastrous",
            "Very Bad",
            "Bad",
            "Poor",
            "Neutral",
            "Good",
            "Very Good",
            "Excellent",
        ]


class TestRollReaction:
    """roll_reaction is the only stochastic surface."""

    def test_zero_modifier_consistency(self):
        result = roll_reaction(0)
        assert isinstance(result, ReactionResult)
        assert 3 <= result.roll.total <= 18
        assert result.total == result.roll.total
        assert result.modifier == 0
        assert result.band == reaction_band(result.roll.total)

    def test_default_modifier_is_zero(self):
        # /roll-style callers omit the modifier.
        result = roll_reaction()
        assert result.modifier == 0
        assert result.total == result.roll.total

    def test_modifier_added_before_band_lookup_positive(self):
        # 3d6 forced to 8, +5 -> 13 -> Good.
        with patch(
            "gurps_bot.mechanics.reaction.roll_3d6",
            return_value=_forced_roll(8),
        ):
            result = roll_reaction(5)
        assert result.roll.total == 8
        assert result.modifier == 5
        assert result.total == 13
        assert result.band.name == "Good"

    def test_modifier_drives_into_open_lower_band(self):
        # 3d6 forced to 7, -10 -> -3 -> Disastrous.
        with patch(
            "gurps_bot.mechanics.reaction.roll_3d6",
            return_value=_forced_roll(7),
        ):
            result = roll_reaction(-10)
        assert result.roll.total == 7
        assert result.modifier == -10
        assert result.total == -3
        assert result.band.name == "Disastrous"

    def test_large_positive_modifier_into_open_upper_band(self):
        # 3d6 forced to 7, +12 -> 19 -> Excellent.
        with patch(
            "gurps_bot.mechanics.reaction.roll_3d6",
            return_value=_forced_roll(7),
        ):
            result = roll_reaction(12)
        assert result.total == 19
        assert result.band.name == "Excellent"

    def test_negative_modifier_default_path(self):
        # Sanity: negative modifier accepted without seeding, band stays consistent.
        for _ in range(50):
            result = roll_reaction(-2)
            assert result.total == result.roll.total - 2
            assert result.band == reaction_band(result.total)

    def test_natural_roll_preserved_for_display(self):
        # The underlying RollResult is kept so callers can show the natural dice.
        with patch(
            "gurps_bot.mechanics.reaction.roll_3d6",
            return_value=_forced_roll(11),
        ):
            result = roll_reaction(3)
        assert result.roll.total == 11          # natural roll, not adjusted
        assert result.total == 14               # adjusted
        assert result.band.name == "Good"

    def test_result_is_frozen(self):
        result = roll_reaction(0)
        with pytest.raises((AttributeError, TypeError)):
            result.total = 999  # type: ignore[misc]

    def test_band_keyed_off_adjusted_not_natural(self):
        # Natural 18 (Very Good) + 1 -> 19 -> Excellent; proves keying off adjusted.
        with patch(
            "gurps_bot.mechanics.reaction.roll_3d6",
            return_value=_forced_roll(18),
        ):
            result = roll_reaction(1)
        assert reaction_band(result.roll.total).name == "Very Good"
        assert result.band.name == "Excellent"

    def test_unmodified_average_is_neutral(self):
        # 3d6 averages 10.5 -> Neutral with no modifier.
        with patch(
            "gurps_bot.mechanics.reaction.roll_3d6",
            return_value=_forced_roll(10),
        ):
            result = roll_reaction()
        assert result.band.name == "Neutral"
