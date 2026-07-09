"""Posture (B551) and deliberate hit-location (B552) lookups: /posture, /target."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.mechanics.hit_location import deliberate_locations, hit_location
from gurps_bot.mechanics.posture import posture, posture_names

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)

_POSTURE_COLOR = discord.Color.dark_red()
_TARGET_COLOR = discord.Color.dark_red()
_FOOTER = "GURPS facts per SJG Online Policy - see /legal"

# both lists sit under discord's 25-choice cap
_POSTURE_CHOICES = [
    app_commands.Choice(name=name, value=name) for name in posture_names()
]
_TARGET_CHOICES = [
    app_commands.Choice(name=loc.name, value=loc.name) for loc in deliberate_locations()
]


def _move_label(fraction: float) -> str:
    """Render a Move fraction compactly (mirrors the GM-screen label)."""
    if fraction >= 1.0:
        return "full"
    if fraction <= 0.0:
        return "none (cannot move)"
    if abs(fraction - 2 / 3) < 1e-6:
        return "×2/3"
    if abs(fraction - 1 / 3) < 1e-6:
        return "×1/3"
    return f"×{fraction:.2g}"


def build_posture_embed(name: str) -> discord.Embed:
    """Embed for one posture's B551 modifiers; unknown names get a help embed, not an error."""
    try:
        p = posture(name)
    except KeyError:
        e = discord.Embed(
            title="Unknown posture",
            description="Pick one of: " + ", ".join(posture_names()) + ".",
            color=_POSTURE_COLOR,
        )
        e.set_footer(text=_FOOTER)
        return e

    e = discord.Embed(title=f"Posture - {p.name} (B551)", color=_POSTURE_COLOR)
    e.add_field(name="Your melee attack", value=f"{p.attack_penalty:+d}", inline=True)
    e.add_field(name="Your active defense", value=f"{p.defense_modifier:+d}", inline=True)
    e.add_field(name="Your Move", value=_move_label(p.move_fraction), inline=True)
    e.add_field(
        name="To hit YOU (ranged)", value=f"{p.ranged_to_hit_you:+d}", inline=True
    )
    e.add_field(
        name="To hit YOU (melee)", value=f"{p.melee_to_hit_you:+d}", inline=True
    )
    e.add_field(name="Notes", value=p.effect, inline=False)
    e.set_footer(text=_FOOTER)
    return e


def build_target_embed(name: str) -> discord.Embed:
    """Embed for one B552 deliberate location; unknown names get a help embed."""
    try:
        loc = hit_location(name)
    except KeyError:
        names = ", ".join(l.name for l in deliberate_locations())
        e = discord.Embed(
            title="Unknown target location",
            description=f"Deliberate targets: {names}.",
            color=_TARGET_COLOR,
        )
        e.set_footer(text=_FOOTER)
        return e

    e = discord.Embed(title=f"Targeting - {loc.name} (B552)", color=_TARGET_COLOR)
    e.add_field(name="To-hit penalty", value=str(loc.penalty), inline=True)
    kind = "Deliberate only" if loc.deliberate_only else "Also on random table"
    e.add_field(name="Availability", value=kind, inline=True)
    e.add_field(name="Effect", value=loc.effect, inline=False)
    e.set_footer(text=_FOOTER)
    return e


class BodyRefCog(commands.Cog):
    "Posture and Deliberate-Targeting Quick Lookups."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="posture",
        description="Look Up a GURPS Posture's Combat Modifiers (B551)",
    )
    @app_commands.describe(name="Which posture")
    @app_commands.choices(name=_POSTURE_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def posture(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.send_message(
            embed=build_posture_embed(name), ephemeral=True
        )

    @app_commands.command(
        name="target",
        description="Look Up a Deliberate Hit Location's Penalty + Effect (B552)",
    )
    @app_commands.describe(location="Which deliberate hit location")
    @app_commands.choices(location=_TARGET_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def target(self, interaction: discord.Interaction, location: str) -> None:
        await interaction.response.send_message(
            embed=build_target_embed(location), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BodyRefCog(bot))
