"""How a crafting project looks — one line in a list, one embed on its own.

Pure rendering: a project (and its ledger) in, Discord objects out. Each
domain has its own paragraph here because each keeps its own state; the only
shared parts are the frame (name, spend by kind, the last few charges) and
the two small formatters the crafting cog uses for modifier breakdowns.

``flawed_theory`` is deliberately never rendered — B473 keeps it from the
player, and a project view they can run themselves is the last place it
should leak.
"""

from __future__ import annotations

import discord

from gurps_bot.db.crafting import CraftingCharge, CraftingProject
from gurps_bot.mechanics import crafting_alchemy as alchemy_rules
from gurps_bot.mechanics import crafting_enchantment as enchantment_rules
from gurps_bot.mechanics import crafting_mundane as mundane_rules
from gurps_bot.mechanics import crafting_repair as repair_rules
from gurps_bot.mechanics.crafting import ModifierBreakdown
from gurps_bot.services import crafting_alchemy as alchemy
from gurps_bot.services import crafting_enchantment as enchantment
from gurps_bot.services import crafting_mundane as mundane
from gurps_bot.services import crafting_repair as repair

COLOUR = discord.Color.dark_gold()

#: Where each domain's rules are printed — the footer of its project view.
CITES = {
    "invention": "B473-474",
    "crafting": "Low-Tech Companion 3 ch. 5",
    "alchemy": "GURPS Magic ch. 28",
    "enchantment": "GURPS Magic pp. 16-18",
    "repair": "B484",
}


def fmt_mod(value: int) -> str:
    return f"+{value}" if value >= 0 else str(value)


def breakdown_lines(modifier: ModifierBreakdown) -> str:
    return "\n".join(f"`{fmt_mod(v):>3}`  {label}" for label, v in modifier.terms)


def _plural(n: float | int, word: str) -> str:
    return f"{n:g} {word}{'' if n == 1 else 's'}"


def _inputs(project: CraftingProject) -> dict:
    """A domain project's figures. Empty for invention, which has none here."""
    return (project.state_json or {}).get("inputs", {})


# --- one line per project, for /craft projects ------------------------------


def list_line(project: CraftingProject) -> str:
    stage = f"**{project.stage}**"
    if project.domain == "crafting":
        head = f"Making · {stage} · {mundane.hours_worked(project):g}/{mundane.required_hours(project):,.1f} h"
        result = (project.state_json or {}).get("result")
        if result:
            head += f" · {mundane_rules.Quality[result['quality']].value}"
        return head
    if project.domain == "alchemy":
        doses = _inputs(project)["doses"]
        return (
            f"Brewing {_plural(doses, 'dose')} · {stage} · "
            f"{alchemy.weeks_elapsed(project):g}/{alchemy.required_weeks(project):g} wk"
        )
    if project.domain == "enchantment":
        if enchantment.method_of(project) is enchantment_rules.Method.QUICK_AND_DIRTY:
            time = f"{_plural(enchantment.required_hours(project), 'hour')}, one sitting"
        else:
            time = f"{enchantment.days_worked(project):g}/{enchantment.required_days(project):g} days"
        return f"Enchanting · {stage} · {time}"
    if project.domain == "repair":
        return (
            f"Repairing · {stage} · {repair.current_hp(project)}/{repair.max_hp(project)} HP · "
            f"{project.attempts} attempt(s)"
        )
    complexity = (project.complexity or "").capitalize()
    return (
        f"{complexity} · {stage} · "
        f"{project.attempts} attempt(s) · {project.elapsed_days} day(s)"
    )


# --- the project view, for /craft project -----------------------------------


def detail_embed(
    project: CraftingProject,
    spent: dict[str, int],
    history: list[CraftingCharge],
) -> discord.Embed:
    embed = discord.Embed(title=project.name, colour=COLOUR)
    renderer = _RENDERERS.get(project.domain, _invention)
    renderer(project, embed)

    # Figures stay apart. Summing them would undo the point of typed rows.
    embed.add_field(
        name="Spent so far",
        value="\n".join(f"{kind}: ${amount:,}" for kind, amount in sorted(spent.items()))
        or "nothing yet",
        inline=False,
    )
    if history:
        recent = history[-5:]
        embed.add_field(
            name=f"Last {len(recent)} of {len(history)} charge(s)",
            value="\n".join(
                f"`{c.kind}` ${c.amount:,}" + (f" — {c.outcome}" if c.outcome else "")
                for c in recent
            ),
            inline=False,
        )
    embed.set_footer(text=CITES.get(project.domain, CITES["invention"]))
    return embed


