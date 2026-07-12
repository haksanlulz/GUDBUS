"""Tracker-embed length caps.

Slash string options accept up to 6000 chars; Discord embeds cap titles at 256
and descriptions at 4096. /notes add used to commit the note and then 400 the
reply — the user saw "Something went wrong", retried, and created duplicates.
Titles/descriptions built from user text now go through the single-owner
_cap_title/_cap_desc helpers; storage stays uncapped (display-only truncation).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.cogs.trackers import (
    EMBED_DESC_LIMIT,
    EMBED_TITLE_LIMIT,
    NotesCog,
    _cap_desc,
    _cap_title,
)
from gurps_bot.db.models import Base
from gurps_bot.db.notes import Note


class TestCapHelpers:
    def test_short_text_passes_through(self):
        assert _cap_title("Study Log") == "Study Log"
        assert _cap_desc("body") == "body"

    def test_title_capped_at_embed_limit(self):
        capped = _cap_title("T" * 400)
        assert len(capped) <= EMBED_TITLE_LIMIT
        assert capped.endswith("…")

    def test_desc_capped_at_embed_limit(self):
        capped = _cap_desc("B" * 6000)
        assert len(capped) <= EMBED_DESC_LIMIT
        assert "…" in capped[-40:]

    def test_exact_limit_untouched(self):
        exact = "T" * EMBED_TITLE_LIMIT
        assert _cap_title(exact) == exact


@pytest_asyncio.fixture
async def session_factory():
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await eng.dispose()


def _interaction(session_factory):
    interaction = MagicMock()
    interaction.guild_id = 100
    interaction.channel_id = 200
    interaction.user.id = 42

    @asynccontextmanager
    async def fake_db():
        async with session_factory() as s:
            yield s

    interaction.client.db = fake_db
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done.return_value = False
    interaction.followup.send = AsyncMock()
    return interaction


class TestNotesAddCaps:
    async def test_long_note_saves_and_replies_within_discord_caps(
        self, session_factory
    ):
        # The failure mode was commit-then-400: note saved, reply raised.
        # Titles are already service-capped (TITLE_MAX=200), so the embed
        # title survives the 256 limit with its "Note #N: " prefix; the body
        # is the uncapped 6000-char slash option vs the 4096 description cap.
        cog = NotesCog(bot=MagicMock())
        interaction = _interaction(session_factory)
        long_title = "T" * 200  # service maximum
        long_body = "B" * 6000

        await cog.notes_add.callback(
            cog,
            interaction,
            title=long_title,
            body=long_body,
            character_scoped=False,
        )

        # Reply went out and fits the embed caps.
        interaction.response.send_message.assert_awaited_once()
        embed = interaction.response.send_message.await_args.kwargs["embed"]
        assert len(embed.title) <= EMBED_TITLE_LIMIT
        assert len(embed.description) <= EMBED_DESC_LIMIT

        # Storage is not capped — truncation is display-only.
        async with session_factory() as s:
            note = (await s.execute(select(Note))).scalar_one()
        assert note.title == long_title
        assert note.body == long_body
