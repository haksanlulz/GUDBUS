from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import Base
from gurps_bot.services.macros import (
    delete_macro,
    get_macro,
    list_macros,
    save_macro,
)

U1 = 111
U2 = 222


@pytest_asyncio.fixture
async def session():
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s
    await eng.dispose()


class TestSaveMacro:
    async def test_save_new_normalizes_name(self, session):
        m = await save_macro(session, U1, "Greatsword", "2d+4")
        await session.commit()
        assert m.name == "greatsword"  # stored lowercase
        assert m.expression == "2d+4"
        got = await get_macro(session, U1, "greatsword")
        assert got is not None and got.expression == "2d+4"

    async def test_save_replaces_existing_case_insensitively(self, session):
        await save_macro(session, U1, "gs", "2d+4")
        await save_macro(session, U1, "GS", "3d-1")  # same key
        await session.commit()
        macros = await list_macros(session, U1)
        assert len(macros) == 1
        assert macros[0].expression == "3d-1"

    async def test_invalid_expression_raises(self, session):
        with pytest.raises(ValueError):
            await save_macro(session, U1, "bad", "not-dice")


class TestGetMacro:
    async def test_case_insensitive_lookup(self, session):
        await save_macro(session, U1, "Fireball", "3d6")
        await session.commit()
        assert (await get_macro(session, U1, "fireball")).expression == "3d6"
        assert (await get_macro(session, U1, "FIREBALL")).expression == "3d6"

    async def test_missing_returns_none(self, session):
        assert await get_macro(session, U1, "nope") is None

    async def test_per_user_isolation(self, session):
        await save_macro(session, U1, "shared", "2d")
        await session.commit()
        assert await get_macro(session, U2, "shared") is None


class TestListAndDelete:
    async def test_list_only_own_ordered(self, session):
        await save_macro(session, U1, "b", "2d")
        await save_macro(session, U1, "a", "1d")
        await save_macro(session, U2, "c", "3d")
        await session.commit()
        names = [m.name for m in await list_macros(session, U1)]
        assert names == ["a", "b"]  # ordered by name, U2's excluded

    async def test_delete_found(self, session):
        await save_macro(session, U1, "x", "1d")
        await session.commit()
        assert await delete_macro(session, U1, "X") is True
        await session.commit()
        assert await get_macro(session, U1, "x") is None

    async def test_delete_missing_returns_false(self, session):
        assert await delete_macro(session, U1, "ghost") is False
