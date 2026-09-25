"""A mundane-crafting project (Low-Tech Companion 3 ch. 5), across sessions.

The calculator behind `/craft make` answers "what would it cost and how long";
this module is the same figures kept: the materials are charged when the
commission is taken, the hours are logged as the work happens, and when the
hours are in, one roll on the highest skill present says how good the piece
came out. Quality is the roll's RETURN VALUE — nothing here takes one.

State lives in `crafting_projects.state_json`, with this shape and no other:

    {"inputs":   {list_price, weight, cost_per_lb, monthly_pay, workers,
                  item_class, labor, materials, fine_materials, crucible_steel},
     "progress": {"hours_worked": float},
     "result":   None | {quality, margin, materials_lost,
                         sells_for_at_most_half, rolled, target}}

Every number is recomputed from ``inputs`` through `mechanics.crafting_mundane`
at read time, so a rules fix reaches an open project rather than freezing the
figure it was saved with. Caller commits.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.crafting import CraftingProject
from gurps_bot.mechanics import crafting_mundane as rules
from gurps_bot.services.crafting import (
    finish_project,
    record_attempt,
    record_charge,
    set_state,
    start_project,
)

DOMAIN = "crafting"


def _inputs(project: CraftingProject) -> dict:
    return (project.state_json or {})["inputs"]


def _progress(project: CraftingProject) -> dict:
    return (project.state_json or {})["progress"]


def _enums(inputs: dict) -> tuple[rules.ItemClass, rules.LaborKind, rules.MaterialMultiplier]:
    try:
        return (
            rules.ItemClass[inputs["item_class"]],
            rules.LaborKind[inputs["labor"]],
            rules.MaterialMultiplier[inputs["materials"]],
        )
    except KeyError as exc:
        raise ValueError(f"unknown crafting option {exc.args[0]!r}") from None


def _figures(inputs: dict) -> tuple[float, float, float]:
    """(materials cost, labour cost, hourly rate) from the book's own functions."""
    _klass, kind, multiplier = _enums(inputs)
    material_cost = rules.materials_cost(inputs["weight"], inputs["cost_per_lb"], multiplier)
    labour = rules.labor_cost(inputs["list_price"], material_cost)
    rate = rules.hourly_labor_rate(inputs["monthly_pay"], kind)
    return material_cost, labour, rate


async def start(
    session: AsyncSession,
    *,
    discord_user_id: int,
    guild_id: int | None,
    name: str,
    skill: int,
    list_price: float,
    weight: float,
    cost_per_lb: float,
    monthly_pay: float,
    workers: int = 1,
    item_class: str = rules.ItemClass.GENERAL.name,
    labor: str = rules.LaborKind.ROUTINE.name,
    materials: str = rules.MaterialMultiplier.NONE.name,
    fine_materials: int = 0,
    crucible_steel: bool = False,
    character_id: int | None = None,
) -> CraftingProject:
    """Take the commission: validate every figure through the engine, charge
    the materials, open at ``working``. Caller commits.

    ``skill`` is the highest craft skill among the workers involved — LTC3's
    reading of who rolls (`rules.rolling_skill`), and the opposite of alchemy's.
    """
    if skill < 1:
        raise ValueError(f"the rolling skill must be at least 1, got {skill}")
    inputs: dict[str, Any] = dict(
        list_price=float(list_price),
        weight=float(weight),
        cost_per_lb=float(cost_per_lb),
        monthly_pay=float(monthly_pay),
        workers=int(workers),
        item_class=item_class,
        labor=labor,
        materials=materials,
        fine_materials=int(fine_materials),
        crucible_steel=bool(crucible_steel),
    )
    material_cost, labour, rate = _figures(inputs)
    if labour < 0:
        # The calculator says this plainly and stops; a project cannot hold
        # negative hours, so there is nothing to persist until it is fixed.
        raise ValueError(
            f"the materials (${material_cost:,.2f}) cost more than the item sells "
            f"for (${inputs['list_price']:,.2f}) — the material or the weight is "
            f"wrong for this item"
        )
    active = rules.active_hours(labour, rate)
    rules.elapsed_hours(active, inputs["workers"])  # the worker count's own bounds
    rules.effective_margin(
        0, fine_materials=inputs["fine_materials"], crucible_steel=inputs["crucible_steel"]
    )

    project = await start_project(
        session,
        discord_user_id=discord_user_id,
        guild_id=guild_id,
        name=name,
        skill=skill,
        domain=DOMAIN,
        character_id=character_id,
        state={"inputs": inputs, "progress": {"hours_worked": 0.0}, "result": None},
    )
    await record_charge(session, project, kind="materials", amount=round(material_cost))
    return project


