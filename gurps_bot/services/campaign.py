"""Per-guild house-rule settings.

Absence of a row means "all defaults", so reads never write and an untouched
guild costs nothing. Every default here is RAW, which makes the switch additive:
a table that never touches it behaves exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.models import CampaignSettings

#: RAW defaults, used whenever a guild has no row yet.
DEFAULT_RULE_OF_14 = True


@dataclass(frozen=True, slots=True)
class CampaignRules:
    """Resolved house rules for one guild — plain values, no ORM identity."""

    rule_of_14: bool = DEFAULT_RULE_OF_14


async def get_campaign_rules(
    session: AsyncSession, guild_id: int | None
) -> CampaignRules:
    """Resolved rules for a guild. No guild (DM) or no row yields RAW defaults."""
    if guild_id is None:
        return CampaignRules()
    stmt = select(CampaignSettings).where(CampaignSettings.guild_id == guild_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return CampaignRules()
    return CampaignRules(rule_of_14=row.rule_of_14)


async def set_rule_of_14(
    session: AsyncSession, guild_id: int, enabled: bool
) -> CampaignRules:
    """Turn B360's Rule of 14 on or off for a guild, creating the row if needed.

    Session-first: the caller commits, matching every other service here.
    """
    stmt = select(CampaignSettings).where(CampaignSettings.guild_id == guild_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = CampaignSettings(guild_id=guild_id, rule_of_14=enabled)
        session.add(row)
    else:
        row.rule_of_14 = enabled
    return CampaignRules(rule_of_14=enabled)


async def purge_guild_campaign_settings(
    session: AsyncSession, guild_id: int
) -> None:
    """Drop a guild's house rules when the bot leaves it. Caller commits.

    House rules are guild-scoped, so they are the guild's data and go with it.
    Without this a kick and re-invite silently restores a setting the new
    occupants never chose — and the bot has already been kicked and re-invited
    once, during the 2026-07-25 rename.
    """
    await session.execute(
        delete(CampaignSettings).where(CampaignSettings.guild_id == guild_id)
    )
