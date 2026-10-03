# formulas only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Wealth + cost-of-living math (B265, B25-27); cost of living keys off Status, not Wealth."""

from __future__ import annotations

# B265: monthly upkeep in $ by Status tier (-2..8), NOT Wealth level
COST_OF_LIVING: dict[int, int] = {
    8: 600000000,
    7: 60000000,
    6: 6000000,
    5: 600000,
    4: 60000,
    3: 12000,
    2: 3000,
    1: 1200,
    0: 600,
    -1: 300,
    -2: 100,
}

# B265: average starting cash by TL, the baseline the Wealth multiplier scales
STARTING_WEALTH_BASE: dict[int, int] = {
    0: 250,
    1: 500,
    2: 750,
    3: 1000,
    4: 2000,
    5: 5000,
    6: 10000,
    7: 15000,
    8: 20000,
    9: 30000,
    10: 50000,
    11: 75000,
    12: 100000,
}

# B25-27: wealth level -> (cash multiplier, point cost); point cost is display-only,
# colocated so the multiplier and its price share one owner
WEALTH_MULTIPLIER: dict[str, tuple[float, int]] = {
    "dead_broke": (0.0, -25),
    "poor": (0.2, -15),
    "struggling": (0.5, -10),
    "average": (1.0, 0),
    "comfortable": (2.0, 10),
    "wealthy": (5.0, 20),
    "very_wealthy": (20.0, 30),
    "filthy_rich": (100.0, 50),
}


def cost_of_living(status: int) -> int:
    """Monthly upkeep in $ for a Status tier -2..8 (B265) — Status, not Wealth level."""
    if status not in COST_OF_LIVING:
        raise ValueError(f"No cost-of-living entry for Status {status}")
    return COST_OF_LIVING[status]


def _normalize_wealth_level(wealth_level: str) -> str:
    key = wealth_level.strip().lower()
    if key not in WEALTH_MULTIPLIER:
        raise ValueError(f"Unknown wealth_level: {wealth_level!r}")
    return key


def starting_wealth(tl: int, wealth_level: str) -> int:
    """Starting cash in $ for TL 0..12 x Wealth level (B25-27, B265): round(base * multiplier)."""
    if tl not in STARTING_WEALTH_BASE:
        raise ValueError(f"No starting-wealth base for tl {tl} (valid 0..12)")
    key = _normalize_wealth_level(wealth_level)
    multiplier, _ = WEALTH_MULTIPLIER[key]
    return round(STARTING_WEALTH_BASE[tl] * multiplier)


def wealth_level_cost(wealth_level: str) -> int:
    """Point cost of a Wealth level (B25-27), e.g. comfortable -> 10, poor -> -15."""
    key = _normalize_wealth_level(wealth_level)
    _, point_cost = WEALTH_MULTIPLIER[key]
    return point_cost
