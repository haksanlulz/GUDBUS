"""Guild-lifecycle composite service — what "guild-scoped" means, in one place.

Owns guild teardown as a concept: the enumeration of WHAT is purged when the
bot leaves a guild vs what survives. Delegates every query to the owning domain
service and runs no SQL of its own, so each table's queries keep a single owner
(same delegation shape as services/dashboard.py). Never commits; the caller
owns the transaction.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.services.campaign import purge_guild_campaign_settings
from gurps_bot.services.characters import purge_guild_active_characters
from gurps_bot.services.combat import purge_guild_combats
from gurps_bot.services.notes import purge_guild_notes
from gurps_bot.services.timers import purge_guild_timers


async def cleanup_guild_data(session: AsyncSession, guild_id: int) -> None:
    """Purge every guild-scoped row for a guild the bot has left.

    Removes the guild's active-character selections, combats (and their
    combatants), notes, timers, and house rules. Characters are global (keyed
    by user, no guild_id) and are kept, as are user-scoped study logs, wealth
    and dice macros. Caller commits.

    The set this has to cover is "every table with a guild_id", which is not
    something to keep in someone's head — `campaign_settings` was added months
    after this function and simply never got added to it, so a kick and
    re-invite silently restored the old occupants' house rules.
    `tests/test_guild_teardown.py` derives the set from the model metadata and
    fails when a new guild-scoped table is not handled here.
    """
    await purge_guild_active_characters(session, guild_id)
    await purge_guild_combats(session, guild_id)
    await purge_guild_notes(session, guild_id)
    await purge_guild_timers(session, guild_id)
    await purge_guild_campaign_settings(session, guild_id)
