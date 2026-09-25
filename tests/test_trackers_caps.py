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
    EMBED_FIELD_LIMIT,
    EMBED_TITLE_LIMIT,
    NotesCog,
    StudyCog,
    TimersCog,
    WealthCog,
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
    interaction.response.defer = AsyncMock()
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


def _sent_embed(interaction):
    call = interaction.response.send_message.await_args
    return call.kwargs["embed"]


def _assert_fits(embed):
    assert len(embed.title or "") <= EMBED_TITLE_LIMIT
    assert len(embed.description or "") <= EMBED_DESC_LIMIT
    for f in embed.fields:
        assert len(f.value) <= EMBED_FIELD_LIMIT, (f.name, len(f.value))


class TestTheOtherUserTextFields:
    """Same commit-then-400 shape, in the fields the first pass did not cap:
    25 tags x 50 chars render to ~1348 chars against a 1024 field cap, and a
    timer's note/target are not length-limited anywhere."""

    _TAGS = ",".join(f"{i:02d}" + "t" * 48 for i in range(25))

    async def test_notes_add_with_the_maximum_tags(self, session_factory):
        cog = NotesCog(bot=MagicMock())
        interaction = _interaction(session_factory)
        await cog.notes_add.callback(
            cog, interaction, title="t", body="b", tags=self._TAGS, character_scoped=False
        )
        _assert_fits(_sent_embed(interaction))

    async def test_notes_edit_with_the_maximum_tags(self, session_factory):
        cog = NotesCog(bot=MagicMock())
        first = _interaction(session_factory)
        await cog.notes_add.callback(cog, first, title="t", body="b", character_scoped=False)
        interaction = _interaction(session_factory)
        await cog.notes_edit.callback(cog, interaction, note_id=1, tags=self._TAGS)
        _assert_fits(_sent_embed(interaction))

    async def test_notes_search_with_a_long_query(self, session_factory):
        cog = NotesCog(bot=MagicMock())
        interaction = _interaction(session_factory)
        await cog.notes_search.callback(cog, interaction, query="q" * 400)
        _assert_fits(_sent_embed(interaction))

    async def test_timer_add_with_a_long_note_and_target(self, session_factory):
        cog = TimersCog(bot=MagicMock())
        interaction = _interaction(session_factory)
        await cog.timer_add.callback(
            cog, interaction, label="L", duration=3, target="T" * 1500, note="N" * 1500
        )
        _assert_fits(_sent_embed(interaction))

    async def test_wealth_adjust_with_a_long_reason(self, session_factory):
        """The worst member of the family: the money moves, the receipt 400s,
        and the user who retries has now spent it twice."""
        cog = WealthCog(bot=MagicMock())
        interaction = _interaction(session_factory)
        await cog.wealth_adjust.callback(
            cog, interaction, amount=-10.0, reason="R" * 1500, character_scoped=False
        )
        _assert_fits(_sent_embed(interaction))


class TestStudyListCountsWhatItHides:
    """The "…and N more" count came from a 50-row fetch minus the 10 shown,
    so it could never exceed 40: a user with 120 logs was told 40, not 110."""

    async def test_the_hidden_count_is_the_real_count(self, session_factory):
        from gurps_bot.services.study import log_study

        async with session_factory() as s:
            for _ in range(120):
                await log_study(s, 42, "Broadsword", "self_teaching", 1.0)
            await s.commit()
        cog = StudyCog(bot=MagicMock())
        interaction = _interaction(session_factory)
        await cog.study_list.callback(cog, interaction, character_scoped=False)
        assert "and 110 more" in _sent_embed(interaction).description
