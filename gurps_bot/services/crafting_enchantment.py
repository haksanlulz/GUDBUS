"""An enchantment in progress (GURPS Magic pp. 16-18), across sessions.

Quick and Dirty is one sitting — the project exists so the roll and its result
are on record, not because a calendar passes. Slow and Sure is where
persistence earns its keep: one mage-day per point of energy, split across the
circle, with a missed day costing two to make up. The ceremonial roll ends
both, and its target is also the finished item's Power.

State shape, and no other:

    {"inputs":   {enchant_skill, spell_skill, energy, method, assistants,
                  hp_spent, bystanders, mana, materials_value},
     "progress": {"days_worked": float, "days_missed": int},
     "result":   None | {outcome, power, works, power_bonus_rolled,
                         may_have_further_enhancement, item_destroyed,
                         materials_lost, rolled, target}}

The project's ``skill`` column holds the base enchanting skill — the LOWER of
Enchant and the spell (`rules.enchanting_skill`). Caller commits.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.crafting import CraftingProject
from gurps_bot.mechanics import crafting_enchantment as rules
from gurps_bot.services.crafting import (
    finish_project,
    record_attempt,
    record_charge,
    set_state,
    start_project,
)

DOMAIN = "enchantment"


def _inputs(project: CraftingProject) -> dict:
    return (project.state_json or {})["inputs"]


def _progress(project: CraftingProject) -> dict:
    return (project.state_json or {})["progress"]


def _enums(inputs: dict) -> tuple[rules.Method, rules.Mana]:
    try:
        return rules.Method[inputs["method"]], rules.Mana[inputs["mana"]]
    except KeyError as exc:
        raise ValueError(f"unknown enchantment option {exc.args[0]!r}") from None


async def start(
    session: AsyncSession,
    *,
    discord_user_id: int,
    guild_id: int | None,
    name: str,
    enchant_skill: int,
    spell_skill: int,
    energy: int,
    method: str = rules.Method.SLOW_AND_SURE.name,
    assistants: int = 0,
    hp_spent: int = 0,
    bystanders: bool = False,
    mana: str = rules.Mana.NORMAL.name,
    materials_value: int = 0,
    character_id: int | None = None,
) -> CraftingProject:
    """Begin the enchantment: validate through the engine, charge the
    materials if a value was given, open at ``enchanting``. Caller commits."""
    inputs: dict[str, Any] = dict(
        enchant_skill=int(enchant_skill),
        spell_skill=int(spell_skill),
        energy=int(energy),
        method=method,
        assistants=int(assistants),
        hp_spent=int(hp_spent),
        bystanders=bool(bystanders),
        mana=mana,
        materials_value=int(materials_value),
    )
    chosen, _where = _enums(inputs)
    if inputs["materials_value"] < 0:
        raise ValueError(f"materials value cannot be negative, got {materials_value}")
    base = rules.enchanting_skill(inputs["enchant_skill"], inputs["spell_skill"])
    # Slow and Sure refuses hp_spent here; every other bound is the engine's too.
    rules.enchanting_modifier(
        method=chosen,
        assistants=inputs["assistants"],
        hp_spent=inputs["hp_spent"],
        bystanders=inputs["bystanders"],
    )
    if chosen is rules.Method.QUICK_AND_DIRTY:
        rules.quick_and_dirty_hours(inputs["energy"])
    else:
        rules.slow_and_sure_days(inputs["energy"], inputs["assistants"] + 1)

    project = await start_project(
        session,
        discord_user_id=discord_user_id,
        guild_id=guild_id,
        name=name,
        skill=base,
        domain=DOMAIN,
        character_id=character_id,
        state={
            "inputs": inputs,
            "progress": {"days_worked": 0.0, "days_missed": 0},
            "result": None,
        },
    )
    if inputs["materials_value"]:
        await record_charge(
            session, project, kind="materials", amount=inputs["materials_value"]
        )
    return project


def method_of(project: CraftingProject) -> rules.Method:
    chosen, _where = _enums(_inputs(project))
    return chosen


def required_hours(project: CraftingProject) -> int:
    """Quick and Dirty: the hours of the one sitting (0 under Slow and Sure)."""
    inputs = _inputs(project)
    if method_of(project) is not rules.Method.QUICK_AND_DIRTY:
        return 0
    return rules.quick_and_dirty_hours(inputs["energy"])


def required_days(project: CraftingProject) -> float:
    """Slow and Sure: mage-days split across the circle, plus two per missed
    day (0 under Quick and Dirty — there is no calendar)."""
    inputs = _inputs(project)
    if method_of(project) is rules.Method.QUICK_AND_DIRTY:
        return 0.0
    return rules.slow_and_sure_days(
        inputs["energy"], inputs["assistants"] + 1
    ) + rules.make_up_days(int(_progress(project).get("days_missed", 0)))


def days_worked(project: CraftingProject) -> float:
    return float(_progress(project).get("days_worked", 0.0))


def days_missed(project: CraftingProject) -> int:
    return int(_progress(project).get("days_missed", 0))


async def log_days(
    session: AsyncSession, project: CraftingProject, days: float, *, missed: int = 0
) -> float:
    """Record days of work and days skipped or interrupted. Returns the new
    total worked. Caller commits."""
    if method_of(project) is rules.Method.QUICK_AND_DIRTY:
        raise ValueError("Quick and Dirty enchantment is one sitting — there is no calendar to log")
    if project.is_finished:
        raise ValueError(f"project {project.id} is {project.stage} — the enchantment is over")
    if days < 0 or missed < 0:
        raise ValueError("days worked and days missed cannot be negative")
    if days == 0 and missed == 0:
        raise ValueError("log at least a day worked or a day missed")
    rules.make_up_days(int(missed))
    state = dict(project.state_json or {})
    progress = dict(state["progress"])
    progress["days_worked"] = days_worked(project) + float(days)
    progress["days_missed"] = days_missed(project) + int(missed)
    state["progress"] = progress
    await set_state(session, project, state)
    return progress["days_worked"]


def roll_target(project: CraftingProject) -> int:
    """The effective skill — and the finished item's Power, one number."""
    inputs = _inputs(project)
    chosen, _where = _enums(inputs)
    return rules.effective_skill(
        inputs["enchant_skill"],
        inputs["spell_skill"],
        method=chosen,
        assistants=inputs["assistants"],
        hp_spent=inputs["hp_spent"],
        bystanders=inputs["bystanders"],
    )


