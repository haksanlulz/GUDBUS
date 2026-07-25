"""Admin service layer — the per-domain homes for the admin cog's queries.

/status counts live in services/{characters,combat}.count_*; the guild-teardown
purges live in purge_guild_* across services/{characters,combat,notes,timers},
composed by services/admin.cleanup_guild_data (which owns no queries of its own).
The composite's end-to-end behavior is covered by tests/test_admin.py; this file
covers the per-domain functions directly.
"""

from __future__ import annotations

from sqlalchemy import func, select

from gurps_bot.db.models import ActiveCharacter, Character, Combat, Combatant
from gurps_bot.db.notes import Note
from gurps_bot.db.timers import Timer
from gurps_bot.services.characters import (
    count_characters,
    purge_guild_active_characters,
)
from gurps_bot.services.combat import count_combats, purge_guild_combats
from gurps_bot.services.notes import purge_guild_notes
from gurps_bot.services.timers import purge_guild_timers

USER = 111
OTHER_USER = 222
GUILD = 999
OTHER_GUILD = 777
CHANNEL = 888


async def _count(session, model, **filt):
    stmt = select(func.count()).select_from(model)
    for k, v in filt.items():
        stmt = stmt.where(getattr(model, k) == v)
    return await session.scalar(stmt)


async def _seed_character(session, user_id: int, name: str) -> int:
    char = Character(discord_user_id=user_id, name=name, total_points=100)
    session.add(char)
    await session.flush()
    return char.id


async def _seed_combat(session, guild_id: int, n_combatants: int) -> int:
    combat = Combat(guild_id=guild_id, channel_id=CHANNEL, started_by=USER)
    session.add(combat)
    await session.flush()
    for slot in range(n_combatants):
        session.add(Combatant(
            combat_id=combat.id, name=f"Goblin {slot}", slot=slot, basic_speed=5.0,
            hp_max=10, hp_current=10, fp_max=10, fp_current=10,
        ))
    return combat.id


class TestStatusCounts:
    async def test_count_characters_empty(self, db_session):
        assert await count_characters(db_session) == 0

    async def test_count_characters_spans_users(self, db_session):
        await _seed_character(db_session, USER, "Hero")
        await _seed_character(db_session, OTHER_USER, "Rival")
        await db_session.commit()
        assert await count_characters(db_session) == 2

    async def test_count_combats_empty(self, db_session):
        assert await count_combats(db_session) == 0

    async def test_count_combats_spans_guilds(self, db_session):
        await _seed_combat(db_session, GUILD, 1)
        await _seed_combat(db_session, OTHER_GUILD, 1)
        await db_session.commit()
        assert await count_combats(db_session) == 2


class TestPurgeGuildActiveCharacters:
    async def test_purges_only_the_guilds_selections(self, db_session):
        char_id = await _seed_character(db_session, USER, "Hero")
        db_session.add(ActiveCharacter(
            discord_user_id=USER, guild_id=GUILD, character_id=char_id))
        db_session.add(ActiveCharacter(
            discord_user_id=USER, guild_id=OTHER_GUILD, character_id=char_id))
        await db_session.commit()

        await purge_guild_active_characters(db_session, GUILD)
        await db_session.commit()

        assert await _count(db_session, ActiveCharacter, guild_id=GUILD) == 0
        assert await _count(db_session, ActiveCharacter, guild_id=OTHER_GUILD) == 1
        # The selection is a pointer; the global Character survives.
        assert await _count(db_session, Character, id=char_id) == 1


class TestPurgeGuildCombats:
    async def test_purges_combats_and_their_combatants_scoped(self, db_session):
        await _seed_combat(db_session, GUILD, 2)
        await _seed_combat(db_session, OTHER_GUILD, 1)
        await db_session.commit()

        await purge_guild_combats(db_session, GUILD)
        await db_session.commit()

        assert await _count(db_session, Combat, guild_id=GUILD) == 0
        # Combatant has no guild_id and bulk delete(Combat) fires no ORM
        # cascade — the purge must delete the guild's combatants itself, and
        # ONLY them.
        assert await _count(db_session, Combatant) == 1
        assert await _count(db_session, Combat, guild_id=OTHER_GUILD) == 1

    async def test_idempotent_on_empty_guild(self, db_session):
        await purge_guild_combats(db_session, 12345)
        await db_session.commit()
        assert await _count(db_session, Combat, guild_id=12345) == 0


class TestPurgeGuildNotes:
    async def test_purges_only_the_guilds_notes(self, db_session):
        db_session.add(Note(discord_user_id=USER, guild_id=GUILD,
                            title="secret plot", body="x", gm_secret=True))
        db_session.add(Note(discord_user_id=USER, guild_id=OTHER_GUILD,
                            title="keep me", body="y"))
        await db_session.commit()

        await purge_guild_notes(db_session, GUILD)
        await db_session.commit()

        assert await _count(db_session, Note, guild_id=GUILD) == 0
        assert await _count(db_session, Note, guild_id=OTHER_GUILD) == 1


class TestPurgeGuildTimers:
    async def test_purges_only_the_guilds_timers(self, db_session):
        db_session.add(Timer(guild_id=GUILD, channel_id=CHANNEL, label="Haste",
                             total=3, remaining=3, unit="turns"))
        db_session.add(Timer(guild_id=OTHER_GUILD, channel_id=CHANNEL, label="Bleed",
                             total=4, remaining=4, unit="turns"))
        await db_session.commit()

        await purge_guild_timers(db_session, GUILD)
        await db_session.commit()

        assert await _count(db_session, Timer, guild_id=GUILD) == 0
        assert await _count(db_session, Timer, guild_id=OTHER_GUILD) == 1
