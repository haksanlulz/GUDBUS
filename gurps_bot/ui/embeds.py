"""Discord embed builders for character sheets, rolls, and lookups."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from gurps_bot.mechanics.checks import CheckResult, Outcome
from gurps_bot.mechanics.damage import DamageResult, HitLocationResult
from gurps_bot.mechanics.dice import RollResult
from gurps_bot.ui.formatters import format_attr_block, format_combatant_line

if TYPE_CHECKING:
    from gurps_bot.db.models import Combat, Combatant

GREEN = discord.Color.green()
RED = discord.Color.red()
DARK_RED = discord.Color.dark_red()
GOLD = discord.Color.gold()
BLUE = discord.Color.blue()
GREY = discord.Color.greyple()
COMBAT_ORANGE = discord.Color.dark_orange()
EMBED_DESC_LIMIT = 4096
EMBED_FIELD_LIMIT = 1024


def turn_announcement(
    combatant: "Combatant | None", note: str | None = None,
) -> str | None:
    """Turn-advance line for message content — a mention only pings from content, never from an embed."""
    parts: list[str] = []
    if note:
        parts.append(note)
    if combatant is not None:
        if combatant.discord_user_id is not None:
            parts.append(f"<@{combatant.discord_user_id}>, your turn!")
        else:
            parts.append(f"**{combatant.name}**'s turn.")
    return "\n".join(parts) if parts else None


def _outcome_color(outcome: Outcome) -> discord.Color:
    if outcome == Outcome.CRITICAL_SUCCESS:
        return GOLD
    if outcome == Outcome.SUCCESS:
        return GREEN
    if outcome == Outcome.CRITICAL_FAILURE:
        return DARK_RED
    return RED


def char_summary_embed(
    name: str,
    total_points: int,
    attrs: dict[str, float],
    calc: dict,
    source: str,
) -> discord.Embed:
    embed = discord.Embed(title=name, color=BLUE)
    attr_text = format_attr_block(attrs, calc)
    if len(attr_text) > EMBED_FIELD_LIMIT:
        attr_text = attr_text[:EMBED_FIELD_LIMIT - 20] + "\n*...truncated*"
    embed.add_field(
        name="Attributes",
        value=attr_text,
        inline=False,
    )
    dodge = calc.get("dodge", [])
    if dodge:
        embed.add_field(name="Dodge", value=str(dodge[0]), inline=True)
    bl = calc.get("basic_lift", "?")
    embed.add_field(name="Basic Lift", value=str(bl), inline=True)
    embed.add_field(name="Points", value=str(total_points), inline=True)
    embed.set_footer(text=f"Source: {source}")
    return embed


def char_list_embed(characters: list[tuple[str, int, bool]]) -> discord.Embed:
    """Items are (name, points, is_active)."""
    embed = discord.Embed(title="Your Characters", color=BLUE)
    if not characters:
        embed.description = "*No characters imported yet. Use `/import` to add one.*"
        return embed
    lines = []
    for name, points, active in characters:
        marker = " **[active]**" if active else ""
        lines.append(f"- {name} ({points} pts){marker}")
    description = "\n".join(lines)
    if len(description) > EMBED_DESC_LIMIT:
        description = description[:EMBED_DESC_LIMIT - 40] + "\n*...truncated*"
    embed.description = description
    return embed


def roll_embed(result: RollResult, label: str | None = None) -> discord.Embed:
    title = f"Roll: {result.spec}" if not label else label
    embed = discord.Embed(title=title, color=GREY)
    dice_str = " + ".join(str(d) for d in result.dice)
    if result.spec.modifier:
        sign = "+" if result.spec.modifier > 0 else ""
        dice_str += f" {sign}{result.spec.modifier}"
    embed.add_field(name="Dice", value=dice_str, inline=True)
    embed.add_field(name="Total", value=f"**{result.total}**", inline=True)
    return embed


def check_embed(result: CheckResult, label: str) -> discord.Embed:
    embed = discord.Embed(
        title=label,
        color=_outcome_color(result.outcome),
    )
    dice_str = " + ".join(str(d) for d in result.roll_result.dice)
    embed.add_field(name="Rolled", value=f"**{result.rolled}** ({dice_str})", inline=True)
    embed.add_field(name="Target", value=str(result.target), inline=True)

    margin_sign = "+" if result.margin >= 0 else ""
    embed.add_field(name="Margin", value=f"{margin_sign}{result.margin}", inline=True)

    embed.add_field(name="Result", value=f"**{result.outcome.value}**", inline=False)
    return embed


def damage_embed(result: DamageResult) -> discord.Embed:
    embed = discord.Embed(title=f"Damage: {result.roll_result.spec} {result.damage_type}", color=RED)
    dice_str = " + ".join(str(d) for d in result.roll_result.dice)
    embed.add_field(name="Rolled", value=f"{dice_str} = {result.roll_result.total}", inline=True)
    embed.add_field(name="After DR", value=str(result.raw_damage), inline=True)
    embed.add_field(
        name="Wound",
        value=f"**{result.wound}** (x{result.wounding_multiplier})",
        inline=True,
    )
    if result.location:
        embed.add_field(name="Location", value=result.location, inline=True)
    return embed


def hit_location_embed(result: HitLocationResult) -> discord.Embed:
    embed = discord.Embed(title="Hit Location", color=BLUE)
    embed.add_field(name="Rolled", value=str(result.rolled), inline=True)
    embed.add_field(name="Location", value=result.location, inline=True)
    embed.add_field(name="Hit Penalty", value=str(result.hit_penalty), inline=True)
    return embed


def contest_embed(
    result_a: CheckResult,
    result_b: CheckResult,
    winner: str,
    label_a: str,
    label_b: str,
) -> discord.Embed:
    embed = discord.Embed(title="Quick Contest", color=GOLD)

    margin_a = f"+{result_a.margin}" if result_a.margin >= 0 else str(result_a.margin)
    margin_b = f"+{result_b.margin}" if result_b.margin >= 0 else str(result_b.margin)

    embed.add_field(
        name=label_a,
        value=f"Rolled **{result_a.rolled}** vs {result_a.target} (margin {margin_a})",
        inline=False,
    )
    embed.add_field(
        name=label_b,
        value=f"Rolled **{result_b.rolled}** vs {result_b.target} (margin {margin_b})",
        inline=False,
    )

    if winner == "Tie":
        winner_text = "**Tie!**"
    else:
        winner_text = f"**{label_a if winner == 'A' else label_b} wins!**"
    embed.add_field(name="Winner", value=winner_text, inline=False)
    return embed


def fright_check_embed(result: CheckResult, effect: str) -> discord.Embed:
    embed = discord.Embed(
        title="Fright Check",
        color=_outcome_color(result.outcome),
    )
    dice_str = " + ".join(str(d) for d in result.roll_result.dice)
    embed.add_field(name="Rolled", value=f"**{result.rolled}** ({dice_str})", inline=True)
    embed.add_field(name="Target", value=str(result.target), inline=True)
    embed.add_field(name="Result", value=f"**{result.outcome.value}**", inline=True)
    if not result.outcome.succeeded:
        embed.add_field(name="Effect", value=effect, inline=False)
    return embed


def paginated_list_embed(
    title: str,
    content: str,
    page: int,
    total_pages: int,
    char_name: str,
) -> discord.Embed:
    embed = discord.Embed(title=f"{char_name} — {title}", color=BLUE)
    embed.description = content
    if total_pages > 1:
        embed.set_footer(text=f"Page {page}/{total_pages}")
    return embed


def combat_tracker_embed(combat: Combat) -> discord.Embed:
    from gurps_bot.mechanics.combat_constants import StatusEffect
    from gurps_bot.services.combat import current_combatant, ordered_combatants

    ordered = ordered_combatants(combat)
    current = current_combatant(combat)
    embed = discord.Embed(
        title=f"Combat \u2014 Round {combat.round_number}",
        color=COMBAT_ORANGE,
    )

    if not ordered:
        embed.description = "*No combatants yet. Use `/combat join` or `/combat add-npc`.*"
        return embed

    lines = []
    for c in ordered:
        effects = set(c.status_effects or [])
        is_out = StatusEffect.DEAD in effects or StatusEffect.UNCONSCIOUS in effects
        lines.append(format_combatant_line(
            name=c.name,
            basic_speed=c.basic_speed,
            hp_current=c.hp_current,
            hp_max=c.hp_max,
            fp_current=c.fp_current,
            fp_max=c.fp_max,
            status_effects=c.status_effects or [],
            maneuver=c.maneuver,
            is_current=(c is current),
            is_out=is_out,
        ))

    description = "\n".join(lines)
    if len(description) > EMBED_DESC_LIMIT:
        description = description[:EMBED_DESC_LIMIT - 40] + "\n*...truncated*"
    embed.description = description
    embed.set_footer(text="/combat hp, /combat status, /combat maneuver")
    return embed
