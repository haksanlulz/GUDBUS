from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from gurps_bot.ui.embeds import combat_tracker_embed

if TYPE_CHECKING:
    from gurps_bot.db.models import Combat

log = logging.getLogger(__name__)

_TRACKER_VIEW = None


def get_tracker_view() -> discord.ui.View:
    """one shared view reused across refreshes instead of a new instance per edit"""
    global _TRACKER_VIEW
    if _TRACKER_VIEW is None:
        from gurps_bot.ui.views import CombatTrackerView
        _TRACKER_VIEW = CombatTrackerView()
    return _TRACKER_VIEW


class TrackerManager:
    """edits the tracker via get_partial_message — 1 API call vs fetch+edit's 2"""

    def __init__(
        self, channel: discord.abc.Messageable, message_id: int | None,
    ) -> None:
        self.channel = channel
        self.message_id = message_id

    async def refresh(self, combat: Combat) -> bool:
        """re-render; False = message deleted or unpermitted — callers warn instead of going stale"""
        if not self.message_id:
            return False
        embed = combat_tracker_embed(combat)
        try:
            partial = self.channel.get_partial_message(self.message_id)
            await partial.edit(embed=embed, view=get_tracker_view())
            return True
        except discord.NotFound:
            log.warning("Tracker message %s deleted, cannot refresh", self.message_id)
        except discord.Forbidden:
            # Forbidden subclasses HTTPException — catch first so a perms problem
            # doesn't log as a generic stack trace
            log.warning(
                "Missing permission to edit tracker message %s; tracker will be "
                "stale until channel permissions are restored", self.message_id,
            )
        except discord.HTTPException:
            log.exception("Failed to refresh tracker message %s", self.message_id)
        return False

    async def end(self) -> None:
        if not self.message_id:
            return
        try:
            partial = self.channel.get_partial_message(self.message_id)
            await partial.edit(content="Combat ended.", embed=None, view=None)
        except discord.HTTPException:
            log.warning("Could not clear tracker message %s", self.message_id)
