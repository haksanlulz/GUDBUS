"""Invention procedure (B473-474): /craft invent|costs.

The anchor scene for slice 1. A player who has read nothing should be able to
reach a resolved Concept stage through menus, without knowing that the roll
carries six modifiers — so ``/craft invent`` asks for the one thing only the
player knows (their skill) and offers everything else as a choice.

⚠️ **There is no GM identity in this bot.** No table, no setting, no role check
anywhere in the codebase names one. B473-474 make the Concept and Prototype
rolls the GM's and secret, so the closest honest implementation is: the target
and its breakdown are public (the modifiers are the GM's own calls and arguing
with them is the point), and the roll itself is **ephemeral** — visible only to
whoever pressed the button, never posted to the channel. Whether that should
become a real GM registry is an operator ruling, not a thing to infer.

Stateless by design. Persistent crafting projects are the next lane; nothing
here writes to the database, which is why this cog opens no session.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.mechanics import crafting
from gurps_bot.mechanics.checks import Outcome, check
from gurps_bot.mechanics.crafting import Complexity, Stage
from gurps_bot.ui.respond import respond

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)

_INVENTION = discord.Color.dark_gold()

#: How long a guided flow stays clickable. Matches the other views in the bot.
_VIEW_TIMEOUT = 300

_COMPLEXITY_BY_VALUE = {c.name.lower(): c for c in Complexity}

#: The situation flags, as the engine's keyword names. Kept in one place so the
#: select and the engine call cannot drift apart.
_SITUATIONS = (
    ("working_model", "I have a working model to copy"),
    ("device_exists", "It exists, but I have no model"),
    ("new_technology", "The basic technology is new to the campaign"),
    ("one_tl_above", "It is one TL above me"),
)


#: `check()` reports an Outcome; the engine speaks the book's own vocabulary.
_OUTCOME_KEYS = {
    Outcome.CRITICAL_SUCCESS: "critical_success",
    Outcome.SUCCESS: "success",
    Outcome.FAILURE: "failure",
    Outcome.CRITICAL_FAILURE: "critical_failure",
}


def _fmt_mod(value: int) -> str:
    return f"+{value}" if value >= 0 else str(value)


def _breakdown_lines(modifier: crafting.ModifierBreakdown) -> str:
    return "\n".join(f"`{_fmt_mod(v):>3}`  {label}" for label, v in modifier.terms)


class InventionFlowView(discord.ui.View):
    """Concept stage, assembled from menus rather than typed as parameters."""

    def __init__(self, skill: int, invoker_id: int) -> None:
        super().__init__(timeout=_VIEW_TIMEOUT)
        self.skill = skill
        self.invoker_id = invoker_id
        self.complexity: Complexity | None = None
        self.situations: set[str] = set()
        self.variant_bonus = 0
        self.description_bonus = 0

    # The flow belongs to whoever opened it; a shared message otherwise lets a
    # bystander rewrite the GM's calls mid-decision.
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "That invention flow belongs to someone else — run `/craft invent` "
                "to start your own.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True

    def modifier(self) -> crafting.ModifierBreakdown:
        return crafting.concept_modifier(
            self.complexity or Complexity.AVERAGE,
            variant_bonus=self.variant_bonus,
            description_bonus=self.description_bonus,
            **{name: name in self.situations for name, _ in _SITUATIONS},
        )

    def target(self) -> int:
        return crafting.effective_target(self.skill, self.modifier())

    def summary_embed(self) -> discord.Embed:
        modifier = self.modifier()
        target = self.target()

        embed = discord.Embed(
            title=f"{Stage.CONCEPT.name} roll — {self.complexity.label} invention",
            colour=_INVENTION,
        )
        embed.add_field(
            name="Modifiers", value=_breakdown_lines(modifier) or "none", inline=False
        )
        embed.add_field(
            name="Effective target",
            value=f"skill {self.skill} {_fmt_mod(modifier.total)} = **{target}**",
            inline=False,
        )
        if target < 3:
            # B347 has no minimum effective skill. Saying so is the difference
            # between an honest long shot and a bot that looks broken.
            embed.add_field(
                name="Below 3",
                value=(
                    "That is a real target, not an error — a natural 3 or 4 still "
                    "succeeds, and nothing else will."
                ),
                inline=False,
            )
        embed.add_field(
            name=Stage.CONCEPT.cadence.capitalize(),
            value=(
                f"The GM rolls this in secret. A failure costs the day and nothing "
                f"else; a critical failure looks like a success and never becomes a "
                f"prototype."
            ),
            inline=False,
        )
        embed.set_footer(text="B473")
        return embed

    async def _refresh(self, interaction: discord.Interaction) -> None:
        if self.complexity is None:
            await interaction.response.defer()
            return
        await interaction.response.edit_message(embed=self.summary_embed(), view=self)

    @discord.ui.select(
        placeholder="How hard is it?",
        options=[
            discord.SelectOption(
                label=c.label,
                value=c.name.lower(),
                description=f"{_fmt_mod(c.concept_penalty)} to the roll",
            )
            for c in Complexity
        ],
    )
    async def complexity_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        self.complexity = _COMPLEXITY_BY_VALUE[select.values[0]]
        await self._refresh(interaction)

    @discord.ui.select(
        placeholder="Anything else true of it? (optional)",
        min_values=0,
        max_values=len(_SITUATIONS),
        options=[
            discord.SelectOption(label=label, value=name)
            for name, label in _SITUATIONS
        ],
    )
    async def situation_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        self.situations = set(select.values)
        await self._refresh(interaction)

    @discord.ui.select(
        placeholder="Is it a variant of something that exists? (GM's call)",
        options=[discord.SelectOption(label="No", value="0")]
        + [
            discord.SelectOption(label=f"Yes, +{n}", value=str(n))
            for n in range(1, 6)
        ],
    )
    async def variant_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        self.variant_bonus = int(select.values[0])
        await self._refresh(interaction)

    @discord.ui.select(
        placeholder="Did the player explain it well? (GM's call)",
        options=[
            discord.SelectOption(label="No bonus", value="0"),
            discord.SelectOption(label="Clear, +1", value="1"),
            discord.SelectOption(label="Clever, +2", value="2"),
        ],
    )
    async def description_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        self.description_bonus = int(select.values[0])
        await self._refresh(interaction)

    @discord.ui.button(label="Roll it (secret)", style=discord.ButtonStyle.primary)
    async def roll_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.complexity is None:
            await interaction.response.send_message(
                "Pick how hard it is first.", ephemeral=True
            )
            return

        result = check(self.target())
        outcome = crafting.concept_outcome(_OUTCOME_KEYS[result.outcome])

        embed = discord.Embed(
            title=f"{Stage.CONCEPT.name} — {result.outcome.value}",
            description=f"{result.roll_result} vs **{result.target}**",
            colour=_INVENTION,
        )
        if outcome.flawed_theory:
            # The trap B473 builds the secrecy around: it advances, and it is
            # dead. The player must not be told, so this text is for the roller.
            embed.add_field(
                name="Flawed theory",
                value=(
                    "It advances to Prototype and can never work. Only a critical "
                    "success on the Prototype roll reveals it."
                ),
                inline=False,
            )
        elif outcome.advances:
            embed.add_field(name="Next", value=f"{Stage.PROTOTYPE.name}", inline=False)
        else:
            embed.add_field(
                name="Next",
                value="Try again tomorrow, at no extra penalty.",
                inline=False,
            )
        embed.set_footer(text="B473 — only you can see this")

        # SPEC gm-rolls-stay-with-the-gm: never to the channel. Ephemeral is the
        # strongest routing available while the bot has no GM identity.
        await interaction.response.send_message(embed=embed, ephemeral=True)


class CraftingCog(commands.Cog):
    "GURPS Invention (Concept, Prototype, Testing, Production)."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    craft = app_commands.Group(
        name="craft",
        description="Invention and item creation (B473)",
    )

    @craft.command(name="invent", description="Walk an invention through its Concept roll (B473)")
    @app_commands.describe(
        skill="Your invention skill — the Engineer, Alchemy, Bioengineering etc. the GM named",
    )
    async def invent(self, interaction: discord.Interaction, skill: int) -> None:
        if not 1 <= skill <= 40:
            await respond(
                interaction,
                "Skill should be somewhere between 1 and 40.",
                ephemeral=True,
            )
            return

        view = InventionFlowView(skill=skill, invoker_id=interaction.user.id)
        embed = discord.Embed(
            title="New invention",
            description=(
                "Describe it to the GM, then answer the menus below. "
                "Nothing is typed twice."
            ),
            colour=_INVENTION,
        )
        embed.set_footer(text="B473")
        await respond(interaction, embed=embed, view=view)

    @craft.command(name="costs", description="What an invention costs to prototype and produce (B474)")
    @app_commands.describe(
        complexity="How hard the GM rated it",
        retail_price="What one finished item sells for",
        one_tl_above="It is one TL above the inventor",
        reuses_facilities="There are usable facilities left from a related project",
        inventors="How many people are each attempting Prototype rolls",
    )
    @app_commands.choices(
        complexity=[
            app_commands.Choice(name=c.label, value=c.name.lower()) for c in Complexity
        ]
    )
    async def costs(
        self,
        interaction: discord.Interaction,
        # Annotated `str`, not `Choice[str]`: Discord sends the choice VALUE, and
        # taking it directly is what `test_cold_guild` exercises. help.py's
        # `Choice[str]` form works too, but only because its parameter is
        # optional and so never reaches that guard.
        complexity: str,
        retail_price: int,
        one_tl_above: bool = False,
        reuses_facilities: bool = False,
        inventors: int = 1,
    ) -> None:
        if retail_price < 0:
            await respond(interaction, "Retail price cannot be negative.", ephemeral=True)
            return
        if not 1 <= inventors <= 20:
            await respond(interaction, "Inventors should be 1 to 20.", ephemeral=True)
            return

        rating = _COMPLEXITY_BY_VALUE[complexity]
        costs = crafting.invention_costs(
            rating,
            retail_price,
            one_tl_above=one_tl_above,
            reuses_facilities=reuses_facilities,
            inventors=inventors,
        )

        embed = discord.Embed(
            title=f"{rating.label} invention — what it costs",
            colour=_INVENTION,
        )
        # Three figures, never one. They have different payers and different
        # triggers, and a single number would be wrong for all three.
        embed.add_field(
            name="Facilities, once, up front",
            value=f"${costs.facilities:,}"
            + (f" ({inventors} inventors)" if inventors > 1 else ""),
            inline=False,
        )
        embed.add_field(
            name="Every prototype attempt",
            value=f"${costs.per_attempt:,}",
            inline=False,
        )
        embed.add_field(
            name="Each copy afterwards",
            value=(
                f"${costs.per_copy_parts_only:,} for parts, or "
                f"${costs.per_copy_with_labour:,} with labour"
            ),
            inline=False,
        )
        embed.add_field(
            name="Time per attempt",
            value=(
                f"{rating.prototype_time.dice} {rating.prototype_time.unit}, "
                f"divided by the skilled people on it (minimum one day)"
            ),
            inline=False,
        )
        embed.set_footer(text="B474")
        await respond(interaction, embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CraftingCog(bot))
