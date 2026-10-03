"""Read-only session snapshot — composes the timers/combat/study/notes read paths, never commits."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.models import Combat
from gurps_bot.db.notes import Note
from gurps_bot.db.study import StudyLog
from gurps_bot.db.timers import Timer
from gurps_bot.services.combat import get_combat
from gurps_bot.services.notes import list_notes
from gurps_bot.services.study import list_study
from gurps_bot.services.timers import list_timers


@dataclass(frozen=True, slots=True)
class Dashboard:
    """One read-only snapshot of a channel's live session state for a user."""

    timers: list[Timer]  # this channel's live (non-expired) timers, soonest first
    combat: Combat | None  # active combat in this channel, or None
    recent_study: list[StudyLog]  # the user's most recent study logs
    recent_notes: list[Note]  # notes visible to the user in this guild


async def get_dashboard(
    session: AsyncSession,
    *,
    guild_id: int | None,
    channel_id: int | None,
    user_id: int,
    study_limit: int = 5,
    note_limit: int = 5,
) -> Dashboard:
    """Snapshot for a channel + user; in a DM (no guild) timers/combat stay empty."""
    timers: list[Timer] = []
    combat: Combat | None = None
    if guild_id is not None and channel_id is not None:
        timers = await list_timers(
            session, guild_id, channel_id, include_expired=False
        )
        combat = await get_combat(session, guild_id, channel_id)

    recent_study = await list_study(session, user_id, limit=study_limit)

    notes = await list_notes(
        session,
        requesting_user_id=user_id,
        guild_id=guild_id,
        include_secret=True,
    )

    return Dashboard(
        timers=timers,
        combat=combat,
        recent_study=recent_study,
        recent_notes=notes[:note_limit],
    )
