"""Fright Check + critical hit/miss tables (B360, B556); effect text is original shorthand, no SJG prose reproduced."""

from __future__ import annotations

# Fright Check — margin of failure → mechanical effect (B360)
FRIGHT_CHECK_TABLE: dict[int, str] = {
    0: "Stunned 1 sec, auto-recover.",
    1: "Stunned 1 sec. HT to recover each sec.",
    2: "Stunned 1 sec. HT-1 to recover each sec.",
    3: "Stunned 1 sec, HT-1 to recover. +quirk.",
    4: "Stunned 1d sec. HT-1 to recover each sec.",
    5: "Stunned 1d sec, HT-1 to recover. +quirk.",
    6: "Stunned 1d sec, HT-1 to recover. Nightmares 1d days.",
    7: "Stunned 2d sec. +quirk.",
    8: "Flee 1d sec, then stunned, HT-1 to recover.",
    9: "Flee 1d sec, then stunned, HT-1 to recover. +quirk.",
    10: "Stunned 1d sec. Gain -10pt mental disad.",
    11: "Stunned 1d sec. -10pt mental disad. Nightmares 1d days.",
    12: "Stunned 1d sec. -10pt mental disad. Physical effect.",
    13: "Faint 1d min, then stunned, HT-1 to recover. +quirk.",
    14: "Faint 2d min. -10pt mental disad.",
    15: "Faint 1d hrs. -10pt mental disad. Lose 1d FP permanently.",
    16: "Faint 1d hrs. -15pt mental disad. Physical effect.",
    17: "Faint 1d days. -15pt mental disad.",
    18: "Faint 1d days. -15pt mental disad. Physical effect.",
    19: "Catatonic until situation changes. -15pt mental disad, -5 IQ permanent.",
}
_FRIGHT_MAX_EFFECT = "Coma, HT/day to wake. -30pt mental disad on recovery."

# Critical Hit — 3d6 → effect on target (B556)
CRITICAL_HIT_TABLE: dict[int, str] = {
    3: "Triple damage.",
    4: "HT or stunned. -4 defenses next turn.",
    5: "HT or stunned. -4 defenses next turn.",
    6: "Drops weapon (right hand).",
    7: "Off balance — -2 active defenses next turn.",
    8: "Normal damage.",
    9: "Normal damage.",
    10: "Normal damage.",
    11: "Normal damage.",
    12: "Normal damage.",
    13: "Normal damage.",
    14: "Normal damage.",
    15: "Drops weapon (right hand).",
    16: "Drops weapon (right hand).",
    17: "HT or stunned. -4 defenses next turn.",
    18: "Triple damage.",
}

# Critical Miss — 3d6 → effect on attacker (B556)
CRITICAL_MISS_TABLE: dict[int, str] = {
    3: "Weapon breaks (unarmed: fall down).",
    4: "Weapon breaks (unarmed: fall down).",
    5: "Weapon flung 1d yards (unarmed: fall down).",
    6: "Weapon flung 1d yards (unarmed: fall down).",
    7: "Off balance — -2 active defenses next turn.",
    8: "Off balance — -2 active defenses next turn.",
    9: "Off balance — no active defenses next turn.",
    10: "Hit own limb, normal damage.",
    11: "Hit own limb, normal damage.",
    12: "Hit self, normal damage.",
    13: "Hit self, normal damage.",
    14: "Hit nearby ally (or self), normal damage.",
    15: "Hit nearby ally (or self), normal damage.",
    16: "Fall down.",
    17: "Drop weapon (breaks if fragile).",
    18: "Drop weapon (breaks if fragile; unarmed: fall down).",
}


def fright_check_effect(margin_of_failure: int) -> str:
    if margin_of_failure < 0:
        return "No fright effect."
    return FRIGHT_CHECK_TABLE.get(margin_of_failure, _FRIGHT_MAX_EFFECT)
