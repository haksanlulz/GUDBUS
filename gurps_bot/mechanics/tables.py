"""Fright Check + critical hit/miss tables (B360-361, B556-557); effect text is
original shorthand, no SJG prose reproduced.

Verified against the printed Basic Set:

* Fright Check (B360-361): roll vs Will under the Rule of 14 — modified Will
  above 13 counts as 13, so 14+ always fails (Fright Checks only, not other Will
  rolls). On a failure, roll 3d, ADD the margin of failure, and read the table,
  which runs 4 through 40+. It is keyed by that TOTAL, not by the bare margin.
* Critical Hit / Critical Head Blow / Critical Miss (B556) and Unarmed Critical
  Miss (B556-557): 3d6 tables, keys 3-18. Half-DR rows round DOWN on the main
  Critical Hit Table and UP on the Head Blow Table — that asymmetry is printed.
"""

from __future__ import annotations

#: Rule of 14 (B360): cap on modified Will for a Fright Check.
FRIGHT_WILL_CAP = 13

# Fright Check — (3d + margin of failure) → effect (B360-361).
# Rows the book groups share one string so escalation reads correctly.
_FRIGHT_4_5 = "Stunned 1 sec; recover automatically."
_FRIGHT_6_7 = "Stunned 1 sec; roll vs unmodified Will each sec to snap out."
_FRIGHT_8_9 = "Stunned 1 sec; roll vs Will (with your original modifiers) each sec to snap out."
_FRIGHT_14_15 = "Lose 1d FP, and stunned 1d sec (modified-Will rolls to snap out)."

FRIGHT_CHECK_TABLE: dict[int, str] = {
    4: _FRIGHT_4_5,
    5: _FRIGHT_4_5,
    6: _FRIGHT_6_7,
    7: _FRIGHT_6_7,
    8: _FRIGHT_8_9,
    9: _FRIGHT_8_9,
    10: "Stunned 1d sec; roll vs modified Will each sec to snap out.",
    11: "Stunned 2d sec; roll vs modified Will each sec to snap out.",
    12: "Retch for (25-HT) sec, then roll vs HT each sec to recover.",
    13: "Acquire a new mental quirk (the one way past the five-quirk limit).",
    14: _FRIGHT_14_15,
    15: _FRIGHT_14_15,
    16: "Stunned 1d sec (modified-Will rolls), plus a new quirk.",
    17: "Faint for 1d min, then roll vs HT each min to recover.",
    18: "Faint 1d min (HT each min); roll vs HT at once — on a failure, take 1 HP as you collapse.",
    19: "Severe faint, 2d min (HT each min to recover); take 1 HP.",
    20: "Faint bordering on shock, 4d min; also lose 1d FP.",
    21: "Panic — flee/scream/weep 1d min, then roll vs unmodified Will each min to snap out.",
    22: "Acquire a -10-point Delusion.",
    23: "Acquire a -10-point Phobia or other -10-point mental disadvantage.",
    24: "Major physical effect, GM's choice: -15 points of physical disadvantages.",
    25: "A related mental disadvantage worsens one self-control step; if none (or already at 6), gain a new -10-point Phobia or other mental disadvantage.",
    26: "Faint 1d min (as 18), plus a new -10-point Delusion.",
    27: "Faint 1d min (as 18), plus a new -10-point mental disadvantage.",
    28: "Light coma: unconscious, roll vs HT every 30 min to wake; -2 on all skill and attribute rolls for 6 hrs after.",
    29: "Coma: unconscious 1d hours, then roll vs HT — on a failure, another 1d hours, and so on.",
    30: "Catatonia for 1d days, then HT (failure: another 1d days); untended, lose 1 HP the first day, 2 the second…; afterward -2 on all rolls for as many days as it lasted.",
    31: "Seizure, 1d min: lose 1d FP and roll vs HT — failure: 1d injury; critical failure: also lose 1 HT permanently.",
    32: "Stricken: fall down, take 2d injury (mild heart attack or stroke).",
    33: "Total panic — GM rolls 3d for how badly you react; if you survive it, roll vs Will to come out, else react again.",
    34: "Acquire a -15-point Delusion.",
    35: "Acquire a -15-point Phobia or other -15-point mental disadvantage.",
    36: "Severe physical effect (as 24): -20 points of physical disadvantages.",
    37: "Severe physical effect (as 24): -30 points of physical disadvantages.",
    38: "Coma (as 29), plus a -15-point Delusion.",
    39: "Coma (as 29), plus a -15-point Phobia or other -15-point mental disadvantage.",
    # Stored under 40; fright_table_effect() maps every higher total here too.
    40: "As 39, plus lose 1 point of IQ permanently (all IQ-based skills, including spells, drop 1).",
}

