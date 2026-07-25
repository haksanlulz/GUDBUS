from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)

# Option names whose values are user free text. Redacted regardless of length: a
# length threshold alone would pass "he did it" straight into the log, and a
# gm_secret note's title is exactly as secret as its body.
_FREE_TEXT_OPTIONS = frozenset({
    "body", "text", "content", "note", "notes", "title", "description", "desc",
    "detail", "details", "summary", "comment", "reason", "message", "msg",
    "query", "search", "tags",
})

# Any OTHER string longer than this is treated as free text — the denylist can't
# know every option a future cog adds. Enum values, dice notation, character and
# skill names, and snowflake IDs all sit well under it.
_MAX_LOGGED_VALUE_LEN = 50

# Option types that carry nested options instead of a value:
# 1 = SUB_COMMAND, 2 = SUB_COMMAND_GROUP.
_SUBCOMMAND_TYPES = frozenset({1, 2})


def _redact_value(name: str, value: object) -> object:
    """A log-safe stand-in for one option value.

    Kept verbatim: non-strings, and short strings not on the free-text denylist.
    Everything else becomes a placeholder carrying type + length — enough to tell
    "empty" from "the user pasted 4KB" without reproducing the content.
    """
    if not isinstance(value, str):
        return value
    if name.lower() in _FREE_TEXT_OPTIONS or len(value) > _MAX_LOGGED_VALUE_LEN:
        return f"<redacted str len={len(value)}>"
    return value


def _flatten_options(
    options: object, prefix: str = "",
) -> list[tuple[str, object]]:
    """Flatten raw interaction options to (dotted_name, value) leaves.

    Group commands nest their real options one or two levels under the subcommand
    entry, so a top-level-only read saw a single pseudo-option {"name": "add",
    "value": None} — no diagnostic at all for every grouped command in the bot.
    Descending is what makes the log useful, and also what puts note bodies in
    reach, hence _redact_value.
    """
    leaves: list[tuple[str, object]] = []
    for o in options if isinstance(options, list) else []:
        if not isinstance(o, dict):
            continue
        name = f"{prefix}{o.get('name')}"
        nested = o.get("options")
        if o.get("type") in _SUBCOMMAND_TYPES or (nested and "value" not in o):
            leaves.extend(_flatten_options(nested, prefix=f"{name}."))
        else:
            leaves.append((name, o.get("value")))
    return leaves


def _interaction_context(interaction: discord.Interaction) -> dict[str, object]:
    """Best-effort log context from an interaction; never raises.

    Option NAMES are what make an error reproducible and are always kept; free-text
    VALUES are redacted — the bot log is a lower trust tier than the channel a
    command came from, and a gm_secret note has no "author only" guarantee there.
    """
    ctx: dict[str, object] = {}
    try:
        ctx["user_id"] = getattr(interaction.user, "id", None)
        ctx["guild_id"] = interaction.guild_id
        ctx["channel_id"] = getattr(interaction.channel, "id", None)
        ctx["command"] = interaction.command.name if interaction.command else None
        # names + redacted values only; Member/Role/Channel objects bloat logs and can leak
        if interaction.data and isinstance(interaction.data, dict):
            ctx["options"] = [
                {"name": name, "value": _redact_value(name, value)}
                for name, value in _flatten_options(interaction.data.get("options"))
            ]
    except Exception:  # pragma: no cover — defensive only
        ctx["context_capture_failed"] = True
    return ctx


class ErrorHandler(commands.Cog):
    """Global app-command error handler."""

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot
        # attached in __init__ so reload_extension re-hooks tree.on_error
        self.bot.tree.on_error = self.on_app_command_error

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        try:
            # most-specific first: CommandOnCooldown and MissingPermissions
            # both subclass CheckFailure — a CheckFailure-first chain swallows
            # them into the generic permission message
            if isinstance(error, app_commands.CommandOnCooldown):
                # round up, floor at 1; never tell the user to wait "0s"
                wait = max(1, math.ceil(error.retry_after))
                msg = f"Command on cooldown. Try again in {wait}s."
            elif isinstance(error, app_commands.MissingPermissions):
                missing = ", ".join(error.missing_permissions)
                msg = f"Missing permissions: {missing}"
            elif isinstance(error, app_commands.CheckFailure):
                msg = "You don't have permission to use this command."
            elif isinstance(error, app_commands.TransformerError):
                msg = f"Invalid input: {error}"
            else:
                # capture context before responding; the send below can fail
                ctx = _interaction_context(interaction)
                cmd_name = ctx.get("command") or "unknown"
                log.exception(
                    "Unhandled command error in /%s — context=%r",
                    cmd_name, ctx, exc_info=error,
                )
                msg = "Something went wrong. The error has been logged."

            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            # responding itself broke; still log the interaction details
            log.exception(
                "Error handler itself failed — context=%r",
                _interaction_context(interaction),
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ErrorHandler(bot))
