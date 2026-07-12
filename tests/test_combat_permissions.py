"""/combat hp|fp|status permission gate — GM or the combatant's own player.

The three mutation commands used to have no permission check, so any guild
member could damage, kill, or mark Dead any combatant. Roster commands
(add-npc / remove) already require the GM; these tests pin the GM-or-owner
gate on the per-combatant mutators. Harness mirrors test_combat_hp_injury.py
(real in-memory SQLite, mocked Interaction, refresh_tracker patched out).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import Base, Combat, Combatant

_REFRESH = "gurps_bot.services.combat_session.CombatContext.refresh_tracker"

GM_ID = 999
OWNER_ID = 42
STRANGER_ID = 777


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


async def _seed(session, *, npc=False):
    """One combatant 'Hero' in guild 100 / channel 200 (GM=GM_ID).

    npc=True seeds an unowned NPC (discord_user_id None) instead of
    OWNER_ID's PC.
    """
    combat = Combat(guild_id=100, channel_id=200, started_by=GM_ID)
    session.add(combat)
    await session.flush()
    c = Combatant(
        combat_id=combat.id,
        discord_user_id=None if npc else OWNER_ID,
        is_npc=npc,
        name="Hero",
        basic_speed=5.0, hp_max=10, hp_current=10,
        fp_max=10, fp_current=10, ht=10, will=10, slot=0,
    )
    session.add(c)
    await session.commit()
    return combat.id, c.id


def _interaction(session_factory, *, user_id):
    interaction = MagicMock()
    interaction.guild_id = 100
    interaction.channel_id = 200
    interaction.user.id = user_id
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done.return_value = False
    interaction.followup.send = AsyncMock()
    interaction.client.db = session_factory
    return interaction


def _cog():
    from gurps_bot.cogs.combat import CombatTrackerGroup

    return CombatTrackerGroup(bot=MagicMock())


async def _read_combatant(session_factory, combatant_id):
    async with session_factory() as s:
        return (
            await s.execute(select(Combatant).where(Combatant.id == combatant_id))
        ).scalar_one()


def _assert_rejected(interaction):
    """The reply is a single ephemeral permission error."""
    interaction.response.send_message.assert_awaited_once()
    call = interaction.response.send_message.await_args
    assert call.kwargs.get("ephemeral") is True
    assert "GM" in call.args[0]


class TestHpPermission:
    async def test_stranger_cannot_damage(self, session, session_factory):
        _, cid = await _seed(session)
        interaction = _interaction(session_factory, user_id=STRANGER_ID)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
            await _cog().hp_cmd.callback(_cog(), interaction, target="Hero", amount=-6)

        _assert_rejected(interaction)
        c = await _read_combatant(session_factory, cid)
        assert c.hp_current == 10  # untouched

    async def test_gm_can_damage(self, session, session_factory):
        _, cid = await _seed(session)
        interaction = _interaction(session_factory, user_id=GM_ID)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
            await _cog().hp_cmd.callback(_cog(), interaction, target="Hero", amount=-3)

        c = await _read_combatant(session_factory, cid)
        assert c.hp_current == 7

    async def test_owner_can_damage_self(self, session, session_factory):
        _, cid = await _seed(session)
        interaction = _interaction(session_factory, user_id=OWNER_ID)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
            await _cog().hp_cmd.callback(_cog(), interaction, target="Hero", amount=-3)

        c = await _read_combatant(session_factory, cid)
        assert c.hp_current == 7

    async def test_non_gm_cannot_touch_npc(self, session, session_factory):
        """NPCs have no owning player — GM-only."""
        _, cid = await _seed(session, npc=True)
        interaction = _interaction(session_factory, user_id=OWNER_ID)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
            await _cog().hp_cmd.callback(_cog(), interaction, target="Hero", amount=-6)

        _assert_rejected(interaction)
        c = await _read_combatant(session_factory, cid)
        assert c.hp_current == 10


class TestFpPermission:
    async def test_stranger_cannot_drain_fp(self, session, session_factory):
        _, cid = await _seed(session)
        interaction = _interaction(session_factory, user_id=STRANGER_ID)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
            await _cog().fp_cmd.callback(_cog(), interaction, target="Hero", amount=-5)

        _assert_rejected(interaction)
        c = await _read_combatant(session_factory, cid)
        assert c.fp_current == 10

    async def test_gm_can_modify_fp(self, session, session_factory):
        _, cid = await _seed(session)
        interaction = _interaction(session_factory, user_id=GM_ID)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
            await _cog().fp_cmd.callback(_cog(), interaction, target="Hero", amount=-5)

        c = await _read_combatant(session_factory, cid)
        assert c.fp_current == 5


class TestStatusPermission:
    async def test_stranger_cannot_mark_dead(self, session, session_factory):
        _, cid = await _seed(session)
        interaction = _interaction(session_factory, user_id=STRANGER_ID)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
            await _cog().status_cmd.callback(
                _cog(), interaction, target="Hero", effect="Dead", action="add"
            )

        _assert_rejected(interaction)
        c = await _read_combatant(session_factory, cid)
        assert "Dead" not in (c.status_effects or [])

    async def test_owner_can_mark_own_status(self, session, session_factory):
        _, cid = await _seed(session)
        interaction = _interaction(session_factory, user_id=OWNER_ID)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
            await _cog().status_cmd.callback(
                _cog(), interaction, target="Hero", effect="Prone", action="add"
            )

        c = await _read_combatant(session_factory, cid)
        assert "Prone" in (c.status_effects or [])
