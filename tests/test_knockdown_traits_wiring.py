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


def _sent_text(interaction) -> str:
    """Everything the command sent back, embeds included."""
    parts = []
    for mock in (interaction.response.send_message, interaction.followup.send):
        for call in mock.call_args_list:
            parts += [str(a) for a in call.args]
            for key, val in call.kwargs.items():
                if key == "embed" and val is not None:
                    parts += [val.title or "", val.description or ""]
                    parts += [f"{f.name} {f.value}" for f in val.fields]
                else:
                    parts.append(f"{key}={val}")
    return "\n".join(parts)


async def _run_major_wound(session_factory, **kwargs):
    """Apply a major wound and return what the bot said.

    The dice are NOT patched. `check` is left real because the modifier is
    deterministic even when the roll is not, and the knockdown line states the
    modifier verbatim — so asserting on the rendered text pins the GM-visible
    contract.

    An earlier version patched `gurps_bot.cogs.combat.check` and asserted on
    call args; it failed under the full suite because `Bot.close()` in
    test_extensions_load popped the cog modules out of sys.modules, leaving
    `patch` and the executing code in two different module objects. That is
    fixed at the source now (see `_restore_extension_modules`), and
    TestModifierArithmetic below patches deliberately again — the two styles
    answer different questions, and the summed modifier is only visible from
    inside the call.
    """
    interaction = _interaction(session_factory)
    with patch(_REFRESH, new_callable=AsyncMock, return_value=True):
        # -6 on a 10 HP target is a major wound (over half HP), so the B420
        # knockdown roll always fires
        await _cog().hp_cmd.callback(
            _cog(), interaction, target="Hero", amount=-6, **kwargs
        )
    text = _sent_text(interaction)
    # CombatContext suppresses CombatPermissionError/CombatTargetNotFound and
    # returns early on "No active combat" — without this, a setup problem reads
    # like a logic failure.
    for bad in ("No active combat", "not in this combat", "Combat error"):
        assert bad not in text, f"command returned early: {text}"
    assert "Knockdown & stunning" in text, f"knockdown never rolled: {text}"
    return text


class TestPainThresholdReachesTheRoll:
    async def test_high_pain_threshold_adds_three(self, session, session_factory):
        await _seed(session, trait_names=["High Pain Threshold"])
        text = await _run_major_wound(session_factory)
        assert "High Pain Threshold +3" in text

    async def test_low_pain_threshold_subtracts_four(self, session, session_factory):
        await _seed(session, trait_names=["Low Pain Threshold"])
        text = await _run_major_wound(session_factory)
        assert "Low Pain Threshold -4" in text

    async def test_no_relevant_trait_is_unmodified(self, session, session_factory):
        await _seed(session, trait_names=["Combat Reflexes"])
        text = await _run_major_wound(session_factory)
        assert "Pain Threshold" not in text
        # HT/Will 10 with no modifier at all
        assert "(HT/Will 10)" in text

    async def test_npc_without_a_character_still_works(self, session, session_factory):
        """No character_id: degrade to no-trait behaviour, never error."""
        await _seed(session, link=False)
        text = await _run_major_wound(session_factory)
        assert "Pain Threshold" not in text
        assert "(HT/Will 10)" in text

    async def test_location_and_trait_both_reach_the_roll(
        self, session, session_factory
    ):
        """Skull and the trait are listed separately, not merged."""
        await _seed(session, trait_names=["High Pain Threshold"])
        text = await _run_major_wound(session_factory, location="skull")
        assert "skull -10" in text
        assert "High Pain Threshold +3" in text


class TestModifierIsAttributedHonestly:
    async def test_location_is_not_blamed_for_the_trait(
        self, session, session_factory
    ):
        """The note used to label the whole modifier as the hit location."""
        await _seed(session, trait_names=["Low Pain Threshold"])
        text = await _run_major_wound(session_factory)
        assert "Low Pain Threshold -4" in text

    async def test_trait_only_case_names_no_location(self, session, session_factory):
        await _seed(session, trait_names=["High Pain Threshold"])
        text = await _run_major_wound(session_factory)
        assert "High Pain Threshold +3" in text
        assert "skull" not in text and "face" not in text


class TestModifierArithmetic:
    """What the rendered text cannot show: the single number that reached the roll.

    The output names each contribution separately — "skull -10", "High Pain
    Threshold +3" — so reading it proves both were considered but never proves
    they were added. Only the call itself carries the sum.

    This patches `gurps_bot.cogs.combat.check`, which was unreliable until the
    module-identity bug in test_extensions_load was fixed; if these ever start
    reporting zero calls again while the bot demonstrably works, that is the
    symptom to recognise, not a wiring regression.
    """

    async def _modifier(self, session_factory, **kwargs):
        interaction = _interaction(session_factory)
        mock = MagicMock(return_value=_fixed_check(8, 10))
        with patch(_REFRESH, new_callable=AsyncMock, return_value=True), patch(
            "gurps_bot.cogs.combat.check", mock
        ):
            await _cog().hp_cmd.callback(
                _cog(), interaction, target="Hero", amount=-6, **kwargs
            )
        mock.assert_called_once()
        return mock.call_args.args[1]

    async def test_high_pain_threshold_is_plus_three(self, session, session_factory):
        await _seed(session, trait_names=["High Pain Threshold"])
        assert await self._modifier(session_factory) == 3

    async def test_low_pain_threshold_is_minus_four(self, session, session_factory):
        await _seed(session, trait_names=["Low Pain Threshold"])
        assert await self._modifier(session_factory) == -4

    async def test_no_relevant_trait_is_zero(self, session, session_factory):
        await _seed(session, trait_names=["Combat Reflexes"])
        assert await self._modifier(session_factory) == 0

    async def test_location_and_trait_are_summed(self, session, session_factory):
        """Skull -10 with High Pain Threshold +3 reaches the roll as -7."""
        await _seed(session, trait_names=["High Pain Threshold"])
        assert await self._modifier(session_factory, location="skull") == -7
