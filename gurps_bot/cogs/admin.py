"""Admin cog: /sync, /status, guild cleanup."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot
from sqlalchemy import delete, func, select

from gurps_bot.db.models import ActiveCharacter, Character, Combat, Combatant
from gurps_bot.db.notes import Note
from gurps_bot.db.timers import Timer

log = logging.getLogger(__name__)


async def cleanup_guild_data(session, guild_id: int) -> None:
    """Purge a departed guild's rows; characters etc. are user-scoped and stay. Caller commits."""
    # Combatant has no guild_id and bulk delete(Combat) won't fire the cascade
    # (sqlite fk enforcement off), so clear combatants first or they dangle
    guild_combats = select(Combat.id).where(Combat.guild_id == guild_id)
    await session.execute(delete(Combatant).where(Combatant.combat_id.in_(guild_combats)))
    for model in (ActiveCharacter, Combat, Note, Timer):
        await session.execute(delete(model).where(model.guild_id == guild_id))


class AdminCog(commands.Cog):
    "Bot Administration Commands."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.command(name="sync", description="Sync Slash Commands (Bot Owner Only)")
    @app_commands.describe(
        scope="Where to register: 'guild' = this server (instant), 'global' = all servers (~1h)",
        clear="Also clear the OTHER scope first — fixes doubled-up commands",
    )
    @app_commands.choices(scope=[
        app_commands.Choice(name="This Guild (Instant)", value="guild"),
        app_commands.Choice(name="Global (All Servers, ~1h)", value="global"),
    ])
    async def sync_commands(
        self,
        interaction: discord.Interaction,
        scope: str = "guild",
        clear: bool = False,
    ) -> None:
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message(
                "Only the bot owner can sync commands.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        tree = interaction.client.tree
        messages: list[str] = []

        if scope == "guild":
            if not interaction.guild_id:
                await interaction.followup.send(
                    "Guild sync must be run inside a server."
                )
                return
            target = discord.Object(id=interaction.guild_id)
            tree.copy_global_to(guild=target)
            synced = await tree.sync(guild=target)
            messages.append(f"Synced {len(synced)} commands to this guild.")
            if clear:
                # clear_commands(guild=None) empties the tree's global set for the
                # whole process, not just at Discord; save/re-add it or the next
                # /sync global pushes an empty set and wipes commands everywhere
                saved = list(tree.get_commands(guild=None))
                tree.clear_commands(guild=None)
                await tree.sync()  # empty global at Discord = drops the duplicates
                for cmd in saved:
                    tree.add_command(cmd)
                messages.append("Cleared duplicate global commands.")
        else:  # global
            if clear and interaction.guild_id:
                guild_target = discord.Object(id=interaction.guild_id)
                tree.clear_commands(guild=guild_target)
                await tree.sync(guild=guild_target)
                messages.append("Cleared this guild's commands (de-duplicated).")
            synced = await tree.sync()
            messages.append(
                f"Synced {len(synced)} commands globally (may take up to 1 hour)."
            )

        await interaction.followup.send(" ".join(messages))

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
            char_count = await session.scalar(select(func.count(Character.id)))
            combat_count = await session.scalar(select(func.count(Combat.id)))
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
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        async with self.bot.db() as session:
            await cleanup_guild_data(session, guild.id)
            await session.commit()
        log.info("Cleaned up guild-scoped data for guild %s (%s)", guild.name, guild.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
