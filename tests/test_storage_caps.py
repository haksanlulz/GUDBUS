"""A stranger must not be able to fill the operator's disk.

Characters have been capped at 20 per user since early on. Notes, macros,
timers and study logs were not capped at all — fine while everyone who could
reach them was at the operator's own table, and a disk-growth vector the moment
the bot is public, because the rows land on a NAS array the operator pays for.

Caps are set well above plausible use; the point is to bound abuse, not ration.
So these tests mostly drive the cap directly rather than creating thousands of
rows, and one test per table proves the cap is actually wired into that table's
create path — which is the part that gets forgotten.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db import notes as _notes_model  # noqa: F401
from gurps_bot.db import study as _study_model  # noqa: F401
from gurps_bot.db import timers as _timers_model  # noqa: F401
from gurps_bot.db import wealth as _wealth_model  # noqa: F401
from gurps_bot.db.models import Base
from gurps_bot.services import limits
from gurps_bot.services.limits import StorageLimitExceeded
from gurps_bot.services.macros import save_macro
from gurps_bot.services.notes import add_note, edit_note
from gurps_bot.services.study import log_study
from gurps_bot.services.timers import add_timer

USER = 4242
GUILD = 100
CHANNEL = 200


@pytest_asyncio.fixture
async def session():
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await eng.dispose()


@pytest.fixture
def tiny_caps(monkeypatch):
    """Drive the caps to 2 so the tests exercise the guard, not the disk."""
    for name in (
        "MAX_NOTES_PER_USER_PER_GUILD",
        "MAX_MACROS_PER_USER",
        "MAX_TIMERS_PER_CHANNEL",
        "MAX_STUDY_LOGS_PER_USER",
    ):
        monkeypatch.setattr(limits, name, 2)
    # The services import the names directly, so patch there too.
    import gurps_bot.services.macros as macros_mod
    import gurps_bot.services.notes as notes_mod
    import gurps_bot.services.study as study_mod
    import gurps_bot.services.timers as timers_mod

    monkeypatch.setattr(notes_mod, "MAX_NOTES_PER_USER_PER_GUILD", 2)
    monkeypatch.setattr(macros_mod, "MAX_MACROS_PER_USER", 2)
    monkeypatch.setattr(timers_mod, "MAX_TIMERS_PER_CHANNEL", 2)
    monkeypatch.setattr(study_mod, "MAX_STUDY_LOGS_PER_USER", 2)


class TestEachTableIsCapped:
    """One per table: the cap has to be wired into that create path."""

    async def test_notes(self, session, tiny_caps):
        for i in range(2):
            await add_note(
                session, discord_user_id=USER, title=f"n{i}", guild_id=GUILD
            )
        with pytest.raises(StorageLimitExceeded, match="notes"):
            await add_note(
                session, discord_user_id=USER, title="over", guild_id=GUILD
            )

    async def test_macros(self, session, tiny_caps):
        for i in range(2):
            await save_macro(session, USER, f"m{i}", "3d6")
        with pytest.raises(StorageLimitExceeded, match="macros"):
            await save_macro(session, USER, "over", "3d6")

    async def test_timers(self, session, tiny_caps):
        for i in range(2):
            await add_timer(session, GUILD, CHANNEL, f"t{i}", 3, "turns")
        with pytest.raises(StorageLimitExceeded, match="timers"):
            await add_timer(session, GUILD, CHANNEL, "over", 3, "turns")

    async def test_study_logs(self, session, tiny_caps):
        for i in range(2):
            await log_study(session, USER, "Broadsword", "self_teaching", 1.0)
        with pytest.raises(StorageLimitExceeded, match="study"):
            await log_study(session, USER, "Broadsword", "self_teaching", 1.0)


class TestTheCapIsScopedNotGlobal:
    """A cap that counted globally would let one user lock out everyone else."""

    async def test_another_user_is_unaffected(self, session, tiny_caps):
        for i in range(2):
            await add_note(
                session, discord_user_id=USER, title=f"n{i}", guild_id=GUILD
            )
        # different user, same guild — must still be able to write
        note = await add_note(
            session, discord_user_id=USER + 1, title="fine", guild_id=GUILD
        )
        assert note.id is not None

    async def test_another_guild_is_unaffected(self, session, tiny_caps):
        for i in range(2):
            await add_note(
                session, discord_user_id=USER, title=f"n{i}", guild_id=GUILD
            )
        note = await add_note(
            session, discord_user_id=USER, title="fine", guild_id=GUILD + 1
        )
        assert note.id is not None

    async def test_another_channel_is_unaffected(self, session, tiny_caps):
        for i in range(2):
            await add_timer(session, GUILD, CHANNEL, f"t{i}", 3, "turns")
        timer = await add_timer(session, GUILD, CHANNEL + 1, "fine", 3, "turns")
        assert timer.id is not None


class TestReplacingIsNotCreating:
    async def test_overwriting_a_macro_does_not_count_against_the_cap(
        self, session, tiny_caps
    ):
        """Same rule as the character import cap: a replace adds no row."""
        for i in range(2):
            await save_macro(session, USER, f"m{i}", "3d6")
        again = await save_macro(session, USER, "m0", "2d6+1")
        assert again.expression == "2d6+1"


class TestTheUserIsTold:
    """A cap the user cannot see is indistinguishable from a broken command."""

    async def test_the_error_handler_surfaces_the_limit_message(self):
        from unittest.mock import AsyncMock, MagicMock

        from discord import app_commands

        from gurps_bot.cogs.error_handler import ErrorHandler

        bot = MagicMock()
        handler = ErrorHandler(bot)
        interaction = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()

        raised = StorageLimitExceeded("You have 250 notes (maximum 250).")
        # discord.py wraps a callback exception before the tree sees it.
        wrapped = app_commands.CommandInvokeError(MagicMock(), raised)
        await handler.on_app_command_error(interaction, wrapped)

        sent = interaction.response.send_message.await_args
        assert "250 notes" in sent.args[0], (
            f"the cap message was swallowed; user saw: {sent.args[0]!r}"
        )
        assert sent.kwargs.get("ephemeral") is True


class TestTheCapsAreDiscoverable:
    def test_every_declared_cap_is_a_positive_int(self):
        declared = {
            n: getattr(limits, n)
            for n in dir(limits)
            if n.startswith("MAX_") and isinstance(getattr(limits, n), int)
        }
        assert declared, "no caps declared"
        for name, value in declared.items():
            assert value > 0, f"{name} is not a positive cap"

    def test_the_set_of_caps_is_pinned(self):
        """Adding a user-writable table should mean adding a cap here.

        Pinned so a new table's absence is visible: if you add one and do not
        cap it, this still passes — but you had to read this list to get here,
        which is the cheapest reminder available.
        """
        declared = {n for n in dir(limits) if n.startswith("MAX_")}
        assert declared == {
            "MAX_CHARACTERS_PER_USER",
            "MAX_NOTES_PER_USER_PER_GUILD",
            "MAX_MACROS_PER_USER",
            "MAX_TIMERS_PER_CHANNEL",
            "MAX_STUDY_LOGS_PER_USER",
        }, "the cap set changed — is a new user-writable table uncapped?"
