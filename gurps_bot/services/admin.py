"""Guild-lifecycle composite service — what "guild-scoped" means, in one place.

Owns guild teardown as a concept: the enumeration of WHAT is purged when the
bot leaves a guild vs what survives. Delegates every query to the owning domain
service and runs no SQL of its own, so each table's queries keep a single owner
(same delegation shape as services/dashboard.py). The one exception is
`stored_guild_ids`, a read across every guild-scoped table: it is derived
from the model metadata precisely so that no table can be left out of it, which
a per-service function each would reintroduce. Never commits; the caller owns
the transaction.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, union
from sqlalchemy.ext.asyncio import AsyncSession

import gurps_bot.db  # noqa: F401 — registers every table on the metadata
from gurps_bot.db.models import Base

from gurps_bot.services.campaign import purge_guild_campaign_settings
from gurps_bot.services.characters import purge_guild_active_characters
from gurps_bot.services.combat import purge_guild_combats
from gurps_bot.services.crafting import purge_guild_crafting_projects
from gurps_bot.services.notes import purge_guild_notes
from gurps_bot.services.timers import purge_guild_timers


async def cleanup_guild_data(session: AsyncSession, guild_id: int) -> None:
    """Purge every guild-scoped row for a guild the bot has left.

    Removes the guild's active-character selections, combats (and their
    combatants), notes, timers, house rules, and crafting projects (with
    their charge ledgers). Characters are global (keyed
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
    await purge_guild_crafting_projects(session, guild_id)


log = logging.getLogger(__name__)


async def stored_guild_ids(session: AsyncSession) -> set[int]:
    """Every guild id that has a row in any guild-scoped table."""
    tables = [
        t for t in Base.metadata.tables.values() if "guild_id" in t.columns.keys()
    ]
    stmt = union(
        *(select(t.c.guild_id).where(t.c.guild_id.is_not(None)) for t in tables)
    )
    return set((await session.scalars(stmt)).all())


async def reconcile_departed_guilds(
    session: AsyncSession, present: set[int]
) -> list[int]:
    """Purge guilds the bot left while it was not connected to hear about it.

    on_guild_remove only fires for a removal the gateway delivers live; Discord
    does not replay it after a fresh login. Run once at startup against the
    guilds the bot is actually in. An empty `present` purges nothing: zero
    guilds is far likelier an unfilled cache than a bot removed from every
    server, and the cost of being wrong is every server's data. Caller commits.
    """
    if not present:
        log.warning("Guild reconcile skipped: the bot reports no guilds")
        return []
    departed = sorted(await stored_guild_ids(session) - present)
    for guild_id in departed:
        await cleanup_guild_data(session, guild_id)
    if departed:
        log.info("Purged data for %d guild(s) left while offline", len(departed))
    return departed
