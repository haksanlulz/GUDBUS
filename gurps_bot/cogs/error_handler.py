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


def _interaction_context(interaction: discord.Interaction) -> dict[str, object]:
    """Best-effort log context from an interaction; never raises."""
    ctx: dict[str, object] = {}
    try:
        ctx["user_id"] = getattr(interaction.user, "id", None)
        ctx["guild_id"] = interaction.guild_id
        ctx["channel_id"] = getattr(interaction.channel, "id", None)
        ctx["command"] = interaction.command.name if interaction.command else None
        # names + simple values only; Member/Role/Channel objects bloat logs and can leak
        if interaction.data and isinstance(interaction.data, dict):
            opts = interaction.data.get("options") or []
            ctx["options"] = [
                {"name": o.get("name"), "value": o.get("value")}
                for o in opts
                if isinstance(o, dict)
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
            if isinstance(error, app_commands.CheckFailure):
                msg = "You don't have permission to use this command."
            elif isinstance(error, app_commands.CommandOnCooldown):
                # round up, floor at 1; never tell the user to wait "0s"
                wait = max(1, math.ceil(error.retry_after))
                msg = f"Command on cooldown. Try again in {wait}s."
            elif isinstance(error, app_commands.MissingPermissions):
                missing = ", ".join(error.missing_permissions)
                msg = f"Missing permissions: {missing}"
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
