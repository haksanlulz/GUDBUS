"""Crafting-project data access. Cogs call this; nobody else touches the tables.

The one rule this module exists to enforce: **a spend and the outcome it bought
are written together, before the user is told anything.** B474 charges the
item's full retail price per prototype attempt whether or not the attempt
works, so "the money left and we do not know why" is a reachable state unless
the pair is atomic.

Caller commits, per the layering contract — the cog owns the transaction. What
this module guarantees is that a single commit either lands both halves or
neither.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.crafting import (
    CHARGE_KINDS,
    ENDINGS,
    STAGES,
    CraftingCharge,
    CraftingProject,
)
#: Owned by services/limits.py, which holds the whole storage surface in one
#: readable place; imported rather than redeclared so there is one number.
from gurps_bot.services.limits import (  # noqa: F401
    MAX_CRAFTING_PROJECTS_PER_USER,
    enforce_row_cap,
)


async def start_project(
    session: AsyncSession,
    *,
    discord_user_id: int,
    guild_id: int | None,
    name: str,
    complexity: str,
    skill: int,
    retail_price: int = 0,
    domain: str = "invention",
    character_id: int | None = None,
    modifiers: dict | None = None,
) -> CraftingProject:
    """Open a project at the Concept stage. Caller commits."""
    await enforce_row_cap(
        session,
        CraftingProject,
        MAX_CRAFTING_PROJECTS_PER_USER,
        "crafting projects",
        discord_user_id=discord_user_id,
    )

    project = CraftingProject(
        discord_user_id=discord_user_id,
        guild_id=guild_id,
        character_id=character_id,
        name=name,
        domain=domain,
        complexity=complexity,
        stage="concept",
        skill=skill,
        retail_price=retail_price,
        modifiers_json=modifiers or {},
    )
    session.add(project)
    await session.flush()
    return project


async def get_project(
    session: AsyncSession, project_id: int, discord_user_id: int
) -> CraftingProject | None:
    """One project, or None if it is not this user's.

    Ownership is part of the lookup rather than a separate check, so there is
    no way to fetch a stranger's project and forget to compare afterwards.
    """
    return await session.scalar(
        select(CraftingProject).where(
            CraftingProject.id == project_id,
            CraftingProject.discord_user_id == discord_user_id,
        )
    )


async def list_projects(
    session: AsyncSession,
    discord_user_id: int,
    guild_id: int | None,
    *,
    include_finished: bool = False,
) -> list[CraftingProject]:
    stmt = select(CraftingProject).where(
        CraftingProject.discord_user_id == discord_user_id,
        CraftingProject.guild_id == guild_id,
    )
    if not include_finished:
        stmt = stmt.where(CraftingProject.stage.notin_(ENDINGS))
    stmt = stmt.order_by(CraftingProject.id)
    return list((await session.scalars(stmt)).all())


async def record_charge(
    session: AsyncSession,
    project: CraftingProject,
    *,
    kind: str,
    amount: int,
    outcome: str | None = None,
    note: str | None = None,
) -> CraftingCharge:
    """Append one spend to the ledger. Caller commits.

    ``facilities`` and ``copy`` legitimately have no outcome — they buy the
    right to roll and a finished item respectively. ``attempt`` does, and
    :func:`record_attempt` is the only way to write one.
    """
    if kind not in CHARGE_KINDS:
        raise ValueError(f"unknown charge kind {kind!r}; expected one of {CHARGE_KINDS}")
    if project.is_finished:
        raise ValueError(
            f"project {project.id} is {project.stage} — a finished project takes "
            f"no further charges"
        )

    charge = CraftingCharge(
        project_id=project.id, kind=kind, amount=amount, outcome=outcome, note=note
    )
    session.add(charge)
    await session.flush()
    return charge


async def record_attempt(
    session: AsyncSession,
    project: CraftingProject,
    *,
    amount: int,
    outcome: str | None,
    elapsed_days: int = 0,
) -> CraftingCharge:
    """Charge an attempt and record what it bought, in one write.

    The outcome is required. An attempt row without one is precisely the state
    the spec forbids — the money is gone and nothing says why — so it is
    refused here rather than defaulted to something plausible.
    """
    if not outcome:
        raise ValueError(
            "an attempt charge must carry the outcome it bought; recording the "
            "spend alone is the failure this is here to prevent"
        )

    charge = await record_charge(
        session, project, kind="attempt", amount=amount, outcome=outcome
    )
    # Same flush, same transaction as the charge above: the counter and the
    # ledger cannot end up disagreeing, in either direction.
    project.attempts += 1
    project.elapsed_days += elapsed_days
    await session.flush()
    return charge


async def charge_history(session: AsyncSession, project_id: int) -> list[CraftingCharge]:
    return list(
        (
            await session.scalars(
                select(CraftingCharge)
                .where(CraftingCharge.project_id == project_id)
                .order_by(CraftingCharge.id)
            )
        ).all()
    )


async def spent_by_kind(session: AsyncSession, project_id: int) -> dict[str, int]:
    """What has been spent, kept apart by what it bought.

    Deliberately not a total. B474's figures have different payers and
    different triggers, and a caller that wants a number has to say which.
    """
    rows = await session.execute(
        select(CraftingCharge.kind, func.sum(CraftingCharge.amount))
        .where(CraftingCharge.project_id == project_id)
        .group_by(CraftingCharge.kind)
    )
    return {kind: int(total) for kind, total in rows.all()}


async def advance_stage(
    session: AsyncSession, project: CraftingProject, stage: str
) -> None:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {STAGES}")
    if project.is_finished:
        raise ValueError(f"project {project.id} is already {project.stage}")
    project.stage = stage
    await session.flush()


async def finish_project(
    session: AsyncSession, project: CraftingProject, ending: str
) -> None:
    """End a project without deleting it — the money was still spent.

    Abandoned and complete are stored in the same column as the stages, so a
    project has exactly one status and cannot be both mid-prototype and done.
    """
    if ending not in ENDINGS:
        raise ValueError(f"unknown ending {ending!r}; expected one of {ENDINGS}")
    project.stage = ending
    await session.flush()


async def mark_flawed_theory(session: AsyncSession, project: CraftingProject) -> None:
    """B473: the Concept critical failure. GM-only — never render this."""
    project.flawed_theory = True
    await session.flush()


async def delete_project(session: AsyncSession, project: CraftingProject) -> None:
    await session.delete(project)
    await session.flush()


async def purge_guild_crafting_projects(session: AsyncSession, guild_id: int) -> None:
    """Drop a departed guild's projects. Caller commits.

    Charges go with them: the FK is ON DELETE CASCADE, and the explicit delete
    below covers SQLite, where foreign keys are off by default per connection
    and a bulk DML delete would otherwise leave the ledger orphaned.
    """
    project_ids = select(CraftingProject.id).where(CraftingProject.guild_id == guild_id)
    await session.execute(
        delete(CraftingCharge).where(CraftingCharge.project_id.in_(project_ids))
    )
    await session.execute(
        delete(CraftingProject).where(CraftingProject.guild_id == guild_id)
    )
