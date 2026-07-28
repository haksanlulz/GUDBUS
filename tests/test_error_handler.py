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
    interaction.response.defer = AsyncMock()
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


# --- Option-value redaction --------------------------------------------------
#
# The diagnostic context goes to the bot's log, a lower trust tier than the
# channel the command came from: /notes add carries a gm_secret flag whose whole
# contract is "visible only to the author", and the log has no such filter.
# Option NAMES are what make an error reproducible; the free-text VALUES are the
# payload.


def _options_interaction(options: list[dict], command_name: str = "notes add"):
    interaction = _interaction(response_done=False)
    interaction.command.name = command_name
    interaction.data = {"options": options}
    return interaction


async def _logged_context(interaction) -> dict:
    """Run the unknown-error branch and return the ctx dict it logged."""
    with patch("gurps_bot.cogs.error_handler.log") as mock_log:
        await _handler().on_app_command_error(
            interaction, app_commands.AppCommandError("boom")
        )
    mock_log.exception.assert_called_once()
    return mock_log.exception.call_args.args[2]


def _opt(ctx: dict, name: str):
    for o in ctx["options"]:
        if o["name"] == name:
            return o
    raise AssertionError(f"option {name!r} not captured: {ctx['options']!r}")


class TestOptionValueRedaction:
    SECRET = (
        "The duke's bastard is the one funding the cult, and the party's "
        "patron already knows it."
    )

    async def test_long_free_text_is_redacted_with_its_length(self):
        interaction = _options_interaction(
            [{"name": "body", "type": 3, "value": self.SECRET}]
        )
        ctx = await _logged_context(interaction)
        assert self.SECRET not in repr(ctx)
        assert "duke" not in repr(ctx)
        assert _opt(ctx, "body")["value"] == f"<redacted str len={len(self.SECRET)}>"

    async def test_short_free_text_option_is_redacted_by_name(self):
        # A length threshold alone lets a short secret through — "he did it"
        # is as secret as three paragraphs of it.
        interaction = _options_interaction(
            [{"name": "body", "type": 3, "value": "he did it"}]
        )
        ctx = await _logged_context(interaction)
        assert "he did it" not in repr(ctx)
        assert _opt(ctx, "body")["value"].startswith("<redacted")

    async def test_nested_subcommand_options_are_reached(self):
        # Group commands nest the real options one level under the subcommand.
        # Reading only the top level logged a single pseudo-option
        # {"name": "add", "value": None} — no leak, but no diagnostic either.
        # Flattening reaches them, so redaction has to as well.
        interaction = _options_interaction([
            {
                "name": "add",
                "type": 1,
                "options": [
                    {"name": "title", "type": 3, "value": "Session 4"},
                    {"name": "body", "type": 3, "value": self.SECRET},
                    {"name": "secret", "type": 5, "value": True},
                ],
            }
        ])
        ctx = await _logged_context(interaction)
        names = [o["name"] for o in ctx["options"]]
        assert names == ["add.title", "add.body", "add.secret"]
        assert self.SECRET not in repr(ctx)
        assert _opt(ctx, "add.secret")["value"] is True

    async def test_short_enum_and_scalar_values_are_kept(self):
        # Debuggability: these are what make an error reproducible and none of
        # them is free text.
        interaction = _options_interaction(
            [
                {"name": "dice", "type": 3, "value": "3d6"},
                {"name": "amount", "type": 4, "value": -5},
                {"name": "location", "type": 3, "value": "torso"},
                {"name": "character_scoped", "type": 5, "value": False},
            ],
            command_name="damage",
        )
        ctx = await _logged_context(interaction)
        assert _opt(ctx, "dice")["value"] == "3d6"
        assert _opt(ctx, "amount")["value"] == -5
        assert _opt(ctx, "location")["value"] == "torso"
        assert _opt(ctx, "character_scoped")["value"] is False

    async def test_unknown_long_value_is_redacted_by_length(self):
        # The denylist can't know every future free-text option name, so a
        # length threshold backstops it.
        blob = "z" * 400
        interaction = _options_interaction(
            [{"name": "somefutureoption", "type": 3, "value": blob}],
            command_name="future",
        )
        ctx = await _logged_context(interaction)
        assert blob not in repr(ctx)
        assert _opt(ctx, "somefutureoption")["value"] == "<redacted str len=400>"

    async def test_option_names_always_survive(self):
        interaction = _options_interaction([
            {"name": "title", "type": 3, "value": self.SECRET},
            {"name": "body", "type": 3, "value": self.SECRET},
            {"name": "tags", "type": 3, "value": "cult,duke"},
        ])
        ctx = await _logged_context(interaction)
        assert [o["name"] for o in ctx["options"]] == ["title", "body", "tags"]

    async def test_meta_failure_path_is_redacted_too(self):
        # The handler's own except branch re-captures context; it has to go
        # through the same redaction or the leak just moves.
        interaction = _options_interaction(
            [{"name": "body", "type": 3, "value": self.SECRET}]
        )
        interaction.response.send_message.side_effect = RuntimeError("dead socket")
        with patch("gurps_bot.cogs.error_handler.log") as mock_log:
            await _handler().on_app_command_error(
                interaction, app_commands.AppCommandError("boom")
            )
        assert self.SECRET not in repr(mock_log.exception.call_args_list)

    async def test_malformed_options_do_not_break_capture(self):
        # Never raise from the diagnostic path — it runs while already handling
        # an error.
        interaction = _options_interaction(
            ["not-a-dict", {"name": "body", "type": 3, "value": self.SECRET}]
        )
        ctx = await _logged_context(interaction)
        assert self.SECRET not in repr(ctx)
        assert _opt(ctx, "body")["value"].startswith("<redacted")
