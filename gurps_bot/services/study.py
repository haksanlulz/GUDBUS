"""Study log persistence (B292-294). Callers own the transaction — nothing here commits."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.study import StudyLog
from gurps_bot.mechanics.study import StudyProgress, learning_hours_for, study_progress


async def log_study(
    session: AsyncSession,
    discord_user_id: int,
    skill_name: str,
    method: str,
    real_hours: float,
    *,
    character_id: int | None = None,
    gm_multiplier: float | None = None,
) -> StudyLog:
    """Record one study session; stores real_hours verbatim (audit) plus the post-cap learning_hours."""
    learning_hours = learning_hours_for(method, real_hours, gm_multiplier)

    row = StudyLog(
        discord_user_id=discord_user_id,
        character_id=character_id,
        # display case preserved; queries match via func.lower so "Stealth" and
        # "stealth" share one bucket (#8)
        skill_name=skill_name.strip(),
        method=method.strip().lower(),
        real_hours=real_hours,
        learning_hours=learning_hours,
    )
    session.add(row)
    await session.flush()  # populate id; caller owns the commit
    return row


async def get_skill_progress(
    session: AsyncSession,
    discord_user_id: int,
    skill_name: str,
    *,
    character_id: int | None = None,
) -> StudyProgress:
    """Sum learning hours for one (user, character?, skill) bucket — character_id None means the NULL bucket, not "any"."""
    stmt = select(
        func.coalesce(func.sum(StudyLog.learning_hours), 0.0)
    ).where(
        StudyLog.discord_user_id == discord_user_id,
        func.lower(StudyLog.skill_name) == skill_name.strip().lower(),
    )
    if character_id is None:
        stmt = stmt.where(StudyLog.character_id.is_(None))
    else:
        stmt = stmt.where(StudyLog.character_id == character_id)

    result = await session.execute(stmt)
    total = float(result.scalar_one())
    return study_progress(total)


async def list_study(
    session: AsyncSession,
    discord_user_id: int,
    *,
    character_id: int | None = None,
    skill_name: str | None = None,
    limit: int = 50,
) -> list[StudyLog]:
    """A user's study rows, newest first; here character_id None means no character filter (unlike get_skill_progress)."""
    stmt = select(StudyLog).where(StudyLog.discord_user_id == discord_user_id)
    if character_id is not None:
        stmt = stmt.where(StudyLog.character_id == character_id)
    if skill_name is not None:
        stmt = stmt.where(func.lower(StudyLog.skill_name) == skill_name.strip().lower())
    stmt = stmt.order_by(StudyLog.logged_at.desc(), StudyLog.id.desc()).limit(limit)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def reset_skill(
    session: AsyncSession,
    discord_user_id: int,
    skill_name: str,
    *,
    character_id: int | None = None,
) -> int:
    """Delete one (user, character?, skill) bucket (None = the NULL bucket only); returns rowcount."""
    stmt = delete(StudyLog).where(
        StudyLog.discord_user_id == discord_user_id,
        func.lower(StudyLog.skill_name) == skill_name.strip().lower(),
    )
    if character_id is None:
        stmt = stmt.where(StudyLog.character_id.is_(None))
    else:
        stmt = stmt.where(StudyLog.character_id == character_id)

    result = await session.execute(stmt)
    return result.rowcount
