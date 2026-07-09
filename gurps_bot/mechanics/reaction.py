# band labels only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Reaction rolls (B560-B561): 3d6 plus modifier, read against the band ladder."""

from __future__ import annotations

from dataclasses import dataclass

from gurps_bot.mechanics.dice import RollResult, roll_3d6

# sentinels for the open-ended outer bands; reaction_band never clamps
_NEG_INF = -(10**9)
_POS_INF = 10**9


@dataclass(frozen=True, slots=True)
class ReactionBand:
    """Inclusive bounds; rank is ordinal severity (-3..4, Neutral = 1)."""

    name: str
    lower: int
    upper: int
    rank: int


# gapless ladder, low rank to high; interior bands are 3 wide, ends open
REACTION_BANDS: tuple[ReactionBand, ...] = (
    ReactionBand("Disastrous", _NEG_INF, 0, -3),
    ReactionBand("Very Bad", 1, 3, -2),
    ReactionBand("Bad", 4, 6, -1),
    ReactionBand("Poor", 7, 9, 0),
    ReactionBand("Neutral", 10, 12, 1),
    ReactionBand("Good", 13, 15, 2),
    ReactionBand("Very Good", 16, 18, 3),
    ReactionBand("Excellent", 19, _POS_INF, 4),
)


@dataclass(frozen=True, slots=True)
class ReactionResult:
    """``roll`` is the natural 3d6, kept so callers can show the dice."""

    roll: RollResult
    modifier: int
    total: int
    band: ReactionBand


def reaction_band(total: int) -> ReactionBand:
    """Band for an adjusted total (B560): open-ended, <= 0 Disastrous, >= 19 Excellent."""
    for band in REACTION_BANDS:
        if band.lower <= total <= band.upper:
            return band
    # Unreachable: the sentinel outer bounds cover the entire int range.
    raise AssertionError(f"no reaction band for total {total!r}")


def roll_reaction(modifier: int = 0) -> ReactionResult:
    """Roll 3d6, apply the modifier, resolve the band (B560)."""
    roll = roll_3d6()
    total = roll.total + modifier
    band = reaction_band(total)
    return ReactionResult(roll=roll, modifier=modifier, total=total, band=band)
