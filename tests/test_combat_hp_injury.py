"""/combat hp: shock (B419) + major-wound (B420) advisory on damaging HP changes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import Base, Combat, Combatant
from gurps_bot.mechanics.checks import CheckResult, _determine_outcome
from gurps_bot.mechanics.dice import DiceSpec, RollResult

# every test patches refresh_tracker out — the tracker HTTP edit is noise here
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


async def _seed(session, *, hp_max=10, hp_current=10, user_id=42, ht=10, will=10):
    """One combatant 'Hero' in guild 100 / channel 200 (GM=999)."""
    combat = Combat(guild_id=100, channel_id=200, started_by=999)
    session.add(combat)
    await session.flush()
    c = Combatant(
        combat_id=combat.id, discord_user_id=user_id, name="Hero",
        basic_speed=5.0, hp_max=hp_max, hp_current=hp_current,
        fp_max=10, fp_current=10, ht=ht, will=will, slot=0,
    )
    session.add(c)
    await session.commit()
    return combat.id, c.id


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


def _sent_content(interaction):
    return interaction.response.send_message.await_args.args[0]


def _fixed_check(rolled, target):
    """A deterministic CheckResult for a fixed 3d6 total vs target (real outcome engine)."""
    rr = RollResult(spec=DiceSpec(3, 6, 0), dice=(rolled,), total=rolled)
    return CheckResult(
        roll_result=rr,
        target=target,
        margin=target - rolled,
        outcome=_determine_outcome(rolled, target),
    )


async def _read_statuses(session_factory, combatant_id):
    async with session_factory() as s:
        c = (
            await s.execute(select(Combatant).where(Combatant.id == combatant_id))
        ).scalar_one()
        return list(c.status_effects or [])


_CHECK = "gurps_bot.cogs.combat.check"


class TestHpInjuryAdvisory:
    async def test_major_wound_blow_shows_shock_and_major(self, session, session_factory):
        await _seed(session)  # 10 HP; a 6-HP blow exceeds half
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
            await _cog().hp_cmd.callback(_cog(), interaction, target="Hero", amount=-6)

        content = _sent_content(interaction)
        assert "Major wound" in content and "B420" in content
        assert "Shock" in content and "B419" in content

    async def test_minor_wound_is_shock_only(self, session, session_factory):
        await _seed(session)  # 3-HP blow: shock, not a major wound
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
            await _cog().hp_cmd.callback(_cog(), interaction, target="Hero", amount=-3)

        content = _sent_content(interaction)
        assert "Shock" in content
        assert "Major wound" not in content

    async def test_heal_shows_no_injury_advisory(self, session, session_factory):
        await _seed(session, hp_current=4)
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
            await _cog().hp_cmd.callback(_cog(), interaction, target="Hero", amount=5)

        content = _sent_content(interaction)
        assert "Shock" not in content
        assert "Major wound" not in content


class TestHpMajorWoundKnockdown:
    async def test_failed_roll_stuns_and_knocks_down(self, session, session_factory):
        _, cid = await _seed(session)  # HT 10; a 6-HP blow is a major wound
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True), \
                patch(_CHECK, return_value=_fixed_check(13, 10)):  # fail by 3
            await _cog().hp_cmd.callback(_cog(), interaction, target="Hero", amount=-6)

        statuses = await _read_statuses(session_factory, cid)
        assert "Stunned" in statuses and "Prone" in statuses
        assert "Unconscious" not in statuses
        assert "stunned and knocked down" in _sent_content(interaction).lower()

    async def test_failed_by_five_knocks_out(self, session, session_factory):
        _, cid = await _seed(session)
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True), \
                patch(_CHECK, return_value=_fixed_check(16, 10)):  # fail by 6
            await _cog().hp_cmd.callback(_cog(), interaction, target="Hero", amount=-6)

        statuses = await _read_statuses(session_factory, cid)
        assert "Unconscious" in statuses
        assert "Stunned" not in statuses
        assert "unconscious" in _sent_content(interaction).lower()

    async def test_made_roll_applies_no_status(self, session, session_factory):
        _, cid = await _seed(session)
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True), \
                patch(_CHECK, return_value=_fixed_check(8, 10)):  # made by 2
            await _cog().hp_cmd.callback(_cog(), interaction, target="Hero", amount=-6)

        statuses = await _read_statuses(session_factory, cid)
        assert "Stunned" not in statuses and "Unconscious" not in statuses
        assert "kept their footing" in _sent_content(interaction).lower()

    async def test_minor_wound_never_rolls_knockdown(self, session, session_factory):
        _, cid = await _seed(session)
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True), \
                patch(_CHECK) as mock_check:
            await _cog().hp_cmd.callback(_cog(), interaction, target="Hero", amount=-3)

        mock_check.assert_not_called()
        assert "Stunned" not in await _read_statuses(session_factory, cid)

    async def test_lethal_blow_skips_knockdown(self, session, session_factory):
        _, cid = await _seed(session)  # 10 HP; -60 drops past -5xHP → Dead
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True), \
                patch(_CHECK) as mock_check:
            await _cog().hp_cmd.callback(_cog(), interaction, target="Hero", amount=-60)

        mock_check.assert_not_called()
        statuses = await _read_statuses(session_factory, cid)
        assert "Dead" in statuses
        assert "Stunned" not in statuses and "Unconscious" not in statuses


class TestKnockdownRollModifiers:
    """The knockdown roll uses max(HT, Will) (B420) and an optional location penalty."""

    async def test_roll_uses_higher_of_ht_or_will(self, session, session_factory):
        await _seed(session, ht=10, will=13)  # Will higher → roll vs 13
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True), \
                patch(_CHECK, return_value=_fixed_check(14, 13)) as mock_check:
            await _cog().hp_cmd.callback(_cog(), interaction, target="Hero", amount=-6)

        mock_check.assert_called_once_with(13, 0)  # max(10,13)=13, no location mod

    async def test_location_applies_b420_penalty(self, session, session_factory):
        await _seed(session, ht=12, will=10)  # roll vs 12
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True), \
                patch(_CHECK, return_value=_fixed_check(11, 2)) as mock_check:
            await _cog().hp_cmd.callback(
                _cog(), interaction, target="Hero", amount=-6, location="skull"
            )

        mock_check.assert_called_once_with(12, -10)  # max(12,10)=12, skull -10

    async def test_face_is_minus_five(self, session, session_factory):
        await _seed(session, ht=11, will=11)
        interaction = _interaction(session_factory)
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True), \
                patch(_CHECK, return_value=_fixed_check(10, 6)) as mock_check:
            await _cog().hp_cmd.callback(
                _cog(), interaction, target="Hero", amount=-6, location="face"
            )

        mock_check.assert_called_once_with(11, -5)