# Critical Hit — 3d6 → effect on target (B556). Doublings/triplings apply to
# BASIC damage, and the target gets no active defense against the attack.
_CRIT_HIT_TRIPLE = "Triple basic damage."
_CRIT_HIT_HALF_DR = "Target's DR protects at half value (round down, after armor divisors)."
_CRIT_HIT_DOUBLE = "Double basic damage."
_CRIT_HIT_MAX = "Maximum normal damage."
_CRIT_HIT_MAJOR = "If any damage penetrates DR, treat it as a major wound regardless of injury."
_CRIT_HIT_NORMAL = "Normal damage only."

CRITICAL_HIT_TABLE: dict[int, str] = {
    3: _CRIT_HIT_TRIPLE,
    4: _CRIT_HIT_HALF_DR,
    5: _CRIT_HIT_DOUBLE,
    6: _CRIT_HIT_MAX,
    7: _CRIT_HIT_MAJOR,
    8: "If any damage penetrates DR: double shock (max -8); a limb/extremity hit is also crippled for (16-HT) sec, min 2, unless crippled outright.",
    9: _CRIT_HIT_NORMAL,
    10: _CRIT_HIT_NORMAL,
    11: _CRIT_HIT_NORMAL,
    12: "Normal damage, and the target drops anything held (whether or not damage penetrates).",
    13: _CRIT_HIT_MAJOR,
    14: _CRIT_HIT_MAJOR,
    15: _CRIT_HIT_MAX,
    16: _CRIT_HIT_DOUBLE,
    17: _CRIT_HIT_HALF_DR,
    18: _CRIT_HIT_TRIPLE,
}

# Critical Head Blow — 3d6, for critical hits to the face, skull, or eye
# (B556). Note the half-DR rows round UP here, unlike the main table.
_HEAD_HALF_DR_MAJOR = "DR protects at half value (round up); any penetrating damage is a major wound."
_HEAD_EYE = "A face or skull hit becomes an EYE hit, even if normally impossible (truly impossible: treat as 4)."
_HEAD_NORMAL = "Normal head-blow damage only."
_HEAD_DEAFEN = "Normal damage; if any penetrates DR, crushing deafens (recovery per B422), anything else scars: -1 appearance level (-2 if burning/corrosion)."

CRITICAL_HEAD_BLOW_TABLE: dict[int, str] = {
    3: "Maximum normal damage, ignoring the target's DR.",
    4: _HEAD_HALF_DR_MAJOR,
    5: _HEAD_HALF_DR_MAJOR,
    6: _HEAD_EYE,
    7: _HEAD_EYE,
    8: "Normal damage; target knocked off balance — must Do Nothing next turn (defends normally).",
    9: _HEAD_NORMAL,
    10: _HEAD_NORMAL,
    11: _HEAD_NORMAL,
    12: _HEAD_DEAFEN,
    13: _HEAD_DEAFEN,
    14: "Normal damage, and the target drops a weapon (roll randomly if holding two).",
    15: "Maximum normal damage.",
    16: "Double basic damage.",
    17: "DR protects at half value (round up, after armor divisors).",
    18: "Triple basic damage.",
}

