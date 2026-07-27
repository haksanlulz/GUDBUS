"""active-defense cumulative penalties; per-turn parry/block counts live on the Combatant (reset in services.combat.advance_turn)"""

from __future__ import annotations

#: B376: each parry after the first in a turn is a cumulative -4 ...
PARRY_STEP: int = -4

#: ... "Reduce this to -2 per parry if you are using a fencing weapon or have
#: the Trained By A Master or Weapon Master advantage" (B376).
PARRY_STEP_REDUCED: int = -2


def cumulative_parry_penalty(prior_parries: int, *, reduced: bool = False) -> int:
    """B376. ``reduced`` = fencing weapon, Trained By A Master, or Weapon Master.

    NOTE the count is per weapon or hand — B376 says "further attempts to parry
    with *that weapon or hand*". Callers passing a single per-turn total
    over-penalize anyone parrying with two weapons or an off hand; see the
    caller-side caveat in services/combat.
    """
    step = PARRY_STEP_REDUCED if reduced else PARRY_STEP
    return step * max(0, prior_parries)


def defense_penalty(
    defense_type: str,
    prior_parries: int,
    prior_blocks: int,
    *,
    reduced_parry: bool = False,
) -> tuple[int, str | None]:
    """dodge 0 (B374, no cap); parry -4 per prior parry, or -2 with a fencing
    weapon / Trained By A Master / Weapon Master (B376); block 0 plus an
    advisory one-per-turn note (B375, not enforced)"""
    dt = defense_type.lower().strip()
    if dt == "dodge":
        return 0, None
    if dt == "parry":
        penalty = cumulative_parry_penalty(prior_parries, reduced=reduced_parry)
        note = None
        if prior_parries:
            kind = " (fencing/Master, -2 step)" if reduced_parry else ""
            note = (
                f"Parry #{prior_parries + 1} this turn — cumulative {penalty}"
                f"{kind} (B376)."
            )
        return penalty, note
    if dt == "block":
        note = None
        if prior_blocks:
            note = "Already Blocked this turn — RAW allows one Block per turn (B375)."
        return 0, note
    raise ValueError(f"Unknown defense_type: {defense_type!r}")
