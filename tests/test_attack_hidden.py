"""GM blind rolls slice 1b: /attack honors hidden:, and a hidden attack's
damage-button (RollDamageView) also responds ephemeral so the whole exchange
stays secret to the roller.

/attack is DB-backed, so it uses a real in-memory SQLite session (the
test_character_context pattern) rather than a mocked session.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import ActiveCharacter, Base, Character


# --------------------------------------------------------------------------- #
# RollDamageView — pure, no DB
# --------------------------------------------------------------------------- #
class TestRollDamageViewHidden:
    def _interaction(self):
        interaction = MagicMock()
        interaction.response.send_message = AsyncMock()
        return interaction

    async def test_hidden_button_is_ephemeral(self):
        from gurps_bot.ui.views import RollDamageView

        view = RollDamageView("2d cut", hidden=True)
        interaction = self._interaction()
        await RollDamageView.roll_damage_btn(view, interaction, MagicMock())
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True

    async def test_default_button_is_public(self):
        from gurps_bot.ui.views import RollDamageView

        view = RollDamageView("2d cut")
        interaction = self._interaction()
        await RollDamageView.roll_damage_btn(view, interaction, MagicMock())
        assert interaction.response.send_message.await_args.kwargs.get("ephemeral") in (None, False)


# --------------------------------------------------------------------------- #
# /attack — DB-backed
# --------------------------------------------------------------------------- #
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


@pytest_asyncio.fixture
async def hero(session):
    """An active character with one equipped weapon (Broadsword, 2d cut)."""
    char = Character(
        discord_user_id=42, name="Hero", total_points=100,
        profile_json={}, calc_json={},
        equipment_json=[{
            "equipped": True,
            "description": "Broadsword",
            "weapons": [{"damage": "2d cut", "level": 12, "usage": "swung"}],
        }],
        settings_json={}, raw_gcs_json={},
    )
    session.add(char)
    await session.flush()
    session.add(ActiveCharacter(discord_user_id=42, guild_id=100, character_id=char.id))
    await session.commit()
    return char


def _attack_interaction(session_factory, *, guild_id=100, user_id=42):
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.user.id = user_id
    interaction.response.send_message = AsyncMock()
    interaction.original_response = AsyncMock(return_value=MagicMock())
    interaction.client.db = session_factory
    return interaction


class TestAttackHidden:
    async def test_attack_hidden_is_ephemeral(self, hero, session_factory):
        from gurps_bot.cogs.combat import CombatCog

        cog = CombatCog(bot=MagicMock())
        interaction = _attack_interaction(session_factory)
        await cog.attack.callback(cog, interaction, weapon="Broadsword", modifier=0, hidden=True)

        kwargs = interaction.response.send_message.await_args.kwargs
        assert kwargs["ephemeral"] is True
        # the damage button must inherit the secrecy
        assert kwargs["view"].hidden is True

    async def test_attack_default_is_public(self, hero, session_factory):
        from gurps_bot.cogs.combat import CombatCog

        cog = CombatCog(bot=MagicMock())
        interaction = _attack_interaction(session_factory)
        await cog.attack.callback(cog, interaction, weapon="Broadsword")

        kwargs = interaction.response.send_message.await_args.kwargs
        assert kwargs.get("ephemeral") in (None, False)
        assert kwargs["view"].hidden is False


# --------------------------------------------------------------------------- #
# /attack — sheet strings reach a public embed, so they are escaped
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture
async def hostile_sheet_hero(session):
    """Active character whose weapon carries markdown + masked-link payloads.

    An imported .gcs is untrusted input; damage and reach land in embed fields.
    """
    char = Character(
        discord_user_id=42, name="Hero", total_points=100,
        profile_json={}, calc_json={},
        equipment_json=[{
            "equipped": True,
            "description": "Cursed Blade",
            "weapons": [{
                "damage": "2d [click](http://evil) **cut**",
                "level": 12,
                "usage": "swung",
                "reach": "1,2 [x](http://evil)",
            }],
        }],
        settings_json={}, raw_gcs_json={},
    )
    session.add(char)
    await session.flush()
    session.add(ActiveCharacter(discord_user_id=42, guild_id=100, character_id=char.id))
    await session.commit()
    return char


class TestAttackEscapesSheetStrings:
    async def _fields(self, session_factory):
        from gurps_bot.cogs.combat import CombatCog

        cog = CombatCog(bot=MagicMock())
        interaction = _attack_interaction(session_factory)
        await cog.attack.callback(cog, interaction, weapon="Cursed Blade")
        embed = interaction.response.send_message.await_args.kwargs["embed"]
        return {f.name: f.value for f in embed.fields}

    async def test_damage_field_is_escaped(self, hostile_sheet_hero, session_factory):
        fields = await self._fields(session_factory)
        assert "[click](http://evil)" not in fields["Damage"]
        assert "\\[click\\]" in fields["Damage"]

    async def test_reach_field_is_escaped(self, hostile_sheet_hero, session_factory):
        fields = await self._fields(session_factory)
        assert "[x](http://evil)" not in fields["Reach"]
