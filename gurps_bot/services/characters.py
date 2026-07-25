"""Character queries. Callers own the transaction — nothing here commits.

Cache coupling: rolling.py caches a user's rollable skill/attribute names under
(user_id, guild_id). The key carries no character id, so every mutation here that
changes WHICH character is active — or deletes one — drops the affected entries.
That invalidation lives at this layer rather than in the cogs so a new caller
can't forget it; it runs pre-commit, which errs toward an unnecessary cache miss
if the transaction rolls back (the safe direction).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.models import (
    ActiveCharacter,
    Attribute,
    Character,
    Skill,
    Spell,
    Trait,
)
from gurps_bot.gcs.parser import ParsedCharacter
from gurps_bot.utils._cache_instances import skill_cache


class NoActiveCharacter(Exception):
    """Raised when a user has no active character in a guild."""


async def get_active_character(
    session: AsyncSession, user_id: int, guild_id: int,
) -> Character | None:
    stmt = (
        select(Character)
        .join(ActiveCharacter, ActiveCharacter.character_id == Character.id)
        .where(
            ActiveCharacter.discord_user_id == user_id,
            ActiveCharacter.guild_id == guild_id,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def require_active_character(
    session: AsyncSession, user_id: int, guild_id: int,
) -> Character:
    char = await get_active_character(session, user_id, guild_id)
    if not char:
        raise NoActiveCharacter()
    return char


async def get_character_attrs(
    session: AsyncSession, char_id: int,
) -> dict[str, float]:
    stmt = select(Attribute).where(Attribute.character_id == char_id)
    result = await session.execute(stmt)
    attrs: dict[str, float] = {}
    for a in result.scalars().all():
        attrs[a.attr_id] = a.value
        if a.current is not None:
            attrs[f"{a.attr_id}_current"] = a.current
    return attrs


async def get_character_skills(
    session: AsyncSession, char_id: int,
) -> list[Skill]:
    stmt = select(Skill).where(Skill.character_id == char_id).order_by(Skill.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_character_spells(
    session: AsyncSession, char_id: int,
) -> list[Spell]:
    stmt = select(Spell).where(Spell.character_id == char_id).order_by(Spell.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_character_traits(
    session: AsyncSession, char_id: int,
) -> list[Trait]:
    stmt = select(Trait).where(Trait.character_id == char_id).order_by(Trait.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def set_active_character(
    session: AsyncSession, user_id: int, guild_id: int, char_id: int,
) -> None:
    """Upsert the active character. Drops this user's cached skill names for THIS
    guild — their other guilds still point where they pointed before."""
    stmt = select(ActiveCharacter).where(
        ActiveCharacter.discord_user_id == user_id,
        ActiveCharacter.guild_id == guild_id,
    )
    result = await session.execute(stmt)
    active = result.scalar_one_or_none()
    if active:
        active.character_id = char_id
    else:
        session.add(ActiveCharacter(
            discord_user_id=user_id,
            guild_id=guild_id,
            character_id=char_id,
        ))
    skill_cache.invalidate((user_id, guild_id))


async def get_user_character_names(
    session: AsyncSession, user_id: int,
) -> list[str]:
    stmt = select(Character.name).where(Character.discord_user_id == user_id)
    result = await session.execute(stmt)
    return [r[0] for r in result.all()]


async def get_user_characters(
    session: AsyncSession, user_id: int,
) -> list[Character]:
    stmt = select(Character).where(Character.discord_user_id == user_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_character_by_name(
    session: AsyncSession, user_id: int, name: str,
) -> Character | None:
    stmt = select(Character).where(
        Character.discord_user_id == user_id,
        Character.name == name,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def import_character(
    session: AsyncSession,
    user_id: int,
    parsed: ParsedCharacter,
    filename: str,
    raw_data: dict | None = None,
) -> tuple[Character, bool]:
    """Import a parsed GCS sheet; returns (character, was_replacement).

    Drops the user's cached skill names in every guild: a replacement rewrites the
    whole skill list in place, so the cache goes stale without the active pointer
    moving at all.
    """
    gcs_id: str | None = None
    if raw_data:
        rid = raw_data.get("id")
        if isinstance(rid, str) and rid:
            gcs_id = rid

    existing = None
    if gcs_id is not None:
        # match on stable gcs id first — survives a sheet rename (#26)
        existing = (await session.execute(
            select(Character).where(
                Character.discord_user_id == user_id,
                Character.gcs_id == gcs_id,
            )
        )).scalar_one_or_none()
    if existing is None:
        # (user, name) fallback: id-less sheets + pre-gcs_id rows (NULL id);
        # the unique constraint caps this at one row
        existing = (await session.execute(
            select(Character).where(
                Character.discord_user_id == user_id,
                Character.name == parsed.name,
            )
        )).scalar_one_or_none()

    if existing:
        # in-place update keeps row id + active_character refs alive
        log.info("Re-importing character '%s' (id=%d) for user %d", parsed.name, existing.id, user_id)
        existing.name = parsed.name  # may differ from the stored name (rename)
        if gcs_id is not None:
            existing.gcs_id = gcs_id  # set on first id-carrying import / keep current
        existing.total_points = parsed.total_points
        existing.profile_json = parsed.profile
        existing.calc_json = parsed.calc
        existing.equipment_json = parsed.equipment
        existing.settings_json = parsed.settings
        existing.raw_gcs_json = raw_data or {}
        existing.source_filename = filename
        existing.imported_at = datetime.now(timezone.utc)

        # delete children explicitly — ORM cascade would lazy-load, which async forbids
        for model in (Attribute, Skill, Spell, Trait):
            await session.execute(
                delete(model).where(model.character_id == existing.id)
            )
        await session.flush()

        char = existing
    else:
        log.info("Importing new character '%s' for user %d", parsed.name, user_id)
        char = Character(
            discord_user_id=user_id,
            name=parsed.name,
            gcs_id=gcs_id,
            total_points=parsed.total_points,
            profile_json=parsed.profile,
            calc_json=parsed.calc,
            equipment_json=parsed.equipment,
            settings_json=parsed.settings,
            raw_gcs_json=raw_data or {},
            source_filename=filename,
        )
        session.add(char)
        await session.flush()

    for a in parsed.attributes:
        session.add(Attribute(
            character_id=char.id,
            attr_id=a.attr_id,
            value=a.value,
            current=a.current,
            points=a.points,
        ))

    for s in parsed.skills:
        session.add(Skill(
            character_id=char.id,
            name=s.name,
            specialization=s.specialization,
            difficulty=s.difficulty,
            level=s.level,
            relative_level=s.relative_level,
            points=s.points,
            defaults_json=s.defaults,
        ))

    for sp in parsed.spells:
        session.add(Spell(
            character_id=char.id,
            name=sp.name,
            college=sp.college,
            difficulty=sp.difficulty,
            level=sp.level,
            relative_level=sp.relative_level,
            points=sp.points,
            casting_cost=sp.casting_cost,
            maintenance_cost=sp.maintenance_cost,
            casting_time=sp.casting_time,
            duration=sp.duration,
            spell_class=sp.spell_class,
        ))

    for t in parsed.traits:
        session.add(Trait(
            character_id=char.id,
            name=t.name,
            group_name=t.group_name,
            points=t.points,
            level=t.level,
            tags_json=t.tags,
            has_weapon=t.has_weapon,
            weapon_json=t.weapons,
            notes=t.notes,
        ))

    # Last thing before returning: the new skill rows are staged, so the window
    # in which a concurrent autocomplete could re-cache the outgoing sheet is as
    # small as this layer can make it.
    skill_cache.invalidate_user(user_id)
    return char, existing is not None


async def delete_character(session: AsyncSession, char_id: int) -> bool:
    """Delete by ID; True if one was found.

    Drops the owner's cached skill names in EVERY guild: the same character can be
    the active one in several, and this signature carries no guild to narrow by.
    The owner is read off the row — the caller supplies only a char_id.
    """
    stmt = select(Character).where(Character.id == char_id)
    result = await session.execute(stmt)
    char = result.scalar_one_or_none()
    if char:
        log.info("Deleting character '%s' (id=%d)", char.name, char_id)
        skill_cache.invalidate_user(char.discord_user_id)
        await session.delete(char)
        return True
    return False
