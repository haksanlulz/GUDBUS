"""`/help` — orientation for a bot with 96 commands.

Descriptions are read from the live command tree rather than restated here.
That is the whole design: help that repeats a command's description is a second
copy to keep true, and a stale help page is worse than none — it tells someone
confidently about a command that no longer works that way. Here the only thing
maintained is which topic a command belongs to, and
`tests/test_help_coverage.py` fails when a command exists that no topic claims,
so a new command cannot quietly go undocumented.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.ui.respond import respond

#: Ordered because the embed renders in this order and a newcomer reads it top
#: down. Each entry: topic key -> (title, one-line framing, command names).
TOPICS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "start": (
        "Getting started",
        "Import a sheet, then roll against it. Everything else is optional.",
        ("char import", "char view", "check", "roll"),
    ),
    "character": (
        "Characters",
        "Your sheets are yours: they follow you between servers.",
        (
            "char import", "char view", "char list", "char switch",
            "char skills", "char spells", "char traits", "char equipment",
            "char export", "char delete",
        ),
    ),
    "rolling": (
        "Rolling",
        "Success rolls, contests, damage, and saved shorthand.",
        ("roll", "check", "contest", "damage",
         "macro save", "macro roll", "macro list", "macro delete"),
    ),
    "combat": (
        "Combat",
        "Attack, defend, and a tracker that keeps initiative and HP.",
        (
            "attack", "defend", "target", "hit-location", "posture",
            "fright-check",
            "combat start", "combat join", "combat add-npc", "combat leave",
            "combat hp", "combat fp", "combat status", "combat maneuver",
            "combat defend", "combat remove", "combat end",
        ),
    ),
    "reference": (
        "Reference lookups",
        "Facts and page citations from the catalog. Own the books.",
        ("skill", "spell", "trait", "technique", "item", "size", "range",
         "ranged", "screen"),
    ),
    "calculators": (
        "Calculators",
        "The arithmetic the book makes you do by hand.",
        (
            "calc fall", "calc collision", "calc explosion", "calc knockback",
            "jump", "throw", "lifting", "swim", "hike", "encumbrance",
            "cast cost", "cast time", "cast distance", "cast missile",
            "cast seek", "cast ceremonial",
            "vehicle control", "vehicle crash", "vehicle cruising",
            "vehicle decel", "vehicle dodge", "vehicle endurance",
        ),
    ),
    "gm": (
        "Running a game",
        "GM-side tools. Secret notes stay secret.",
        ("gm", "screen", "campaign show", "campaign rule-of-14",
         "notes add", "notes list", "notes search", "notes edit",
         "notes delete",
         "timer add", "timer list", "timer tick", "timer remove",
         "reaction roll", "reaction band"),
    ),
    "tracking": (
        "Between sessions",
        "Study time and money, tracked across sessions.",
        ("study log", "study progress", "study list", "study reset",
         "wealth show", "wealth set", "wealth adjust", "wealth starting",
         "wealth status", "wealth upkeep"),
    ),
}

#: Commands deliberately absent from every topic, with the reason. Listed so the
#: coverage test can tell "decided against" from "forgotten".
UNTOPICED: dict[str, str] = {
    "about": "shown on the /help landing page itself",
    "legal": "shown on the /help landing page itself",
    "support": "shown on the /help landing page itself",
    "donate": "shown on the /help landing page itself",
    "status": "diagnostics, not a player-facing feature",
    "sync": "owner-only recovery tool",
    "help": "this command",
}

QUICK_START = (
    "**1.** `/char import` — upload your `.gcs` file (from GURPS Character Sheet)\n"
    "**2.** `/char view` — check it came in right\n"
    "**3.** `/check` — roll against a skill or attribute\n"
    "**4.** `/combat start` — when the fighting starts\n"
)


def _tree_descriptions(tree: app_commands.CommandTree) -> dict[str, str]:
    """Every command's own description, keyed by its full invocation name."""
    found: dict[str, str] = {}
    for cmd in tree.get_commands():
        if isinstance(cmd, app_commands.Group):
            for sub in cmd.commands:
                found[f"{cmd.name} {sub.name}"] = sub.description
        else:
            found[cmd.name] = cmd.description
    return found


class HelpCog(commands.Cog):
    "Orientation."

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="What this bot does, by topic")
    @app_commands.describe(topic="Which area to explain. Omit for an overview.")
    @app_commands.choices(topic=[
        app_commands.Choice(name=title, value=key)
        for key, (title, _, _) in TOPICS.items()
    ])
    async def help_cmd(
        self,
        interaction: discord.Interaction,
        topic: app_commands.Choice[str] | None = None,
    ) -> None:
        descriptions = _tree_descriptions(self.bot.tree)

        if topic is None:
            embed = discord.Embed(
                title="GUDBUS — a GURPS 4e table aid",
                description=(
                    "Unofficial, free, and not endorsed by Steve Jackson Games. "
                    "Reference lookups return facts and page citations only — "
                    "own the books.\n\n"
                    f"**Quick start**\n{QUICK_START}"
                ),
                colour=discord.Colour.dark_gold(),
            )
            embed.add_field(
                name="Topics",
                value="\n".join(
                    f"`/help {key}` — {framing}"
                    for key, (_, framing, _) in TOPICS.items()
                ),
                inline=False,
            )
            embed.set_footer(text="/about · /legal · /support")
            await respond(interaction, embed=embed, ephemeral=True)
            return

        title, framing, names = TOPICS[topic.value]
        lines = [
            f"`/{name}` — {descriptions[name]}"
            for name in names
            if name in descriptions
        ]
        embed = discord.Embed(
            title=title, description=framing, colour=discord.Colour.dark_gold()
        )
        # Discord caps a field value at 1024 characters, and the combat topic is
        # already close, so split rather than let the tail vanish silently.
        chunk: list[str] = []
        size = 0
        part = 1
        for line in lines:
            if size + len(line) + 1 > 1000 and chunk:
                embed.add_field(
                    name="Commands" if part == 1 else f"Commands ({part})",
                    value="\n".join(chunk),
                    inline=False,
                )
                chunk, size, part = [], 0, part + 1
            chunk.append(line)
            size += len(line) + 1
        if chunk:
            embed.add_field(
                name="Commands" if part == 1 else f"Commands ({part})",
                value="\n".join(chunk),
                inline=False,
            )
        await respond(interaction, embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
