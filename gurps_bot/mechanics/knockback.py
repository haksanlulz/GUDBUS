# formulas only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""Knockback distance + fall-check math (B378)."""

from __future__ import annotations

from dataclasses import dataclass

# codes match damage.py
_CRUSHING = "cr"
_CUTTING = "cut"


@dataclass(frozen=True, slots=True)
class KnockbackResult:
    """B378 outcome; the fall check is vs best of DX/Acrobatics/Judo at fall_check_modifier."""

    yards: int
    fall_check_triggered: bool
    fall_check_modifier: int
    eligible: bool
    effective_denom: int
    double_knockback: bool


def _knockback_eligible(damage_type: str, penetrated_dr: bool) -> bool:
    dtype = damage_type.strip().lower()
    if dtype == _CRUSHING:
        return True
    if dtype == _CUTTING:
        return not penetrated_dr
    return False


def calc_knockback(
    basic_damage: int,
    damage_type: str,
    target_st: int,
    *,
    penetrated_dr: bool = True,
    double_knockback: bool = False,
    perfect_balance: bool = False,
) -> KnockbackResult:
    """B378: basic_damage is the PRE-DR roll total; pass object HP as target_st for walls; cr always, cut only if it failed to penetrate (cinematic B417 out of scope)."""
    eligible = _knockback_eligible(damage_type, penetrated_dr)

    # B378: denom = ST - 2, floored at 1 (ST <= 3 collapses to a yard per point)
    denom = max(1, target_st - 2)

    # double knockback halves the denom after the low-ST collapse, still floored at 1
    effective_denom = max(1, denom // 2) if double_knockback else denom

    if not eligible:
        return KnockbackResult(
            yards=0,
            fall_check_triggered=False,
            fall_check_modifier=0,
            eligible=False,
            effective_denom=effective_denom,
            double_knockback=double_knockback,
        )

    yards = max(0, basic_damage) // effective_denom

    fall_check_triggered = yards >= 1
    if fall_check_triggered:
        modifier = -(yards - 1) + (4 if perfect_balance else 0)
    else:
        modifier = 0

    return KnockbackResult(
        yards=yards,
        fall_check_triggered=fall_check_triggered,
        fall_check_modifier=modifier,
        eligible=True,
        effective_denom=effective_denom,
        double_knockback=double_knockback,
    )
