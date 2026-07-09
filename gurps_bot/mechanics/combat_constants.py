"""GURPS combat enums, status effects, and display helpers."""

from __future__ import annotations

from enum import Enum


class Maneuver(str, Enum):
    ATTACK = "Attack"
    ALL_OUT_ATTACK = "All-Out Attack"
    MOVE = "Move"
    MOVE_AND_ATTACK = "Move and Attack"
    ALL_OUT_DEFENSE = "All-Out Defense"
    CONCENTRATE = "Concentrate"
    READY = "Ready"
    WAIT = "Wait"
    DO_NOTHING = "Do Nothing"


class StatusEffect(str, Enum):
    STUNNED = "Stunned"
    PRONE = "Prone"
    KNEELING = "Kneeling"
    UNCONSCIOUS = "Unconscious"
    DEAD = "Dead"
    DISARMED = "Disarmed"


STATUS_ICONS: dict[StatusEffect, str] = {
    StatusEffect.STUNNED: "\u26a1",
    StatusEffect.PRONE: "\u2b07\ufe0f",
    StatusEffect.KNEELING: "\U0001f9ce",
    StatusEffect.UNCONSCIOUS: "\U0001f4a4",
    StatusEffect.DEAD: "\u2620\ufe0f",
    StatusEffect.DISARMED: "\u270b",
}

MANEUVER_CHOICES: list[tuple[str, str]] = [
    (m.value, m.value) for m in Maneuver
]


def hp_status_label(hp_current: int, hp_max: int) -> str:
    if hp_max <= 0:
        return ""
    if hp_current <= -5 * hp_max:
        return "Dead"
    if hp_current <= -hp_max:
        return "Dying"
    if hp_current <= 0:
        return "Collapsing"
    if hp_current <= hp_max // 3:
        return "Reeling"
    return ""


def hp_bar(current: int, maximum: int, width: int = 10) -> str:
    """Render a text HP/FP bar: [####------] 8/13"""
    ratio = max(0.0, min(1.0, current / maximum)) if maximum > 0 else 0.0
    filled = round(ratio * width)
    return f"[{'#' * filled}{'-' * (width - filled)}] {current}/{maximum}"
