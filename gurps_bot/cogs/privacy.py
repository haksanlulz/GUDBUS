"""/privacy: self-service deletion of everything stored about you."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.services.privacy import count_user_data, delete_user_data
from gurps_bot.ui.views import ConfirmView

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)

_PROMPT = (
    "Delete **everything this bot stores about you**, in every server: {what} "
    "Your entries in a running combat stay on the tracker without your name "
    "attached until that combat ends. This cannot be undone."
)

#: Table name -> how the summary reads it.
_LABELS = {
    "characters": "character",
    "dice_macros": "macro",
    "notes": "note",
    "study_logs": "study log",
    "wealth": "wallet",
    "crafting_projects": "crafting project",
    "combatants": "combat entry",
}


def _listing(counts: dict[str, int]) -> str:
    parts = []
    for table, label in _LABELS.items():
        n = counts.get(table, 0)
        if n:
            parts.append(f"{n} {label}{'' if n == 1 else 's'}")
    return ", ".join(parts)


def summarise(counts: dict[str, int]) -> str:
    listing = _listing(counts)
    return f"Deleted: {listing}." if listing else "There was nothing stored for you."


class PrivacyGroup(app_commands.Group):
    """Group holder so the cog stays a thin command surface."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(name="privacy", description="Your data stored by this bot")
        self.bot = bot

    @app_commands.command(
        name="delete-my-data",
        description="Delete everything this bot stores about you, in every server",
    )
    @app_commands.checks.cooldown(1, 30.0)
    async def delete_my_data(self, interaction: discord.Interaction[GURPSBot]) -> None:
        user_id = interaction.user.id
        async with interaction.client.db() as session:
            stored = await count_user_data(session, user_id)
        if not any(stored.values()):
            await interaction.response.send_message(
                "This bot stores nothing about you.", ephemeral=True
            )
            return

        view = ConfirmView(author_id=user_id)
        await interaction.response.send_message(
            _PROMPT.format(what=_listing(stored) + "."), view=view, ephemeral=True
        )
        view.message = await interaction.original_response()
        await view.wait()
        if not view.confirmed:
            return

        async with interaction.client.db() as session:
            counts = await delete_user_data(session, user_id)
            await session.commit()
        await interaction.followup.send(summarise(counts), ephemeral=True)


class PrivacyCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.group = PrivacyGroup(bot)
        bot.tree.add_command(self.group)


async def setup(bot: GURPSBot) -> None:
    await bot.add_cog(PrivacyCog(bot))
