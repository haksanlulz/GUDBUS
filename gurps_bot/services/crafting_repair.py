"""A repair job (B484-485), across sessions.

Repair has no calendar of its own: an attempt IS the clock, thirty minutes
each, and the roll returns a quantity — 1 HP per point of margin, minimum 1.
A major repair (the item at 0 HP or less) buys spare parts first, at 1d x 10%
of the original price, and only then starts rolling. Something beyond repair
is refused at the door: the book says replace it, so there is nothing to keep.

State shape, and no other:

    {"inputs":   {price, max_hp, starting_hp, tier, workspace, time_spent,
                  tech_level, item_tech_level, unfamiliar, emp},
     "progress": {"current_hp": int, "parts_bought": bool},
     "result":   None | {"current_hp": int, "attempts": int}}

The project's ``skill`` column holds the mechanic's repair skill. Caller commits.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.crafting import CraftingProject
from gurps_bot.mechanics import crafting_repair as rules
from gurps_bot.mechanics import equipment_quality
from gurps_bot.mechanics import tech_level as tech_level_rules
from gurps_bot.mechanics.checks import Outcome, check_against
from gurps_bot.mechanics.crafting import ModifierBreakdown
from gurps_bot.services.crafting import (
    advance_stage,
    finish_project,
    record_attempt,
    record_charge,
    set_state,
    start_project,
)

DOMAIN = "repair"


def _inputs(project: CraftingProject) -> dict:
    return (project.state_json or {})["inputs"]


def _progress(project: CraftingProject) -> dict:
    return (project.state_json or {})["progress"]


def _modifier(inputs: dict) -> ModifierBreakdown:
    """The repair roll's modifiers, from the same rules `/craft repair` reads."""
    try:
        quality = equipment_quality.EquipmentQuality[inputs["workspace"]]
        emp = rules.EmpDamage[inputs["emp"]]
        tier = rules.RepairTier[inputs["tier"]]
    except KeyError as exc:
        raise ValueError(f"unknown repair option {exc.args[0]!r}") from None
    # Repair skills are technological, so the harsher half of B345 applies.
    equipment = equipment_quality.modifier(
        quality, technological=True, tech_level=inputs["tech_level"]
    )
    gap = None
    if inputs["item_tech_level"] is not None:
        if inputs["tech_level"] is None:
            raise ValueError(
                "to price a TL gap the mechanic's own TL is needed too — B168 "
                "measures the penalty between the skill and the equipment"
            )
        gap = tech_level_rules.tl_gap(
            skill_tl=inputs["tech_level"], equipment_tl=inputs["item_tech_level"]
        )
    return rules.repair_modifier(
        inputs["price"],
        tier,
        equipment_modifier=equipment,
        time_spent_modifier=inputs["time_spent"],
        tech_level_gap=gap,
        unfamiliar=inputs["unfamiliar"],
        emp=emp,
    )


async def start(
    session: AsyncSession,
    *,
    discord_user_id: int,
    guild_id: int | None,
    name: str,
    skill: int,
    price: int,
    current_hp: int,
    max_hp: int,
    workspace: str = equipment_quality.EquipmentQuality.BASIC.name,
    time_spent: int = 0,
    tech_level: int | None = None,
    item_tech_level: int | None = None,
    unfamiliar: bool = False,
    emp: str = rules.EmpDamage.NONE.name,
    character_id: int | None = None,
) -> CraftingProject:
    """Take the job: tier from the damage, every modifier validated through
    the engine, open at ``parts`` (major) or ``repairing`` (minor). Caller commits."""
    if skill < 1:
        raise ValueError(f"the repair skill must be at least 1, got {skill}")
    tier = rules.repair_tier(current_hp, max_hp)
    if tier is rules.RepairTier.BEYOND_REPAIR:
        raise ValueError(
            f"beyond repair — B484 says replace it at full price "
            f"(${rules.replacement_cost(price):,}); there is no job to keep"
        )
    inputs = dict(
        price=int(price),
        max_hp=int(max_hp),
        starting_hp=int(current_hp),
        tier=tier.name,
        workspace=workspace,
        time_spent=int(time_spent),
        tech_level=None if tech_level is None else int(tech_level),
        item_tech_level=None if item_tech_level is None else int(item_tech_level),
        unfamiliar=bool(unfamiliar),
        emp=emp,
    )
    _modifier(inputs)  # refuses an impossible TL gap, a bad workspace, a bad price

    project = await start_project(
        session,
        discord_user_id=discord_user_id,
        guild_id=guild_id,
        name=name,
        skill=skill,
        domain=DOMAIN,
        character_id=character_id,
        state={
            "inputs": inputs,
            "progress": {"current_hp": int(current_hp), "parts_bought": False},
            "result": None,
        },
    )
    if tier is rules.RepairTier.MINOR:
        await advance_stage(session, project, "repairing")
    return project


