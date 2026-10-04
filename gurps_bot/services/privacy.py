"""Self-service data deletion: everything keyed to one Discord user."""

from __future__ import annotations

import logging
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.crafting import CraftingCharge, CraftingProject
from gurps_bot.db.models import ActiveCharacter, Combatant, DiceMacro
from gurps_bot.db.notes import Note
from gurps_bot.db.study import StudyLog
from gurps_bot.db.wealth import Wealth
from gurps_bot.services.characters import delete_user_characters

log = logging.getLogger(__name__)

#: Tables whose rows for the user are deleted outright. Child tables without a
#: user id (skills, spells, traits, attributes, crafting charges) go with their
#: parent row.
DELETED_TABLES = (
    "active_characters",
    "characters",
    "crafting_projects",
    "dice_macros",
    "notes",
    "study_logs",
    "wealth",
)

#: Tables whose rows are kept but stripped of the user id. A combatant in a
#: running combat is part of other players' turn order; removing it mid-fight
#: would reorder their game, so the row stays as an unowned tracker entry until
#: that combat ends or goes idle and is swept.
ANONYMISED_TABLES = ("combatants",)


async def count_user_data(session: AsyncSession, discord_user_id: int) -> dict[str, int]:
    """Rows keyed to the user, per table: what `delete_user_data` would touch."""
    from sqlalchemy import func

    from gurps_bot.db.models import Base

    counts: dict[str, int] = {}
    for name in (*DELETED_TABLES, *ANONYMISED_TABLES):
        table = Base.metadata.tables[name]
        counts[name] = await session.scalar(
            select(func.count()).select_from(table).where(
                table.c.discord_user_id == discord_user_id
            )
        ) or 0
    return counts


async def delete_user_data(session: AsyncSession, discord_user_id: int) -> dict[str, int]:
    """Delete or anonymise every row keyed to the user. Returns row counts per
    table. Caller commits."""
    counts: dict[str, int] = {}

    result = cast("CursorResult[Any]", await session.execute(
        update(Combatant)
        .where(Combatant.discord_user_id == discord_user_id)
        .values(discord_user_id=None, character_id=None)
    ))
    counts["combatants"] = result.rowcount or 0

    project_ids = select(CraftingProject.id).where(
        CraftingProject.discord_user_id == discord_user_id
    )
    await session.execute(
        delete(CraftingCharge).where(CraftingCharge.project_id.in_(project_ids))
    )

    for name, model in (
        ("active_characters", ActiveCharacter),
        ("crafting_projects", CraftingProject),
        ("dice_macros", DiceMacro),
        ("notes", Note),
        ("study_logs", StudyLog),
        ("wealth", Wealth),
    ):
        result = cast("CursorResult[Any]", await session.execute(
            delete(model).where(model.discord_user_id == discord_user_id)
        ))
        counts[name] = result.rowcount or 0
    counts["characters"] = await delete_user_characters(session, discord_user_id)

    log.info("Deleted stored data for user id=%d", discord_user_id)
    return counts