def _invention(project: CraftingProject, embed: discord.Embed) -> None:
    embed.description = (
        f"{(project.complexity or '').capitalize()} {project.domain} · "
        f"stage **{project.stage}** · skill {project.skill}"
    )
    embed.add_field(
        name="Progress",
        value=f"{project.attempts} attempt(s) over {project.elapsed_days} day(s)",
        inline=False,
    )


def _crafting(project: CraftingProject, embed: discord.Embed) -> None:
    inputs = _inputs(project)
    klass = mundane_rules.ItemClass[inputs["item_class"]]
    kind = mundane_rules.LaborKind[inputs["labor"]]
    multiplier = mundane_rules.MaterialMultiplier[inputs["materials"]]
    embed.description = f"Making it by hand · stage **{project.stage}** · rolling skill {project.skill}"
    embed.add_field(
        name="The piece",
        value=(
            f"${inputs['list_price']:,.2f} list · {inputs['weight']:g} lbs at "
            f"${inputs['cost_per_lb']:,.2f}/lb"
            + (f" x{multiplier.value}" if multiplier.value != 1 else "")
            + f" · {klass.value} · {kind.value}"
            + (f" · {inputs['workers']} working" if inputs["workers"] > 1 else "")
        ),
        inline=False,
    )
    required = mundane.required_hours(project)
    line = f"**{mundane.hours_worked(project):g}** of **{required:,.1f}** man-hours logged"
    if inputs["workers"] > 1:
        line += f" ({mundane.elapsed_hours(project):,.1f} hours with the crew)"
    embed.add_field(name="Time", value=line, inline=False)
    extras = []
    if inputs["fine_materials"]:
        extras.append(f"superior materials +{inputs['fine_materials']} to the margin")
    if inputs["crucible_steel"]:
        extras.append(f"crucible steel +{mundane_rules.CRUCIBLE_STEEL_MARGIN} to the margin")
    result = (project.state_json or {}).get("result")
    if result:
        quality = mundane_rules.Quality[result["quality"]]
        text = f"**{quality.value}** — rolled {result['rolled']} vs {result['target']}, margin {result['margin']}"
        if result["materials_lost"]:
            text += "; at least half the raw materials lost"
        if result["sells_for_at_most_half"]:
            text += "; sells for at most half price"
        embed.add_field(name="Result", value=text, inline=False)
    else:
        embed.add_field(
            name="The roll",
            value=f"Against **{mundane.roll_target(project)}** once the hours are in"
            + (" · " + "; ".join(extras) if extras else ""),
            inline=False,
        )


def _alchemy(project: CraftingProject, embed: discord.Embed) -> None:
    inputs = _inputs(project)
    lab = alchemy_rules.LabQuality[inputs["lab"]]
    mana = alchemy_rules.Mana[inputs["mana"]]
    embed.description = f"Brewing · stage **{project.stage}** · rolling skill {project.skill}"
    batch = (
        f"{_plural(inputs['doses'], 'dose')} at ${inputs['cost_per_dose']:,}/dose · "
        f"{lab.value} · {mana.value}"
    )
    if inputs["helper_skill"] is not None:
        batch += f" · helper at {inputs['helper_skill']}"
    if inputs["formulary"]:
        batch += " · formulary"
    if inputs["teacher"]:
        batch += " · supervised"
    embed.add_field(name="The batch", value=batch, inline=False)
    embed.add_field(
        name="Time",
        value=f"**{alchemy.weeks_elapsed(project):g}** of **{alchemy.required_weeks(project):g}** weeks",
        inline=False,
    )
    result = (project.state_json or {}).get("result")
    if project.stage == "disaster":
        embed.add_field(
            name="Disaster roll pending",
            value=(
                f"The technique roll against **{alchemy.disaster_target(project)}** "
                f"decides whether the critical failure becomes a disaster."
            ),
            inline=False,
        )
    elif result:
        if result["succeeded"]:
            text = f"**{_plural(result['doses'], 'dose')} brewed** — rolled {result['rolled']} vs {result['target']}"
        else:
            text = f"**Failed** — rolled {result['rolled']} vs {result['target']}; ingredients ruined"
            disaster = result.get("disaster")
            if disaster:
                parts = [f"table roll {disaster['rolled_3d']}"]
                if disaster["elixir_radius_yards"]:
                    parts.append(
                        f"everyone within {disaster['elixir_radius_yards']} yards suffers "
                        f"the elixir's effect or its reverse, even odds"
                    )
                if disaster["lab_destroyed"]:
                    parts.append("the laboratory is destroyed")
                if disaster["alchemist_damage"]:
                    parts.append(f"the alchemist takes {disaster['alchemist_damage']}")
                text += "; **disaster** — " + "; ".join(parts)
            elif result.get("disaster", 0) is None:
                text += "; the disaster was averted"
        embed.add_field(name="Result", value=text, inline=False)
    else:
        embed.add_field(
            name="The roll",
            value=f"Against **{alchemy.roll_target(project)}** once the weeks have passed — no critical successes",
            inline=False,
        )


