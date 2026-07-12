"""Combat tracker queries. Callers own the transaction — nothing here commits."""

from __future__ import annotations

import logging
import math
import random
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from gurps_bot.db.models import Attribute, Combat, Combatant
from gurps_bot.mechanics.checks import check
from gurps_bot.mechanics.combat_constants import StatusEffect


def ordered_combatants(combat: Combat) -> list[Combatant]:
    """Return combatants in initiative order (highest speed first)."""
    return sorted(
        combat.combatants,
        key=lambda c: (-c.basic_speed, -c.dx, c.tiebreaker),
    )


def _position_of(ordered: list[Combatant], combatant_id: int | None) -> int | None:
    if combatant_id is None:
        return None
    for i, c in enumerate(ordered):
        if c.id == combatant_id:
            return i
    return None


def current_combatant(combat: Combat) -> Combatant | None:
    """Whose turn it is — anchored by current_combatant_id; index fallback for pre-anchor combats."""
    ordered = ordered_combatants(combat)
    if not ordered:
        return None
    pos = _position_of(ordered, combat.current_combatant_id)
    if pos is None:
        pos = combat.current_index % len(ordered)
    return ordered[pos]


def _sync_index_to_anchor(combat: Combat) -> None:
    """Recompute current_index from the anchor; no-op when unanchored or the anchor is gone."""
    if combat.current_combatant_id is None:
        return
    pos = _position_of(ordered_combatants(combat), combat.current_combatant_id)
    if pos is not None:
        combat.current_index = pos