def ready_to_roll(project: CraftingProject) -> str | None:
    """None when the ceremonial roll may be made, else the reason it may not."""
    if project.is_finished:
        return f"project {project.id} is already {project.stage}"
    if method_of(project) is rules.Method.QUICK_AND_DIRTY:
        return None
    done, needed = days_worked(project), required_days(project)
    if done + 1e-9 < needed:
        return f"{done:g} of {needed:g} days worked — the circle is not finished"
    return None


async def resolve_roll(
    session: AsyncSession,
    project: CraftingProject,
    *,
    rolled_3d: int,
    power_bonus_rolled: int | None = None,
) -> rules.EnchantmentResult:
    """The ceremonial roll (16 always fails, 17-18 always critical). Records
    the outcome and completes. Caller commits.

    ``power_bonus_rolled`` is the 2d the book adds to Power on a critical
    success; it is required exactly when the roll is one, and ignored otherwise.
    """
    reason = ready_to_roll(project)
    if reason:
        raise ValueError(reason)
    inputs = _inputs(project)
    chosen, where = _enums(inputs)
    target = roll_target(project)
    outcome = rules.ceremonial_outcome(rolled_3d, target)
    result = rules.resolve(outcome, chosen, rolled_3d)

    power: int | None = None
    works: bool | None = None
    if outcome in (rules.CeremonialOutcome.SUCCESS, rules.CeremonialOutcome.CRITICAL_SUCCESS):
        power = rules.item_power(target)
        if result.power_bonus is not None:
            if power_bonus_rolled is None:
                raise ValueError(
                    f"a critical success adds {result.power_bonus} to Power — roll it "
                    f"and pass power_bonus_rolled"
                )
            power += int(power_bonus_rolled)
        works = rules.item_works(power, where)

    note = f"rolled {rolled_3d} vs {target}"
    if power is not None:
        note += f"; Power {power}"
    if result.item_destroyed:
        note += "; item and materials destroyed"
    elif result.materials_lost:
        note += "; materials lost"
    await record_attempt(
        session, project, amount=0, outcome=outcome.value, kind="casting", note=note
    )
    state = dict(project.state_json or {})
    state["result"] = {
        "outcome": outcome.name,
        "power": power,
        "works": works,
        "power_bonus_rolled": power_bonus_rolled if result.power_bonus else None,
        "may_have_further_enhancement": result.may_have_further_enhancement,
        "item_destroyed": result.item_destroyed,
        "materials_lost": result.materials_lost,
        "energy_spent": result.energy_spent,
        "rolled": rolled_3d,
        "target": target,
    }
    await set_state(session, project, state)
    await finish_project(session, project, "complete")
    return result
