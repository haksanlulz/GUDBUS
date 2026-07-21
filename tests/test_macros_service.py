"""Dice-macro service CRUD (services/macros.py).

Per-user named dice expressions, case-insensitive names, upsert-on-save, expression
validated through the dice parser. In-memory SQLite per test.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import Base
from gurps_bot.services.macros import (
    MAX_NAME_LEN,
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


class TestNameSanitizing:
    """The saved name is echoed back into public replies, so it is sanitized
    and length-capped at the service boundary, not only at the cog."""

    async def test_markdown_and_mention_chars_stripped(self, session):
        m = await save_macro(session, U1, "**gs**", "2d+4")
        await session.commit()
        assert m.name == "gs"

    async def test_masked_link_name_cannot_survive(self, session):
        m = await save_macro(session, U1, "[click](http://evil)", "2d")
        await session.commit()
        assert "[" not in m.name and "]" not in m.name

    async def test_name_capped_at_max_len(self, session):
        m = await save_macro(session, U1, "x" * 300, "2d")
        await session.commit()
        assert len(m.name) == MAX_NAME_LEN

    async def test_name_with_no_usable_chars_raises(self, session):
        with pytest.raises(ValueError):
            await save_macro(session, U1, "***", "2d")

    async def test_lookup_normalizes_the_same_way(self, session):
        await save_macro(session, U1, "**gs**", "2d+4")
        await session.commit()
        assert (await get_macro(session, U1, "GS")).expression == "2d+4"


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
