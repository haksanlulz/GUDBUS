"""Deferring: available, tested, and OFF by default.

Discord invalidates an un-deferred interaction token after 3 seconds. SQLite
waits up to `busy_timeout` (5000 ms here) for a write lock. Those are ordered
wrong: a contended write can still be succeeding when the token is already
dead, and the user sees "The application did not respond" on a command that
worked. Deferring moves the ceiling to 15 minutes.

Measured at rising concurrent WRITES (not guild count — 120 guilds is not 120
simultaneous writes): slowest write 0.37s at 24, 0.62s at 60, 1.58s at 120
where the pool queues. Under the deadline, but by under 2x at the top and on a
workstation SSD rather than the NAS array.

Shipped disabled by operator ruling 2026-07-28: at one guild the wall is
unreachable and the "thinking..." state Discord shows while deferred is pure
cost. The machinery is kept complete and covered so enabling it is a config
change rather than a rewrite. `config.DEFER_INTERACTIONS` holds the conditions
that should flip it.

Every test here passes an explicit `defer=`, so none of them becomes vacuous if
that default moves in either direction — which one of them did, before this
note existed.
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


class TestDefaultIsOff:
    """Shipped disabled, deliberately.

    At one guild a combat write takes ~10ms, so the 3-second wall is
    unreachable and the "thinking..." state Discord shows while deferred is
    pure cost. The machinery stays present and tested so turning it on is a
    config change rather than a rewrite — see config.DEFER_INTERACTIONS for the
    measurements and the conditions that should flip it.
    """

    async def test_config_default_is_off(self):
        from gurps_bot import config

        assert config.DEFER_INTERACTIONS is False

    async def test_context_does_not_defer_by_default(self, session_factory):
        await _seed(session_factory)
        interaction = _interaction(session_factory)
        async with CombatContext(interaction):  # no explicit flag
            pass
        interaction.response.defer.assert_not_awaited()
        interaction.response.send_message.assert_not_awaited()


class TestCombatContextDefers:
    """Behaviour when enabled. Explicit flag, so these do not silently become
    vacuous if the default flips either way."""

    async def test_it_defers(self, session_factory):
        await _seed(session_factory)
        interaction = _interaction(session_factory)
        async with CombatContext(interaction, defer=True):
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

        async with CombatContext(interaction, defer=True):
            pass

        assert order[:2] == ["defer", "db"], f"wrong order: {order}"

    async def test_it_defers_even_when_no_combat_is_active(self, session_factory):
        """The lookup is itself a query; the ack cannot wait on its result."""
        interaction = _interaction(session_factory)  # nothing seeded
        async with CombatContext(interaction, defer=True) as ctx:
            assert not ctx.ok
        interaction.response.defer.assert_awaited_once()

    async def test_it_does_not_defer_twice(self, session_factory):
        """A command that already answered must not be re-acknowledged.

        Explicitly enabled: with the default off this would pass without
        exercising the guard at all.
        """
        await _seed(session_factory)
        interaction = _interaction(session_factory, already_done=True)
        async with CombatContext(interaction, defer=True):
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
