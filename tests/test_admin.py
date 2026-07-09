"""guild-leave cleanup: purge guild-scoped rows, keep user-owned characters"""

from __future__ import annotations

from sqlalchemy import func, select

from gurps_bot.cogs.admin import cleanup_guild_data
from gurps_bot.db.models import ActiveCharacter, Character, Combat, Combatant
from gurps_bot.db.notes import Note
from gurps_bot.db.timers import Timer

USER = 111
GUILD = 999
OTHER_GUILD = 777
CHANNEL = 888


async def _seed(session):
    # global character — must survive the leave
    char = Character(discord_user_id=USER, name="Hero", total_points=100)
    session.add(char)
    await session.flush()
    # rows scoped to the guild being left
    session.add(ActiveCharacter(discord_user_id=USER, guild_id=GUILD, character_id=char.id))
    combat = Combat(guild_id=GUILD, channel_id=CHANNEL, started_by=USER)
    session.add(combat)
    await session.flush()
    for slot in range(2):
        session.add(Combatant(
            combat_id=combat.id, name=f"Goblin {slot}", slot=slot, basic_speed=5.0,
            hp_max=10, hp_current=10, fp_max=10, fp_current=10,
        ))
    session.add(Note(discord_user_id=USER, guild_id=GUILD, title="secret plot",
                     body="x", gm_secret=True))
    session.add(Timer(guild_id=GUILD, channel_id=CHANNEL, label="Haste",
                      total=3, remaining=3, unit="turns"))
    # same rows in another guild — must stay
    session.add(Note(discord_user_id=USER, guild_id=OTHER_GUILD, title="keep me", body="y"))
    session.add(Timer(guild_id=OTHER_GUILD, channel_id=CHANNEL, label="Bleed",
                      total=4, remaining=4, unit="turns"))
    await session.commit()
    return char.id


async def _count(session, model, **filt):
    stmt = select(func.count()).select_from(model)
    for k, v in filt.items():
        stmt = stmt.where(getattr(model, k) == v)
    return await session.scalar(stmt)


class TestCleanupGuildData:
    async def test_purges_only_the_left_guilds_scoped_data(self, db_session):
        char_id = await _seed(db_session)

        await cleanup_guild_data(db_session, GUILD)
        await db_session.commit()

        # left guild purged
        assert await _count(db_session, ActiveCharacter, guild_id=GUILD) == 0
        assert await _count(db_session, Combat, guild_id=GUILD) == 0
        # bulk delete(Combat) fires no cascade — combatants need their own delete
        assert await _count(db_session, Combatant) == 0
        assert await _count(db_session, Note, guild_id=GUILD) == 0
        assert await _count(db_session, Timer, guild_id=GUILD) == 0

        # other guild survives
        assert await _count(db_session, Note, guild_id=OTHER_GUILD) == 1
        assert await _count(db_session, Timer, guild_id=OTHER_GUILD) == 1

        # global character untouched
        assert await _count(db_session, Character, id=char_id) == 1

    async def test_idempotent_on_empty_guild(self, db_session):
        await cleanup_guild_data(db_session, 12345)
        await db_session.commit()
        assert await _count(db_session, Note, guild_id=12345) == 0
