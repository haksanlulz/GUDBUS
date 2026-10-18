"""Owner tools: `@<bot> admin ...` — another member's imported characters.

The host sometimes has to do a member's sheet work for them (an NPC set imported under
the GM's account, a stale sheet removed for a phone-only player). These act on the same
services /char does, with the member and, optionally, the server given as arguments.

Mention-prefixed text commands rather than slash commands on purpose: Discord shows a
slash command to everyone its permissions allow and cannot hide one by identity, so an
owner-only slash entry is clutter in every member's picker. A text command registers
nothing with Discord; it is owner-gated by ``commands.is_owner`` and, like ``@<bot> sync``,
needs no message-content intent (a message that mentions the bot carries its content).

    @<bot> admin list @member [server-id]
    @<bot> admin import @member [server-id]      (the .gcs attached to the same message)
    @<bot> admin switch @member [server-id] <name>
    @<bot> admin delete @member <name>

Replies are ordinary messages in the channel the owner typed in.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

from gurps_bot.cogs.characters import precheck_upload, read_sheet, store_sheet
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

log = logging.getLogger(__name__)

USAGE = (
    "`@bot admin list @member [server-id]` · `@bot admin import @member [server-id]` with the "
    "`.gcs` attached · `@bot admin switch @member [server-id] <name>` · "
    "`@bot admin delete @member <name>`"
)


def _guild_for(ctx: commands.Context, guild_id: int | None) -> int | None:
    """The server whose active-character pointer is meant: the given id, else this server."""
    if guild_id is not None:
        return guild_id
    return ctx.guild.id if ctx.guild is not None else None


class AdminCharsCog(commands.Cog):
    "Owner tools for another member's sheets (mention-prefixed; owner only)."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @commands.group(name="admin", invoke_without_command=True, help="@<bot> admin ... (owner)")
    @commands.is_owner()
    async def admin(self, ctx: commands.Context) -> None:
        await ctx.reply(USAGE)

    @admin.command(name="list")
    @commands.is_owner()
    async def admin_list(
        self, ctx: commands.Context, user: discord.User, guild_id: int | None = None,
    ) -> None:
        gid = _guild_for(ctx, guild_id)
        if gid is None:
            await ctx.reply("Give a server id when running this outside a server.")
            return
        async with ctx.bot.db() as session:
            chars = await get_user_characters(session, user.id)
            active = await get_active_character(session, user.id, gid)
            active_id = active.id if active else None
        embed = embeds.char_list_embed([(c.name, c.total_points, c.id == active_id) for c in chars])
        embed.title = f"Characters of {user.display_name}"
        await ctx.reply(embed=embed)

    @admin.command(name="import")
    @commands.is_owner()
    async def admin_import(
        self, ctx: commands.Context, user: discord.User, guild_id: int | None = None,
    ) -> None:
        gid = _guild_for(ctx, guild_id)
        if gid is None:
            await ctx.reply("Give a server id when running this outside a server.")
            return
        if not ctx.message.attachments:
            await ctx.reply("Attach the `.gcs` file to the same message.")
            return
        file = ctx.message.attachments[0]
        refusal = precheck_upload(file)
        if refusal:
            await ctx.reply(refusal)
            return
        got = await read_sheet(file, user.id)
        if isinstance(got, str):
            await ctx.reply(got)
            return
        parsed, data = got
        log.warning("admin: owner %s imports a sheet for user %s in guild %s", ctx.author.id, user.id, gid)
        async with ctx.bot.db() as session:
            stored = await store_sheet(
                session, user_id=user.id, guild_id=gid, parsed=parsed, data=data,
                filename=file.filename,
            )
        if isinstance(stored, str):
            await ctx.reply(stored)
            return
        text, embed = stored
        await ctx.reply(f"{text} for {user.mention}.", embed=embed)

    @admin.command(name="switch")
    @commands.is_owner()
    async def admin_switch(
        self, ctx: commands.Context, user: discord.User, guild_id: int | None = None, *, name: str,
    ) -> None:
        gid = _guild_for(ctx, guild_id)
        if gid is None:
            await ctx.reply("Give a server id when running this outside a server.")
            return
        async with ctx.bot.db() as session:
            char = await get_character_by_name(session, user.id, name)
            if not char:
                await ctx.reply(f"{user.mention} has no character named **{name}**.")
                return
            await set_active_character(session, user.id, gid, char.id)
            await session.commit()
        log.warning("admin: owner %s switched the active character of user %s in guild %s",
                    ctx.author.id, user.id, gid)
        await ctx.reply(f"Switched {user.mention} to **{name}**.")

    @admin.command(name="delete")
    @commands.is_owner()
    async def admin_delete(self, ctx: commands.Context, user: discord.User, *, name: str) -> None:
        async with ctx.bot.db() as session:
            char = await get_character_by_name(session, user.id, name)
        if not char:
            await ctx.reply(f"{user.mention} has no character named **{name}**.")
            return

        view = ConfirmView(author_id=ctx.author.id)
        view.message = await ctx.reply(
            f"Delete **{name}** ({char.total_points} pts) belonging to {user.mention}? "
            "This cannot be undone.",
            view=view,
        )
        await view.wait()
        if not view.confirmed:
            return

        async with ctx.bot.db() as session:
            try:
                deleted = await delete_character(session, char.id)
            except WalletOverflow as e:
                await ctx.reply(str(e))
                return
            if deleted:
                await session.commit()
        if deleted:
            log.warning("admin: owner %s deleted a character of user %s", ctx.author.id, user.id)
            await ctx.reply(f"Deleted **{name}** for {user.mention}.")
        else:
            await ctx.reply("Nothing deleted; it may already be gone.")


async def setup(bot: GURPSBot) -> None:
    await bot.add_cog(AdminCharsCog(bot))
