"""Spellcasting calculators (B234-242): /cast cost|time|ceremonial|distance|seek|missile."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.mechanics.magic import (
    casting_time,
    ceremonial_energy,
    effective_spell_cost,
    long_distance_modifier,
    maintenance_cost,
    missile_spell_damage,
    regular_spell_distance_penalty,
)

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)

_MAGIC = discord.Color.purple()

_DISTANCE_UNIT_CHOICES = [
    app_commands.Choice(name="Yards", value="yards"),
    app_commands.Choice(name="Miles", value="miles"),
]


def _fmt_mod(value: int) -> str:
    """Render a signed skill modifier (+0 / -5)."""
    return f"+{value}" if value >= 0 else str(value)


class CalcMagicCog(commands.Cog):
    "GURPS Spellcasting Calculators (Cost, Time, Ceremonial, Range, Missile)."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    # group is "cast", not "spell"; /spell is the reference cog's lookup command
    cast = app_commands.Group(
        name="cast",
        description="Spellcasting Calculators (Cost, Time, Ceremonial, Range, Missile)",
    )

    @cast.command(name="cost", description="Energy Cost to Cast a Spell (B236-240)")
    @app_commands.describe(
        base_cost="The spell's listed energy cost (Area spells: its base cost)",
        skill="Your base skill with the spell (drives the high-skill reduction)",
        size_modifier="Regular spell: subject's Size Modifier (cost x(1+SM) for SM>0)",
        area_radius="Area spell: radius in yards (cost = base x radius)",
        maintain="Optional: listed maintenance cost, to also show the reduced upkeep",
        low_mana="Low-mana area (-5 to base skill for the reduction)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def cost(
        self,
        interaction: discord.Interaction,
        base_cost: float,
        skill: int,
        size_modifier: int = 0,
        area_radius: int = 0,
        maintain: int | None = None,
        low_mana: bool = False,
    ) -> None:
        try:
            result = effective_spell_cost(
                base_cost,
                skill,
                size_modifier=size_modifier,
                area_radius=area_radius,
                low_mana=low_mana,
            )
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        embed = discord.Embed(title="Spell Cost", color=_MAGIC)
        if result.area_radius > 0:
            shape = f"Area, radius {result.area_radius} yd (x{result.area_radius})"
        elif result.size_modifier > 0:
            shape = f"Regular, SM +{result.size_modifier} (x{1 + result.size_modifier})"
        else:
            shape = "Regular, SM 0"
        embed.add_field(name="Spell", value=shape, inline=False)
        embed.add_field(
            name="Scaled Cost", value=f"{result.scaled_cost} FP", inline=True
        )
        embed.add_field(
            name=f"High Skill (≥15)",
            value=f"−{result.reduction}" + (" (low mana −5)" if result.low_mana else ""),
            inline=True,
        )
        embed.add_field(
            name="To Cast", value=f"**{result.final_cost} FP**", inline=True
        )
        if maintain is not None:
            upkeep = maintenance_cost(maintain, skill, low_mana=low_mana)
            embed.add_field(
                name="To Maintain",
                value=f"**{upkeep}**/interval (listed {maintain})",
                inline=False,
            )
        embed.set_footer(text="B236-240 — scale for size/area, then reduce for high skill")
        await interaction.response.send_message(embed=embed)

    @cast.command(name="time", description="Seconds to Cast a Spell (B236-238)")
    @app_commands.describe(
        base_seconds="The spell's listed casting time in seconds (most spells: 1)",
        skill="Your base skill (≤9 doubles time; 20+ halves; 25+ ÷4; …)",
        ceremonial="Ceremonial magic (×10 time, no high-skill reduction)",
        low_mana="Low-mana area (-5 to base skill)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def time(
        self,
        interaction: discord.Interaction,
        base_seconds: int,
        skill: int,
        ceremonial: bool = False,
        low_mana: bool = False,
    ) -> None:
        try:
            seconds = casting_time(
                base_seconds, skill, low_mana=low_mana, ceremonial=ceremonial
            )
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        embed = discord.Embed(title="Casting Time", color=_MAGIC)
        embed.add_field(name="Base", value=f"{base_seconds} s", inline=True)
        embed.add_field(name="At Skill", value=str(skill), inline=True)
        embed.add_field(name="Actual", value=f"**{seconds} s**", inline=True)
        if ceremonial:
            embed.add_field(
                name="Ceremonial",
                value="×10 time; high skill gives no reduction",
                inline=False,
            )
        embed.set_footer(text="B236-238 casting time / ritual tiers")
        await interaction.response.send_message(embed=embed)

    @cast.command(
        name="ceremonial",
        description="Pool Ceremonial Energy + Extra-Energy Skill Bonus (B238)",
    )
    @app_commands.describe(
        spell_cost="The spell's energy cost (after size/area scaling)",
        caster_energy="Energy the lead caster contributes",
        mage_energy="Total energy from assistants who know the spell at 15+ (unlimited each)",
        skilled_nonmages="Non-mages who know the spell at 15+ (3 each)",
        low_skill_mages="Mages who know the spell at ≤14 (3 each)",
        supporters="Supporting spectators (+1 each, max +100)",
        opposers="Opposing spectators (−5 each, max −100)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def ceremonial(
        self,
        interaction: discord.Interaction,
        spell_cost: int,
        caster_energy: int = 0,
        mage_energy: int = 0,
        skilled_nonmages: int = 0,
        low_skill_mages: int = 0,
        supporters: int = 0,
        opposers: int = 0,
    ) -> None:
        try:
            result = ceremonial_energy(
                spell_cost,
                caster_energy=caster_energy,
                mage_energy=mage_energy,
                skilled_nonmages=skilled_nonmages,
                low_skill_mages=low_skill_mages,
                supporters=supporters,
                opposers=opposers,
            )
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        embed = discord.Embed(title="Ceremonial Magic", color=_MAGIC)
        embed.add_field(
            name="Energy Pooled",
            value=f"**{result.total_energy}** vs cost {result.spell_cost}",
            inline=True,
        )
        embed.add_field(
            name="Surplus", value=f"{result.extra_energy}", inline=True
        )
        embed.add_field(
            name="Skill Bonus",
            value=f"**{_fmt_mod(result.skill_bonus)}** to cast",
            inline=True,
        )
        embed.add_field(name="Notes", value=result.coordination_note, inline=False)
        embed.set_footer(text="B238 ceremonial magic — ×10 casting time")
        await interaction.response.send_message(embed=embed)

    @cast.command(
        name="distance",
        description="Skill Penalty to Cast a Regular Spell at Range (B240)",
    )
    @app_commands.describe(
        yards="Distance to the subject in yards",
        can_touch="You can touch the subject (no penalty)",
        can_see="You can see the subject (else a further −5)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def distance(
        self,
        interaction: discord.Interaction,
        yards: float,
        can_touch: bool = False,
        can_see: bool = True,
    ) -> None:
        try:
            penalty = regular_spell_distance_penalty(
                yards, can_touch=can_touch, can_see=can_see
            )
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        embed = discord.Embed(title="Regular-Spell Range", color=_MAGIC)
        embed.add_field(name="Distance", value=f"{yards:g} yd", inline=True)
        embed.add_field(
            name="Skill Penalty", value=f"**{_fmt_mod(penalty)}**", inline=True
        )
        if not can_touch and not can_see:
            embed.add_field(
                name="Note", value="Can't touch or see: extra −5 applied", inline=False
            )
        embed.set_footer(text="B240 — −1/yd if not touching; further −5 if unseen")
        await interaction.response.send_message(embed=embed)

    @cast.command(
        name="seek",
        description="Long-Distance Modifier for an Information/Seek Spell (B241)",
    )
    @app_commands.describe(
        distance="Distance to the subject",
        unit="Whether distance is in yards or miles",
    )
    @app_commands.choices(unit=_DISTANCE_UNIT_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def seek(
        self,
        interaction: discord.Interaction,
        distance: float,
        unit: str = "miles",
    ) -> None:
        try:
            penalty = long_distance_modifier(
                yards=distance if unit == "yards" else None,
                miles=distance if unit == "miles" else None,
            )
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        embed = discord.Embed(title="Long-Distance Modifier", color=_MAGIC)
        embed.add_field(name="Distance", value=f"{distance:g} {unit}", inline=True)
        embed.add_field(
            name="Skill Penalty", value=f"**{_fmt_mod(penalty)}**", inline=True
        )
        embed.set_footer(text="B241 long-distance modifiers (Information spells)")
        await interaction.response.send_message(embed=embed)

    @cast.command(
        name="missile",
        description="Missile-Spell Damage: 1d per Energy, ≤Magery/sec, ≤3 s (B240)",
    )
    @app_commands.describe(
        magery="Your Magery level (max energy per second of casting)",
        seconds="Seconds spent building the missile (1 to cast + up to 2 to enlarge)",
        energy="Energy actually invested (default = the maximum allowed)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def missile(
        self,
        interaction: discord.Interaction,
        magery: int,
        seconds: int = 1,
        energy: int | None = None,
    ) -> None:
        try:
            spec = missile_spell_damage(magery, seconds=seconds, energy=energy)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        capped_seconds = min(seconds, 3)
        embed = discord.Embed(title="Missile Spell", color=_MAGIC)
        embed.add_field(
            name="Damage", value=f"**{spec}** ({spec.min}–{spec.max})", inline=True
        )
        embed.add_field(
            name="Energy",
            value=f"{spec.count} pt (cap {magery}×{capped_seconds}s = {magery * capped_seconds})",
            inline=True,
        )
        embed.set_footer(text="B240 — 1d/energy point, up to Magery per second, max 3 s")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CalcMagicCog(bot))
