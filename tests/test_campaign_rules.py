"""Per-guild house rules, and the Rule-of-14 switch on /fright-check.

GAUNTLET §5 SPEC fright-follows-the-book, operator-ratified 2026-07-27:
Rule of 14 is ON by default (RAW) and a campaign may turn it off, in which case
modified Will is used uncapped and the bot says which mode it used.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import Base, Character, Trait
from gurps_bot.mechanics.checks import CheckResult, _determine_outcome
from gurps_bot.mechanics.dice import DiceSpec, RollResult
from gurps_bot.services.campaign import (
    DEFAULT_RULE_OF_14,
    get_campaign_rules,
    set_rule_of_14,
)

_CHECK = "gurps_bot.cogs.rolling.check"


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


class TestServiceDefaults:
    async def test_raw_is_the_default(self):
        assert DEFAULT_RULE_OF_14 is True

    async def test_untouched_guild_needs_no_row(self, session):
        rules = await get_campaign_rules(session, 999)
        assert rules.rule_of_14 is True

    async def test_reading_does_not_create_a_row(self, session):
        from sqlalchemy import func, select

        from gurps_bot.db.models import CampaignSettings

        await get_campaign_rules(session, 999)
        count = (
            await session.execute(select(func.count()).select_from(CampaignSettings))
        ).scalar_one()
        assert count == 0

    async def test_no_guild_yields_defaults(self, session):
        assert (await get_campaign_rules(session, None)).rule_of_14 is True


class TestServiceWrites:
    async def test_turning_off_then_reading_back(self, session):
        await set_rule_of_14(session, 100, False)
        await session.commit()
        assert (await get_campaign_rules(session, 100)).rule_of_14 is False

    async def test_turning_back_on(self, session):
        await set_rule_of_14(session, 100, False)
        await session.commit()
        await set_rule_of_14(session, 100, True)
        await session.commit()
        assert (await get_campaign_rules(session, 100)).rule_of_14 is True

    async def test_guilds_are_independent(self, session):
        await set_rule_of_14(session, 100, False)
        await session.commit()
        assert (await get_campaign_rules(session, 200)).rule_of_14 is True

    async def test_repeated_writes_keep_one_row(self, session):
        from sqlalchemy import func, select

        from gurps_bot.db.models import CampaignSettings

        for enabled in (False, True, False):
            await set_rule_of_14(session, 100, enabled)
            await session.commit()
        count = (
            await session.execute(select(func.count()).select_from(CampaignSettings))
        ).scalar_one()
        assert count == 1


def _fixed_check(rolled: int, target: int) -> CheckResult:
    rr = RollResult(spec=DiceSpec(3, 6, 0), dice=(rolled,), total=rolled)
    return CheckResult(
        roll_result=rr, target=target, margin=target - rolled,
        outcome=_determine_outcome(rolled, target),
    )


def _interaction(session_factory, guild_id=100):
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.user.id = 42
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done.return_value = False
    interaction.followup.send = AsyncMock()
    interaction.client.db = session_factory
    return interaction


def _cog():
    from gurps_bot.cogs.rolling import RollingCog

    return RollingCog(MagicMock())


async def _seed_character(session, *, will: int, traits: list[str] | None = None):
    from gurps_bot.db.models import ActiveCharacter, Attribute

    char = Character(discord_user_id=42, name="Hero")
    session.add(char)
    await session.flush()
    session.add(Attribute(character_id=char.id, attr_id="will", value=will))
    for t in traits or []:
        session.add(Trait(character_id=char.id, name=t))
    session.add(
        ActiveCharacter(discord_user_id=42, guild_id=100, character_id=char.id)
    )
    await session.commit()
    return char


async def _run_fright(session_factory, mock_check, modifier=0):
    interaction = _interaction(session_factory)
    with patch(_CHECK, mock_check):
        await _cog().fright_check.callback(
            _cog(), interaction, modifier=modifier
        )
    return interaction


def _embed_text(interaction) -> str:
    """All rendered text from the embed that was sent — title, description and
    every field. The mock's repr shows only the object, not its contents."""
    embed = interaction.response.send_message.call_args.kwargs["embed"]
    parts = [embed.title or "", embed.description or ""]
    for field in embed.fields:
        parts += [field.name or "", field.value or ""]
    return "\n".join(parts)


