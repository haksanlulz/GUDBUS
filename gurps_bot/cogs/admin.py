"""Admin cog: /sync, /status, guild cleanup."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

from gurps_bot.services.admin import cleanup_guild_data
from gurps_bot.services.characters import count_characters
from gurps_bot.services.combat import count_combats

log = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    "Bot Administration Commands."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    # Registration is single-scope (global) and normally happens at startup,
    # fingerprint-gated (command_sync.auto_sync). This is the manual force.
    # The old scope/clear machinery is gone on purpose: guild+clear left every
    # registration guild-scoped with the global set emptied, so one kick wiped
    # all commands with no in-Discord way back (2026-07-25 escape).
    @app_commands.command(
        name="sync", description="Force a global slash-command re-register (Bot Owner Only)"
    )
    async def sync_commands(self, interaction: discord.Interaction) -> None:
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message(
                "Only the bot owner can sync commands.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        synced = await interaction.client.tree.sync()
        await interaction.followup.send(f"Synced {len(synced)} commands globally.")

    # The rescue channel. Mention-prefixed text command, so it works with ZERO
    # slash commands registered (a wiped registration cannot take it down) and
    # no message-content intent (mentions are the content carve-out).
    #   @<bot> sync         -> global re-register
    #   @<bot> sync purge   -> clear THIS guild's guild-scoped registrations
    #                          (de-dupes leftovers from the old guild-scope era)
    @commands.command(name="sync", help="@<bot> sync [purge] — registration rescue (owner)")
    @commands.is_owner()
    async def sync_rescue(self, ctx: commands.Context, action: str | None = None) -> None:
        tree = ctx.bot.tree
        if action == "purge":
            if ctx.guild is None:
                await ctx.reply("purge runs inside a server.")
                return
            tree.clear_commands(guild=ctx.guild)
            await tree.sync(guild=ctx.guild)
            await ctx.reply(
                "Cleared this server's guild-scoped commands (global set untouched)."
            )
            return
        synced = await tree.sync()
        await ctx.reply(f"Synced {len(synced)} commands globally.")

    @app_commands.command(name="status", description="Bot Status and Diagnostics")
    async def status(self, interaction: discord.Interaction) -> None:
        import sys
        from datetime import datetime, timezone

        import discord as discord_lib

        bot = interaction.client
        now = datetime.now(timezone.utc)
        uptime = now - bot.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        embed = discord.Embed(title="Bot Status", color=discord.Color.blue())
        embed.add_field(name="Guilds", value=str(len(bot.guilds)), inline=True)
        embed.add_field(
            name="Latency", value=f"{bot.latency * 1000:.0f}ms", inline=True
        )
        embed.add_field(
            name="Uptime", value=f"{hours}h {minutes}m {seconds}s", inline=True
        )
        embed.add_field(
            name="Python", value=f"{sys.version_info.major}.{sys.version_info.minor}", inline=True
        )
        embed.add_field(
            name="discord.py", value=discord_lib.__version__, inline=True
        )

        async with bot.db() as session:
            char_count = await count_characters(session)
            combat_count = await count_combats(session)
        embed.add_field(name="Characters", value=str(char_count), inline=True)
        embed.add_field(name="Active Combats", value=str(combat_count), inline=True)

        # 85056 = minimum permission bits for the invite
        app_id = bot.application_id
        if app_id:
            invite = f"https://discord.com/oauth2/authorize?client_id={app_id}&permissions=85056&scope=bot+applications.commands"
            embed.add_field(name="Invite", value=f"[Add to server]({invite})", inline=False)

        embed.set_footer(
            text=(
                "GURPS is a trademark of Steve Jackson Games, and its rules and art "
                "are copyrighted by Steve Jackson Games. All rights are reserved by "
                "Steve Jackson Games. This game aid is not official and is not endorsed "
                "by Steve Jackson Games. Released for free distribution under the "
                "SJG Online Policy."
            )
        )
        # Ephemeral: /status is a diagnostic the caller runs for themselves, and
        # it reports uptime, latency, guild count and an invite link. None of
        # that is table content, so posting it publicly only adds noise to a
        # play channel (operator ruling 2026-07-27).
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        async with self.bot.db() as session:
            await cleanup_guild_data(session, guild.id)
            await session.commit()
        log.info("Cleaned up guild-scoped data for guild %s (%s)", guild.name, guild.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
