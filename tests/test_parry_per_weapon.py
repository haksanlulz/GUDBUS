"""B376 scopes the cumulative parry penalty per weapon, not per turn.

Printed, verbatim: "Once you have attempted a parry with a particular weapon or
bare hand, further attempts to parry with that weapon or hand are at a
cumulative -4 per parry after the first."

The count lived in one integer, so a two-weapon fighter's off-hand parry was
penalised for work the main hand did.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import Base, Combat, Combatant
from gurps_bot.services.combat import parry_key, record_defense

_REFRESH = "gurps_bot.services.combat_session.CombatContext.refresh_tracker"


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


async def _seed(session):
    combat = Combat(guild_id=100, channel_id=200, started_by=999)
    session.add(combat)
    await session.flush()
    c = Combatant(
        combat_id=combat.id, discord_user_id=42, name="Hero",
        basic_speed=5.0, hp_max=10, hp_current=10, fp_max=10, fp_current=10, slot=0,
    )
    session.add(c)
    await session.commit()
    return c.id


class TestKeyNormalisation:
    def test_none_and_blank_share_the_default_key(self):
        assert parry_key(None) == parry_key("") == parry_key("   ")

    def test_case_and_padding_ignored(self):
        assert parry_key(" Broadsword ") == parry_key("broadsword")

    def test_distinct_weapons_get_distinct_keys(self):
        assert parry_key("broadsword") != parry_key("main-gauche")


class TestCountsAreScopedPerWeapon:
    async def test_each_weapon_counts_separately(self, session):
        cid = await _seed(session)
        await record_defense(session, cid, "parry", weapon="broadsword")
        await record_defense(session, cid, "parry", weapon="broadsword")
        c = await record_defense(session, cid, "parry", weapon="main-gauche")
        await session.commit()
        assert c.parries_by_weapon["broadsword"] == 2
        assert c.parries_by_weapon["main-gauche"] == 1

    async def test_turn_total_still_counts_every_parry(self, session):
        """`parries_this_turn` is kept as the informational total."""
        cid = await _seed(session)
        await record_defense(session, cid, "parry", weapon="broadsword")
        c = await record_defense(session, cid, "parry", weapon="main-gauche")
        await session.commit()
        assert c.parries_this_turn == 2

    async def test_unnamed_weapon_uses_the_default_key(self, session):
        cid = await _seed(session)
        c = await record_defense(session, cid, "parry")
        await session.commit()
        assert c.parries_by_weapon == {"": 1}

    async def test_blocks_do_not_touch_the_parry_map(self, session):
        cid = await _seed(session)
        c = await record_defense(session, cid, "block")
        await session.commit()
        assert c.parries_by_weapon in ({}, None)
        assert c.blocks_this_turn == 1

    async def test_map_survives_a_reload(self, session, session_factory):
        """Rebinding the attribute, not mutating it, is what makes this persist."""
        cid = await _seed(session)
        await record_defense(session, cid, "parry", weapon="axe")
        await session.commit()
        async with session_factory() as s:
            c = (
                await s.execute(select(Combatant).where(Combatant.id == cid))
            ).scalar_one()
            assert c.parries_by_weapon == {"axe": 1}


def _interaction(session_factory):
    interaction = MagicMock()
    interaction.guild_id = 100
    interaction.channel_id = 200
    interaction.user.id = 42
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done.return_value = False
    interaction.followup.send = AsyncMock()
    interaction.client.db = session_factory
    return interaction


def _cog():
    from gurps_bot.cogs.combat import CombatTrackerGroup

    return CombatTrackerGroup(bot=MagicMock())


class TestPenaltyThroughTheCog:
    async def test_off_hand_parry_is_unpenalised(self, session, session_factory):
        """The whole point: main hand has parried twice, off hand is fresh."""
        cid = await _seed(session)
        async with session_factory() as s:
            await record_defense(s, cid, "parry", weapon="broadsword")
            await record_defense(s, cid, "parry", weapon="broadsword")
            await s.commit()

        from gurps_bot.mechanics.checks import check as real_check

        fake = real_check(7)
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True), \
                patch("gurps_bot.cogs.combat.check", return_value=fake) as mock_check:
            await _cog().defend_tracked.callback(
                _cog(), interaction, defense_type="parry", value=11,
                weapon="main-gauche",
            )
        mock_check.assert_called_once_with(11, 0)

    async def test_same_weapon_still_accrues(self, session, session_factory):
        cid = await _seed(session)
        async with session_factory() as s:
            await record_defense(s, cid, "parry", weapon="broadsword")
            await record_defense(s, cid, "parry", weapon="broadsword")
            await s.commit()

        from gurps_bot.mechanics.checks import check as real_check

        fake = real_check(7)
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True), \
                patch("gurps_bot.cogs.combat.check", return_value=fake) as mock_check:
            await _cog().defend_tracked.callback(
                _cog(), interaction, defense_type="parry", value=11,
                weapon="broadsword",
            )
        mock_check.assert_called_once_with(11, -8)

    async def test_fencing_reduction_composes_with_per_weapon(
        self, session, session_factory
    ):
        """-2 step, two prior parries with that weapon -> -4."""
        cid = await _seed(session)
        async with session_factory() as s:
            await record_defense(s, cid, "parry", weapon="rapier")
            await record_defense(s, cid, "parry", weapon="rapier")
            await s.commit()

        from gurps_bot.mechanics.checks import check as real_check

        fake = real_check(7)
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True), \
                patch("gurps_bot.cogs.combat.check", return_value=fake) as mock_check:
            await _cog().defend_tracked.callback(
                _cog(), interaction, defense_type="parry", value=11,
                weapon="rapier", fencing_or_master=True,
            )
        mock_check.assert_called_once_with(11, -4)
