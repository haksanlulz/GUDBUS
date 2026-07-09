"""/macro — save, roll, list, delete named dice expressions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.mechanics.dice import roll
from gurps_bot.services.macros import (
    delete_macro,
    get_macro,
    list_macros,
    save_macro,
)

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)


class MacroCog(commands.GroupCog, group_name="macro"):
    "Save and roll named dice expressions."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.command(name="save", description="Save a Named Dice Macro")
    @app_commands.describe(
        name="Macro name (e.g. greatsword)",
        expression="Dice notation (e.g. 2d+4, 3d6, 1d-1)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def save(
        self, interaction: discord.Interaction, name: str, expression: str,
    ) -> None:
        async with interaction.client.db() as session:
            try:
                await save_macro(session, interaction.user.id, name, expression)
            except ValueError as e:
                await interaction.response.send_message(
                    f"Invalid dice expression: {e}", ephemeral=True
                )
                return
            await session.commit()
        await interaction.response.send_message(
            f"Saved macro **{name.strip().lower()}** = `{expression}`.", ephemeral=True
        )

    @app_commands.command(name="roll", description="Roll a Saved Macro")
    @app_commands.describe(name="Macro name")
    @app_commands.checks.cooldown(2, 5.0)
    async def roll_macro(self, interaction: discord.Interaction, name: str) -> None:
        async with interaction.client.db() as session:
            macro = await get_macro(session, interaction.user.id, name)
        if macro is None:
            await interaction.response.send_message(
                f"No macro named **{name.strip().lower()}**. Save one with `/macro save`.",
                ephemeral=True,
            )
            return
        result = roll(macro.expression)
        dice = ", ".join(str(d) for d in result.dice)
        await interaction.response.send_message(
            f"**{macro.name}** (`{macro.expression}`): [{dice}] = **{result.total}**"
        )

    @app_commands.command(name="list", description="List Your Saved Macros")
    @app_commands.checks.cooldown(2, 5.0)
    async def list_cmd(self, interaction: discord.Interaction) -> None:
        async with interaction.client.db() as session:
            macros = await list_macros(session, interaction.user.id)
        if not macros:
            await interaction.response.send_message(
                "You have no saved macros. Add one with `/macro save`.", ephemeral=True
            )
            return
        lines = "\n".join(f"**{m.name}** = `{m.expression}`" for m in macros)
        await interaction.response.send_message(lines, ephemeral=True)

    @app_commands.command(name="delete", description="Delete a Saved Macro")
    @app_commands.describe(name="Macro name")
    @app_commands.checks.cooldown(2, 5.0)
    async def delete_cmd(self, interaction: discord.Interaction, name: str) -> None:
        async with interaction.client.db() as session:
            removed = await delete_macro(session, interaction.user.id, name)
            await session.commit()
        key = name.strip().lower()
        if removed:
            await interaction.response.send_message(
                f"Deleted macro **{key}**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"No macro named **{key}**.", ephemeral=True
            )


async def setup(bot: GURPSBot) -> None:
    await bot.add_cog(MacroCog(bot))