def required_hours(project: CraftingProject) -> float:
    """Man-hours the piece needs, from the labour share and the pay rate."""
    _material_cost, labour, rate = _figures(_inputs(project))
    return rules.active_hours(max(labour, 0.0), rate)


def elapsed_hours(project: CraftingProject) -> float:
    """Wall-clock hours, with the six-worker cap applied by the rule."""
    return rules.elapsed_hours(required_hours(project), _inputs(project)["workers"])


def hours_worked(project: CraftingProject) -> float:
    return float(_progress(project).get("hours_worked", 0.0))


async def log_hours(session: AsyncSession, project: CraftingProject, hours: float) -> float:
    """Add worked hours; returns the new total. Caller commits."""
    if hours <= 0:
        raise ValueError(f"log a positive number of hours, got {hours}")
    if project.is_finished:
        raise ValueError(f"project {project.id} is {project.stage} — nothing left to work on")
    state = dict(project.state_json or {})
    progress = dict(state["progress"])
    progress["hours_worked"] = hours_worked(project) + float(hours)
    state["progress"] = progress
    await set_state(session, project, state)
    return progress["hours_worked"]


def roll_target(project: CraftingProject) -> int:
    return project.skill


def ready_to_roll(project: CraftingProject) -> str | None:
    """None when the roll may be made, else the reason it may not."""
    if project.is_finished:
        return f"project {project.id} is already {project.stage}"
    worked, needed = hours_worked(project), required_hours(project)
    if worked + 1e-9 < needed:
        return f"{worked:g} of {needed:,.1f} hours logged — the work is not done"
    return None


async def resolve_roll(
    session: AsyncSession, project: CraftingProject, *, rolled: int
) -> rules.CraftResult:
    """One roll, one quality. Records the outcome and completes. Caller commits.

    ⚑ LTC3 reads the roll by MARGIN alone: a critical success "doesn't impact
    quality beyond margin of success", so the core engine's outcome is not
    consulted — `craft_quality` is the whole verdict.
    """
    reason = ready_to_roll(project)
    if reason:
        raise ValueError(reason)
    if not 3 <= rolled <= 18:
        raise ValueError(f"a 3d roll is 3..18, got {rolled}")
    inputs = _inputs(project)
    klass, _kind, _multiplier = _enums(inputs)
    target = roll_target(project)
    margin = rules.effective_margin(
        target - rolled,
        fine_materials=inputs["fine_materials"],
        crucible_steel=inputs["crucible_steel"],
    )
    result = rules.craft_quality(margin, klass)

    note = f"rolled {rolled} vs {target}"
    if result.materials_lost:
        note += "; at least half the raw materials lost"
    if result.sells_for_at_most_half:
        note += "; sells for at most half price"
    await record_attempt(
        session, project, amount=0, outcome=result.quality.name, kind="roll", note=note
    )
    state = dict(project.state_json or {})
    state["result"] = {
        "quality": result.quality.name,
        "margin": result.margin,
        "materials_lost": result.materials_lost,
        "sells_for_at_most_half": result.sells_for_at_most_half,
        "rolled": rolled,
        "target": target,
    }
    await set_state(session, project, state)
    await finish_project(session, project, "complete")
    return result
