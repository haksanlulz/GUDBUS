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

from gurps_bot.mechanics import (
    crafting,
    crafting_alchemy,
    crafting_enchantment,
    crafting_mundane,
    crafting_repair,
    equipment_quality,
)
# Aliased: `/craft repair` already has a `tech_level` parameter, which would
# shadow the module inside the callback.
from gurps_bot.mechanics import tech_level as tech_level_rules
from gurps_bot.mechanics.checks import Outcome, check
from gurps_bot.mechanics.crafting import Complexity, Method, Stage
from gurps_bot.services.crafting import (
    charge_history,
    finish_project,
    get_project,
    list_projects,
    spent_by_kind,
)
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
        self.method = Method.NEW_INVENTIONS
        self.situations: set[str] = set()
        self.variant_bonus = 0
        self.description_bonus = 0
        #: How many TLs above the inventor. Graded rather than a yes/no, because
        #: the anchor scene is a TL+3 superscience item and a boolean cannot say
        #: so — at -5 per step, TL+3 is -15, not -5.
        self.tl_gap = 0

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
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

    def modifier(self) -> crafting.ModifierBreakdown:
        complexity = self.complexity or Complexity.AVERAGE
        situations = {name: name in self.situations for name, _ in _SITUATIONS}
        shared = dict(
            variant_bonus=self.variant_bonus,
            description_bonus=self.description_bonus,
            tl_gap=self.tl_gap,
        )
        if self.method is Method.NEW_INVENTIONS:
            return crafting.concept_modifier(complexity, **shared, **situations)

        # B475 tells a gadgeteer to ignore the new-technology penalty outright,
        # and the engine refuses the argument rather than accepting and dropping
        # it — so the menu choice is discarded HERE, visibly, and the embed says
        # so. Silently passing it through would be a -5 nobody could find.
        situations.pop("new_technology", None)
        return crafting.gadgeteer_concept_modifier(complexity, **shared, **situations)

    def target(self) -> int:
        return crafting.effective_target(self.skill, self.modifier())

    def stored_modifiers(self) -> dict:
        """The GM's calls, in the shape a resumed project can re-render.

        Stored rather than the resulting integer: a project picked up weeks
        later shows the same itemised breakdown, and a bare "-27" is a number
        nobody can argue with.
        """
        return {
            "method": self.method.name,
            "situations": sorted(self.situations),
            "variant_bonus": self.variant_bonus,
            "description_bonus": self.description_bonus,
            "tl_gap": self.tl_gap,
        }

    def summary_embed(self) -> discord.Embed:
        modifier = self.modifier()
        target = self.target()

        embed = discord.Embed(
            title=f"{Stage.CONCEPT.name} roll — {(self.complexity or Complexity.AVERAGE).label} invention",
            description=f"Using **{self.method.value}** rules",
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
        if self.method is not Method.NEW_INVENTIONS and "new_technology" in self.situations:
            # Say it rather than silently dropping a -5 the player picked.
            embed.add_field(
                name="Ignored",
                value=(
                    "A gadgeteer ignores the penalty for technology new to the "
                    "campaign, so that choice is not applied (B475)."
                ),
                inline=False,
            )
        embed.add_field(
            name=Stage.CONCEPT.cadence.capitalize(),
            value=(
                "The GM rolls this in secret. A failure costs the day and nothing "
                "else; a critical failure looks like a success, advances, and "
                "only shows itself after prototype money is spent."
            ),
            inline=False,
        )
        embed.set_footer(text="B473")
        return embed

    async def _redraw(self, interaction: discord.Interaction) -> None:
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
        self, interaction: discord.Interaction[GURPSBot], select: discord.ui.Select
    ) -> None:
        self.complexity = _COMPLEXITY_BY_VALUE[select.values[0]]
        await self._redraw(interaction)

    @discord.ui.select(
        placeholder="Which rules? (Gadgeteer advantage required for the last two)",
        options=[
            discord.SelectOption(
                label="New Inventions",
                value=Method.NEW_INVENTIONS.name,
                description="B473 — realistic, at most one TL ahead",
                default=True,
            ),
            discord.SelectOption(
                label="Gadgeteering",
                value=Method.GADGETEERING.name,
                description="B475 — needs the Gadgeteer advantage; any TL",
            ),
            discord.SelectOption(
                label="Quick Gadgeteering",
                value=Method.QUICK_GADGETEERING.name,
                description="B476 — needs Quick Gadgeteer; minutes, not months",
            ),
        ],
    )
    async def method_select(
        self, interaction: discord.Interaction[GURPSBot], select: discord.ui.Select
    ) -> None:
        self.method = Method[select.values[0]]
        await self._redraw(interaction)

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
        self, interaction: discord.Interaction[GURPSBot], select: discord.ui.Select
    ) -> None:
        self.situations = set(select.values)
        await self._redraw(interaction)

    @discord.ui.button(label="GM adjustments…", style=discord.ButtonStyle.secondary)
    async def adjust_btn(
        self, interaction: discord.Interaction[GURPSBot], button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(GmAdjustmentsModal(self))

    @discord.ui.button(label="Roll it (secret)", style=discord.ButtonStyle.primary)
    async def roll_btn(
        self, interaction: discord.Interaction[GURPSBot], button: discord.ui.Button
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

    @discord.ui.button(label="Save as project", style=discord.ButtonStyle.secondary)
    async def save_btn(
        self, interaction: discord.Interaction[GURPSBot], button: discord.ui.Button
    ) -> None:
        if self.complexity is None:
            await interaction.response.send_message(
                "Pick how hard it is first.", ephemeral=True
            )
            return
        await interaction.response.send_modal(StartProjectModal(self))


class GmAdjustmentsModal(discord.ui.Modal, title="GM adjustments"):
    """The three graded calls B473 leaves to the GM.

    A modal rather than three more selects: Discord allows five action rows and
    the flow already spends two on menus and one on buttons. It also suits the
    values better — the TL gap is an integer with no natural ceiling, and a
    select would have to guess where to stop.
    """

    tl_gap = discord.ui.TextInput(
        label="TLs above the inventor (0 = same TL)",
        placeholder="0",
        required=False,
        default="0",
        max_length=2,
    )
    variant_bonus = discord.ui.TextInput(
        label="Variant of an existing item? (+0 to +5)",
        placeholder="0",
        required=False,
        default="0",
        max_length=1,
    )
    description_bonus = discord.ui.TextInput(
        label="Clear or clever description? (+0 to +2)",
        placeholder="0",
        required=False,
        default="0",
        max_length=1,
    )

    def __init__(self, view: InventionFlowView) -> None:
        super().__init__()
        self.flow = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            gap = int(self.tl_gap.value or "0")
            variant = int(self.variant_bonus.value or "0")
            description = int(self.description_bonus.value or "0")
        except ValueError:
            await interaction.response.send_message(
                "Those need to be whole numbers.", ephemeral=True
            )
            return

        flow = self.flow
        try:
            # Let the engine's own bounds do the validating — a second copy of
            # "+1 to +5" here is a second thing to keep true.
            crafting.concept_modifier(
                flow.complexity or Complexity.AVERAGE,
                variant_bonus=variant,
                description_bonus=description,
                tl_gap=gap,
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        flow.tl_gap = gap
        flow.variant_bonus = variant
        flow.description_bonus = description
        await flow._redraw(interaction)


class StartProjectModal(discord.ui.Modal, title="Start a crafting project"):
    """The name and price the menus cannot ask for.

    B473 has the player describe the invention to the GM, so the name is
    genuinely the player's text rather than a value the bot could offer. Retail
    price drives the per-attempt charge and the copy cost, and only the GM knows
    what the finished item is worth.
    """

    project_name = discord.ui.TextInput(
        label="What is it?", placeholder="portable mansion", max_length=200,
    )
    retail_price = discord.ui.TextInput(
        label="Retail price of one finished item ($)",
        placeholder="250000",
        required=False,
        default="0",
    )

    def __init__(self, view: InventionFlowView) -> None:
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction[GURPSBot]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]  # discord.py types this over any client; this bot has one
        from gurps_bot.services.crafting import start_project
        from gurps_bot.services.limits import StorageLimitExceeded
        from gurps_bot.utils.sanitize import sanitize_name

        try:
            price = int(self.retail_price.value or "0")
        except ValueError:
            await respond(
                interaction, "Retail price must be a whole number.", ephemeral=True
            )
            return
        if price < 0:
            await respond(interaction, "Retail price cannot be negative.", ephemeral=True)
            return

        name = sanitize_name(self.project_name.value)
        if not name:
            await respond(
                interaction,
                "That name is empty once special characters are removed.",
                ephemeral=True,
            )
            return

        view = self.view
        complexity = view.complexity
        if complexity is None:
            # save_btn gates the modal on it, but the flow is the modal's to read,
            # not to trust — the same answer the button gives
            await respond(interaction, "Pick how hard it is first.", ephemeral=True)
            return
        try:
            async with interaction.client.db() as session:
                project = await start_project(
                    session,
                    discord_user_id=interaction.user.id,
                    guild_id=interaction.guild_id,
                    name=name,
                    complexity=complexity.name.lower(),
                    skill=view.skill,
                    retail_price=price,
                    modifiers=view.stored_modifiers(),
                )
                await session.commit()
                project_id = project.id
        except StorageLimitExceeded as exc:
            await respond(interaction, str(exc), ephemeral=True)
            return

        await respond(
            interaction,
            f"Started **{name}** as project `{project_id}`. "
            f"`/craft project id:{project_id}` to pick it back up.",
            ephemeral=True,
        )


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
    async def invent(self, interaction: discord.Interaction[GURPSBot], skill: int) -> None:
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
        tl_gap="How many TLs above the inventor it is (0 = same TL)",
        tl_cost_multiplier="GM override for the TL surcharge (B474 prints x3 for one step)",
        reuses_facilities="There are usable facilities left from a related project",
        inventors="How many inventors — each makes their own Prototype attempts",
    )
    @app_commands.choices(
        complexity=[
            app_commands.Choice(name=c.label, value=c.name.lower()) for c in Complexity
        ]
    )
    async def costs(
        self,
        interaction: discord.Interaction[GURPSBot],
        # Annotated `str`, not `Choice[str]`: Discord sends the choice VALUE, and
        # taking it directly is what `test_cold_guild` exercises. help.py's
        # `Choice[str]` form works too, but only because its parameter is
        # optional and so never reaches that guard.
        complexity: str,
        retail_price: int,
        tl_gap: int = 0,
        reuses_facilities: bool = False,
        inventors: int = 1,
        tl_cost_multiplier: int | None = None,
    ) -> None:
        if retail_price < 0:
            await respond(interaction, "Retail price cannot be negative.", ephemeral=True)
            return
        if not 1 <= inventors <= 20:
            await respond(interaction, "Inventors should be 1 to 20.", ephemeral=True)
            return
        if not 0 <= tl_gap <= 10:
            await respond(interaction, "TL gap should be 0 to 10.", ephemeral=True)
            return
        if tl_cost_multiplier is not None and not 1 <= tl_cost_multiplier <= 100:
            await respond(
                interaction, "TL cost multiplier should be 1 to 100.", ephemeral=True
            )
            return

        rating = _COMPLEXITY_BY_VALUE[complexity]
        costs = crafting.invention_costs(
            rating,
            retail_price,
            tl_gap=tl_gap,
            tl_cost_multiplier=tl_cost_multiplier,
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

    @craft.command(name="repair", description="What it takes to repair a damaged item (B484)")
    @app_commands.describe(
        price="What the item costs new — repair difficulty scales off this, not off complexity",
        current_hp="Its HP now (0 or less needs spare parts)",
        max_hp="Its HP undamaged",
        workspace="Quality of the shop or toolkit (B345)",
        time_spent="Time-spent modifier, the GM's call (B346)",
        destroyed="It failed its HT roll to avoid destruction",
        tech_level="Your TL — for the best-available workspace, and for the item's TL gap",
        item_tech_level="The item's TL, if it is not from your own (B168)",
        unfamiliar="You have never worked on this make or model (B169)",
        emp="Whether an EMP is what broke it",
    )
    @app_commands.choices(
        workspace=[
            app_commands.Choice(name=q.value, value=q.name)
            for q in equipment_quality.EquipmentQuality
        ],
        emp=[
            app_commands.Choice(name=e.value, value=e.name)
            for e in crafting_repair.EmpDamage
        ],
    )
    async def repair(
        self,
        interaction: discord.Interaction[GURPSBot],
        price: int,
        current_hp: int,
        max_hp: int,
        workspace: str = equipment_quality.EquipmentQuality.BASIC.name,
        time_spent: int = 0,
        destroyed: bool = False,
        tech_level: int | None = None,
        item_tech_level: int | None = None,
        unfamiliar: bool = False,
        emp: str = crafting_repair.EmpDamage.NONE.name,
    ) -> None:
        if price < 0:
            await respond(interaction, "Price cannot be negative.", ephemeral=True)
            return
        if max_hp < 1:
            await respond(interaction, "Max HP should be at least 1.", ephemeral=True)
            return
        if not -10 <= time_spent <= 10:
            await respond(
                interaction, "The time-spent modifier should be -10 to +10.",
                ephemeral=True,
            )
            return
        try:
            quality = equipment_quality.EquipmentQuality[workspace]
            emp_damage = crafting_repair.EmpDamage[emp]
            # Armoury, Electronics Repair, Machinist and Mechanic are all
            # technological skills, so the harsher half of B345's split applies.
            equipment = equipment_quality.modifier(
                quality, technological=True, tech_level=tech_level
            )
        except (KeyError, ValueError) as exc:
            await respond(interaction, str(exc) or "Unknown workspace.", ephemeral=True)
            return

        gap = None
        if item_tech_level is not None:
            if tech_level is None:
                await respond(
                    interaction,
                    "To price a TL gap I need your TL too — B168 measures the "
                    "penalty between the skill and the equipment, so one TL on "
                    "its own says nothing.",
                    ephemeral=True,
                )
                return
            try:
                # Repair skills are IQ-based, which is the harsher of B168's two
                # rules: one TL up is -5, where an operating skill would take -1.
                gap = tech_level_rules.tl_gap(
                    skill_tl=tech_level, equipment_tl=item_tech_level
                )
            except ValueError as exc:
                await respond(interaction, str(exc), ephemeral=True)
                return
            if gap.impossible:
                await respond(
                    interaction,
                    f"TL{item_tech_level} gear is {gap.steps} TLs above TL"
                    f"{tech_level} skill. B168 stops rather than scaling: at four "
                    f"or more it is impossible, not merely very hard. No roll.",
                    ephemeral=True,
                )
                return

        tier = crafting_repair.repair_tier(current_hp, max_hp, destroyed=destroyed)
        embed = discord.Embed(
            title=f"{tier.value} — ${price:,} item",
            colour=_INVENTION,
        )

        if tier is crafting_repair.RepairTier.BEYOND_REPAIR:
            embed.add_field(
                name="Beyond repair",
                value=(
                    f"Replace it at full price: "
                    f"**${crafting_repair.replacement_cost(price):,}**. B484 gives "
                    f"no salvage credit and no roll."
                ),
                inline=False,
            )
            embed.set_footer(text="B484")
            await respond(interaction, embed=embed)
            return

        modifier = crafting_repair.repair_modifier(
            price,
            tier,
            equipment_modifier=equipment,
            time_spent_modifier=time_spent,
            tech_level_gap=gap,
            unfamiliar=unfamiliar,
            emp=emp_damage,
        )
        embed.add_field(
            name="Modifiers", value=_breakdown_lines(modifier) or "none", inline=False
        )
        embed.add_field(
            name="Workspace",
            value=f"{quality.value} ({_fmt_mod(equipment)}) — B345",
            inline=False,
        )
        embed.add_field(
            name="Roll",
            value=(
                f"Your repair skill {_fmt_mod(modifier.total)} — the GM picks which "
                f"skill (Armoury, Electronics Repair, Mechanic…)"
            ),
            inline=False,
        )
        # The distinctive rule of this domain: the roll returns a quantity.
        embed.add_field(
            name="On a success",
            value="Restores **1 HP per point of margin**, minimum 1.",
            inline=False,
        )
        time_spec = crafting_repair.minor_repair_time()
        embed.add_field(
            name="Per attempt",
            value=f"{time_spec.dice.modifier} {time_spec.unit}, whatever the item",
            inline=False,
        )
        if tier is crafting_repair.RepairTier.MAJOR:
            low = crafting_repair.major_repair_parts_cost(price, 1)
            high = crafting_repair.major_repair_parts_cost(price, 6)
            embed.add_field(
                name="Spare parts first",
                value=f"1d×10% of ${price:,} — **${low:,} to ${high:,}**",
                inline=False,
            )
        embed.set_footer(text="B484")
        await respond(interaction, embed=embed)

    @craft.command(
        name="enchant", description="Enchanting an item: Power, time, and the ceremonial thresholds"
    )
    @app_commands.describe(
        enchant_skill="Your skill with the Enchant spell",
        spell_skill="Your skill with the spell going into the item",
        energy="The enchantment's energy cost, from its own entry",
        method="Quick and Dirty burns energy; Slow and Sure burns the calendar",
        assistants="Other qualified mages — Quick and Dirty: -1 each; Slow and Sure: they split the days",
        hp_spent="HP you spend to power it — Quick and Dirty only, each a further -1",
        bystanders="Anyone but you and your assistants within 10 yards — a Quick and Dirty concern",
        mana="Where the finished item will be used — not where it is made",
    )
    @app_commands.choices(
        method=[
            app_commands.Choice(name=m.value, value=m.name)
            for m in crafting_enchantment.Method
        ],
        mana=[
            app_commands.Choice(name=m.value, value=m.name)
            for m in crafting_enchantment.Mana
        ],
    )
    async def enchant(
        self,
        interaction: discord.Interaction[GURPSBot],
        enchant_skill: int,
        spell_skill: int,
        energy: int,
        method: str = crafting_enchantment.Method.SLOW_AND_SURE.name,
        assistants: int = 0,
        hp_spent: int = 0,
        bystanders: bool = False,
        mana: str = crafting_enchantment.Mana.NORMAL.name,
    ) -> None:
        try:
            chosen = crafting_enchantment.Method[method]
            where = crafting_enchantment.Mana[mana]
            # Method-scoped: under Slow and Sure this comes back empty (and
            # refuses hp_spent outright) — the penalties are Quick and Dirty's.
            modifier = crafting_enchantment.enchanting_modifier(
                method=chosen,
                assistants=assistants, hp_spent=hp_spent, bystanders=bystanders,
            )
            base = crafting_enchantment.enchanting_skill(enchant_skill, spell_skill)
            hours = crafting_enchantment.quick_and_dirty_hours(energy)
            days = crafting_enchantment.slow_and_sure_days(energy, max(assistants + 1, 1))
        except (KeyError, ValueError) as exc:
            await respond(interaction, str(exc) or "Unknown option.", ephemeral=True)
            return

        effective = base + modifier.total
        cap = crafting_enchantment.assistant_cap(base)

        embed = discord.Embed(title="Enchanting", colour=_INVENTION)
        embed.add_field(
            name="Base skill",
            value=(
                f"**{base}** — the lower of Enchant {enchant_skill} and the spell "
                f"{spell_skill}. No averaging."
            ),
            inline=False,
        )
        if modifier.terms:
            embed.add_field(
                name="Modifiers", value=_breakdown_lines(modifier), inline=False
            )

        # The cap is derived FROM the -1, so it binds Quick and Dirty only —
        # a slow circle has no headcount ceiling, it just shares the days.
        if chosen is crafting_enchantment.Method.QUICK_AND_DIRTY and assistants > cap:
            embed.add_field(
                name="⚠️ Too many hands",
                value=(
                    f"At skill {base} you may bring **{cap}**. {assistants} would put "
                    f"you at {effective}, and below 15 the enchantment simply will "
                    f"not work."
                ),
                inline=False,
            )
        elif effective < crafting_enchantment.MINIMUM_EFFECTIVE_SKILL:
            embed.add_field(
                name="⚠️ Below 15",
                value=(
                    f"Effective skill {effective}. Everyone involved needs 15 or "
                    f"better in **both** spells."
                ),
                inline=False,
            )

        embed.add_field(
            name="Roll against, and the item's Power",
            value=(
                f"**{effective}** — one number, not two. The roll says whether it "
                f"worked; how good it is was decided before the dice."
            ),
            inline=False,
        )

        power = crafting_enchantment.power_in_play(effective, where)
        if power is None:
            works = "**No magic item works in a no-mana area**, whatever its Power."
        else:
            verdict = "works" if crafting_enchantment.item_works(effective, where) else (
                "**will not work**"
            )
            works = f"Power {power} where it is used — it {verdict} (15 is the floor)."
            if where is crafting_enchantment.Mana.LOW:
                works += " Low mana costs 5, so 20 is the real threshold there."
        embed.add_field(name="Where it will be used", value=works, inline=False)

        embed.add_field(
            name="Thresholds",
            value=(
                "Ceremonial: a **16 always fails** and **17-18 is always a critical "
                "failure**, however high your skill. A critical failure destroys the "
                "item and every material in it."
            ),
            inline=False,
        )

        if chosen is crafting_enchantment.Method.QUICK_AND_DIRTY:
            timing = (
                f"**{hours} hour{'s' if hours != 1 else ''}** for {energy} energy. "
                f"Succeed or fail, the energy is spent when the dice land."
            )
        else:
            timing = (
                f"**{days:g} day{'s' if days != 1 else ''}** of eight-hour work for "
                f"{energy} energy, split across {assistants + 1}. No FP or HP cost at "
                f"all — but every assistant must be there every day, a missed day "
                f"costs two, and losing a mage ends the project."
            )
        embed.add_field(name=chosen.value, value=timing, inline=False)
        embed.set_footer(text="GURPS Magic pp. 16-18")
        await respond(interaction, embed=embed)

    @craft.command(
        name="make", description="Making a mundane item: cost, time, and what the roll means"
    )
    @app_commands.describe(
        list_price="What the finished item sells for",
        weight="What it weighs, in pounds",
        cost_per_lb="Your material's cost per pound, from the raw materials table",
        monthly_pay="The craftsman's monthly pay for this trade",
        item_class="Which quality ladder the finished piece reads",
        labor="Routine utilitarian work, or artistic and arms manufacture",
        materials="Items whose raw materials cost more than their weight suggests",
        workers="Craftsmen and assistants working together (six is the cap)",
    )
    @app_commands.choices(
        item_class=[
            app_commands.Choice(name=c.value, value=c.name)
            for c in crafting_mundane.ItemClass
        ],
        labor=[
            app_commands.Choice(name=k.value, value=k.name)
            for k in crafting_mundane.LaborKind
        ],
        materials=[
            app_commands.Choice(name=m.name.replace("_", " ").capitalize(), value=m.name)
            for m in crafting_mundane.MaterialMultiplier
        ],
    )
    async def make(
        self,
        interaction: discord.Interaction[GURPSBot],
        list_price: float,
        weight: float,
        cost_per_lb: float,
        monthly_pay: float,
        item_class: str = crafting_mundane.ItemClass.GENERAL.name,
        labor: str = crafting_mundane.LaborKind.ROUTINE.name,
        materials: str = crafting_mundane.MaterialMultiplier.NONE.name,
        workers: int = 1,
    ) -> None:
        try:
            klass = crafting_mundane.ItemClass[item_class]
            kind = crafting_mundane.LaborKind[labor]
            multiplier = crafting_mundane.MaterialMultiplier[materials]
        except KeyError:
            await respond(interaction, "Unknown option.", ephemeral=True)
            return

        try:
            material_cost = crafting_mundane.materials_cost(
                weight, cost_per_lb, multiplier
            )
            labor_cost = crafting_mundane.labor_cost(list_price, material_cost)
            rate = crafting_mundane.hourly_labor_rate(monthly_pay, kind)
            active = crafting_mundane.active_hours(max(labor_cost, 0), rate)
            elapsed = crafting_mundane.elapsed_hours(active, workers)
        except ValueError as exc:
            await respond(interaction, str(exc), ephemeral=True)
            return

        embed = discord.Embed(title="Making it by hand", colour=_INVENTION)

        if labor_cost < 0:
            # The materials cost more than the item sells for. Said plainly
            # rather than clamped silently, because it usually means the wrong
            # material was picked off the table.
            embed.add_field(
                name="⚠️ The materials cost more than the item",
                value=(
                    f"${material_cost:,.2f} of materials against a ${list_price:,.2f} "
                    f"list price. Labour cannot be negative, so either the material "
                    f"or the weight is wrong for this item."
                ),
                inline=False,
            )

        embed.add_field(
            name="Materials",
            value=f"**${material_cost:,.2f}** — {weight:g} lbs at ${cost_per_lb:,.2f}/lb"
            + (f" x{multiplier.value}" if multiplier.value != 1 else ""),
            inline=False,
        )
        embed.add_field(
            name="Labour",
            value=f"**${max(labor_cost, 0):,.2f}** — the list price minus the materials",
            inline=False,
        )
        embed.add_field(
            name="Time",
            value=(
                f"**{active:,.1f} man-hours** at ${rate:,.2f}/hour"
                + (
                    f", so **{elapsed:,.1f} hours** with {min(workers, crafting_mundane.MAX_WORKERS)} "
                    f"working together"
                    if workers > 1
                    else ""
                )
            ),
            inline=False,
        )
        if workers > crafting_mundane.MAX_WORKERS:
            embed.add_field(
                name="Six is the cap",
                value=(
                    f"{workers} were named; past six, extra hands do not make it "
                    f"faster."
                ),
                inline=False,
            )

        # Quality is a return value, so the command shows what the roll will
        # MEAN rather than asking which quality is wanted.
        ladder = "\n".join(
            f"`{label:>16}`  {crafting_mundane.craft_quality(margin, klass).quality.value}"
            for label, margin in (
                ("failure by 4+", -4),
                ("failure by 1-3", -1),
                ("success by 0-11", 0),
                ("success by 12-17", 12),
                ("success by 18+", 18),
            )
        )
        embed.add_field(
            name=f"Then one roll, on the highest skill present — {klass.value}",
            value=ladder,
            inline=False,
        )
        embed.add_field(
            name="What the roll is not",
            value=(
                "You do not choose the quality; the margin does. Junk loses at "
                "least half the raw materials, and a flawed piece still sells "
                "for up to half price."
            ),
            inline=False,
        )
        embed.set_footer(text="Low-Tech Companion 3 ch. 5")
        await respond(interaction, embed=embed)

    @craft.command(name="brew", description="Brewing a batch of elixirs (GURPS Magic ch. 28)")
    @app_commands.describe(
        alchemy_skill="Your Alchemy skill",
        cost_per_dose="What the elixir's materials cost per dose, from its own entry",
        doses="How many doses in the batch",
        technique="Your level in this elixir's technique (default: Alchemy-1)",
        lab="The laboratory you are working in",
        mana="Local mana level — it changes the time, the duration and the failures",
        weeks="The elixir's printed brewing time, in weeks",
        formulary="You have the written formula to hand",
        teacher="A master alchemist is supervising",
        helper_skill="The lowest Alchemy skill among anyone helping",
        tech_level="Your TL — only needed for a cutting-edge lab",
    )
    @app_commands.choices(
        lab=[
            app_commands.Choice(name=q.value, value=q.name)
            for q in crafting_alchemy.LabQuality
        ],
        mana=[
            app_commands.Choice(name=m.value, value=m.name) for m in crafting_alchemy.Mana
        ],
    )
    async def brew(
        self,
        interaction: discord.Interaction[GURPSBot],
        alchemy_skill: int,
        cost_per_dose: int,
        doses: int = 1,
        technique: int | None = None,
        lab: str = crafting_alchemy.LabQuality.BASIC.name,
        mana: str = crafting_alchemy.Mana.NORMAL.name,
        weeks: float = 1.0,
        formulary: bool = False,
        teacher: bool = False,
        helper_skill: int | None = None,
        tech_level: int | None = None,
    ) -> None:
        if doses < 1:
            await respond(interaction, "A batch is at least one dose.", ephemeral=True)
            return
        if cost_per_dose < 0:
            await respond(
                interaction, "Cost per dose cannot be negative.", ephemeral=True
            )
            return
        if weeks <= 0:
            await respond(
                interaction, "Brewing time should be more than zero.", ephemeral=True
            )
            return
        try:
            quality = crafting_alchemy.LabQuality[lab]
            mana_level = crafting_alchemy.Mana[mana]
        except KeyError:
            await respond(interaction, "Unknown laboratory or mana level.", ephemeral=True)
            return

        if not crafting_alchemy.can_brew(mana_level):
            await respond(
                interaction,
                "Elixirs cannot be made or used in a no-mana area at all.",
                ephemeral=True,
            )
            return

        # The weakest pair of hands makes the final roll — alchemy's reading of
        # "assistant", and the opposite of invention's.
        roller = alchemy_skill
        if helper_skill is not None:
            roller = crafting_alchemy.final_roller_skill([alchemy_skill, helper_skill])

        try:
            modifier = crafting_alchemy.brewing_modifier(
                alchemy_skill=roller,
                technique=technique,
                lab=quality,
                tech_level=tech_level,
                doses=doses,
                formulary=formulary,
                teacher=teacher,
            )
        except ValueError as exc:
            await respond(interaction, str(exc), ephemeral=True)
            return

        target = roller + modifier.total
        embed = discord.Embed(
            title=f"Brewing {doses} dose{'s' if doses > 1 else ''}",
            colour=_INVENTION,
        )
        embed.add_field(
            name="Modifiers", value=_breakdown_lines(modifier) or "none", inline=False
        )
        embed.add_field(name="Roll against", value=f"**{target}**", inline=False)
        if helper_skill is not None and roller < alchemy_skill:
            embed.add_field(
                name="Who rolls",
                value=(
                    f"The lowest-skill alchemist who touched the batch — {roller}, "
                    f"not your {alchemy_skill}."
                ),
                inline=False,
            )
        embed.add_field(
            name="Materials",
            value=f"**${crafting_alchemy.batch_materials_cost(cost_per_dose, doses):,}** "
            f"(${cost_per_dose:,} x {doses})",
            inline=False,
        )
        elapsed = weeks * crafting_alchemy.brewing_time_multiplier(mana_level)
        embed.add_field(
            name="Time",
            value=(
                f"**{elapsed:g} week{'s' if elapsed != 1 else ''}** for the whole "
                f"batch — batch size drives the cost and the penalty, not the clock."
            ),
            inline=False,
        )
        if crafting_alchemy.every_failure_is_critical(mana_level):
            embed.add_field(
                name="Very high mana",
                value="Half the brewing time, but **every** failure is critical.",
                inline=False,
            )
        if mana_level is crafting_alchemy.Mana.LOW:
            embed.add_field(
                name="Low mana",
                value="Twice the time, and the elixir works half as long.",
                inline=False,
            )
        embed.add_field(
            name="On a failure",
            value=(
                "Ruined ingredients, and the money with them. There are **no "
                "critical successes** in alchemy. A critical failure takes a "
                f"second technique roll at **{crafting_alchemy.disaster_roll_penalty(doses)}** "
                "(one per dose, not per extra dose) before any disaster fires."
            ),
            inline=False,
        )
        embed.set_footer(text="GURPS Magic ch. 28")
        await respond(interaction, embed=embed)

    @craft.command(name="projects", description="Your crafting projects in this server")
    @app_commands.describe(include_finished="Also show abandoned and completed ones")
    async def projects(
        self, interaction: discord.Interaction[GURPSBot], include_finished: bool = False
    ) -> None:
        async with interaction.client.db() as session:
            found = await list_projects(
                session,
                interaction.user.id,
                interaction.guild_id,
                include_finished=include_finished,
            )

        if not found:
            await respond(
                interaction,
                "No crafting projects here yet. `/craft invent` starts one.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(title="Crafting projects", colour=_INVENTION)
        for project in found:
            embed.add_field(
                name=f"`{project.id}` {project.name}",
                value=(
                    f"{project.complexity.capitalize()} · **{project.stage}** · "
                    f"{project.attempts} attempt(s) · {project.elapsed_days} day(s)"
                ),
                inline=False,
            )
        embed.set_footer(text="B473-474")
        await respond(interaction, embed=embed, ephemeral=True)

    @craft.command(name="project", description="One project: stage, time, and what it has cost")
    @app_commands.describe(id="The project id from /craft projects")
    async def project(self, interaction: discord.Interaction[GURPSBot], id: int) -> None:
        async with interaction.client.db() as session:
            found = await get_project(session, id, interaction.user.id)
            if found is None:
                await respond(
                    interaction, f"No project `{id}` of yours.", ephemeral=True
                )
                return
            spent = await spent_by_kind(session, found.id)
            history = await charge_history(session, found.id)

        embed = discord.Embed(
            title=found.name,
            description=(
                f"{found.complexity.capitalize()} {found.domain} · "
                f"stage **{found.stage}** · skill {found.skill}"
            ),
            colour=_INVENTION,
        )
        embed.add_field(
            name="Progress",
            value=f"{found.attempts} attempt(s) over {found.elapsed_days} day(s)",
            inline=False,
        )
        # Three figures, still apart. Summing them here would undo the whole
        # point of storing them as typed rows.
        embed.add_field(
            name="Spent so far",
            value="\n".join(
                f"{kind}: ${amount:,}" for kind, amount in sorted(spent.items())
            )
            or "nothing yet",
            inline=False,
        )
        if history:
            recent = history[-5:]
            embed.add_field(
                name=f"Last {len(recent)} of {len(history)} charge(s)",
                value="\n".join(
                    f"`{c.kind}` ${c.amount:,}"
                    + (f" — {c.outcome}" if c.outcome else "")
                    for c in recent
                ),
                inline=False,
            )
        # `flawed_theory` is deliberately absent from this embed. B473 makes the
        # Concept roll secret so the player cannot learn it, and a project view
        # they can run themselves is the last place it should leak.
        embed.set_footer(text="B473-474")
        await respond(interaction, embed=embed, ephemeral=True)

    @craft.command(name="abandon", description="End a project — the spending stays on record")
    @app_commands.describe(id="The project id from /craft projects")
    async def abandon(self, interaction: discord.Interaction[GURPSBot], id: int) -> None:
        async with interaction.client.db() as session:
            found = await get_project(session, id, interaction.user.id)
            if found is None:
                await respond(
                    interaction, f"No project `{id}` of yours.", ephemeral=True
                )
                return
            if found.is_finished:
                await respond(
                    interaction,
                    f"`{id}` is already {found.stage}.",
                    ephemeral=True,
                )
                return
            name = found.name
            await finish_project(session, found, "abandoned")
            await session.commit()

        await respond(
            interaction,
            f"Abandoned **{name}**. Its charge history stays — the money was "
            f"still spent.",
            ephemeral=True,
        )


async def setup(bot: GURPSBot) -> None:
    await bot.add_cog(CraftingCog(bot))
