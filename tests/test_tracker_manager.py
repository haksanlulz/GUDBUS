"""TrackerManager must survive a channel that cannot hold the tracker.

It is built from ``interaction.channel``, which discord.py types as any channel
kind or None. Only some kinds have ``get_partial_message``; the rest used to
raise AttributeError out of ``refresh``, past the HTTP-error handling, after the
command had already committed and replied. ``refresh`` returning False is the
existing contract for "could not redraw" — callers warn the user on it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord

from gurps_bot.ui.tracker import TrackerManager


class TestAChannelWithoutMessagesIsNotATracker:
    async def test_no_channel_reports_a_failed_refresh(self):
        assert await TrackerManager(None, 123).refresh(MagicMock()) is False

    async def test_a_category_channel_reports_a_failed_refresh(self):
        category = MagicMock(spec=discord.CategoryChannel)
        assert await TrackerManager(category, 123).refresh(MagicMock()) is False

    async def test_end_on_no_channel_is_a_no_op(self):
        await TrackerManager(None, 123).end()

    async def test_a_messageable_channel_still_edits(self, monkeypatch):
        monkeypatch.setattr(
            "gurps_bot.ui.tracker.combat_tracker_embed", lambda combat: discord.Embed()
        )
        monkeypatch.setattr("gurps_bot.ui.tracker.get_tracker_view", lambda: None)
        partial = MagicMock()
        partial.edit = AsyncMock()
        channel = MagicMock(spec=discord.TextChannel)
        channel.get_partial_message.return_value = partial
        assert await TrackerManager(channel, 123).refresh(MagicMock()) is True
        channel.get_partial_message.assert_called_once_with(123)