def tier_of(project: CraftingProject) -> rules.RepairTier:
    return rules.RepairTier[_inputs(project)["tier"]]


def modifier(project: CraftingProject) -> ModifierBreakdown:
    return _modifier(_inputs(project))


def roll_target(project: CraftingProject) -> int:
    return project.skill + modifier(project).total


def needs_parts(project: CraftingProject) -> bool:
    return project.stage == "parts"


def current_hp(project: CraftingProject) -> int:
    return int(_progress(project)["current_hp"])


def max_hp(project: CraftingProject) -> int:
    return int(_inputs(project)["max_hp"])


def minutes_spent(project: CraftingProject) -> int:
    """Attempts x the flat half hour — derived, never stored."""
    return project.attempts * rules.MINOR_REPAIR_MINUTES


async def buy_parts(session: AsyncSession, project: CraftingProject, *, rolled_1d: int) -> int:
    """B484: spare parts at 1d x 10% of the original price, once. Returns the
    cost; moves the job to ``repairing``. Caller commits."""
    if not needs_parts(project):
        raise ValueError(f"project {project.id} is not waiting for parts (stage {project.stage})")
    cost = rules.major_repair_parts_cost(_inputs(project)["price"], rolled_1d)
    await record_charge(
        session, project, kind="parts", amount=cost, note=f"1d rolled {rolled_1d}"
    )
    state = dict(project.state_json or {})
    progress = dict(state["progress"])
    progress["parts_bought"] = True
    state["progress"] = progress
    await set_state(session, project, state)
    await advance_stage(session, project, "repairing")
    return cost


async def resolve_attempt(
    session: AsyncSession, project: CraftingProject, *, rolled: int
) -> tuple[Outcome, int]:
    """One half-hour attempt. Returns (outcome, HP restored). Completes the
    job when the item is whole. Caller commits."""
    if project.is_finished:
        raise ValueError(f"project {project.id} is already {project.stage}")
    if needs_parts(project):
        raise ValueError("spare parts first — a major repair cannot start without them")
    if not 3 <= rolled <= 18:
        raise ValueError(f"a 3d roll is 3..18, got {rolled}")
    target = roll_target(project)
    outcome = check_against(rolled, target)
    hp, ceiling = current_hp(project), max_hp(project)
    restored = 0
    if outcome.succeeded:
        restored = min(rules.hp_restored(target - rolled), ceiling - hp)
        hp += restored

    note = f"rolled {rolled} vs {target}"
    if restored:
        note += f"; +{restored} HP ({hp}/{ceiling})"
    await record_attempt(
        session, project, amount=0, outcome=outcome.value.lower(), kind="attempt", note=note
    )
    state = dict(project.state_json or {})
    progress = dict(state["progress"])
    progress["current_hp"] = hp
    state["progress"] = progress
    if hp >= ceiling:
        state["result"] = {"current_hp": hp, "attempts": project.attempts}
    await set_state(session, project, state)
    if hp >= ceiling:
        await finish_project(session, project, "complete")
    return outcome, restored