def _enchantment(project: CraftingProject, embed: discord.Embed) -> None:
    inputs = _inputs(project)
    method = enchantment.method_of(project)
    where = enchantment_rules.Mana[inputs["mana"]]
    embed.description = f"{method.value} · stage **{project.stage}** · base skill {project.skill}"
    circle = f"{inputs['energy']} energy"
    if inputs["assistants"]:
        circle += f" · {_plural(inputs['assistants'], 'assistant')}"
    if inputs["hp_spent"]:
        circle += f" · {inputs['hp_spent']} HP spent"
    if inputs["bystanders"]:
        circle += " · someone within 10 yards"
    circle += f" · used in {where.value.lower()}"
    embed.add_field(name="The enchantment", value=circle, inline=False)
    if method is enchantment_rules.Method.QUICK_AND_DIRTY:
        time = f"**{_plural(enchantment.required_hours(project), 'hour')}**, one sitting"
    else:
        time = (
            f"**{enchantment.days_worked(project):g}** of "
            f"**{enchantment.required_days(project):g}** days"
        )
        if enchantment.days_missed(project):
            time += f" ({_plural(enchantment.days_missed(project), 'day')} missed, two each to make up)"
    embed.add_field(name="Time", value=time, inline=False)
    result = (project.state_json or {}).get("result")
    if result:
        outcome = enchantment_rules.CeremonialOutcome[result["outcome"]]
        text = f"**{outcome.value.capitalize()}** — rolled {result['rolled']} vs {result['target']}"
        if result["power"] is not None:
            text += f"; Power **{result['power']}**"
            if result.get("power_bonus_rolled") is not None:
                text += f" (+{result['power_bonus_rolled']} for the critical success)"
            text += ", it works" if result["works"] else ", it will not work where it is used"
        if result["may_have_further_enhancement"]:
            text += "; the GM may add a further enhancement"
        if result["item_destroyed"]:
            text += "; item and materials destroyed"
        elif result["materials_lost"]:
            text += "; materials lost"
        embed.add_field(name="Result", value=text, inline=False)
    else:
        embed.add_field(
            name="Roll against, and the item's Power",
            value=f"**{enchantment.roll_target(project)}** — a 16 always fails, 17-18 is always critical",
            inline=False,
        )


def _repair(project: CraftingProject, embed: discord.Embed) -> None:
    inputs = _inputs(project)
    tier = repair.tier_of(project)
    embed.description = f"{tier.value} · stage **{project.stage}** · repair skill {project.skill}"
    embed.add_field(
        name="The item",
        value=(
            f"${inputs['price']:,} · **{repair.current_hp(project)}/{repair.max_hp(project)} HP** "
            f"(started at {inputs['starting_hp']})"
        ),
        inline=False,
    )
    modifier = repair.modifier(project)
    embed.add_field(name="Modifiers", value=breakdown_lines(modifier) or "none", inline=False)
    if repair.needs_parts(project):
        embed.add_field(
            name="Spare parts first",
            value=(
                f"1d x 10% of ${inputs['price']:,} — "
                f"${repair_rules.major_repair_parts_cost(inputs['price'], 1):,} to "
                f"${repair_rules.major_repair_parts_cost(inputs['price'], 6):,}; "
                f"`/craft roll` rolls it"
            ),
            inline=False,
        )
    else:
        embed.add_field(
            name="Each attempt",
            value=(
                f"Against **{repair.roll_target(project)}**, {repair_rules.MINOR_REPAIR_MINUTES} "
                f"minutes; success restores 1 HP per point of margin (minimum 1)"
            ),
            inline=False,
        )
    embed.add_field(
        name="Attempts",
        value=f"{project.attempts} ({repair.minutes_spent(project)} minutes)",
        inline=False,
    )
    if project.stage == "complete":
        embed.add_field(name="Result", value="**Repaired** — the item is at full HP", inline=False)


_RENDERERS = {
    "invention": _invention,
    "crafting": _crafting,
    "alchemy": _alchemy,
    "enchantment": _enchantment,
    "repair": _repair,
}