async def get_combat(
    session: AsyncSession, guild_id: int, channel_id: int,
) -> Combat | None:
    """Fetch the active combat for a channel, with combatants eagerly loaded."""
    stmt = (
        select(Combat)
        .options(selectinload(Combat.combatants))
        .where(Combat.guild_id == guild_id, Combat.channel_id == channel_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def start_combat(
    session: AsyncSession, guild_id: int, channel_id: int, started_by: int,
) -> Combat:
    """Create a combat; ValueError if one is already live in this channel."""
    existing = await get_combat(session, guild_id, channel_id)
    if existing:
        raise ValueError("A combat is already active in this channel.")

    log.info("Starting combat in guild=%d channel=%d by user=%d", guild_id, channel_id, started_by)
    combat = Combat(
        guild_id=guild_id,
        channel_id=channel_id,
        started_by=started_by,
    )
    session.add(combat)
    await session.flush()
    # load the (empty) combatants list now — lazy-load raises under async
    await session.refresh(combat, ["combatants"])
    return combat


async def end_combat(
    session: AsyncSession, guild_id: int, channel_id: int,
) -> bool:
    combat = await get_combat(session, guild_id, channel_id)
    if not combat:
        return False
    log.info("Ending combat id=%d in guild=%d channel=%d", combat.id, guild_id, channel_id)
    await session.delete(combat)
    return True


def _next_slot(combat: Combat) -> int:
    """Next slot from the in-memory list — racy; prefer _allocate_slot_and_add."""
    if not combat.combatants:
        return 0
    return max(c.slot for c in combat.combatants) + 1


async def _allocate_slot_and_add(
    session: AsyncSession,
    combat: Combat,
    combatant: Combatant,
) -> Combatant:
    """Insert with the slot allocated SQL-side — concurrent adds can't collide on MAX(slot)+1."""
    # slot comes from the SQL subquery, id from autoincrement — omit both
    values = {
        "combat_id": combatant.combat_id,
        "character_id": combatant.character_id,
        "discord_user_id": combatant.discord_user_id,
        "name": combatant.name,
        "is_npc": combatant.is_npc,
        "basic_speed": combatant.basic_speed,
        "dx": combatant.dx,
        "tiebreaker": combatant.tiebreaker,
        "hp_max": combatant.hp_max,
        "hp_current": combatant.hp_current,
        "fp_max": combatant.fp_max,
        "fp_current": combatant.fp_current,
        "ht": combatant.ht,
        "will": combatant.will,
        "maneuver": combatant.maneuver,
        "status_effects": combatant.status_effects or [],
        "parries_this_turn": 0,
        "blocks_this_turn": 0,
        "slot": (
            select(func.coalesce(func.max(Combatant.slot) + 1, 0))
            .where(Combatant.combat_id == combat.id)
            .scalar_subquery()
        ),
    }
    stmt = insert(Combatant).values(**values).returning(Combatant.id)
    new_id = (await session.execute(stmt)).scalar_one()

    # re-fetch so the caller gets a live ORM object with the SQL-computed slot
    refreshed = (
        await session.execute(
            select(Combatant).where(Combatant.id == new_id)
        )
    ).scalar_one()
    combat.combatants.append(refreshed)
    return refreshed


async def _read_character_combat_stats(
    session: AsyncSession, character_id: int,
) -> dict:
    stmt = select(Attribute).where(Attribute.character_id == character_id)
    result = await session.execute(stmt)
    attrs: dict[str, float] = {}
    for a in result.scalars().all():
        attrs[a.attr_id] = a.value
        if a.current is not None:
            attrs[f"{a.attr_id}_current"] = a.current

    return {
        "basic_speed": attrs.get("basic_speed", 5.0),
        "dx": int(attrs.get("dx", 10)),
        "hp_max": int(attrs.get("hp", 10)),
        "hp_current": int(attrs.get("hp_current", attrs.get("hp", 10))),
        "fp_max": int(attrs.get("fp", 10)),
        "fp_current": int(attrs.get("fp_current", attrs.get("fp", 10))),
        "ht": int(attrs.get("ht", 10)),
        "will": int(attrs.get("will", 10)),
    }


async def add_pc_combatant(
    session: AsyncSession,
    combat: Combat,
    character_id: int,
    character_name: str,
    discord_user_id: int,
) -> Combatant:
    """Add a PC; ValueError if already in this combat."""
    for c in combat.combatants:
        if c.character_id == character_id:
            raise ValueError(f"{character_name} is already in this combat.")

    log.info("Adding PC '%s' to combat id=%d", character_name, combat.id)
    stats = await _read_character_combat_stats(session, character_id)
    combatant = Combatant(
        combat_id=combat.id,
        character_id=character_id,
        discord_user_id=discord_user_id,
        name=character_name,
        is_npc=False,
        basic_speed=stats["basic_speed"],
        dx=stats["dx"],
        tiebreaker=random.randint(0, 9999),
        hp_max=stats["hp_max"],
        hp_current=stats["hp_current"],
        fp_max=stats["fp_max"],
        fp_current=stats["fp_current"],
        ht=stats["ht"],
        will=stats["will"],
        # slot allocated by _allocate_slot_and_add
    )
    added = await _allocate_slot_and_add(session, combat, combatant)
    # adding reshuffles initiative order — re-anchor so the turn doesn't jump (#9)
    _sync_index_to_anchor(combat)
    return added


async def add_npc_combatant(
    session: AsyncSession,
    combat: Combat,
    name: str,
    basic_speed: float,
    hp: int,
    fp: int,
    dx: int = 10,
    ht: int = 10,
    will: int = 10,
) -> Combatant:
    # NaN compares False with everything, so a NaN speed makes the initiative
    # sort arbitrary and undetectable; mirror the wealth service's guard.
    if not math.isfinite(basic_speed):
        raise ValueError("Basic Speed must be a finite number.")
    log.info("Adding NPC '%s' to combat id=%d (speed=%.2f, hp=%d)", name, combat.id, basic_speed, hp)
    combatant = Combatant(
        combat_id=combat.id,
        character_id=None,
        discord_user_id=None,
        name=name,
        is_npc=True,
        basic_speed=basic_speed,
        dx=dx,
        tiebreaker=random.randint(0, 9999),
        hp_max=hp,
        hp_current=hp,
        fp_max=fp,
        fp_current=fp,
        ht=ht,
        will=will,
        # slot allocated by _allocate_slot_and_add
    )
    added = await _allocate_slot_and_add(session, combat, combatant)
    # adding reshuffles initiative order — re-anchor so the turn doesn't jump (#9)
    _sync_index_to_anchor(combat)
    return added


async def remove_combatant(
    session: AsyncSession, combat: Combat, combatant_id: int,
) -> bool:
    """Remove a combatant; removing the current actor passes the turn to the next in order."""
    ordered = ordered_combatants(combat)
    target_idx = None
    target = None
    for i, c in enumerate(ordered):
        if c.id == combatant_id:
            target_idx = i
            target = c
            break
    if target is None:
        return False

    removing_current = combat.current_combatant_id == combatant_id

    await session.delete(target)
    combat.combatants.remove(target)

    remaining = ordered_combatants(combat)
    if not remaining:
        combat.current_index = 0
        combat.current_combatant_id = None
        return True

    if removing_current:
        # next-in-order slides into target_idx; wrap to the top if the removed was last
        new_idx = target_idx if target_idx < len(remaining) else 0
        combat.current_index = new_idx
        combat.current_combatant_id = remaining[new_idx].id
    elif combat.current_combatant_id is not None:
        # anchor unchanged — resync its cached index after the shrink
        _sync_index_to_anchor(combat)
    else:
        # pre-anchor combat — keep the legacy positional shift
        if target_idx < combat.current_index:
            combat.current_index = max(0, combat.current_index - 1)
        elif combat.current_index >= len(remaining):
            combat.current_index = 0

    return True


def advance_turn(combat: Combat) -> str | None:
    """Advance the turn (sync, mutates in place); returns a stun/round message or None."""
    ordered = ordered_combatants(combat)
    if not ordered:
        return None

    # anchor first, stored index for pre-anchor combats
    pos = _position_of(ordered, combat.current_combatant_id)
    if pos is None:
        pos = combat.current_index % len(ordered)

    current = ordered[pos]
    current.maneuver = None
    current.parries_this_turn = 0
    current.blocks_this_turn = 0

    # scan bounded to n steps so the wrap fires at most once per call — an n+1
    # scan double-wraps and emits duplicate "Round N begins" banners when
    # everyone is down
    n = len(ordered)
    messages: list[str] = []
    target: int | None = None
    wrapped = False
    for step in range(1, n + 1):
        np = pos + step
        if np >= n:
            np -= n
            wrapped = True
        next_combatant = ordered[np]
        effects = set(next_combatant.status_effects or [])

        if StatusEffect.DEAD in effects or StatusEffect.UNCONSCIOUS in effects:
            continue

        # B419: at <=0 HP, roll HT at turn start or fall unconscious — at a
        # cumulative -1 per full multiple of HP below zero (flat HT in the
        # 0..-1xHP band, HT-1 from -1xHP, ...). Auto-rolled, GM can override
        # via /combat status
        if next_combatant.hp_current <= 0:
            penalty = 0
            if next_combatant.hp_max > 0:
                penalty = -(abs(next_combatant.hp_current) // next_combatant.hp_max)
            con = check(next_combatant.ht, penalty)
            effective = next_combatant.ht + penalty
            note = f", B419 {penalty} at -{-penalty}×HP" if penalty else ""
            if con.outcome.succeeded:
                messages.append(
                    f"**{next_combatant.name}** stays conscious "
                    f"(HT {con.rolled} vs {effective}{note})."
                )
            else:
                next_combatant.status_effects = (
                    list(next_combatant.status_effects or []) + [StatusEffect.UNCONSCIOUS]
                )
                messages.append(
                    f"**{next_combatant.name}** falls unconscious "
                    f"(HT {con.rolled} vs {effective}{note})."
                )
                continue

        target = np
        if StatusEffect.STUNNED in effects:
            next_combatant.maneuver = "Do Nothing"
            messages.append(
                f"**{next_combatant.name}** is Stunned — forced Do Nothing. "
                "Roll HT to recover at end of turn."
            )
        break

    if target is None:
        # everyone down — advance exactly one step so rounds don't inflate
        target = (pos + 1) % n
        wrapped = pos + 1 >= n
        messages.append("All combatants are down.")

    if wrapped:
        combat.round_number += 1
        messages.insert(0, f"Round {combat.round_number} begins.")

    combat.current_index = target
    combat.current_combatant_id = ordered[target].id
    combat.updated_at = datetime.now(timezone.utc)
    return "\n".join(messages) if messages else None


def previous_turn(combat: Combat) -> None:
    """Move back to the previous combatant (undo). Sync — modifies ORM objects in-place."""
    ordered = ordered_combatants(combat)
    if not ordered:
        return

    pos = _position_of(ordered, combat.current_combatant_id)
    if pos is None:
        pos = combat.current_index % len(ordered)

    pos -= 1
    if pos < 0:
        pos = len(ordered) - 1
        combat.round_number = max(1, combat.round_number - 1)

    combat.current_index = pos
    combat.current_combatant_id = ordered[pos].id
    combat.updated_at = datetime.now(timezone.utc)


async def modify_hp(
    session: AsyncSession, combatant_id: int, delta: int,
) -> tuple[Combatant, str]:
    """Apply an HP delta atomically; returns (combatant, warning)."""
    # atomic clamp-and-add — read-modify-write loses one of two parallel hits
    update_stmt = (
        update(Combatant)
        .where(Combatant.id == combatant_id)
        .values(hp_current=func.min(Combatant.hp_max, Combatant.hp_current + delta))
    )
    await session.execute(update_stmt)

    # re-fetch: the warning + DEAD check need the post-update hp
    stmt = select(Combatant).where(Combatant.id == combatant_id)
    result = await session.execute(stmt)
    c = result.scalar_one()

    warning = ""
    if c.hp_current <= -5 * c.hp_max:
        if StatusEffect.DEAD not in (c.status_effects or []):
            c.status_effects = list(c.status_effects or []) + [StatusEffect.DEAD]
        warning = f"**{c.name}** is dead (-5xHP)."
    elif c.hp_current <= -c.hp_max:
        warning = f"**{c.name}** must roll HT to survive ({c.hp_current} HP, threshold -{c.hp_max})."
    elif c.hp_current <= 0:
        warning = f"**{c.name}** must roll HT to stay conscious ({c.hp_current} HP)."

    return c, warning


async def modify_fp(
    session: AsyncSession, combatant_id: int, delta: int,
) -> Combatant:
    """Apply an FP delta atomically — same race shape as modify_hp."""
    update_stmt = (
        update(Combatant)
        .where(Combatant.id == combatant_id)
        .values(fp_current=func.min(Combatant.fp_max, Combatant.fp_current + delta))
    )
    await session.execute(update_stmt)
    stmt = select(Combatant).where(Combatant.id == combatant_id)
    result = await session.execute(stmt)
    return result.scalar_one()


async def set_maneuver(
    session: AsyncSession, combatant_id: int, maneuver: str,
) -> Combatant:
    stmt = select(Combatant).where(Combatant.id == combatant_id)
    result = await session.execute(stmt)
    c = result.scalar_one()
    c.maneuver = maneuver
    return c


async def add_status(
    session: AsyncSession, combatant_id: int, status: str,
) -> Combatant:
    """Add a status effect (validated against StatusEffect)."""
    valid = {e.value for e in StatusEffect}
    if status not in valid:
        raise ValueError(f"Unknown status: {status}. Valid: {', '.join(sorted(valid))}")

    # known race: the JSON-list column is read-mutate-write, so two concurrent
    # status changes can drop one — rare, cosmetic, GM-recoverable, and an
    # atomic JSON UPDATE is dialect-specific, so accepted
    stmt = select(Combatant).where(Combatant.id == combatant_id)
    result = await session.execute(stmt)
    c = result.scalar_one()
    effects = list(c.status_effects or [])
    if status not in effects:
        effects.append(status)
        c.status_effects = effects
    return c


async def remove_status(
    session: AsyncSession, combatant_id: int, status: str,
) -> Combatant:
    """Remove a status effect — same accepted race as add_status."""
    stmt = select(Combatant).where(Combatant.id == combatant_id)
    result = await session.execute(stmt)
    c = result.scalar_one()
    effects = list(c.status_effects or [])
    if status in effects:
        effects.remove(status)
        c.status_effects = effects
    return c


async def set_message_id(
    session: AsyncSession, combat_id: int, message_id: int,
) -> None:
    """Store the Discord message ID of the tracker embed."""
    stmt = select(Combat).where(Combat.id == combat_id)
    result = await session.execute(stmt)
    combat = result.scalar_one()
    combat.message_id = message_id


async def record_defense(
    session: AsyncSession, combatant_id: int, defense_type: str,
) -> Combatant:
    """Bump this turn's parry/block counter (atomic — same race shape as modify_hp)."""
    if defense_type == "parry":
        column = Combatant.parries_this_turn
        update_stmt = (
            update(Combatant)
            .where(Combatant.id == combatant_id)
            .values(parries_this_turn=column + 1)
        )
    elif defense_type == "block":
        column = Combatant.blocks_this_turn
        update_stmt = (
            update(Combatant)
            .where(Combatant.id == combatant_id)
            .values(blocks_this_turn=column + 1)
        )
    else:
        raise ValueError(
            f"Unknown defense_type: {defense_type}. Expected 'parry' or 'block'."
        )

    await session.execute(update_stmt)
    stmt = select(Combatant).where(Combatant.id == combatant_id)
    result = await session.execute(stmt)
    return result.scalar_one()


async def cleanup_stale_combats(
    session: AsyncSession, max_age_hours: int = 24,
) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    stmt = select(Combat).where(Combat.updated_at < cutoff)
    result = await session.execute(stmt)
    stale = result.scalars().all()
    for c in stale:
        await session.delete(c)
    return len(stale)
