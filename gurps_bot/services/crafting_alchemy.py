"""A brewing batch (GURPS Magic ch. 28), across sessions.

The ingredients are paid when the batch is started, the calendar passes, and
one roll decides the whole batch — with no critical successes, and a two-step
disaster on a critical failure: first the technique roll at -1 per dose, then,
if that fails too, 3d on the disaster table.

State shape, and no other:

    {"inputs":   {alchemy_skill, helper_skill, cost_per_dose, doses, technique,
                  lab, mana, weeks, formulary, teacher, tech_level},
     "progress": {"weeks_elapsed": float, "disaster_roll_modifier": int?},
     "result":   None | {succeeded, ingredients_ruined, doses, rolled, target,
                         disaster?: {...}}}

The project's ``skill`` column holds the ROLLER's skill — the lowest-skilled
alchemist who touched the batch (`rules.final_roller_skill`). Caller commits.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.crafting import CraftingProject
from gurps_bot.mechanics import crafting_alchemy as rules
from gurps_bot.mechanics.checks import Outcome, check_against
from gurps_bot.services.crafting import (
    advance_stage,
    finish_project,
    record_attempt,
    record_charge,
    set_state,
    start_project,
)

DOMAIN = "alchemy"


def _inputs(project: CraftingProject) -> dict:
    return (project.state_json or {})["inputs"]


def _progress(project: CraftingProject) -> dict:
    return (project.state_json or {})["progress"]


def _enums(inputs: dict) -> tuple[rules.LabQuality, rules.Mana]:
    try:
        return rules.LabQuality[inputs["lab"]], rules.Mana[inputs["mana"]]
    except KeyError as exc:
        raise ValueError(f"unknown alchemy option {exc.args[0]!r}") from None


async def start(
    session: AsyncSession,
    *,
    discord_user_id: int,
    guild_id: int | None,
    name: str,
    alchemy_skill: int,
    cost_per_dose: int,
    doses: int = 1,
    technique: int | None = None,
    lab: str = rules.LabQuality.BASIC.name,
    mana: str = rules.Mana.NORMAL.name,
    weeks: float = 1.0,
    formulary: bool = False,
    teacher: bool = False,
    helper_skill: int | None = None,
    tech_level: int | None = None,
    character_id: int | None = None,
) -> CraftingProject:
    """Start the batch: validate through the engine, charge the ingredients,
    open at ``brewing``. Caller commits."""
    inputs: dict[str, Any] = dict(
        alchemy_skill=int(alchemy_skill),
        helper_skill=None if helper_skill is None else int(helper_skill),
        cost_per_dose=int(cost_per_dose),
        doses=int(doses),
        technique=None if technique is None else int(technique),
        lab=lab,
        mana=mana,
        weeks=float(weeks),
        formulary=bool(formulary),
        teacher=bool(teacher),
        tech_level=None if tech_level is None else int(tech_level),
    )
    quality, mana_level = _enums(inputs)
    if not rules.can_brew(mana_level):
        raise ValueError("elixirs cannot be made or used in a no-mana area at all")
    if inputs["weeks"] <= 0:
        raise ValueError(f"brewing time should be more than zero, got {weeks}")
    roller = inputs["alchemy_skill"]
    if inputs["helper_skill"] is not None:
        roller = rules.final_roller_skill([roller, inputs["helper_skill"]])
    # the engine's own bounds on doses, technique and the lab
    rules.brewing_modifier(
        alchemy_skill=roller,
        technique=inputs["technique"],
        lab=quality,
        tech_level=inputs["tech_level"],
        doses=inputs["doses"],
        formulary=inputs["formulary"],
        teacher=inputs["teacher"],
    )
    cost = rules.batch_materials_cost(inputs["cost_per_dose"], inputs["doses"])

    project = await start_project(
        session,
        discord_user_id=discord_user_id,
        guild_id=guild_id,
        name=name,
        skill=roller,
        domain=DOMAIN,
        character_id=character_id,
        state={"inputs": inputs, "progress": {"weeks_elapsed": 0.0}, "result": None},
    )
    await record_charge(session, project, kind="ingredients", amount=cost)
    return project


def required_weeks(project: CraftingProject) -> float:
    inputs = _inputs(project)
    _quality, mana_level = _enums(inputs)
    return inputs["weeks"] * rules.brewing_time_multiplier(mana_level)


def weeks_elapsed(project: CraftingProject) -> float:
    return float(_progress(project).get("weeks_elapsed", 0.0))


async def log_weeks(session: AsyncSession, project: CraftingProject, weeks: float) -> float:
    """Let the calendar pass; returns the new total. Caller commits."""
    if weeks <= 0:
        raise ValueError(f"log a positive number of weeks, got {weeks}")
    if project.is_finished:
        raise ValueError(f"project {project.id} is {project.stage} — the batch is done")
    if project.stage == "disaster":
        raise ValueError("the disaster roll is pending — nothing is brewing")
    state = dict(project.state_json or {})
    progress = dict(state["progress"])
    progress["weeks_elapsed"] = weeks_elapsed(project) + float(weeks)
    state["progress"] = progress
    await set_state(session, project, state)
    return progress["weeks_elapsed"]


def roll_target(project: CraftingProject) -> int:
    inputs = _inputs(project)
    quality, _mana = _enums(inputs)
    return rules.effective_target(
        alchemy_skill=project.skill,
        technique=inputs["technique"],
        lab=quality,
        tech_level=inputs["tech_level"],
        doses=inputs["doses"],
        formulary=inputs["formulary"],
        teacher=inputs["teacher"],
    )


def ready_to_roll(project: CraftingProject) -> str | None:
    """None when the brewing roll may be made, else the reason it may not."""
    if project.is_finished:
        return f"project {project.id} is already {project.stage}"
    if project.stage == "disaster":
        return "the batch is past its brewing roll — the disaster roll is what is pending"
    done, needed = weeks_elapsed(project), required_weeks(project)
    if done + 1e-9 < needed:
        return f"{done:g} of {needed:g} weeks elapsed — the batch is still brewing"
    return None


def _outcome_key(outcome: Outcome) -> str:
    # The domain's own check variant: "either the process worked or it did
    # not". A critical success is READ AS a success here, deliberately, so the
    # engine's `resolve_brew` never sees the key it refuses.
    if outcome.succeeded:
        return "success"
    if outcome is Outcome.CRITICAL_FAILURE:
        return "critical_failure"
    return "failure"


async def resolve_roll(
    session: AsyncSession, project: CraftingProject, *, rolled: int
) -> rules.BrewOutcome:
    """The brewing roll. Completes the batch, or parks it at ``disaster``.
    Caller commits."""
    reason = ready_to_roll(project)
    if reason:
        raise ValueError(reason)
    if not 3 <= rolled <= 18:
        raise ValueError(f"a 3d roll is 3..18, got {rolled}")
    inputs = _inputs(project)
    _quality, mana_level = _enums(inputs)
    target = roll_target(project)
    key = _outcome_key(check_against(rolled, target))
    brew = rules.resolve_brew(key, inputs["doses"], mana_level)

    state = dict(project.state_json or {})
    progress = dict(state["progress"])
    if brew.needs_disaster_roll:
        await record_attempt(
            session, project, amount=0, outcome="critical_failure", kind="roll",
            note=f"rolled {rolled} vs {target}; ingredients ruined, disaster roll pending",
        )
        progress["disaster_roll_modifier"] = brew.disaster_roll_modifier
        progress["brew_rolled"] = rolled
        progress["brew_target"] = target
        state["progress"] = progress
        await set_state(session, project, state)
        await advance_stage(session, project, "disaster")
        return brew

    note = f"rolled {rolled} vs {target}"
    if brew.ingredients_ruined:
        note += "; ingredients ruined"
    await record_attempt(session, project, amount=0, outcome=key, kind="roll", note=note)
    state["result"] = {
        "succeeded": brew.succeeded,
        "ingredients_ruined": brew.ingredients_ruined,
        "doses": inputs["doses"] if brew.succeeded else 0,
        "rolled": rolled,
        "target": target,
    }
    await set_state(session, project, state)
    await finish_project(session, project, "complete")
    return brew


def disaster_target(project: CraftingProject) -> int:
    """The second technique roll: the elixir's technique at -1 per dose."""
    if project.stage != "disaster":
        raise ValueError(f"project {project.id} has no disaster roll pending")
    inputs = _inputs(project)
    technique = inputs["technique"]
    if technique is None:
        technique = rules.default_technique_level(project.skill)
    return technique + _progress(project)["disaster_roll_modifier"]


