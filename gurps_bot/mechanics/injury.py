"""Per-blow injury effects: shock (B419) and major wound (B420)."""

from __future__ import annotations

from enum import Enum

from gurps_bot.mechanics.combat_constants import StatusEffect

# B380: the cap is -4 at ANY HP total. High HP doesn't raise it — it raises how
# much injury each point of shock costs (see shock_penalty).
SHOCK_CAP: int = 4

# B380: at or above this HP, shock is -1 per (HP/10) lost rather than -1 per HP
SHOCK_SCALING_HP: int = 20


def shock_penalty(injury: int, hp_max: int | None = None) -> int:
    """B380/B419 shock: -1 per HP lost, or per (HP/10) at 20+ HP; capped at -4.

    A tough creature is shocked LESS easily, not more: each point of shock costs
    it HP/10 rather than 1 HP. hp_max is optional — omitting it gives -1 per HP,
    which is correct below 20 HP. Advisory; does not reduce active defenses.
    """
    if injury <= 0:
        return 0
    hp_per_point = 1
    if hp_max is not None and hp_max >= SHOCK_SCALING_HP:
        hp_per_point = hp_max // 10
    return -min(SHOCK_CAP, injury // hp_per_point)


def is_major_wound(injury: int, hp_max: int) -> bool:
    """B420 major wound: a single blow of strictly more than half hp_max."""
    if hp_max <= 0 or injury <= 0:
        return False
    return injury * 2 > hp_max


def injury_effects(injury: int, hp_max: int) -> list[str]:
    """Advisory lines for one blow: major wound first (it gates an HT roll), then shock."""
    if injury <= 0:
        return []
    notes: list[str] = []
    if is_major_wound(injury, hp_max):
        notes.append(
            f"**Major wound** (injury {injury} exceeds half of {hp_max} HP) — "
            "knockdown & stunning check (B420): failure = mentally stunned "
            "+ knocked down (Prone); failure by 5+ or a critical failure = "
            "unconscious."
        )
    penalty = shock_penalty(injury, hp_max)
    if penalty:
        notes.append(
            f"Shock {penalty} to DX, IQ, and DX/IQ-based skills next turn "
            "(does not affect active defenses, B419)."
        )
    return notes


class KnockdownOutcome(str, Enum):
    """Result of a major-wound knockdown & stunning HT roll (B420)."""

    NONE = "none"
    STUNNED_PRONE = "stunned_prone"
    KNOCKED_OUT = "knocked_out"


def resolve_knockdown(
    *, succeeded: bool, margin: int, critical_failure: bool
) -> KnockdownOutcome:
    """B420: failure = stunned + prone; failure by 5+ (margin <= -5) or crit = out."""
    if succeeded:
        return KnockdownOutcome.NONE
    if critical_failure or margin <= -5:
        return KnockdownOutcome.KNOCKED_OUT
    return KnockdownOutcome.STUNNED_PRONE


_KNOCKDOWN_STATUSES: dict[KnockdownOutcome, tuple[str, ...]] = {
    KnockdownOutcome.NONE: (),
    KnockdownOutcome.STUNNED_PRONE: (StatusEffect.STUNNED.value, StatusEffect.PRONE.value),
    KnockdownOutcome.KNOCKED_OUT: (StatusEffect.UNCONSCIOUS.value,),
}

_KNOCKDOWN_LABELS: dict[KnockdownOutcome, str] = {
    KnockdownOutcome.NONE: "kept their footing — no knockdown",
    KnockdownOutcome.STUNNED_PRONE: "**stunned and knocked down**",
    KnockdownOutcome.KNOCKED_OUT: "**knocked unconscious**",
}


def knockdown_statuses(outcome: KnockdownOutcome) -> tuple[str, ...]:
    return _KNOCKDOWN_STATUSES[outcome]


def knockdown_label(outcome: KnockdownOutcome) -> str:
    return _KNOCKDOWN_LABELS[outcome]


# B420 knockdown penalty by location: -5 for face/vitals/groin, -10 for skull/eye
_KNOCKDOWN_LOCATION_MODIFIERS: dict[str, int] = {
    "face": -5,
    "vitals": -5,
    "groin": -5,
    "skull": -10,
    "eye": -10,
    "eyes": -10,
}


def knockdown_modifier(location: str | None) -> int:
    if not location:
        return 0
    return _KNOCKDOWN_LOCATION_MODIFIERS.get(location.lower().strip(), 0)
