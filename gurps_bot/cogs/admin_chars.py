"""Owner tools: /admin — another member's imported characters.

The host sometimes has to do a member's sheet work for them (an NPC set imported under
the GM's account, a stale sheet removed from a phone-only player). These act on the
same services /char does, with the target user and, optionally, the server supplied as
parameters. Bot owner only; the group is hidden from members by default permissions
and the owner check runs on every call regardless.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

from gurps_bot.cogs.characters import import_sheet
from gurps_bot.services.characters import (
    delete_character,
    get_active_character,
    get_character_by_name,
    get_user_characters,
    set_active_character,
)
from gurps_bot.services.wealth import WalletOverflow
from gurps_bot.ui import embeds
from gurps_bot.ui.views import ConfirmView
from gurps_bot.utils.scope import guild_id_of

log = logging.getLogger(__name__)


async def _owner_only(interaction: discord.Interaction[GURPSBot]) -> bool:
    if await interaction.client.is_owner(interaction.user):
        return True
    await interaction.response.send_message(
        "Only the bot owner can use /admin commands.", ephemeral=True
    )
    return False


async def _target_guild(
    interaction: discord.Interaction[GURPSBot], guild_id: str | None
) -> int | None:
    """The server whose active-character pointer is meant: this one unless an id is given."""
    if guild_id is None or not guild_id.strip():
        return guild_id_of(interaction)
    text = guild_id.strip()
    if not text.isdigit():
        await interaction.response.send_message(
            "`guild_id` must be a server id (digits only).", ephemeral=True
        )
        return None
    return int(text)


@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
class AdminGroup(commands.GroupCog, group_name="admin"):
    "Bot owner tools."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.command(name="list", description="List a member's imported characters (owner)")
    @app_commands.describe(user="The member", guild_id="Server id for the active mark; this server if blank")
    async def list_chars(
        self, interaction: discord.Interaction[GURPSBot], user: discord.User,
        guild_id: str | None = None,
    ) -> None:
        if not await _owner_only(interaction):
            return
        gid = await _target_guild(interaction, guild_id)
        if gid is None:
            return
        await interaction.response.defer(ephemeral=True)
        async with interaction.client.db() as session:
            chars = await get_user_characters(session, user.id)
            active = await get_active_character(session, user.id, gid)
            active_id = active.id if active else None
        embed = embeds.char_list_embed([(c.name, c.total_points, c.id == active_id) for c in chars])
        embed.title = f"Characters of {user.display_name}"
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="import", description="Import a .gcs file as a member's character (owner)")
    @app_commands.describe(
        user="The member it belongs to", file="A .gcs character sheet file",
        guild_id="Server where it becomes their active character; this server if blank",
    )
    async def import_char(
        self, interaction: discord.Interaction[GURPSBot], user: discord.User,
        file: discord.Attachment, guild_id: str | None = None,
    ) -> None:
        if not await _owner_only(interaction):
            return
        gid = await _target_guild(interaction, guild_id)
        if gid is None:
            return
        log.warning("admin: owner %s imports a sheet for user %s in guild %s",
                    interaction.user.id, user.id, gid)
        await import_sheet(
            interaction, file, user_id=user.id, guild_id=gid, for_whom=f" for {user.mention}",
        )

    @app_commands.command(name="switch", description="Set a member's active character (owner)")
    @app_commands.describe(
        user="The member", name="Their character's name (exact)",
        guild_id="Server for the active mark; this server if blank",
    )
    async def switch(
        self, interaction: discord.Interaction[GURPSBot], user: discord.User, name: str,
        guild_id: str | None = None,
    ) -> None:
        if not await _owner_only(interaction):
            return
        gid = await _target_guild(interaction, guild_id)
        if gid is None:
            return
        async with interaction.client.db() as session:
            char = await get_character_by_name(session, user.id, name)
            if not char:
                await interaction.response.send_message(
                    f"{user.mention} has no character named **{name}**.", ephemeral=True
                )
                return
            await set_active_character(session, user.id, gid, char.id)
            await session.commit()
        log.warning("admin: owner %s switched the active character of user %s in guild %s",
                    interaction.user.id, user.id, gid)
        await interaction.response.send_message(
            f"Switched {user.mention} to **{name}**.", ephemeral=True
        )

    @app_commands.command(name="delete", description="Delete a member's imported character (owner)")
    @app_commands.describe(user="The member", name="Their character's name (exact)")
    async def delete_char(
        self, interaction: discord.Interaction[GURPSBot], user: discord.User, name: str,
    ) -> None:
        if not await _owner_only(interaction):
            return
        async with interaction.client.db() as session:
            char = await get_character_by_name(session, user.id, name)
        if not char:
            await interaction.response.send_message(
                f"{user.mention} has no character named **{name}**.", ephemeral=True
            )
            return

        view = ConfirmView(author_id=interaction.user.id)
        await interaction.response.send_message(
            f"Delete **{name}** ({char.total_points} pts) belonging to {user.mention}? "
            "This cannot be undone.",
            view=view, ephemeral=True,
        )
        view.message = await interaction.original_response()
        await view.wait()
        if not view.confirmed:
            return

        async with interaction.client.db() as session:
            try:
                deleted = await delete_character(session, char.id)
            except WalletOverflow as e:
                await interaction.followup.send(str(e), ephemeral=True)
                return
            if deleted:
                await session.commit()
        if deleted:
            log.warning("admin: owner %s deleted a character of user %s",
                        interaction.user.id, user.id)
            await interaction.followup.send(f"Deleted **{name}** for {user.mention}.", ephemeral=True)
        else:
            await interaction.followup.send("Nothing deleted; it may already be gone.", ephemeral=True)


async def setup(bot: GURPSBot) -> None:
    await bot.add_cog(AdminGroup(bot))
