"""/macro cog wiring only — the CRUD itself is covered in test_macros_service.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import Base, DiceMacro


@pytest_asyncio.fixture
async def session_factory():
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    await eng.dispose()


def _interaction(session_factory, user_id=42):
    i = MagicMock()
    i.user.id = user_id
    i.client.db = session_factory
    i.response.send_message = AsyncMock()
    return i


def _cog():
    from gurps_bot.cogs.macros import MacroCog

    return MacroCog(bot=MagicMock())


def _sent(interaction):
    return interaction.response.send_message.await_args


async def _count(session_factory, user_id):
    async with session_factory() as s:
        rows = (
            await s.execute(
                select(DiceMacro).where(DiceMacro.discord_user_id == user_id)
            )
        ).scalars().all()
        return len(rows)


class TestMacroCog:
    async def test_save_persists_and_confirms(self, session_factory):
        i = _interaction(session_factory)
        await _cog().save.callback(_cog(), i, name="GS", expression="2d+4")
        assert await _count(session_factory, 42) == 1
        assert "gs" in _sent(i).args[0].lower()

    async def test_save_invalid_does_not_persist(self, session_factory):
        i = _interaction(session_factory)
        await _cog().save.callback(_cog(), i, name="bad", expression="xyz")
        assert await _count(session_factory, 42) == 0
        assert _sent(i).kwargs.get("ephemeral") is True
        assert "invalid" in _sent(i).args[0].lower()

    async def test_roll_saved_macro_shows_name_and_expr(self, session_factory):
        await _cog().save.callback(
            _cog(), _interaction(session_factory), name="fb", expression="3d6"
        )
        i = _interaction(session_factory)
        await _cog().roll_macro.callback(_cog(), i, name="fb")
        out = _sent(i).args[0]
        assert "fb" in out and "3d6" in out

    async def test_roll_missing_macro(self, session_factory):
        i = _interaction(session_factory)
        await _cog().roll_macro.callback(_cog(), i, name="ghost")
        assert "no macro" in _sent(i).args[0].lower()

    async def test_list_empty_then_populated(self, session_factory):
        i = _interaction(session_factory)
        await _cog().list_cmd.callback(_cog(), i)
        assert "no saved macros" in _sent(i).args[0].lower()

        await _cog().save.callback(
            _cog(), _interaction(session_factory), name="a", expression="1d"
        )
        i2 = _interaction(session_factory)
        await _cog().list_cmd.callback(_cog(), i2)
        out = _sent(i2).args[0]
        assert "a" in out and "1d" in out

    async def test_delete_found_then_missing(self, session_factory):
        await _cog().save.callback(
            _cog(), _interaction(session_factory), name="x", expression="1d"
        )
        i = _interaction(session_factory)
        await _cog().delete_cmd.callback(_cog(), i, name="X")
        assert "deleted" in _sent(i).args[0].lower()
        assert await _count(session_factory, 42) == 0

        i2 = _interaction(session_factory)
        await _cog().delete_cmd.callback(_cog(), i2, name="ghost")
        assert "no macro" in _sent(i2).args[0].lower()
