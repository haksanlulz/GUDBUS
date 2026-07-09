"""active-defense cumulative penalties; per-turn parry/block counts live on the Combatant (reset in services.combat.advance_turn)"""

from __future__ import annotations

#: B376: each parry after the first in a turn is a cumulative -4
PARRY_STEP: int = -4


def cumulative_parry_penalty(prior_parries: int) -> int:
    return PARRY_STEP * max(0, prior_parries)


def defense_penalty(
    defense_type: str, prior_parries: int, prior_blocks: int,
) -> tuple[int, str | None]:
    """dodge 0 (B374, no cap); parry -4 per prior parry (B376); block 0 plus an advisory one-per-turn note (B375, not enforced)"""
    dt = defense_type.lower().strip()
    if dt == "dodge":
        return 0, None
    if dt == "parry":
        penalty = cumulative_parry_penalty(prior_parries)
        note = None
        if prior_parries:
            note = f"Parry #{prior_parries + 1} this turn — cumulative {penalty} (B376)."
        return penalty, note
    if dt == "block":
        note = None
        if prior_blocks:
            note = "Already Blocked this turn — RAW allows one Block per turn (B375)."
        return 0, note
    raise ValueError(f"Unknown defense_type: {defense_type!r}")
