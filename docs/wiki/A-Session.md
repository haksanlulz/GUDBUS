# A session

One combat, start to finish. The message formats below are the ones the code
emits (`gurps_bot/ui/formatters.py`, `gurps_bot/ui/embeds.py` and
`gurps_bot/cogs/combat.py`), and the two most drift-prone renderings are pinned
by `tests/test_readme.py`, which builds them from those modules and fails if
what is quoted here stops matching. The character names and the individual die
faces are chosen for the example; nothing seeds `random`, so a real roll will
differ. The arithmetic follows from the same rules the code applies.

**GM, `/combat start`.** Posts the tracker, and keeps editing that one message
for the rest of the fight.

> **Combat — Round 1**
> *No combatants yet. Use `/combat join` or `/combat add-npc`.*

**Player, `/combat join`.** Speed, HP and FP come off their active character.

> **Aldric** joined combat (Speed 5.75).

**GM, `/combat add-npc` `name: Ogre` `speed: 4.5` `hp: 25` `fp: 12`.**

> Added **Ogre** (Speed 4.5, HP 25).

The tracker message now reads:

> **Combat — Round 1**
> ▶ **Aldric** | Spd 5.75 | [########] 13/13 HP | [########] 11/11 FP
>  **Ogre** | Spd 4.5 | [########] 25/25 HP | [########] 12/12 FP

Order is Basic Speed descending, then DX, then a per-combatant tiebreaker.
▶ marks whose turn it is.

**Player, `/attack` `weapon: Broadsword`.** 3d against the weapon's skill level
as imported from the sheet. The embed lays these out as fields side by side:

> **Aldric — Attack: Broadsword (swung)**
> Rolled **11** (4 + 6 + 1) — Target 14 — Margin +3
> Result: **Success**
> Damage 2d cut — Reach 1

A **Roll Damage** button comes attached to that message:

> **Damage: 2d cut**
> Rolled 1 + 5 = 6 — After DR 6 — Wound **9** (×1.5)

Cutting wounds at ×1.5 on whatever gets past DR (B379), so 6 becomes 9.

**GM, `/combat hp` `target: Ogre` `amount: -9`.**

> **Ogre** HP -9 → 16/25
> Shock -4 to DX, IQ, and DX/IQ-based skills next turn (does not affect active defenses, B419).

Shock scales with the target's own HP: at 25 HP the Ogre pays 2 HP per point of
it rather than 1 (B380/B419). The tracker redraws itself:

> **Combat — Round 1**
> ▶ **Aldric** | Spd 5.75 | [########] 13/13 HP | [########] 11/11 FP
>  **Ogre** | Spd 4.5 | [#####---] 16/25 HP | [########] 12/12 FP

**GM, `/combat end`.**

> Combat ended.