# Critical Miss — 3d6 → effect on attacker (B556).
_MISS_BREAK = "Weapon breaks (breakage-resistant weapons reroll: only a second break-result breaks it, any other result means you drop it instead)."
_MISS_BALANCE = "Lose balance: nothing else (not even free actions) until your next turn, and active defenses -2 until then."
_MISS_READY = "Weapon turns in your hand — an extra Ready is needed before it can be used again."
_MISS_DROP = "Drop your weapon (a cheap weapon breaks instead)."

CRITICAL_MISS_TABLE: dict[int, str] = {
    3: _MISS_BREAK,
    4: _MISS_BREAK,
    5: "Hit your own arm or leg (50% each): normal damage. Impaling/piercing melee or any ranged attack rerolls (second self-hit result stands).",
    6: "Hit your own arm or leg as per 5, but half damage.",
    7: _MISS_BALANCE,
    8: _MISS_READY,
    9: _MISS_DROP,
    10: _MISS_DROP,
    11: _MISS_DROP,
    12: _MISS_READY,
    13: _MISS_BALANCE,
    14: "Swing: weapon flies 1d yards (50% ahead/behind; anyone on the spot rolls DX or takes half damage). Thrust/ranged/parry: you drop it.",
    15: "Strained shoulder: weapon arm unusable for attack or defense for 30 min (you keep your grip).",
    16: "Fall down! (On a ranged attack, lose balance as per 7 instead.)",
    17: _MISS_BREAK,
    18: _MISS_BREAK,
}

# Unarmed Critical Miss — 3d6, for unarmed attacks/parries incl. animals
# (B556-557). Fighters that cannot fall take 1d-3 general injury on any
# fall-down result; fliers/swimmers are forced into an awkward position
# (-4 attack / -3 defense) instead.
_UNARMED_KO = "Knock yourself out! Roll vs HT every 30 min to recover."
_UNARMED_SOLID = "Hit a solid object: your thrust crushing damage to the part used (against a ready impaling weapon, you fall on it — its damage at your ST)."
_UNARMED_STUMBLE = "Stumble: on an attack, advance a yard past the foe and end facing away; on a parry, fall down."
_UNARMED_BALANCE = "Lose balance: nothing else until your next turn, active defenses -2."

UNARMED_CRITICAL_MISS_TABLE: dict[int, str] = {
    3: _UNARMED_KO,
    4: "Strain the limb used: 1 HP of injury and it is unusable for 30 min (bite/butt: pulled muscle — moderate pain for (20-HT) min, min 1).",
    5: _UNARMED_SOLID,
    6: "As 5, but half damage (natural weapons break instead: -1 damage until healed).",
    7: _UNARMED_STUMBLE,
    8: "Fall down!",
    9: _UNARMED_BALANCE,
    10: _UNARMED_BALANCE,
    11: _UNARMED_BALANCE,
    12: "Trip: roll DX to avoid falling (DX-4 if kicking; doubled penalty for techniques that risk a miss mishap).",
    13: "Drop your guard: active defenses -2 next turn, and Evaluate bonuses or Feint penalties against you count double (obvious to foes).",
    14: _UNARMED_STUMBLE,
    15: "Tear a muscle: 1d-3 injury to the limb used (neck if biting/butting); -1 to attacks and defenses next turn, -3 with that part until healed (-1 with High Pain Threshold).",
    16: _UNARMED_SOLID,
    17: "Strain the limb as per 4 (an IQ 3-5 animal instead loses its nerve: it flees, or bares its throat if cornered).",
    18: _UNARMED_KO,
}


def fright_table_effect(total: int) -> str:
    """Look up the Fright Check Table row for ``3d + margin of failure``.

    Totals past the table's end use the 40+ row; totals below 4 (impossible in
    play — 3d minimum 3 plus margin minimum 1) clamp to the first row.
    """
    return FRIGHT_CHECK_TABLE[max(4, min(total, 40))]
