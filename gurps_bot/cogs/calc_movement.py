"""Movement calculators: /jump, /throw, /hike, /swim, and the /vehicle group."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.mechanics import checks as checks_mod
from gurps_bot.mechanics import hiking as hiking_mod
from gurps_bot.mechanics import jump as jump_mod
from gurps_bot.mechanics import swimming as swim_mod
from gurps_bot.mechanics import throwing as throw_mod
from gurps_bot.mechanics import vehicles as veh_mod

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)

BLUE = discord.Color.blue()
GREEN = discord.Color.green()

# values must match jump.ENCUMBRANCE_FACTORS keys
_JUMP_ENCUMBRANCE_CHOICES = [
    app_commands.Choice(name="None", value="none"),
    app_commands.Choice(name="Light", value="light"),
    app_commands.Choice(name="Medium", value="medium"),
    app_commands.Choice(name="Heavy", value="heavy"),
    app_commands.Choice(name="Extra-Heavy", value="extra-heavy"),
]

# values are hiking.Encumbrance member names
_HIKE_ENCUMBRANCE_CHOICES = [
    app_commands.Choice(name="None", value="NONE"),
    app_commands.Choice(name="Light", value="LIGHT"),
    app_commands.Choice(name="Medium", value="MEDIUM"),
    app_commands.Choice(name="Heavy", value="HEAVY"),
    app_commands.Choice(name="Extra-Heavy", value="EXTRA_HEAVY"),
]

_TERRAIN_CHOICES = [
    app_commands.Choice(name="Very Bad (x0.20)", value="VERY_BAD"),
    app_commands.Choice(name="Bad (x0.50)", value="BAD"),
    app_commands.Choice(name="Average (x1.00)", value="AVERAGE"),
    app_commands.Choice(name="Good (x1.25)", value="GOOD"),
]

_WEATHER_CHOICES = [
    app_commands.Choice(name="Clear (x1.0)", value="CLEAR"),
    app_commands.Choice(name="Rain (x0.5)", value="RAIN"),
    app_commands.Choice(name="Ankle-Deep Snow (x0.5)", value="SNOW_ANKLE"),
    app_commands.Choice(name="Deep Snow (x0.25)", value="SNOW_DEEP"),
    app_commands.Choice(name="Ice (x0.5)", value="ICE"),
]

# values are swimming.Encumbrance member names
_SWIM_ENCUMBRANCE_CHOICES = [
    app_commands.Choice(name="None", value="NONE"),
    app_commands.Choice(name="Light", value="LIGHT"),
    app_commands.Choice(name="Medium", value="MEDIUM"),
    app_commands.Choice(name="Heavy", value="HEAVY"),
    app_commands.Choice(name="Extra-Heavy", value="EXTRA_HEAVY"),
]


_VEHICLE_TERRAIN_CHOICES = [
    app_commands.Choice(name="Very Bad (Snow/Swamp)", value="VERY_BAD"),
    app_commands.Choice(name="Bad (Hills/Woods)", value="BAD"),
    app_commands.Choice(name="Average (Dirt Road/Plains)", value="AVERAGE"),
    app_commands.Choice(name="Good (Paved Road)", value="GOOD"),
]

_LOCOMOTION_CHOICES = [
    app_commands.Choice(name="Wheels", value="WHEELS"),
    app_commands.Choice(name="Runners (Sled/Skids)", value="RUNNERS"),
    app_commands.Choice(name="Tracks", value="TRACKS"),
    app_commands.Choice(name="Legs", value="LEGS"),
    app_commands.Choice(name="Other", value="OTHER"),
]

_VEHICLE_KIND_CHOICES = [
    app_commands.Choice(name="Powered Wheeled (Decel 5)", value="WHEELED_POWERED"),
    app_commands.Choice(
        name="Animal/Tracked/Walking (Decel 10)", value="ANIMAL_TRACKED_WALKING"
    ),
    app_commands.Choice(name="Air or Water (5+HND)", value="AIR_WATER"),
]


class CalcMovementCog(commands.Cog):
    "Movement & Action Calculators (Jump, Throw, Hike, Swim)."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="jump",
        description="High-Jump Height (Inches) and Long-Jump Distance (Yards) From Basic Move",
    )
    @app_commands.describe(
        basic_move="Basic Move (yards/second)",
        jumping_skill="Jumping skill level (substitutes Move/2 if higher)",
        st="ST (for the GM 'ST/4' jump substitution)",
        running_start="Add a running start (yards run before the jump)",
        yards_run="Yards run before jumping (with running start)",
        super_jump="Super Jump levels (each doubles the jump)",
        encumbrance="Encumbrance level (scales height & distance)",
    )
    @app_commands.choices(encumbrance=_JUMP_ENCUMBRANCE_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def jump(
        self,
        interaction: discord.Interaction,
        basic_move: float,
        jumping_skill: int | None = None,
        st: int | None = None,
        running_start: bool = False,
        yards_run: float = 0.0,
        super_jump: int = 0,
        encumbrance: str = "none",
    ) -> None:
        if basic_move < 0:
            await interaction.response.send_message(
                "Basic Move must be >= 0.", ephemeral=True
            )
            return
        if super_jump < 0:
            await interaction.response.send_message(
                "Super Jump levels must be >= 0.", ephemeral=True
            )
            return
        enc_factor = jump_mod.ENCUMBRANCE_FACTORS.get(encumbrance)
        if enc_factor is None:
            await interaction.response.send_message(
                f"Unknown encumbrance '{encumbrance}'.", ephemeral=True
            )
            return

        use_st = st is not None
        kwargs = dict(
            running_start=running_start,
            yards_run=yards_run,
            super_jump=super_jump,
            jumping_skill=jumping_skill,
            st=st,
            use_st_jump=use_st,
            encumbrance=enc_factor,
        )
        high = jump_mod.high_jump(basic_move, **kwargs)
        long = jump_mod.long_jump(basic_move, **kwargs)

        embed = discord.Embed(title="Jump", color=BLUE)
        cap_note = " (capped at 2x standing)" if high.capped else ""
        embed.add_field(
            name="High Jump",
            value=f"**{high.value:g} in** ({high.feet:g} ft){cap_note}",
            inline=True,
        )
        embed.add_field(
            name="Long Jump",
            value=f"**{long.value:g} yd** ({long.feet:g} ft)",
            inline=True,
        )
        embed.add_field(name="Effective Move", value=f"{high.effective_move:g}", inline=True)
        if super_jump > 0:
            embed.add_field(
                name="Super Jump",
                value=f"x{high.super_jump_multiplier} ({super_jump} lvl)",
                inline=True,
            )
        if enc_factor != 1.0:
            embed.add_field(name="Encumbrance", value=f"x{enc_factor:g}", inline=True)
        if running_start:
            start_detail = f"{yards_run:g} yd run" if yards_run else "running"
            embed.add_field(name="Running Start", value=start_detail, inline=True)
        embed.set_footer(text="B352 — distance/height only; combat prep & skill rolls not applied.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="throw",
        description="Throwing Distance (Yards) and Thrown Damage From ST + Object Weight",
    )
    @app_commands.describe(
        st="Strength (1-40)",
        weight="Object weight in pounds",
        damage_type="Damage type for the throw (default cr)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def throw(
        self,
        interaction: discord.Interaction,
        st: app_commands.Range[int, 1, 40],
        weight: float,
        damage_type: str = "cr",
    ) -> None:
        try:
            estimate = throw_mod.throw(st, weight, damage_type=damage_type)
        except ValueError as e:
            await interaction.response.send_message(f"Cannot throw: {e}", ephemeral=True)
            return

        res = estimate.result
        embed = discord.Embed(title="Throw", color=GREEN)
        embed.add_field(name="ST", value=str(res.st), inline=True)
        embed.add_field(name="Weight", value=f"{res.weight_lbs:g} lbs", inline=True)
        embed.add_field(name="Basic Lift", value=f"{res.basic_lift:g} lbs", inline=True)

        if not res.throwable:
            embed.add_field(
                name="Distance",
                value=f"**Too heavy** (> 8x BL = {8 * res.basic_lift:g} lbs)",
                inline=False,
            )
            embed.set_footer(text="B355 — object exceeds 8x Basic Lift; cannot be thrown.")
            await interaction.response.send_message(embed=embed)
            return

        hands = "one-handed" if res.one_handed else "two-handed"
        embed.add_field(
            name="Distance",
            value=f"**{res.distance_yards:g} yd** ({hands})",
            inline=True,
        )
        embed.add_field(
            name="Modifier",
            value=f"ST x{res.distance_modifier:g} (ratio {res.weight_ratio:.2f})",
            inline=True,
        )
        if estimate.damage is not None:
            embed.add_field(
                name="Thrown Damage",
                value=f"**{estimate.damage}** {estimate.damage_type}",
                inline=True,
            )
        embed.set_footer(text="B355 — distance + damage; min-1 injury applied at the wounding step.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="hike",
        description="Miles Travelled per Day From Basic Move, Encumbrance, Terrain, and Weather",
    )
    @app_commands.describe(
        basic_move="Basic Move (yards/second)",
        encumbrance="Encumbrance level",
        terrain="Terrain band (roads/quality folded in)",
        weather="Weather condition",
        hiking_success="Did the once-per-day Hiking roll succeed? (+20%)",
        enhanced_move="Enhanced Move (Ground) multiple (>= 1.0; e.g. 2.0)",
    )
    @app_commands.choices(
        encumbrance=_HIKE_ENCUMBRANCE_CHOICES,
        terrain=_TERRAIN_CHOICES,
        weather=_WEATHER_CHOICES,
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def hike(
        self,
        interaction: discord.Interaction,
        basic_move: int,
        encumbrance: str = "NONE",
        terrain: str = "AVERAGE",
        weather: str = "CLEAR",
        hiking_success: bool = False,
        enhanced_move: float = 1.0,
    ) -> None:
        try:
            enc = hiking_mod.Encumbrance[encumbrance]
            terr = hiking_mod.Terrain[terrain]
            weath = hiking_mod.Weather[weather]
        except KeyError as e:
            await interaction.response.send_message(f"Invalid option: {e}", ephemeral=True)
            return

        try:
            result = hiking_mod.calc_hiking(
                basic_move,
                encumbrance=enc,
                terrain=terr,
                weather=weath,
                hiking_success=hiking_success,
                enhanced_move_mult=enhanced_move,
            )
        except ValueError as e:
            await interaction.response.send_message(f"Cannot compute: {e}", ephemeral=True)
            return

        embed = discord.Embed(title="Daily March", color=BLUE)
        embed.add_field(
            name="Distance",
            value=f"**{result.miles_per_day} mi/day**",
            inline=True,
        )
        embed.add_field(
            name="Effective Move",
            value=f"{result.effective_move} (from {result.basic_move})",
            inline=True,
        )
        embed.add_field(
            name="Ideal",
            value=f"{result.base_miles} mi (10 x Move)",
            inline=True,
        )
        embed.add_field(
            name="Terrain",
            value=f"{terr.name.title()} (x{result.terrain_mult:g})",
            inline=True,
        )
        embed.add_field(
            name="Weather",
            value=f"{weath.name.title()} (x{result.weather_mult:g})",
            inline=True,
        )
        if hiking_success:
            embed.add_field(name="Hiking Roll", value="Success (+20%)", inline=True)
        if result.enhanced_move_mult != 1.0:
            embed.add_field(
                name="Enhanced Move",
                value=f"x{result.enhanced_move_mult:g}",
                inline=True,
            )
        embed.add_field(name="FP Cost", value=result.fp_note, inline=False)
        embed.set_footer(text="B351 march; FP costs B426.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="swim",
        description="Water Move, Distance Over a Duration, and Fatigue Timing From Basic Move",
    )
    @app_commands.describe(
        basic_move="Basic Move (yards/second)",
        ht="HT (for the fatigue-roll target)",
        seconds="Duration to cover, in seconds",
        swimming_skill="Swimming skill level (raises the fatigue target)",
        encumbrance="Encumbrance level (scales water Move)",
        aquatic="Amphibious/Aquatic: full Basic Move, no /5 divisor",
        fatigued="FP below 1/3 of max? (halves Move)",
        top_speed="Swimming at top speed (fatigue every 60s) vs slow/float (every 30 min)",
    )
    @app_commands.choices(encumbrance=_SWIM_ENCUMBRANCE_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def swim(
        self,
        interaction: discord.Interaction,
        basic_move: int,
        ht: int,
        seconds: float = 10.0,
        swimming_skill: int | None = None,
        encumbrance: str = "NONE",
        aquatic: bool = False,
        fatigued: bool = False,
        top_speed: bool = True,
    ) -> None:
        if basic_move < 0:
            await interaction.response.send_message(
                "Basic Move must be >= 0.", ephemeral=True
            )
            return
        if seconds < 0:
            await interaction.response.send_message(
                "Duration must be >= 0 seconds.", ephemeral=True
            )
            return
        try:
            enc = swim_mod.Encumbrance[encumbrance]
        except KeyError as e:
            await interaction.response.send_message(f"Invalid encumbrance: {e}", ephemeral=True)
            return

        result = swim_mod.swim_report(
            basic_move,
            seconds,
            ht,
            swimming_skill,
            encumbrance=enc,
            aquatic=aquatic,
            fatigued=fatigued,
            top_speed=top_speed,
        )

        embed = discord.Embed(title="Swimming", color=BLUE)
        embed.add_field(
            name="Water Move",
            value=f"**{result.effective_water_move:g} yd/s** (base {result.base_water_move})",
            inline=True,
        )
        embed.add_field(
            name="Distance",
            value=f"**{result.distance_yards:g} yd** in {result.duration_seconds:g}s",
            inline=True,
        )
        embed.add_field(
            name="Fatigue Rolls",
            value=f"{result.fatigue_rolls} vs HT/Swimming {result.fatigue_target}",
            inline=True,
        )
        embed.add_field(
            name="Roll Cadence",
            value=f"every {result.fatigue_interval_seconds}s",
            inline=True,
        )
        flags = []
        if aquatic:
            flags.append("Aquatic")
        if fatigued:
            flags.append("Fatigued (Move halved)")
        if enc is not swim_mod.Encumbrance.NONE:
            flags.append(f"{enc.name.title()} enc")
        if flags:
            embed.add_field(name="Conditions", value=", ".join(flags), inline=False)
        embed.set_footer(text="B354 — fatigue/drowning rolls are made separately via /check.")
        await interaction.response.send_message(embed=embed)

    # --- /vehicle group ---------------------------------------------------

    vehicle = app_commands.Group(
        name="vehicle",
        description="Vehicle Calculators (Cruising, Endurance, Dodge, Control, Decel, Crash)",
    )

    @vehicle.command(
        name="cruising",
        description="Sustainable Cruising Speed Over Terrain (B463/466)",
    )
    @app_commands.describe(
        top_speed="Vehicle Top Speed in yards/second",
        terrain="Terrain band",
        locomotion="How the vehicle moves over ground",
        road_bound="Road-bound (e.g. a car): capped when off-road",
        off_road="Currently off-road (applies the road-bound cap)",
        acceleration="Acceleration in yds/sec (needed for a road-bound off-road cap)",
    )
    @app_commands.choices(terrain=_VEHICLE_TERRAIN_CHOICES, locomotion=_LOCOMOTION_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def vehicle_cruising(
        self,
        interaction: discord.Interaction,
        top_speed: float,
        terrain: str,
        locomotion: str = "WHEELS",
        road_bound: bool = False,
        off_road: bool = False,
        acceleration: float | None = None,
    ) -> None:
        try:
            mph = veh_mod.cruising_speed(
                top_speed,
                veh_mod.Terrain[terrain],
                locomotion=veh_mod.Locomotion[locomotion],
                road_bound=road_bound,
                off_road=off_road,
                acceleration=acceleration,
            )
        except (ValueError, KeyError) as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        embed = discord.Embed(title="Cruising Speed", color=BLUE)
        embed.add_field(
            name="Top Speed",
            value=f"{top_speed:g} yd/s ({veh_mod.yards_per_sec_to_mph(top_speed):g} mph flat-out)",
            inline=False,
        )
        embed.add_field(name="Terrain", value=terrain.replace("_", " ").title(), inline=True)
        embed.add_field(name="Locomotion", value=locomotion.title(), inline=True)
        embed.add_field(name="Cruising", value=f"**{mph:g} mph**", inline=True)
        embed.set_footer(text="B463/466 — Top Speed × terrain multiplier")
        await interaction.response.send_message(embed=embed)

    @vehicle.command(
        name="endurance",
        description="Loiter Endurance: Range ÷ Cruising Speed (B463)",
    )
    @app_commands.describe(
        range_miles="Vehicle Range in miles",
        cruising_mph="Cruising speed in mph (from /vehicle cruising)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def vehicle_endurance(
        self,
        interaction: discord.Interaction,
        range_miles: float,
        cruising_mph: float,
    ) -> None:
        try:
            hours = veh_mod.endurance(range_miles, cruising_mph)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        embed = discord.Embed(title="Endurance", color=BLUE)
        embed.add_field(name="Range", value=f"{range_miles:g} mi", inline=True)
        embed.add_field(name="Cruising", value=f"{cruising_mph:g} mph", inline=True)
        embed.add_field(name="Endurance", value=f"**{hours:g} hours**", inline=True)
        embed.set_footer(text="B463 — Range ÷ cruising speed")
        await interaction.response.send_message(embed=embed)

    @vehicle.command(
        name="dodge",
        description="Vehicle Dodge: floor(skill/2) + Handling (B470)",
    )
    @app_commands.describe(
        control_skill="Operator's control skill (Driving/Piloting/Boating…)",
        handling="Vehicle Handling (Hnd)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def vehicle_dodge(
        self,
        interaction: discord.Interaction,
        control_skill: int,
        handling: int,
    ) -> None:
        try:
            dodge = veh_mod.vehicle_dodge(control_skill, handling)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        embed = discord.Embed(title="Vehicle Dodge", color=BLUE)
        embed.add_field(name="Control Skill", value=str(control_skill), inline=True)
        embed.add_field(name="Handling", value=f"{handling:+d}", inline=True)
        embed.add_field(name="Dodge", value=f"**{dodge}**", inline=True)
        embed.set_footer(text="B470 — floor(skill/2) + Handling")
        await interaction.response.send_message(embed=embed)

    @vehicle.command(
        name="control",
        description="Make a Control Roll and Read It vs Stability Rating (B466)",
    )
    @app_commands.describe(
        control_skill="Operator's control skill",
        handling="Vehicle Handling (Hnd)",
        sr="Stability Rating (the SR in Hnd/SR)",
        visibility="Visibility penalty (−1..−10 for fog/darkness), 0 if clear",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def vehicle_control(
        self,
        interaction: discord.Interaction,
        control_skill: int,
        handling: int,
        sr: int,
        visibility: int = 0,
    ) -> None:
        if sr < 0:
            await interaction.response.send_message(
                "Stability Rating cannot be negative.", ephemeral=True
            )
            return
        result = checks_mod.check(control_skill, modifier=handling + visibility)
        rolled = result.rolled
        if result.outcome.succeeded:
            embed = discord.Embed(title="Control Roll — Kept Control", color=GREEN)
            embed.add_field(name="Rolled", value=f"{rolled} vs {result.target}", inline=True)
            embed.add_field(name="Outcome", value=result.outcome.value, inline=True)
        else:
            margin_of_failure = rolled - result.target
            critical = result.outcome is checks_mod.Outcome.CRITICAL_FAILURE
            severity = veh_mod.classify_control_failure(
                margin_of_failure, sr, critical=critical
            )
            color = discord.Color.red() if severity == "major" else discord.Color.orange()
            embed = discord.Embed(title="Control Roll — Lost Control", color=color)
            embed.add_field(name="Rolled", value=f"{rolled} vs {result.target}", inline=True)
            embed.add_field(name="Failed By", value=f"{margin_of_failure} (SR {sr})", inline=True)
            meaning = (
                "skid / minor problem"
                if severity == "minor"
                else "crash / spin / major problem"
            )
            embed.add_field(name="Severity", value=f"**{severity}** — {meaning}", inline=False)
        embed.set_footer(text="B466 — skill + Hnd + visibility; fail ≤ SR is minor")
        await interaction.response.send_message(embed=embed)

    @vehicle.command(
        name="decel",
        description="Safe Deceleration per Turn by Drivetrain (B468)",
    )
    @app_commands.describe(
        kind="Drivetrain class",
        handling="Vehicle Handling (only affects air/water)",
    )
    @app_commands.choices(kind=_VEHICLE_KIND_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def vehicle_decel(
        self,
        interaction: discord.Interaction,
        kind: str,
        handling: int = 0,
    ) -> None:
        dec = veh_mod.deceleration(handling, veh_mod.VehicleKind[kind])
        embed = discord.Embed(title="Deceleration", color=BLUE)
        embed.add_field(name="Drivetrain", value=kind.replace("_", " ").title(), inline=True)
        embed.add_field(name="Per Turn", value=f"**{dec} yd/s**", inline=True)
        embed.set_footer(text="B468 — wheeled 5 · animal/tracked/walking 10 · air/water 5+Hnd")
        await interaction.response.send_message(embed=embed)

    @vehicle.command(
        name="crash",
        description="Crash / Ram Damage: Impact at Velocity + Skid (B468/430)",
    )
    @app_commands.describe(
        velocity="Impact velocity in yards/second",
        hp="Vehicle (or faller's) HP",
        dr="DR protecting against the impact",
        flying="Was the vehicle airborne? (adds a separate altitude fall)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def vehicle_crash(
        self,
        interaction: discord.Interaction,
        velocity: int,
        hp: int,
        dr: int = 0,
        flying: bool = False,
    ) -> None:
        try:
            result = veh_mod.crash(velocity, hp, dr=dr, flying=flying)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        embed = discord.Embed(title="Crash", color=discord.Color.red())
        embed.add_field(
            name="Impact",
            value=f"{result.dice_float:g}d → **{result.dice}** ({result.dice.min}–{result.dice.max}) {result.damage_type}",
            inline=False,
        )
        embed.add_field(name="Skid", value=f"{result.skid_yards} yd", inline=True)
        if dr:
            embed.add_field(name="DR", value=str(dr), inline=True)
        if flying:
            embed.add_field(
                name="Airborne",
                value="Add falling damage from altitude (use /calc fall)",
                inline=False,
            )
        embed.set_footer(text="B468/430 — immovable-object collision at velocity (2×HP)")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CalcMovementCog(bot))
