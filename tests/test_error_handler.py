"""Global error-handler cog tests.

Error handlers fail open — a bug here swallows every command error into
silence. Pin the contract: friendly message per known error class, ephemeral
reply via the right channel (response vs followup), unknown errors logged
with context, and the handler surviving its own send failing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from discord import app_commands

from gurps_bot.cogs.error_handler import ErrorHandler


def _interaction(*, response_done: bool):
    interaction = MagicMock()
    interaction.user.id = 42
    interaction.guild_id = 100
    interaction.channel.id = 200
    interaction.command.name = "roll"
    interaction.data = {"options": [{"name": "dice", "value": "3d6"}]}
    interaction.response.is_done.return_value = response_done
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _handler() -> ErrorHandler:
    return ErrorHandler(bot=MagicMock())


class TestKnownErrorClasses:
    async def test_check_failure_gets_permission_message(self):
        interaction = _interaction(response_done=False)
        await _handler().on_app_command_error(
            interaction, app_commands.CheckFailure()
        )
        interaction.response.send_message.assert_awaited_once()
        args = interaction.response.send_message.await_args
        assert "permission" in args.args[0]
        assert args.kwargs.get("ephemeral") is True

    async def test_cooldown_never_says_zero_seconds(self):
        # Regression: CommandOnCooldown subclasses CheckFailure, and a
        # CheckFailure-first chain answered every cooldown hit with
        # "you don't have permission".
        interaction = _interaction(response_done=False)
        cooldown = MagicMock()
        await _handler().on_app_command_error(
            interaction,
            app_commands.CommandOnCooldown(cooldown, retry_after=0.2),
        )
        msg = interaction.response.send_message.await_args.args[0]
        assert "cooldown" in msg.lower()
        assert "1s" in msg and "0s" not in msg

    async def test_missing_permissions_names_the_permissions(self):
        # Same subclass trap as cooldown — must beat CheckFailure to its branch.
        interaction = _interaction(response_done=False)
        await _handler().on_app_command_error(
            interaction,
            app_commands.MissingPermissions(["manage_guild"]),
        )
        msg = interaction.response.send_message.await_args.args[0]
        assert "manage_guild" in msg


class TestResponseChannel:
    async def test_uses_response_when_not_done(self):
        interaction = _interaction(response_done=False)
        await _handler().on_app_command_error(
            interaction, app_commands.AppCommandError("boom")
        )
        interaction.response.send_message.assert_awaited_once()
        interaction.followup.send.assert_not_awaited()

    async def test_uses_followup_when_already_done(self):
        interaction = _interaction(response_done=True)
        await _handler().on_app_command_error(
            interaction, app_commands.AppCommandError("boom")
        )
        interaction.followup.send.assert_awaited_once()
        interaction.response.send_message.assert_not_awaited()
        assert interaction.followup.send.await_args.kwargs.get("ephemeral") is True


class TestUnknownErrorLogging:
    # Assert on the module logger directly (not caplog): other tests
    # reconfigure logging/propagation, and these must hold in any suite order.

    async def test_unknown_error_logged_with_context(self):
        interaction = _interaction(response_done=False)
        with patch("gurps_bot.cogs.error_handler.log") as mock_log:
            await _handler().on_app_command_error(
                interaction, app_commands.AppCommandError("kaboom")
            )
        mock_log.exception.assert_called_once()
        assert "Unhandled command error" in mock_log.exception.call_args.args[0]
        # the generic user-facing message, not the raw exception text
        msg = interaction.response.send_message.await_args.args[0]
        assert "logged" in msg
        assert "kaboom" not in msg

    async def test_handler_survives_its_own_send_failing(self):
        # The meta-failure path: responding itself raises. Must log, not raise.
        interaction = _interaction(response_done=False)
        interaction.response.send_message.side_effect = RuntimeError("dead socket")
        with patch("gurps_bot.cogs.error_handler.log") as mock_log:
            await _handler().on_app_command_error(
                interaction, app_commands.AppCommandError("boom")
            )
        meta_calls = [
            c for c in mock_log.exception.call_args_list
            if "handler itself failed" in c.args[0]
        ]
        assert meta_calls, "meta-failure was not logged"
