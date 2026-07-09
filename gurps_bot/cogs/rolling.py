"""Dice rolling and skill/attribute check cog."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot
from discord import app_commands
from discord.ext import commands

from gurps_bot.mechanics.checks import check, contest
from gurps_bot.mechanics.damage import (
    DAMAGE_TYPE_DISPLAY,
    HIT_LOCATION_NAMES,
    roll_damage,
)
from gurps_bot.mechanics.dice import parse_dice, roll
from gurps_bot.mechanics.tables import fright_check_effect
from gurps_bot.services.characters import (
    get_active_character,
    get_character_attrs,
    get_character_skills,
)
from gurps_bot.ui import embeds
from gurps_bot.ui.formatters import format_modifier_suffix
from gurps_bot.utils._cache_instances import skill_cache as _skill_cache
from gurps_bot.utils.fuzzy import fuzzy_match

log = logging.getLogger(__name__)

ROLLABLE_ATTRS = {"st", "dx", "iq", "ht", "will", "per", "hp", "fp", "vision", "hearing", "taste_smell", "touch", "fright_check"}
ATTR_DISPLAY = {
    "st": "ST", "dx": "DX", "iq": "IQ", "ht": "HT",
    "will": "Will", "per": "Per", "hp": "HP", "fp": "FP",
    "vision": "Vision", "hearing": "Hearing",
    "taste_smell": "Taste/Smell", "touch": "Touch",
    "fright_check": "Fright Check",
}

DAMAGE_TYPE_CHOICES = [
    app_commands.Choice(name=display, value=key)
    for key, display in DAMAGE_TYPE_DISPLAY.items()
]

LOCATION_CHOICES = [
    app_commands.Choice(name=loc, value=loc.lower())
    for loc in HIT_LOCATION_NAMES
]

async def _skill_attr_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if not interaction.guild_id:
        return []

    cache_key = (interaction.user.id, interaction.guild_id)
    candidates = _skill_cache.get(cache_key)

    if candidates is None:
        async with interaction.client.db() as session:
            char = await get_active_character(session, interaction.user.id, interaction.guild_id)
            if not char:
                return []

            candidates = []
            attrs = await get_character_attrs(session, char.id)
            for attr_id in ROLLABLE_ATTRS:
                if attr_id in attrs:
                    candidates.append(ATTR_DISPLAY.get(attr_id, attr_id))

            skills = await get_character_skills(session, char.id)
            for s in skills:
                candidates.append(s.display_name)

        _skill_cache.set(cache_key, candidates)

    if not current:
        return [app_commands.Choice(name=c, value=c) for c in candidates[:25]]

    matches = fuzzy_match(current, candidates, limit=25, score_cutoff=40)
    return [app_commands.Choice(name=m, value=m) for m, _ in matches]


async def _resolve_target(
    interaction: discord.Interaction,
    target_str: str,
    *,
    use_followup: bool = False,
) -> tuple[int, str] | None:
    """Try raw int, then attribute, then fuzzy skill; sends the error itself and returns None on failure."""
    async def _send_error(msg: str) -> None:
        if use_followup:
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    try:
        value = int(target_str)
        return value, f"Target {value}"
    except ValueError:
        pass

    if not interaction.guild_id:
        await _send_error("Character lookup requires a server. Use a raw number in DMs.")
        return None

    async with interaction.client.db() as session:
        char = await get_active_character(session, interaction.user.id, interaction.guild_id)
        if not char:
            await _send_error("No active character. Use `/import` first.")
            return None

        target_lower = target_str.lower()
        attr_map = {v.lower(): k for k, v in ATTR_DISPLAY.items()}
        if target_lower in attr_map:
            attr_id = attr_map[target_lower]
            attrs = await get_character_attrs(session, char.id)
            if attr_id not in attrs:
                await _send_error(f"Attribute **{target_str}** not found.")
                return None
            return int(attrs[attr_id]), f"{char.name} — {ATTR_DISPLAY[attr_id]}"

        skills = await get_character_skills(session, char.id)
        skill_names = [s.display_name for s in skills]
        matches = fuzzy_match(target_str, skill_names, limit=1, score_cutoff=50)
        if not matches:
            await _send_error(f"No skill or attribute matching **{target_str}**.")
            return None

        matched_name = matches[0][0]
        skill = next(s for s in skills if s.display_name == matched_name)
        return skill.level, f"{char.name} — {skill.display_name}"


class RollingCog(commands.Cog):
    "Dice Rolling and GURPS Checks."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.command(name="roll", description="Roll Dice (e.g. 3d6, 2d+1, 4d6+3)")
    @app_commands.describe(
        dice="Dice expression (e.g. 3d6, 2d+1, 1d-2)",
        hidden="Roll in secret (GM blind roll): only you see the result",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def roll_dice(
        self, interaction: discord.Interaction, dice: str, hidden: bool = False,
    ) -> None:
        try:
            spec = parse_dice(dice)
        except ValueError as e:
            await interaction.response.send_message(f"Invalid dice: {e}", ephemeral=True)
            return

        result = roll(spec)
        embed = embeds.roll_embed(result)
        await interaction.response.send_message(embed=embed, ephemeral=hidden)

    @app_commands.command(name="check", description="Roll 3d6 vs a Skill or Attribute")
    @app_commands.describe(
        target="Skill or attribute name (or raw number)",
        modifier="Bonus (+) or penalty (-) to the roll",
        hidden="Roll in secret (GM blind roll): only you see the result",
    )
    @app_commands.autocomplete(target=_skill_attr_autocomplete)
    @app_commands.checks.cooldown(2, 5.0)
    async def check_roll(
        self,
        interaction: discord.Interaction,
        target: str,
        modifier: int = 0,
        hidden: bool = False,
    ) -> None:
        resolved = await _resolve_target(interaction, target)
        if resolved is None:
            return  # error already sent

        target_value, label = resolved
        label += f" Check{format_modifier_suffix(modifier)}"
        result = check(target_value, modifier)
        embed = embeds.check_embed(result, label)
        await interaction.response.send_message(embed=embed, ephemeral=hidden)

    @app_commands.command(name="contest", description="Quick Contest Between Two Targets")
    @app_commands.describe(
        target_a="First side's target number or skill name",
        target_b="Second side's target number or skill name",
        label_a="Label for first side",
        label_b="Label for second side",
        hidden="Roll in secret (GM blind roll): only you see the result",
    )
    @app_commands.autocomplete(target_a=_skill_attr_autocomplete, target_b=_skill_attr_autocomplete)
    @app_commands.checks.cooldown(2, 5.0)
    async def contest_roll(
        self,
        interaction: discord.Interaction,
        target_a: str,
        target_b: str,
        label_a: str = "Side A",
        label_b: str = "Side B",
        hidden: bool = False,
    ) -> None:
        await interaction.response.defer(ephemeral=hidden)

        resolved_a = await _resolve_target(interaction, target_a, use_followup=True)
        if resolved_a is None:
            return
        val_a, resolved_label_a = resolved_a
        if label_a == "Side A":
            label_a = resolved_label_a

        resolved_b = await _resolve_target(interaction, target_b, use_followup=True)
        if resolved_b is None:
            return
        val_b, resolved_label_b = resolved_b
        if label_b == "Side B":
            label_b = resolved_label_b

        result_a, result_b, winner = contest(val_a, val_b)
        embed = embeds.contest_embed(result_a, result_b, winner, label_a, label_b)
        await interaction.followup.send(embed=embed, ephemeral=hidden)

    @app_commands.checks.cooldown(2, 5.0)
    @app_commands.command(name="fright-check", description="Roll a Fright Check")
    @app_commands.describe(
        modifier="Bonus or penalty to the fright check",
        hidden="Roll in secret (GM blind roll): only you see the result",
    )
    async def fright_check(
        self,
        interaction: discord.Interaction,
        modifier: int = 0,
        hidden: bool = False,
    ) -> None:
        if interaction.guild_id:
            async with interaction.client.db() as session:
                char = await get_active_character(session, interaction.user.id, interaction.guild_id)
                if char:
                    attrs = await get_character_attrs(session, char.id)
                    will_value = int(attrs.get("will", attrs.get("iq", 10)))
                    label = f"{char.name} — Fright Check"
                else:
                    will_value = 10
                    label = "Fright Check (Will 10)"
        else:
            will_value = 10
            label = "Fright Check (Will 10)"

        label += format_modifier_suffix(modifier)

        result = check(will_value, modifier)
        effect = ""
        if not result.outcome.succeeded:
            mof = abs(result.margin)
            effect = fright_check_effect(mof)

        embed = embeds.fright_check_embed(result, effect)
        await interaction.response.send_message(embed=embed, ephemeral=hidden)

    @app_commands.command(name="damage", description="Roll Damage Dice With Type")
    @app_commands.describe(
        dice="Damage dice (e.g. 2d+1)",
        damage_type="Damage type (cr, cut, imp, pi, burn, etc.)",
        dr="Damage resistance to subtract",
        location="Hit location for wounding modifier",
        hidden="Roll in secret (GM blind roll): only you see the result",
    )
    @app_commands.choices(damage_type=DAMAGE_TYPE_CHOICES, location=LOCATION_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def damage_roll(
        self,
        interaction: discord.Interaction,
        dice: str,
        damage_type: str = "cr",
        dr: app_commands.Range[int, 0, 100000] = 0,
        location: str | None = None,
        hidden: bool = False,
    ) -> None:
        try:
            result = roll_damage(dice, damage_type, dr=dr, location=location)
        except ValueError as e:
            await interaction.response.send_message(f"Invalid dice: {e}", ephemeral=True)
            return

        embed = embeds.damage_embed(result)
        await interaction.response.send_message(embed=embed, ephemeral=hidden)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RollingCog(bot))