async def resolve_disaster(
    session: AsyncSession,
    project: CraftingProject,
    *,
    rolled: int,
    rolled_3d: int | None,
) -> rules.Disaster | None:
    """The disaster-avoidance roll, then the table if it fails. Caller commits.

    ``rolled`` is the technique roll; ``rolled_3d`` is the table roll, needed
    only when the first one fails. Returns the disaster row, or None when it
    was averted. Either way the batch completes — the ingredients were already
    ruined by the critical failure that brought it here.
    """
    target = disaster_target(project)
    if not 3 <= rolled <= 18:
        raise ValueError(f"a 3d roll is 3..18, got {rolled}")
    state = dict(project.state_json or {})
    brew = _progress(project)
    base = {
        "succeeded": False,
        "ingredients_ruined": True,
        "doses": 0,
        "rolled": brew.get("brew_rolled"),
        "target": brew.get("brew_target"),
    }
    if check_against(rolled, target).succeeded:
        await record_attempt(
            session, project, amount=0, outcome="disaster averted", kind="roll",
            note=f"technique roll {rolled} vs {target}",
        )
        state["result"] = {**base, "disaster": None}
        await set_state(session, project, state)
        await finish_project(session, project, "complete")
        return None

    if rolled_3d is None:
        raise ValueError("the disaster roll failed — the 3d table roll is needed too")
    disaster = rules.disaster_for(rolled_3d)
    await record_attempt(
        session, project, amount=0, outcome="disaster", kind="roll",
        note=f"technique roll {rolled} vs {target}; table roll {rolled_3d}",
    )
    state["result"] = {
        **base,
        "disaster": {
            "rolled_3d": rolled_3d,
            "elixir_radius_yards": disaster.elixir_radius_yards,
            "reversed_is_even_odds": disaster.reversed_is_even_odds,
            "lab_destroyed": disaster.lab_destroyed,
            "alchemist_damage": (
                str(disaster.alchemist_damage) if disaster.alchemist_damage else None
            ),
        },
    }
    await set_state(session, project, state)
    await finish_project(session, project, "complete")
    return disaster
