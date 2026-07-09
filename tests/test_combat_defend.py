"""/combat defend: cumulative Parry penalty (B376), Parry/Block counted per turn, Dodge uncounted."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import Base, Combat, Combatant


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory):
    async with session_factory() as s:
        yield s


async def _seed(session, *, parries=0, blocks=0, user_id=42):
    """Create a combat (GM=999) in guild 100 / channel 200 with one player combatant."""
    combat = Combat(guild_id=100, channel_id=200, started_by=999)
    session.add(combat)
    await session.flush()
    c = Combatant(
        combat_id=combat.id, discord_user_id=user_id, name="Hero",
        basic_speed=5.0, hp_max=10, hp_current=10, fp_max=10, fp_current=10,
        slot=0, parries_this_turn=parries, blocks_this_turn=blocks,
    )
    session.add(c)
    await session.commit()
    return combat.id, c.id


async def _read_counts(session_factory, combatant_id):
    async with session_factory() as s:
        c = (await s.execute(select(Combatant).where(Combatant.id == combatant_id))).scalar_one()
        return c.parries_this_turn, c.blocks_this_turn


def _interaction(session_factory, *, guild_id=100, channel_id=200, user_id=42):
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.channel_id = channel_id
    interaction.user.id = user_id
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done.return_value = False
    interaction.followup.send = AsyncMock()
    interaction.client.db = session_factory
    return interaction


def _cog():
    from gurps_bot.cogs.combat import CombatTrackerGroup

    return CombatTrackerGroup(bot=MagicMock())


class TestCombatDefend:
    async def test_parry_records_and_increments(self, session, session_factory):
        _, cid = await _seed(session)
        interaction = _interaction(session_factory)
        await _cog().defend_tracked.callback(_cog(), interaction, defense_type="parry", value=11)

        interaction.response.send_message.assert_awaited()
        parries, _blocks = await _read_counts(session_factory, cid)
        assert parries == 1

    async def test_second_parry_applies_cumulative_penalty(self, session, session_factory):
        _, cid = await _seed(session, parries=1)
        interaction = _interaction(session_factory)

        from gurps_bot.mechanics.checks import check as real_check
        fake = real_check(7)
        with patch("gurps_bot.cogs.combat.check", return_value=fake) as mock_check:
            await _cog().defend_tracked.callback(_cog(), interaction, defense_type="parry", value=11)

        # prior_parries=1 -> penalty -4; modifier 0 -> check(11, -4)
        mock_check.assert_called_once_with(11, -4)
        parries, _blocks = await _read_counts(session_factory, cid)
        assert parries == 2
        embed = interaction.response.send_message.await_args.kwargs["embed"]
        assert any("B376" in (f.value or "") for f in embed.fields)

    async def test_dodge_does_not_record(self, session, session_factory):
        _, cid = await _seed(session)
        interaction = _interaction(session_factory)
        await _cog().defend_tracked.callback(_cog(), interaction, defense_type="dodge", value=9)

        assert await _read_counts(session_factory, cid) == (0, 0)

    async def test_hidden_is_ephemeral(self, session, session_factory):
        await _seed(session)
        interaction = _interaction(session_factory)
        await _cog().defend_tracked.callback(_cog(), interaction, defense_type="dodge", value=9, hidden=True)
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True

    async def test_not_in_combat_errors_ephemerally(self, session_factory):
        interaction = _interaction(session_factory)  # nothing seeded
        await _cog().defend_tracked.callback(_cog(), interaction, defense_type="dodge", value=9)
        interaction.response.send_message.assert_awaited()
        assert interaction.response.send_message.await_args.kwargs.get("ephemeral") is True
