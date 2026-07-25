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


def _interaction(session_factory, user_id=42, guild_id=7):
    i = MagicMock()
    i.user.id = user_id
    i.guild_id = guild_id
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


class TestUnusableNameIsHandled:
    """A name that sanitizes to nothing must not escape as a raw ValueError.

    normalize_macro_name raises when every character is stripped. save caught it;
    roll and delete called straight into get_macro and the exception reached the
    global handler as a generic "something went wrong".
    """

    async def test_roll_unusable_name_replies_instead_of_raising(self, session_factory):
        i = _interaction(session_factory)
        await _cog().roll_macro.callback(_cog(), i, name="***")
        assert _sent(i).kwargs.get("ephemeral") is True
        assert "usable" in _sent(i).args[0].lower()

    async def test_delete_unusable_name_replies_instead_of_raising(self, session_factory):
        i = _interaction(session_factory)
        # only markdown chars — note ( ) are deliberately NOT stripped here
        await _cog().delete_cmd.callback(_cog(), i, name="[]|~")
        assert _sent(i).kwargs.get("ephemeral") is True
        assert "usable" in _sent(i).args[0].lower()

    async def test_save_unusable_name_does_not_blame_the_expression(
        self, session_factory
    ):
        # The expression is valid; only the name is unusable. Reporting
        # "Invalid dice expression" sent the user to fix the wrong argument.
        i = _interaction(session_factory)
        await _cog().save.callback(_cog(), i, name="***", expression="2d+4")
        msg = _sent(i).args[0].lower()
        assert await _count(session_factory, 42) == 0
        assert "dice expression" not in msg
        assert "name" in msg

    async def test_roll_unrollable_stored_expression_replies(self, session_factory):
        # Defence in depth: a row whose expression predates current parser
        # bounds (or was written outside the service) must not 500 the command.
        async with session_factory() as s:
            s.add(DiceMacro(discord_user_id=42, name="legacy", expression="99999d"))
            await s.commit()
        i = _interaction(session_factory)
        await _cog().roll_macro.callback(_cog(), i, name="legacy")
        assert _sent(i).kwargs.get("ephemeral") is True
        assert "legacy" in _sent(i).args[0].lower()


class TestEchoMatchesStoredReality:
    """Confirmations must quote what was stored, not what was typed."""

    async def test_save_echo_uses_the_sanitized_name(self, session_factory):
        i = _interaction(session_factory)
        await _cog().save.callback(_cog(), i, name="Great_Sword", expression="2d+4")
        msg = _sent(i).args[0]
        async with session_factory() as s:
            stored = (await s.execute(select(DiceMacro))).scalar_one()
        assert stored.name == "greatsword"
        assert "greatsword" in msg
        assert "great_sword" not in msg.lower()

    async def test_save_echo_uses_the_truncated_name(self, session_factory):
        i = _interaction(session_factory)
        await _cog().save.callback(_cog(), i, name="z" * 80, expression="1d")
        msg = _sent(i).args[0]
        async with session_factory() as s:
            stored = (await s.execute(select(DiceMacro))).scalar_one()
        assert len(stored.name) == 50
        assert "z" * 80 not in msg
        assert stored.name in msg

    async def test_miss_message_quotes_the_lookup_key(self, session_factory):
        # "No macro named **x_y**" when the key actually looked up was "xy"
        # sends the user hunting for a macro name that cannot exist.
        i = _interaction(session_factory)
        await _cog().roll_macro.callback(_cog(), i, name="X_Y")
        assert "xy" in _sent(i).args[0]
        assert "x_y" not in _sent(i).args[0].lower()


class TestNameAutocomplete:
    """/macro roll and /macro delete suggest the caller's own macro names."""

    @staticmethod
    async def _suggest(cog, interaction, current, command="roll_macro"):
        """Invoke the callback the way discord.py's dispatcher does.

        _invoke_autocomplete only prepends the cog binding when the callback
        carries pass_command_binding (i.e. it was registered as a cog method);
        a module-level callback is called as (interaction, value).
        """
        callback = getattr(cog, command)._params["name"].autocomplete
        assert callback is not None, f"no autocomplete registered on {command}.name"
        if getattr(callback, "pass_command_binding", False):
            return await callback(cog, interaction, current)
        return await callback(interaction, current)

    async def _seed(self, session_factory, names, user_id=42):
        for n in names:
            await _cog().save.callback(
                _cog(), _interaction(session_factory, user_id), name=n, expression="1d"
            )

    async def test_roll_lists_saved_macros_when_query_empty(self, session_factory):
        await self._seed(session_factory, ["fireball", "greatsword"])
        cog, i = _cog(), _interaction(session_factory)
        names = [c.name for c in await self._suggest(cog, i, "")]
        assert sorted(names) == ["fireball", "greatsword"]

    async def test_delete_has_the_same_autocomplete(self, session_factory):
        await self._seed(session_factory, ["fireball"])
        cog, i = _cog(), _interaction(session_factory)
        names = [c.name for c in await self._suggest(cog, i, "", command="delete_cmd")]
        assert names == ["fireball"]

    async def test_fuzzy_filters_and_ranks_by_current(self, session_factory):
        await self._seed(session_factory, ["fireball", "greatsword", "punch"])
        cog, i = _cog(), _interaction(session_factory)
        names = [c.name for c in await self._suggest(cog, i, "fire")]
        assert names[0] == "fireball"  # best match ranks first
        assert "punch" not in names  # scores under the cutoff, dropped

    async def test_typo_still_matches(self, session_factory):
        # WRatio (not partial_ratio) — typo tolerance over a short per-user list.
        await self._seed(session_factory, ["greatsword"])
        cog, i = _cog(), _interaction(session_factory)
        names = [c.name for c in await self._suggest(cog, i, "gratsword")]
        assert names == ["greatsword"]

    async def test_only_the_callers_own_macros(self, session_factory):
        await self._seed(session_factory, ["mine"], user_id=42)
        await self._seed(session_factory, ["theirs"], user_id=77)
        cog, i = _cog(), _interaction(session_factory, user_id=42)
        names = [c.name for c in await self._suggest(cog, i, "")]
        assert names == ["mine"]

    async def test_capped_at_25_choices(self, session_factory):
        async with session_factory() as s:
            for n in range(40):
                s.add(DiceMacro(discord_user_id=42, name=f"m{n:02d}", expression="1d"))
            await s.commit()
        cog, i = _cog(), _interaction(session_factory)
        assert len(await self._suggest(cog, i, "")) == 25
        assert len(await self._suggest(cog, i, "m")) == 25

    async def test_choice_name_and_value_capped_at_100(self, session_factory):
        # Discord 400s the WHOLE payload on one over-long Choice. Macro names
        # are capped at 50 by the service, but a row written before that cap
        # (or outside it) must not kill every suggestion.
        long_name = "q" * 150
        async with session_factory() as s:
            s.add(DiceMacro(discord_user_id=42, name=long_name, expression="1d"))
            await s.commit()
        cog, i = _cog(), _interaction(session_factory)
        for query in ("", long_name[:40]):
            choices = await self._suggest(cog, i, query)
            assert len(choices) == 1, f"query={query!r}"
            assert len(choices[0].name) <= 100
            assert len(choices[0].value) <= 100
