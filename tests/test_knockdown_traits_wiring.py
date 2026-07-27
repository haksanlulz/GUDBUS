"""/combat hp reads the target's pain-threshold traits (B420), end to end.

The mechanics were correct and tested from the day they landed, but nothing at
the table saw them until the cog fetched trait names. These tests exercise the
real cog path so the wiring cannot silently regress to a location-only modifier.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import Base, Character, Combat, Combatant, Trait
from gurps_bot.mechanics.checks import CheckResult, _determine_outcome
from gurps_bot.mechanics.dice import DiceSpec, RollResult

_REFRESH = "gurps_bot.services.combat_session.CombatContext.refresh_tracker"
_CHECK = "gurps_bot.cogs.combat.check"


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


def _fixed_check(rolled: int, target: int) -> CheckResult:
    """Deterministic CheckResult for a fixed 3d6 total (real outcome engine)."""
    rr = RollResult(spec=DiceSpec(3, 6, 0), dice=(rolled,), total=rolled)
    return CheckResult(
        roll_result=rr,
        target=target,
        margin=target - rolled,
        outcome=_determine_outcome(rolled, target),
    )


async def _seed(session, *, trait_names: list[str] | None = None, link=True):
    """Combatant 'Hero' with 10 HP, optionally backed by a character with traits."""
    combat = Combat(guild_id=100, channel_id=200, started_by=999)
    session.add(combat)
    await session.flush()

    char_id = None
    if link:
        char = Character(discord_user_id=42, name="Hero")
        session.add(char)
        await session.flush()
        char_id = char.id
        for name in trait_names or []:
            session.add(Trait(character_id=char_id, name=name))

    c = Combatant(
        combat_id=combat.id, discord_user_id=42, name="Hero", character_id=char_id,
        basic_speed=5.0, hp_max=10, hp_current=10,
        fp_max=10, fp_current=10, ht=10, will=10, slot=0,
    )
    session.add(c)
    await session.commit()
    return c.id


def _interaction(session_factory):
    interaction = MagicMock()
    interaction.guild_id = 100
    interaction.channel_id = 200
    interaction.user.id = 999  # GM
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done.return_value = False
    interaction.followup.send = AsyncMock()
    interaction.client.db = session_factory
    return interaction


def _cog():
    from gurps_bot.cogs.combat import CombatTrackerGroup

    return CombatTrackerGroup(bot=MagicMock())


async def _run_major_wound(session_factory, mock_check, **kwargs):
    interaction = _interaction(session_factory)
    with patch(_REFRESH, new_callable=AsyncMock, return_value=True), \
            patch(_CHECK, mock_check):
        # -6 on a 10 HP target is a major wound (over half HP)
        await _cog().hp_cmd.callback(
            _cog(), interaction, target="Hero", amount=-6, **kwargs
        )
    return interaction


class TestPainThresholdReachesTheRoll:
    async def test_high_pain_threshold_adds_three(self, session, session_factory):
        await _seed(session, trait_names=["High Pain Threshold"])
        mock = MagicMock(return_value=_fixed_check(8, 10))
        await _run_major_wound(session_factory, mock)
        mock.assert_called_once()
        assert mock.call_args.args[1] == 3

    async def test_low_pain_threshold_subtracts_four(self, session, session_factory):
        await _seed(session, trait_names=["Low Pain Threshold"])
        mock = MagicMock(return_value=_fixed_check(8, 10))
        await _run_major_wound(session_factory, mock)
        assert mock.call_args.args[1] == -4

    async def test_no_relevant_trait_is_unmodified(self, session, session_factory):
        await _seed(session, trait_names=["Combat Reflexes"])
        mock = MagicMock(return_value=_fixed_check(8, 10))
        await _run_major_wound(session_factory, mock)
        assert mock.call_args.args[1] == 0

    async def test_npc_without_a_character_still_works(self, session, session_factory):
        """No character_id: degrade to no-trait behaviour, never error."""
        await _seed(session, link=False)
        mock = MagicMock(return_value=_fixed_check(8, 10))
        await _run_major_wound(session_factory, mock)
        assert mock.call_args.args[1] == 0

    async def test_location_and_trait_sum_through_the_cog(self, session, session_factory):
        """Skull -10 with High Pain Threshold +3 = -7."""
        await _seed(session, trait_names=["High Pain Threshold"])
        mock = MagicMock(return_value=_fixed_check(8, 10))
        await _run_major_wound(session_factory, mock, location="skull")
        assert mock.call_args.args[1] == -7


class TestModifierIsAttributedHonestly:
    async def test_message_names_the_pain_threshold(self, session, session_factory):
        await _seed(session, trait_names=["High Pain Threshold"])
        mock = MagicMock(return_value=_fixed_check(8, 10))
        interaction = await _run_major_wound(session_factory, mock)
        sent = interaction.response.send_message.call_args
        text = str(sent)
        assert "High Pain Threshold" in text

    async def test_message_does_not_blame_the_location_for_the_trait(
        self, session, session_factory
    ):
        """The note used to label the whole modifier as the location."""
        await _seed(session, trait_names=["Low Pain Threshold"])
        mock = MagicMock(return_value=_fixed_check(8, 10))
        interaction = await _run_major_wound(session_factory, mock)
        text = str(interaction.response.send_message.call_args)
        assert "Low Pain Threshold" in text
