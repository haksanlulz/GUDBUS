"""Combat-physics calculators: /calc fall|collision|explosion|knockback."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.mechanics.collision import (
    CollisionAngle,
    CollisionParty,
    resolve_collision,
)
from gurps_bot.mechanics.dice import DiceSpec
from gurps_bot.mechanics.explosion import explosion_report
from gurps_bot.mechanics.fall import compute_fall
from gurps_bot.mechanics.knockback import calc_knockback

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)

# mirror ui/embeds palette
_PHYSICS = discord.Color.dark_orange()
_RED = discord.Color.red()

_SURFACE_CHOICES = [
    app_commands.Choice(name="Hard (2x HP)", value="hard"),
    app_commands.Choice(name="Soft (1x HP)", value="soft"),
]

_ANGLE_CHOICES = [
    app_commands.Choice(name="Head-on (Speeds Add)", value="head-on"),
    app_commands.Choice(name="Rear-End (Speeds Subtract)", value="rear-end"),
    app_commands.Choice(name="Side-on / Moving-vs-Stationary", value="side-on"),
]

_ENVIRONMENT_CHOICES = [
    app_commands.Choice(name="Normal Air (÷3/yd)", value="normal"),
    app_commands.Choice(name="Underwater (÷1/yd)", value="underwater"),
    app_commands.Choice(name="Vacuum / Trace (÷10/yd)", value="vacuum"),
]

# B378: only cr (always) and cut that fails to penetrate DR cause knockback
_KNOCKBACK_TYPE_CHOICES = [
    app_commands.Choice(name="Crushing (cr)", value="cr"),
    app_commands.Choice(name="Cutting (cut)", value="cut"),
]


def _spec_line(spec: DiceSpec) -> str:
    """Render a DiceSpec with its average/min/max for an embed field."""
    return f"**{spec}** (avg {spec.average:g}, {spec.min}–{spec.max})"


# one line per distance lands in a single 1024-char embed field; unbounded
# input overflows it and the send dies with a generic error
_MAX_DISTANCES = 20


def _parse_distances(raw: str) -> list[int]:
    """Parse comma/space-separated non-negative yard distances; ValueError on bad input."""
    tokens = [t for t in raw.replace(",", " ").split() if t]
    if not tokens:
        raise ValueError("Provide at least one distance in yards.")
    if len(tokens) > _MAX_DISTANCES:
        raise ValueError(
            f"Too many distances ({len(tokens)}; max {_MAX_DISTANCES}). "
            "List a handful of yard bands, not a long sweep."
        )
    distances: list[int] = []
    for tok in tokens:
        try:
            d = int(tok)
        except ValueError:
            raise ValueError(f"`{tok}` is not a whole number of yards.") from None
        if d < 0:
            raise ValueError(f"Distance cannot be negative: {d}.")
        distances.append(d)
    return distances


class CalcCombatCog(commands.Cog):
    "GURPS Combat-Physics Calculators (Fall, Collision, Explosion, Knockback)."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    calc = app_commands.Group(
        name="calc",
        description="Combat-Physics Calculators (Fall, Collision, Explosion, Knockback)",
    )

    @calc.command(name="fall", description="Falling Damage From a Height (B431)")
    @app_commands.describe(
        height="Distance fallen (number)",
        unit="Whether height is in yards or feet",
        hp="Faller's HP (drives the damage dice)",
        dr="Damage Resistance subtracted if rolling",
        surface="Hard ground (2x HP) or soft (1x HP)",
        gravity="Local gravity in Gs (Earth = 1)",
        catfall="Faller has the Catfall advantage (B41)",
        acrobatics="A successful Acrobatics roll was made (controlled fall)",
        do_roll="Also roll the damage dice now",
    )
    @app_commands.choices(unit=[
        app_commands.Choice(name="Yards", value="yards"),
        app_commands.Choice(name="Feet", value="feet"),
    ], surface=_SURFACE_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def fall(
        self,
        interaction: discord.Interaction,
        height: float,
        hp: int,
        unit: str = "yards",
        dr: int = 0,
        surface: str = "hard",
        gravity: float = 1.0,
        catfall: bool = False,
        acrobatics: bool = False,
        do_roll: bool = False,
    ) -> None:
        if height < 0:
            await interaction.response.send_message(
                "Height cannot be negative.", ephemeral=True
            )
            return
        if hp <= 0:
            await interaction.response.send_message(
                "HP must be positive.", ephemeral=True
            )
            return

        try:
            result = compute_fall(
                distance_yards=height if unit == "yards" else None,
                distance_feet=height if unit == "feet" else None,
                hp=hp,
                dr=dr,
                gravity=gravity,
                surface=surface,
                acrobatics_success=acrobatics,
                has_catfall=catfall,
                roll_damage=do_roll,
            )
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Fall — {result.distance_yards:g} yd",
            color=_PHYSICS,
        )
        eff_note = (
            f" (effective {result.effective_distance_yards:g} yd)"
            if result.effective_distance_yards != result.distance_yards
            else ""
        )
        embed.add_field(
            name="Velocity",
            value=f"{result.velocity} yd/s{eff_note}",
            inline=True,
        )
        embed.add_field(
            name="Surface",
            value=f"{result.surface} (x{result.hp_multiplier} HP)",
            inline=True,
        )
        embed.add_field(
            name="Damage",
            value=f"{result.dice_float:g}d → {_spec_line(result.dice)} {result.damage_type}",
            inline=False,
        )
        flags = []
        if result.has_catfall:
            flags.append("Catfall (½ dmg)")
        if result.acrobatics_success:
            flags.append("Acrobatics (−5 yd)")
        if flags:
            embed.add_field(name="Modifiers", value=", ".join(flags), inline=False)

        if result.roll_result is not None:
            roll_dice = " + ".join(str(d) for d in result.roll_result.dice)
            line = f"{roll_dice} = **{result.roll_result.total}**"
            if result.total_dr:
                line += f" − {result.total_dr} DR = {result.penetrating_damage} pen"
            else:
                line += f" ({result.penetrating_damage} pen)"
            if result.blunt_trauma:
                line += f", {result.blunt_trauma} blunt trauma"
            embed.add_field(name="Rolled", value=line, inline=False)

        embed.set_footer(text="B431 falling damage — always crushing")
        await interaction.response.send_message(embed=embed)

    @calc.command(
        name="collision",
        description="Two-Body Collision / Vehicle Slam Damage (B430)",
    )
    @app_commands.describe(
        striker_hp="Striking body's HP",
        striker_velocity="Striking body's speed in yd/s (2 mph = 1 yd/s)",
        struck_hp="Struck body's HP",
        struck_velocity="Struck body's speed in yd/s (0 if stationary)",
        angle="Relative geometry (sets the shared closing velocity)",
        striker_streamlined="Striker is streamlined/sharp (half damage, alt type)",
        struck_streamlined="Struck body is streamlined/sharp (half damage, alt type)",
    )
    @app_commands.choices(angle=_ANGLE_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def collision(
        self,
        interaction: discord.Interaction,
        striker_hp: int,
        striker_velocity: int,
        struck_hp: int,
        struck_velocity: int = 0,
        angle: str = "side-on",
        striker_streamlined: bool = False,
        struck_streamlined: bool = False,
    ) -> None:
        if striker_hp <= 0 or struck_hp <= 0:
            await interaction.response.send_message(
                "Both bodies need positive HP.", ephemeral=True
            )
            return
        if striker_velocity < 0 or struck_velocity < 0:
            await interaction.response.send_message(
                "Velocities cannot be negative.", ephemeral=True
            )
            return

        try:
            result = resolve_collision(
                CollisionParty(
                    hp=striker_hp,
                    velocity=striker_velocity,
                    streamlined=striker_streamlined,
                ),
                CollisionParty(
                    hp=struck_hp,
                    velocity=struck_velocity,
                    streamlined=struck_streamlined,
                ),
                CollisionAngle(angle),
            )
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        embed = discord.Embed(
            title="Collision / Slam",
            description=f"Closing velocity **{result.collision_velocity}** yd/s ({angle})",
            color=_PHYSICS,
        )
        embed.add_field(
            name=f"Striker ({striker_hp} HP) Inflicts",
            value=f"{_spec_line(result.striker_damage)} {result.striker_type}",
            inline=False,
        )
        struck_line = f"{_spec_line(result.struck_damage)} {result.struck_type}"
        if result.struck_dice_capped:
            struck_line += "\n*capped to striker's dice (B431)*"
        embed.add_field(
            name=f"Struck ({struck_hp} HP) Inflicts",
            value=struck_line,
            inline=False,
        )
        if result.overrun_thrust_st is not None:
            embed.add_field(
                name="Overrun (B432)",
                value=f"Striker gains thrust at ST {result.overrun_thrust_st}",
                inline=False,
            )
        embed.set_footer(text="B430/B371 — (HP × velocity) ÷ 100 crushing each way")
        await interaction.response.send_message(embed=embed)

    @calc.command(
        name="explosion",
        description="Concussion Falloff + Fragmentation Danger Radius (B414)",
    )
    @app_commands.describe(
        basic_damage="Pre-rolled basic explosion damage (roll the dice yourself)",
        distances="Yards from center to evaluate, e.g. '0 2 5 10'",
        frag_dice="Fragmentation dice COUNT (the N in [Nd]); omit if none",
        environment="Medium (sets the per-yard concussion divisor)",
    )
    @app_commands.choices(environment=_ENVIRONMENT_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def explosion(
        self,
        interaction: discord.Interaction,
        basic_damage: int,
        distances: str,
        frag_dice: int | None = None,
        environment: str = "normal",
    ) -> None:
        if basic_damage < 0:
            await interaction.response.send_message(
                "Basic damage cannot be negative.", ephemeral=True
            )
            return
        if frag_dice is not None and frag_dice < 1:
            await interaction.response.send_message(
                "Fragmentation dice must be at least 1 (omit for no fragmentation).",
                ephemeral=True,
            )
            return

        try:
            dist_list = _parse_distances(distances)
            result = explosion_report(
                basic_damage,
                dist_list,
                frag_dice=frag_dice,
                environment=environment,
            )
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Explosion — {basic_damage} Basic Dmg",
            description=f"Environment: {result.environment}",
            color=_RED,
        )
        collateral_lines = []
        for c in result.collateral:
            label = "center / direct hit" if c.distance == 0 else f"{c.distance} yd"
            collateral_lines.append(f"`{label}` → **{c.damage}**")
        embed.add_field(
            name="Concussion (Collateral)",
            value="\n".join(collateral_lines),
            inline=False,
        )

        if result.frag_dice is not None:
            embed.add_field(
                name="Fragmentation",
                value=(
                    f"[{result.frag_dice}d] cutting — "
                    f"danger radius **{result.danger_radius} yd**"
                ),
                inline=False,
            )
            frag_lines = []
            for f in result.fragmentation:
                label = "center" if f.distance == 0 else f"{f.distance} yd"
                if f.auto_hit:
                    reach = "auto-hit"
                elif f.in_radius:
                    reach = f"in radius, attack skill {f.effective_skill}"
                else:
                    reach = "out of radius"
                frag_lines.append(f"`{label}` — {reach}")
            embed.add_field(
                name="Fragment Reach",
                value="\n".join(frag_lines),
                inline=False,
            )

        embed.set_footer(text="B414 — collateral = floor(basic ÷ (divisor × yd))")
        await interaction.response.send_message(embed=embed)

    @calc.command(
        name="knockback",
        description="Knockback Distance + Fall-Check Trigger (B378)",
    )
    @app_commands.describe(
        basic_damage="Pre-DR damage roll total (sum of dice before DR)",
        damage_type="Damage type (only cr, or cut that fails to penetrate, knocks back)",
        target_st="Target's ST (or the object's HP for a non-resisting object)",
        penetrated_dr="Did the damage penetrate DR? (only matters for cutting)",
        double_knockback="Double Knockback enhancement (halves the denominator)",
        perfect_balance="Target has Perfect Balance (+4 to the fall check)",
    )
    @app_commands.choices(damage_type=_KNOCKBACK_TYPE_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def knockback(
        self,
        interaction: discord.Interaction,
        basic_damage: int,
        target_st: int,
        damage_type: str = "cr",
        penetrated_dr: bool = True,
        double_knockback: bool = False,
        perfect_balance: bool = False,
    ) -> None:
        if basic_damage < 0:
            await interaction.response.send_message(
                "Basic damage cannot be negative.", ephemeral=True
            )
            return
        if target_st <= 0:
            await interaction.response.send_message(
                "Target ST (or object HP) must be positive.", ephemeral=True
            )
            return

        result = calc_knockback(
            basic_damage,
            damage_type,
            target_st,
            penetrated_dr=penetrated_dr,
            double_knockback=double_knockback,
            perfect_balance=perfect_balance,
        )

        color = _PHYSICS if result.yards else discord.Color.greyple()
        embed = discord.Embed(title="Knockback", color=color)

        if not result.eligible:
            embed.description = (
                f"**{damage_type}** cannot cause knockback here "
                f"(only crushing, or cutting that fails to penetrate DR, qualifies)."
            )
            embed.set_footer(text="B378 knockback")
            await interaction.response.send_message(embed=embed)
            return

        embed.add_field(name="Distance", value=f"**{result.yards}** yd", inline=True)
        embed.add_field(
            name="Per",
            value=f"{result.effective_denom} pt/yd",
            inline=True,
        )
        if result.double_knockback:
            embed.add_field(name="Double KB", value="yes", inline=True)

        if result.fall_check_triggered:
            mod = result.fall_check_modifier
            mod_str = f"+{mod}" if mod > 0 else str(mod)
            embed.add_field(
                name="Fall Check",
                value=(
                    f"Roll vs best of DX / Acrobatics / Judo at **{mod_str}** "
                    f"to stay standing"
                ),
                inline=False,
            )
        else:
            embed.add_field(name="Fall Check", value="Not triggered", inline=False)

        embed.set_footer(text="B378 — 1 yd per full (ST−2) points of pre-DR damage")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CalcCombatCog(bot))
