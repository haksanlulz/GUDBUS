"""/screen paginated rules reference and /gm session dashboard."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.services.dashboard import Dashboard, get_dashboard
from gurps_bot.ui import screen
from gurps_bot.ui.embeds import EMBED_FIELD_LIMIT
from gurps_bot.ui.views import PaginatorView

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)


def _cap_field(value: str) -> str:
    """Cap to Discord's 1024-char field limit; user-supplied labels can overflow and kill the send."""
    if len(value) > EMBED_FIELD_LIMIT:
        return value[: EMBED_FIELD_LIMIT - 15].rstrip() + "\n*…truncated*"
    return value

_CATEGORY_CHOICES = [
    app_commands.Choice(name="Combat (Maneuvers, Status)", value="combat"),
    app_commands.Choice(name="Body (Posture & Targeting)", value="body"),
    app_commands.Choice(name="Speed/Range & Size", value="ranged"),
    app_commands.Choice(name="Movement (Encumbrance, Travel)", value="movement"),
    app_commands.Choice(name="Reaction & Criticals", value="rolls"),
    app_commands.Choice(name="Fright Check", value="fright"),
]

_DASHBOARD = discord.Color.dark_teal()


def _dashboard_embed(dash: Dashboard) -> discord.Embed:
    embed = discord.Embed(title="GM Dashboard", color=_DASHBOARD)

    if dash.timers:
        lines = []
        for t in dash.timers[:10]:
            target = f" → {t.target}" if t.target else ""
            lines.append(f"⏳ **{t.label}** {t.remaining}/{t.total} {t.unit}{target}")
        embed.add_field(name="Live Timers", value=_cap_field("\n".join(lines)), inline=False)
    else:
        embed.add_field(name="Live Timers", value="*none*", inline=False)

    if dash.combat is not None:
        embed.add_field(
            name="Combat",
            value=f"Round {dash.combat.round_number} · {len(dash.combat.combatants)} combatants",
            inline=True,
        )
    else:
        embed.add_field(name="Combat", value="*none*", inline=True)

    if dash.recent_study:
        lines = [
            f"📘 **{s.skill_name}** +{s.learning_hours:g}h ({s.method})"
            for s in dash.recent_study
        ]
        embed.add_field(name="Your Recent Study", value=_cap_field("\n".join(lines)), inline=False)

    if dash.recent_notes:
        lines = [
            f"{'🔒 ' if n.gm_secret else '📝 '}{n.title}" for n in dash.recent_notes
        ]
        embed.add_field(name="Recent Notes", value=_cap_field("\n".join(lines)), inline=False)

    embed.set_footer(text="GM Dashboard · this channel + your tracker state")
    return embed


class GMScreenCog(commands.Cog):
    """GM Quick-Reference Screen Composed From the Shipped Rules Tables."""

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="screen",
        description="GM Quick-Reference Screen — Paginated GURPS Tables",
    )
    @app_commands.describe(category="Jump straight to a section (optional)")
    @app_commands.choices(category=_CATEGORY_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def screen(
        self,
        interaction: discord.Interaction,
        category: str | None = None,
    ) -> None:
        pages = screen.build_screen_pages()
        start = screen.CATEGORY_INDEX.get(category, 0) if category else 0

        view = PaginatorView(pages, interaction.user.id)
        view.current = start
        view._update_buttons()
        await interaction.response.send_message(embed=pages[start], view=view)
        try:
            view.message = await interaction.original_response()
        except discord.HTTPException:
            # page already posted; paginator just won't auto-disable on timeout
            log.warning("Could not fetch original_response for /screen paginator")

    @app_commands.command(
        name="gm",
        description="GM Dashboard — Live Timers, Combat, and Your Recent Study/Notes",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def gm(self, interaction: discord.Interaction) -> None:
        async with interaction.client.db() as session:
            dash = await get_dashboard(
                session,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                user_id=interaction.user.id,
            )
            embed = _dashboard_embed(dash)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GMScreenCog(bot))
