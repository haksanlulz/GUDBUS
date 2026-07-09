from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import Base, Character, Attribute, ActiveCharacter
from gurps_bot.services.character_context import CharacterContext


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


def _make_interaction(session_factory, *, guild_id=100, user_id=42):
    from contextlib import asynccontextmanager
    from unittest.mock import MagicMock, AsyncMock

    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.user.id = user_id
    interaction.response.is_done.return_value = False
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    interaction.client.db = session_factory
    return interaction


class TestCharacterContext:
    async def test_enters_with_active_character(self, session, session_factory):
        char = Character(
            discord_user_id=42, name="Test Hero", total_points=100,
            profile_json={}, calc_json={}, equipment_json=[],
            settings_json={}, raw_gcs_json={},
        )
        session.add(char)
        await session.flush()
        session.add(ActiveCharacter(discord_user_id=42, guild_id=100, character_id=char.id))
        await session.commit()

        interaction = _make_interaction(session_factory)
        async with CharacterContext(interaction) as ctx:
            assert ctx.char.name == "Test Hero"
            assert ctx.char_name == "Test Hero"
            assert ctx.char_id == char.id
            assert ctx.session is not None

    async def test_no_active_character_sends_error(self, session_factory):
        interaction = _make_interaction(session_factory)

        async with CharacterContext(interaction) as ctx:
            assert not ctx.ok

        interaction.followup.send.assert_called_once()
        call_kwargs = interaction.followup.send.call_args
        assert "No active character" in call_kwargs[0][0]
        assert call_kwargs[1]["ephemeral"] is True

    async def test_defers_by_default(self, session, session_factory):
        char = Character(
            discord_user_id=42, name="Test Hero", total_points=100,
            profile_json={}, calc_json={}, equipment_json=[],
            settings_json={}, raw_gcs_json={},
        )
        session.add(char)
        await session.flush()
        session.add(ActiveCharacter(discord_user_id=42, guild_id=100, character_id=char.id))
        await session.commit()

        interaction = _make_interaction(session_factory)
        async with CharacterContext(interaction) as ctx:
            pass
        interaction.response.defer.assert_called_once()

    async def test_skip_defer_when_false(self, session, session_factory):
        char = Character(
            discord_user_id=42, name="Test Hero", total_points=100,
            profile_json={}, calc_json={}, equipment_json=[],
            settings_json={}, raw_gcs_json={},
        )
        session.add(char)
        await session.flush()
        session.add(ActiveCharacter(discord_user_id=42, guild_id=100, character_id=char.id))
        await session.commit()

        interaction = _make_interaction(session_factory)
        async with CharacterContext(interaction, defer=False) as ctx:
            pass
        interaction.response.defer.assert_not_called()

    async def test_convenience_methods_work(self, session, session_factory):
        char = Character(
            discord_user_id=42, name="Test Hero", total_points=100,
            profile_json={}, calc_json={}, equipment_json=[],
            settings_json={}, raw_gcs_json={},
        )
        session.add(char)
        await session.flush()
        session.add(Attribute(character_id=char.id, attr_id="st", value=14, points=40))
        session.add(ActiveCharacter(discord_user_id=42, guild_id=100, character_id=char.id))
        await session.commit()

        interaction = _make_interaction(session_factory)
        async with CharacterContext(interaction) as ctx:
            attrs = await ctx.get_attrs()
            skills = await ctx.get_skills()
            spells = await ctx.get_spells()
            traits = await ctx.get_traits()

        assert attrs["st"] == 14
        assert skills == []
        assert spells == []
        assert traits == []
