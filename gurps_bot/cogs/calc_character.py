"""Derived-stat calculators: /encumbrance, /lifting, /reaction, /ranged, /range, /size."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.mechanics import encumbrance as enc
from gurps_bot.mechanics import lifting as lift
from gurps_bot.mechanics import reaction as react
from gurps_bot.mechanics import speed_range as srng
from gurps_bot.ui.formatters import format_modifier_suffix

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)

# match ui/embeds.py palette
BLUE = discord.Color.blue()
GOLD = discord.Color.gold()
GREEN = discord.Color.green()


def _fmt_weight(lbs: float) -> str:
    """Format a pound weight: drop a trailing .0, otherwise one decimal."""
    rounded = round(lbs, 1)
    if rounded == int(rounded):
        return f"{int(rounded)} lb"
    return f"{rounded:g} lb"


# B560: original one-line glosses per band (not SJG text), keyed by band rank
_REACTION_BLURBS: dict[int, str] = {
    -3: "Hostile — attacks or actively works against you.",
    -2: "Very unfriendly — refuses, may threaten or report you.",
    -1: "Unhelpful — uncooperative, wants you gone.",
    0: "Unimpressed — no help, but no harm either.",
    1: "Indifferent — does the minimum asked, nothing more.",
    2: "Helpful — cooperates and offers modest assistance.",
    3: "Very helpful — goes out of its way to aid you.",
    4: "Devoted — treats your interests as its own.",
}


class CalcCharacterCog(commands.Cog):
    "GURPS Derived Calculators: Encumbrance, Lifting, Reaction, Speed/Range."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="encumbrance",
        description="Basic Lift, Encumbrance Level, Effective Move and Dodge for a Carried Weight",
    )
    @app_commands.describe(
        st="Strength (ST)",
        basic_move="Basic Move (yards/turn)",
        basic_speed="Basic Speed",
        weight="Carried weight in pounds",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def encumbrance(
        self,
        interaction: discord.Interaction,
        st: int,
        basic_move: int,
        basic_speed: float,
        weight: float,
    ) -> None:
        try:
            result = enc.encumbrance_report(st, basic_move, basic_speed, weight)
            thresholds = enc.encumbrance_thresholds(result.basic_lift)
        except ValueError as e:
            await interaction.response.send_message(f"Invalid input: {e}", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Encumbrance — ST {st}, {_fmt_weight(weight)} Carried",
            color=BLUE,
        )
        embed.add_field(name="Basic Lift", value=_fmt_weight(result.basic_lift), inline=True)
        embed.add_field(
            name="Level",
            value=f"**{result.level} — {result.level_name}**",
            inline=True,
        )
        embed.add_field(name="X Move", value=f"{result.move_multiplier:g}", inline=True)
        move_val = "0 (cannot move)" if result.overloaded else str(result.effective_move)
        embed.add_field(name="Effective Move", value=move_val, inline=True)
        embed.add_field(name="Dodge", value=str(result.dodge), inline=True)
        embed.add_field(name="​", value="​", inline=True)

        threshold_lines = [
            f"`{t.level}` **{t.name}** ≤ {_fmt_weight(t.max_weight)} "
            f"(x{t.move_multiplier:g} Move, −{t.dodge_penalty} Dodge)"
            for t in thresholds
        ]
        embed.add_field(name="Bands", value="\n".join(threshold_lines), inline=False)
        embed.set_footer(text="B15/B17")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="lifting",
        description="One/Two-Handed, Overhead, Shove and Drag Capacities for a Strength Score",
    )
    @app_commands.describe(st="Strength (ST)")
    @app_commands.checks.cooldown(2, 5.0)
    async def lifting(self, interaction: discord.Interaction, st: int) -> None:
        try:
            caps = lift.lifting_capacities(st)
        except (ValueError, TypeError) as e:
            await interaction.response.send_message(f"Invalid input: {e}", ephemeral=True)
            return

        embed = discord.Embed(title=f"Lifting & Moving — ST {st}", color=BLUE)
        embed.add_field(name="Basic Lift", value=_fmt_weight(caps.basic_lift), inline=True)
        embed.add_field(
            name=f"One-Handed Lift ({caps.one_handed_lift_seconds}s)",
            value=_fmt_weight(caps.one_handed_lift),
            inline=True,
        )
        embed.add_field(
            name=f"Two-Handed / Overhead ({caps.two_handed_lift_seconds}s)",
            value=_fmt_weight(caps.two_handed_lift),
            inline=True,
        )
        embed.add_field(name="Shove", value=_fmt_weight(caps.shove), inline=True)
        embed.add_field(
            name="Shove (Running Start)",
            value=_fmt_weight(caps.shove_running),
            inline=True,
        )
        embed.add_field(name="Drag", value=_fmt_weight(caps.drag), inline=True)
        embed.set_footer(text="B353")
        await interaction.response.send_message(embed=embed)

    reaction = app_commands.Group(name="reaction", description="GURPS Reaction-Roll Helpers (B560)")

    @reaction.command(name="roll", description="Roll 3d + Modifier and Read the Reaction Band")
    @app_commands.describe(modifier="Net reaction modifier (bonus + / penalty -)")
    @app_commands.checks.cooldown(2, 5.0)
    async def reaction_roll(self, interaction: discord.Interaction, modifier: int = 0) -> None:
        result = react.roll_reaction(modifier)
        dice_str = " + ".join(str(d) for d in result.roll.dice)
        embed = discord.Embed(
            title=f"Reaction Roll{format_modifier_suffix(modifier)}",
            color=GOLD,
        )
        embed.add_field(
            name="Rolled",
            value=f"**{result.roll.total}** ({dice_str})",
            inline=True,
        )
        embed.add_field(name="Adjusted Total", value=str(result.total), inline=True)
        embed.add_field(name="Reaction", value=f"**{result.band.name}**", inline=False)
        embed.add_field(
            name="Meaning",
            value=_REACTION_BLURBS.get(result.band.rank, "​"),
            inline=False,
        )
        embed.set_footer(text="B560")
        await interaction.response.send_message(embed=embed)

    @reaction.command(name="band", description="Look up the Reaction Band for an Adjusted Total")
    @app_commands.describe(total="Adjusted reaction total (3d + modifiers, already summed)")
    @app_commands.checks.cooldown(2, 5.0)
    async def reaction_band(self, interaction: discord.Interaction, total: int) -> None:
        band = react.reaction_band(total)
        embed = discord.Embed(title=f"Reaction Band — Total {total}", color=GOLD)
        embed.add_field(name="Reaction", value=f"**{band.name}**", inline=True)
        if band.lower <= -(10**8):
            range_str = f"≤ {band.upper}"
        elif band.upper >= 10**8:
            range_str = f"≥ {band.lower}"
        else:
            range_str = f"{band.lower}–{band.upper}"
        embed.add_field(name="Range", value=range_str, inline=True)
        embed.add_field(
            name="Meaning",
            value=_REACTION_BLURBS.get(band.rank, "​"),
            inline=False,
        )
        embed.set_footer(text="B560")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="ranged",
        description="Combined Ranged-Attack to-Hit Modifier (Range + Speed + Size)",
    )
    @app_commands.describe(
        distance="Distance to target in yards",
        target_size="Target's longest dimension in yards",
        target_speed="Target's speed in yards/second (0 if stationary)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def ranged(
        self,
        interaction: discord.Interaction,
        distance: float,
        target_size: float,
        target_speed: float = 0.0,
    ) -> None:
        try:
            mod = srng.ranged_hit_modifier(distance, target_size, target_speed)
        except ValueError as e:
            await interaction.response.send_message(f"Invalid input: {e}", ephemeral=True)
            return

        embed = discord.Embed(title="Ranged to-Hit Modifier", color=GREEN)
        embed.add_field(name="Speed/Range", value=f"{mod.speed_range_modifier:+d}", inline=True)
        embed.add_field(name="Size", value=f"{mod.size_modifier:+d}", inline=True)
        embed.add_field(name="Net Modifier", value=f"**{mod.total:+d}**", inline=False)
        embed.set_footer(
            text=f"{mod.distance_yards:g}yd • size {mod.target_size_yards:g}yd "
            f"• {mod.target_speed_yards_per_second:g}yd/s • B550"
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="range",
        description="Speed/Range Table Penalty for a Distance in Yards",
    )
    @app_commands.describe(yards="Distance in yards")
    @app_commands.checks.cooldown(2, 5.0)
    async def range_mod(self, interaction: discord.Interaction, yards: float) -> None:
        try:
            mod = srng.range_modifier(yards)
        except ValueError as e:
            await interaction.response.send_message(f"Invalid input: {e}", ephemeral=True)
            return

        embed = discord.Embed(title=f"Range Modifier — {yards:g} yd", color=GREEN)
        embed.add_field(name="Modifier", value=f"**{mod:+d}**", inline=True)
        embed.set_footer(text="B550")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="size",
        description="Size Modifier (SM) for an Object's Longest Dimension in Yards",
    )
    @app_commands.describe(longest_dimension="Longest dimension in yards")
    @app_commands.checks.cooldown(2, 5.0)
    async def size_mod(self, interaction: discord.Interaction, longest_dimension: float) -> None:
        try:
            sm = srng.size_modifier(longest_dimension)
        except ValueError as e:
            await interaction.response.send_message(f"Invalid input: {e}", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Size Modifier — {longest_dimension:g} yd",
            color=GREEN,
        )
        embed.add_field(name="SM", value=f"**{sm:+d}**", inline=True)
        embed.set_footer(text="B550/B19")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CalcCharacterCog(bot))
