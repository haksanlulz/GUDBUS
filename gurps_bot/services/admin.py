"""Guild-lifecycle composite service — what "guild-scoped" means, in one place.

Owns guild teardown as a concept: the enumeration of WHAT is purged when the
bot leaves a guild vs what survives. Delegates every query to the owning domain
service and runs no SQL of its own, so each table's queries keep a single owner
(same delegation shape as services/dashboard.py). Never commits; the caller
owns the transaction.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.services.characters import purge_guild_active_characters
from gurps_bot.services.combat import purge_guild_combats
from gurps_bot.services.notes import purge_guild_notes
from gurps_bot.services.timers import purge_guild_timers


async def cleanup_guild_data(session: AsyncSession, guild_id: int) -> None:
    """Purge every guild-scoped row for a guild the bot has left.

    Removes the guild's active-character selections, combats (and their
    combatants), notes, and timers. Characters are global (keyed by user, no
    guild_id) and are kept, as are user-scoped study logs and wealth. Caller
    commits.
    """
    await purge_guild_active_characters(session, guild_id)
    await purge_guild_combats(session, guild_id)
    await purge_guild_notes(session, guild_id)
    await purge_guild_timers(session, guild_id)
