"""Text commands (@<bot> sync, @<bot> admin ...) answer on failure and log on success.

Before 2026-10-18 a failed check or a bad argument on a text command went to discord.py's
default handler (stderr, no reply) and a success logged nothing, so an owner command's
silence could not be told from a bot that never saw the message.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from discord.ext import commands

from gurps_bot.cogs.error_handler import ErrorHandler
from gurps_bot.services.limits import StorageLimitExceeded


def _ctx(command: str = "admin delete", guild: bool = True):
    ctx = MagicMock()
    ctx.command.qualified_name = command
    ctx.author.id = 1
    if guild:
        ctx.guild.id = 100
    else:
        ctx.guild = None
    ctx.reply = AsyncMock()
    return ctx


def _handler() -> ErrorHandler:
    return ErrorHandler(bot=MagicMock())


def _said(ctx) -> str:
    return "\n".join(str(a) for call in ctx.reply.await_args_list for a in call.args)


class TestFailuresAreAnswered:
    async def test_not_owner_is_told_so(self):
        ctx = _ctx()
        await _handler().on_command_error(ctx, commands.NotOwner())
        assert "bot owner" in _said(ctx)

    async def test_a_missing_argument_names_the_command(self):
        ctx = _ctx()
        param = MagicMock()
        param.name = "user"
        param.displayed_name = "user"
        await _handler().on_command_error(ctx, commands.MissingRequiredArgument(param))
        assert "admin delete" in _said(ctx) and "user" in _said(ctx)

    async def test_an_unresolvable_member_is_a_bad_input_not_a_crash(self):
        ctx = _ctx()
        await _handler().on_command_error(ctx, commands.UserNotFound("nobody"))
        assert "Bad input" in _said(ctx)

    async def test_command_not_found_stays_silent(self):
        """A bare mention is conversation; replying to every one would be noise."""
        ctx = _ctx()
        await _handler().on_command_error(ctx, commands.CommandNotFound("x"))
        ctx.reply.assert_not_awaited()

    async def test_a_row_cap_is_surfaced_in_its_own_words(self):
        ctx = _ctx()
        err = commands.CommandInvokeError(StorageLimitExceeded("You have 50 characters (maximum 50)."))
        await _handler().on_command_error(ctx, err)
        assert "maximum 50" in _said(ctx)

    async def test_an_unknown_error_is_logged_with_ids_and_apologised_for(self):
        ctx = _ctx()
        err = commands.CommandInvokeError(RuntimeError("boom"))
        with patch("gurps_bot.cogs.error_handler.log") as log:
            await _handler().on_command_error(ctx, err)
        assert "Something went wrong" in _said(ctx)
        [call] = log.exception.call_args_list
        assert "admin delete" in call.args and 1 in call.args and call.kwargs.get("exc_info") is err

    async def test_a_failing_reply_does_not_raise(self):
        ctx = _ctx()
        ctx.reply = AsyncMock(side_effect=RuntimeError("no channel"))
        with patch("gurps_bot.cogs.error_handler.log") as log:
            await _handler().on_command_error(ctx, commands.NotOwner())
        [call] = log.exception.call_args_list
        assert "handler itself failed" in call.args[0]


class TestSuccessIsLogged:
    async def test_an_invocation_logs_ids_only(self):
        ctx = _ctx("admin list")
        with patch("gurps_bot.cogs.error_handler.log") as log:
            await _handler().on_command(ctx)
        [call] = log.info.call_args_list
        assert "text command" in call.args[0]
        assert call.args[1:] == ("admin list", 1, 100)

    async def test_outside_a_guild_logs_none(self):
        ctx = _ctx("sync", guild=False)
        with patch("gurps_bot.cogs.error_handler.log") as log:
            await _handler().on_command(ctx)
        [call] = log.info.call_args_list
        assert call.args[1:] == ("sync", 1, None)
