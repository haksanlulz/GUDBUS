"""Deferring: available, tested, and ON by default since 2026-07-29.

Discord invalidates an un-deferred interaction token after 3 seconds. SQLite
waits up to `busy_timeout` (5000 ms here) for a write lock. Those are ordered
wrong: a contended write can still be succeeding when the token is already
dead, and the user sees "The application did not respond" on a command that
worked. Deferring moves the ceiling to 15 minutes.

Measured at rising concurrent WRITES (not guild count — 120 guilds is not 120
simultaneous writes): slowest write 0.37s at 24, 0.62s at 60, 1.58s at 120
where the pool queues. Under the deadline, but by under 2x at the top and on a
workstation SSD rather than the NAS array.

Shipped disabled by operator ruling 2026-07-28 — at one guild the wall is
unreachable and the "thinking..." state is pure cost — then enabled 2026-07-29
when the bot was published. The measurements did not change; the population did.
`config.DEFER_INTERACTIONS` holds both halves of that reasoning.

Every test here passes an explicit `defer=`, so none of them becomes vacuous if
that default moves in either direction — which one of them did, before this
note existed. That foresight is why flipping the default cost two assertions
instead of a rewrite.

⚠️ The flip did expose a coverage hole, and `TestDeferredPathEndToEnd` below is
the answer to it. Every cog-test fixture in this suite sets
`is_done.return_value = False` as a CONSTANT, so once a command defers, the mock
still reports not-done and `respond()` routes the reply to
`response.send_message` — while production, having really deferred, routes to
`followup.send`. Green tests, opposite branch. A faithful mock has to let
`is_done()` change, because that is the whole thing the router reads.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import Base, Combat
from gurps_bot.services.combat_session import CombatContext
from gurps_bot.ui.respond import respond

#: Same target the other combat cog tests patch; the tracker edit is HTTP noise.
_REFRESH = "gurps_bot.services.combat_session.CombatContext.refresh_tracker"


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


class TestDefaultIsOn:
    """Shipped enabled from 2026-07-29, having shipped off on 2026-07-28.

    The measurements did not change; the population did. Off was right while the
    only installs were the operator's own table, where a combat write takes
    ~10ms and the 3-second wall is unreachable, so the "thinking..." state is
    pure cost. A public bot runs on hosts nobody here has measured, and the
    margin was already under 2x at 120 concurrent writes on a workstation SSD.
    A stranger's first contended /attack showing "The application did not
    respond" on a command that worked costs more than a flicker does.

    `CharacterContext` has defaulted to deferring all along, so this also ends
    a split where the character commands deferred and the write-heavy combat
    ones did not. See config.DEFER_INTERACTIONS for the numbers.
    """

    async def test_config_default_is_on(self):
        from gurps_bot import config

        assert config.DEFER_INTERACTIONS is True

    async def test_context_defers_by_default(self, session_factory):
        await _seed(session_factory)
        interaction = _interaction(session_factory)
        async with CombatContext(interaction):  # no explicit flag
            pass
        interaction.response.defer.assert_awaited_once()

    async def test_the_two_contexts_now_agree(self, session_factory):
        """The split this closes, asserted rather than described.

        CharacterContext's parameter default and CombatContext's config-driven
        one are separate mechanisms, so nothing but a test keeps them aligned.
        """
        import inspect

        from gurps_bot.services.character_context import CharacterContext

        char_default = inspect.signature(CharacterContext).parameters["defer"].default
        assert char_default is True
        from gurps_bot import config

        assert config.DEFER_INTERACTIONS is char_default


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


def _faithful_interaction(session_factory, *, user_id=999):
    """A mock whose `is_done()` actually tracks whether it has answered.

    The rest of the suite pins it to a constant False, which is fine while
    nothing defers and wrong the moment something does: `respond()` picks its
    channel by reading exactly this, so a frozen False sends every deferred
    reply down the un-deferred path in the test and the other one in
    production.
    """
    interaction = MagicMock()
    interaction.guild_id = 100
    interaction.channel_id = 200
    interaction.user.id = user_id
    answered: list[bool] = [False]

    async def _defer(*a, **k):
        answered[0] = True

    async def _send_message(*a, **k):
        # discord.py raises here rather than no-opping: InteractionResponse
        # .send_message checks `if self._response_type: raise
        # InteractionResponded`, and defer() sets that attribute. Modelling the
        # raise means a regression reproduces the production failure instead of
        # merely disagreeing with an assertion about routing.
        if answered[0]:
            raise discord.InteractionResponded(interaction)
        answered[0] = True

    interaction.response.defer = AsyncMock(side_effect=_defer)
    interaction.response.send_message = AsyncMock(side_effect=_send_message)
    interaction.response.is_done = lambda: answered[0]
    interaction.followup.send = AsyncMock()
    interaction.client.db = session_factory
    return interaction


class TestDeferredPathEndToEnd:
    """Drive a real combat command through the default, with a mock that moves.

    Everything else here tests `CombatContext` or `respond()` in isolation.
    This is the one place that runs an actual cog callback the way production
    now runs it — deferred, therefore answering through the followup — because
    the isolated tests both pass while the two halves disagree about which
    channel is in use.
    """

    async def _hp_cog_and_target(self, session_factory):
        from gurps_bot.cogs.combat import CombatTrackerGroup
        from gurps_bot.db.models import Combatant

        async with session_factory() as s:
            combat = Combat(guild_id=100, channel_id=200, started_by=999)
            s.add(combat)
            await s.flush()
            c = Combatant(
                combat_id=combat.id, discord_user_id=999, name="Hero",
                basic_speed=5.0, hp_max=10, hp_current=10,
                fp_max=10, fp_current=10, ht=10, will=10, slot=0,
            )
            s.add(c)
            await s.commit()
        return CombatTrackerGroup(bot=MagicMock())

    async def test_a_combat_command_answers_through_the_followup(self, session_factory):
        cog = await self._hp_cog_and_target(session_factory)
        interaction = _faithful_interaction(session_factory)

        # Patched for the same reason every other combat cog test patches it:
        # the tracker edit is an HTTP call against a MagicMock channel, and its
        # failure path sends a reply of its own, which is noise here.
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
            await cog.hp_cmd.callback(cog, interaction, target="Hero", amount=-2)

        interaction.response.defer.assert_awaited_once()
        assert interaction.followup.send.await_count == 1, (
            "deferred, so the reply must go to the followup; the rest of the "
            "suite cannot see this because its is_done() never changes"
        )
        interaction.response.send_message.assert_not_awaited()

    async def test_the_reply_still_carries_the_damage(self, session_factory):
        """Routing correctly is not enough if the content is lost with it."""
        cog = await self._hp_cog_and_target(session_factory)
        interaction = _faithful_interaction(session_factory)

        # Patched for the same reason every other combat cog test patches it:
        # the tracker edit is an HTTP call against a MagicMock channel, and its
        # failure path sends a reply of its own, which is noise here.
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
            await cog.hp_cmd.callback(cog, interaction, target="Hero", amount=-2)

        sent = interaction.followup.send.await_args
        body = " ".join(str(a) for a in sent.args) + str(sent.kwargs)
        assert "Hero" in body
        assert "8" in body, f"HP after a 2-point hit is missing: {body}"

    async def test_the_mock_is_the_thing_being_relied_on(self, session_factory):
        """Guard the guard: prove is_done() really moves.

        If this helper ever regresses to a constant, the two tests above keep
        passing while checking nothing — the exact failure they exist to catch.
        """
        interaction = _faithful_interaction(session_factory)
        assert interaction.response.is_done() is False
        await interaction.response.defer()
        assert interaction.response.is_done() is True


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
