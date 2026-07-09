"""Shared autocomplete factory for Discord slash command options."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord
from discord import app_commands
from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.utils.fuzzy import fuzzy_match


def make_autocomplete(
    fetch: Callable[[AsyncSession, discord.Interaction], Awaitable[list[str]]],
    score_cutoff: int = 40,
) -> Callable[[discord.Interaction, str], Awaitable[list[app_commands.Choice[str]]]]:
    """Build an autocomplete callback from a (session, interaction) -> candidates fetch."""

    async def autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if not interaction.guild_id:
            return []
        async with interaction.client.db() as session:
            candidates = await fetch(session, interaction)
        if not current:
            return [app_commands.Choice(name=c, value=c) for c in candidates[:25]]
        matches = fuzzy_match(current, candidates, limit=25, score_cutoff=score_cutoff)
        return [app_commands.Choice(name=m, value=m) for m, _ in matches]

    return autocomplete
