"""/campaign: per-guild house rules.

Rules-as-written is the default for everything here, so a table that never opens
this group behaves exactly as it did before the group existed.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.services.campaign import get_campaign_rules, set_rule_of_14

log = logging.getLogger(__name__)

_COLOR = discord.Color.dark_teal()
_FOOTER = "GURPS facts per SJG Online Policy - see /legal"


def _rules_embed(rule_of_14: bool) -> discord.Embed:
    embed = discord.Embed(title="Campaign house rules", color=_COLOR)
    embed.add_field(
        name="Rule of 14 (B360)",
        value=(
            "**ON** — RAW. Modified Will is capped at 13 for Fright Checks, so "
            "a roll of 14+ always fails."
            if rule_of_14
            else "**OFF** — house rule. Modified Will is used uncapped on "
            "Fright Checks."
        ),
        inline=False,
    )
    embed.set_footer(text=_FOOTER)
    return embed


class CampaignGroup(app_commands.Group):
    """Group holder so the cog stays a thin command surface."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(name="campaign", description="Per-guild house rules")
        self.bot = bot

    @app_commands.command(name="show", description="Show this server's house rules")
    async def show(self, interaction: discord.Interaction) -> None:
        async with interaction.client.db() as session:
            rules = await get_campaign_rules(session, interaction.guild_id)
        await interaction.response.send_message(
            embed=_rules_embed(rules.rule_of_14), ephemeral=True
        )

    @app_commands.command(
        name="rule-of-14",
        description="Turn B360's Rule of 14 on (RAW) or off (house rule)",
    )
    @app_commands.describe(
        enabled="ON caps modified Will at 13 for Fright Checks (RAW). OFF uses it uncapped."
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def rule_of_14(
        self, interaction: discord.Interaction, enabled: bool
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "House rules are per-server; run this in a server.", ephemeral=True
            )
            return
        async with interaction.client.db() as session:
            rules = await set_rule_of_14(session, interaction.guild_id, enabled)
            await session.commit()
        await interaction.response.send_message(
            embed=_rules_embed(rules.rule_of_14), ephemeral=False
        )


class CampaignCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.group = CampaignGroup(bot)
        bot.tree.add_command(self.group)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CampaignCog(bot))
