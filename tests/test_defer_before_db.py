"""Combat commands must acknowledge Discord before they touch the database.

Discord invalidates an un-deferred interaction token after 3 seconds. SQLite
waits up to `busy_timeout` (5000 ms here) for a write lock. Those are ordered
wrong: a contended write can still be succeeding when the token is already
dead, and the user sees "The application did not respond" on a command that
worked. Deferring moves the ceiling to 15 minutes.

Measured before the change, at rising concurrent guild writes: slowest write
0.37s at 24, 0.62s at 60, 1.58s at 120 — under the deadline, but by under 2x
at the top and on a workstation SSD rather than the NAS array.

The whole suite passed identically before and after CombatContext started
deferring, which is exactly why these exist: nothing else asserts it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import Base, Combat
from gurps_bot.services.combat_session import CombatContext
from gurps_bot.ui.respond import respond


@pytest_asyncio.fixture
async def session_factory():
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    await eng.dispose()


def _interaction(session_factory, *, already_done: bool = False):
    interaction = MagicMock()
    interaction.guild_id = 100
    interaction.channel_id = 200
    interaction.user.id = 999
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done.return_value = already_done
    interaction.followup.send = AsyncMock()
    interaction.client.db = session_factory
    return interaction


async def _seed(session_factory):
    async with session_factory() as s:
        s.add(Combat(guild_id=100, channel_id=200, started_by=999))
        await s.commit()


class TestCombatContextDefers:
    async def test_it_defers(self, session_factory):
        await _seed(session_factory)
        interaction = _interaction(session_factory)
        async with CombatContext(interaction):
            pass
        interaction.response.defer.assert_awaited_once()

    async def test_it_defers_before_opening_the_session(self, session_factory):
        """Order is the point — deferring after a blocked write is too late."""
        await _seed(session_factory)
        interaction = _interaction(session_factory)
        order: list[str] = []

        interaction.response.defer = AsyncMock(
            side_effect=lambda *a, **k: order.append("defer")
        )
        real_db = interaction.client.db

        def tracked_db(*a, **k):
            order.append("db")
            return real_db(*a, **k)

        interaction.client.db = tracked_db

        async with CombatContext(interaction):
            pass

        assert order[:2] == ["defer", "db"], f"wrong order: {order}"

    async def test_it_defers_even_when_no_combat_is_active(self, session_factory):
        """The lookup is itself a query; the ack cannot wait on its result."""
        interaction = _interaction(session_factory)  # nothing seeded
        async with CombatContext(interaction) as ctx:
            assert not ctx.ok
        interaction.response.defer.assert_awaited_once()

    async def test_it_does_not_defer_twice(self, session_factory):
        """A command that already answered must not be re-acknowledged."""
        await _seed(session_factory)
        interaction = _interaction(session_factory, already_done=True)
        async with CombatContext(interaction):
            pass
        interaction.response.defer.assert_not_awaited()

    async def test_deferring_can_be_turned_off(self, session_factory):
        await _seed(session_factory)
        interaction = _interaction(session_factory)
        async with CombatContext(interaction, defer=False):
            pass
        interaction.response.defer.assert_not_awaited()


class TestRespondRoutes:
    """Using the wrong channel raises; the helper picks by interaction state."""

    @pytest.mark.parametrize("done,expect", [(False, "response"), (True, "followup")])
    async def test_routes_on_is_done(self, session_factory, done, expect):
        interaction = _interaction(session_factory, already_done=done)
        await respond(interaction, "hi", ephemeral=True)

        if expect == "response":
            interaction.response.send_message.assert_awaited_once()
            interaction.followup.send.assert_not_awaited()
        else:
            interaction.followup.send.assert_awaited_once()
            interaction.response.send_message.assert_not_awaited()

    async def test_it_forwards_content_embed_view_and_ephemeral(self, session_factory):
        interaction = _interaction(session_factory, already_done=True)
        embed, view = MagicMock(), MagicMock()
        await respond(interaction, "body", embed=embed, view=view, ephemeral=True)

        kwargs = interaction.followup.send.await_args.kwargs
        assert kwargs["content"] == "body"
        assert kwargs["embed"] is embed
        assert kwargs["view"] is view
        assert kwargs["ephemeral"] is True

    async def test_it_drops_none_valued_extras(self, session_factory):
        """A None view means "no view", not "view=None" — which discord.py
        treats as an explicit removal."""
        interaction = _interaction(session_factory, already_done=True)
        await respond(interaction, "body", embed=None, view=None)

        kwargs = interaction.followup.send.await_args.kwargs
        assert "embed" not in kwargs and "view" not in kwargs