class TestRuleOf14Switch:
    async def test_on_by_default_caps_at_thirteen(self, session, session_factory):
        await _seed_character(session, will=16)
        mock = MagicMock(return_value=_fixed_check(8, 13))
        await _run_fright(session_factory, mock)
        assert mock.call_args.args[0] == 13

    async def test_off_uses_will_uncapped(self, session, session_factory):
        await _seed_character(session, will=16)
        await set_rule_of_14(session, 100, False)
        await session.commit()
        mock = MagicMock(return_value=_fixed_check(8, 16))
        await _run_fright(session_factory, mock)
        assert mock.call_args.args[0] == 16

    async def test_below_the_cap_is_unaffected_either_way(
        self, session, session_factory
    ):
        await _seed_character(session, will=11)
        mock = MagicMock(return_value=_fixed_check(8, 11))
        await _run_fright(session_factory, mock)
        assert mock.call_args.args[0] == 11

    async def test_the_bot_says_which_mode_it_used(self, session, session_factory):
        """Ratified spec requires the mode be stated, since the same roll means
        different things under each."""
        await _seed_character(session, will=16)
        mock = MagicMock(return_value=_fixed_check(8, 13))
        interaction = await _run_fright(session_factory, mock)
        assert "Rule of 14" in _embed_text(interaction)

    async def test_off_mode_is_announced_too(self, session, session_factory):
        await _seed_character(session, will=16)
        await set_rule_of_14(session, 100, False)
        await session.commit()
        mock = MagicMock(return_value=_fixed_check(8, 16))
        interaction = await _run_fright(session_factory, mock)
        text = _embed_text(interaction)
        assert "OFF" in text or "house rule" in text


class TestFrightTraits:
    async def test_fearlessness_adds_before_the_cap(self, session, session_factory):
        """Will 10 + Fearlessness 2 = 12, still under the cap."""
        await _seed_character(session, will=10, traits=["Fearlessness 2"])
        mock = MagicMock(return_value=_fixed_check(8, 12))
        await _run_fright(session_factory, mock)
        assert mock.call_args.args[0] == 12

    async def test_fearlessness_is_wasted_above_the_cap(
        self, session, session_factory
    ):
        """The RAW consequence the bot must not hide: added before the cap, so
        a Will-13 character gains nothing."""
        await _seed_character(session, will=13, traits=["Fearlessness 3"])
        mock = MagicMock(return_value=_fixed_check(8, 13))
        await _run_fright(session_factory, mock)
        assert mock.call_args.args[0] == 13

    async def test_fearlessness_pays_off_with_the_rule_off(
        self, session, session_factory
    ):
        await _seed_character(session, will=13, traits=["Fearlessness 3"])
        await set_rule_of_14(session, 100, False)
        await session.commit()
        mock = MagicMock(return_value=_fixed_check(8, 16))
        await _run_fright(session_factory, mock)
        assert mock.call_args.args[0] == 16

    async def test_fearfulness_subtracts(self, session, session_factory):
        await _seed_character(session, will=12, traits=["Fearfulness 2"])
        mock = MagicMock(return_value=_fixed_check(8, 10))
        await _run_fright(session_factory, mock)
        assert mock.call_args.args[0] == 10

    async def test_fearfulness_floors_will_at_three(self, session, session_factory):
        """"You may not reduce your Will roll below 3." """
        await _seed_character(session, will=5, traits=["Fearfulness 8"])
        mock = MagicMock(return_value=_fixed_check(3, 3))
        await _run_fright(session_factory, mock)
        assert mock.call_args.args[0] == 3

    async def test_unfazeable_rolls_nothing_at_all(self, session, session_factory):
        """B95: "You are exempt from Fright Checks." Reporting a made roll would
        be a different rule."""
        await _seed_character(session, will=10, traits=["Unfazeable"])
        mock = MagicMock(return_value=_fixed_check(8, 10))
        interaction = await _run_fright(session_factory, mock)
        mock.assert_not_called()
        assert "Exempt" in _embed_text(interaction)
