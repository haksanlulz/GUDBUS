"""/legal and /about — SJG Online Policy notice, credits, privacy."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)

ONLINE_POLICY_URL = "https://www.sjgames.com/general/online_policy.html"
# online policy requires the game aid be attributed to its author
AUTHOR_ENV = "BOT_AUTHOR_LEGAL_NAME"
_AUTHOR_PLACEHOLDER = (
    "[CONFIG REQUIRED: set BOT_AUTHOR_LEGAL_NAME — this notice is NOT "
    "SJG-Online-Policy-compliant until the author's legal name is set]"
)

_INVITE_PLACEHOLDER = "*(invite link not configured — set BOT_INVITE_URL)*"
_SUPPORT_PLACEHOLDER = "*(support link not configured — set BOT_SUPPORT_URL)*"

_LEGAL_COLOR = discord.Color.dark_grey()


def build_legal_embed(
    author: str,
    invite_url: str | None,
    support_url: str | None,
) -> discord.Embed:
    """Build the legal/about embed; pure, no discord runtime or I/O."""
    embed = discord.Embed(
        title="Legal & Credits",
        color=_LEGAL_COLOR,
    )

    # sjg online policy notice — text must stay verbatim, author injected
    notice = (
        "GURPS is a trademark of Steve Jackson Games, and its rules and art "
        "are copyrighted by Steve Jackson Games. All rights are reserved by "
        "Steve Jackson Games. This game aid is the original creation of "
        f"{author} and is released for free distribution, and not for resale, "
        "under the permissions granted in the Steve Jackson Games Online Policy."
    )
    # hyperlink only the final policy-phrase occurrence; sentence text stays verbatim
    linked = notice.rsplit("Steve Jackson Games Online Policy", 1)
    notice_value = (
        f"[Steve Jackson Games Online Policy]({ONLINE_POLICY_URL})".join(linked)
    )
    embed.add_field(name="Steve Jackson Games Online Policy", value=notice_value, inline=False)

    embed.add_field(
        name="Reference Data Credits",
        value=(
            "Reference data is sourced from the GURPS Character Sheet master "
            "library ([richardwilkes/gcs_master_library]"
            "(https://github.com/richardwilkes/gcs_master_library)) by Richard "
            "Wilkes, licensed MPL-2.0. GCS: [gurpscharactersheet.com]"
            "(https://gurpscharactersheet.com)."
        ),
        inline=False,
    )

    embed.add_field(
        name="Trademark",
        value=(
            "GURPS is a registered trademark of Steve Jackson Games. This bot "
            "is *for* GURPS — it is **not official** and is **not endorsed** by "
            "Steve Jackson Games."
        ),
        inline=False,
    )

    embed.add_field(
        name="Privacy",
        value=(
            "This bot **does not read message content** (it runs on default "
            "Discord intents). Keyed to your Discord user ID, it stores data you "
            "create through commands — characters, study logs, notes, timers, "
            "wealth, and combat-tracker participation — plus the Discord server, "
            "channel, and message IDs needed to scope combats, notes, and timers. "
            "Remove an imported character with `/char delete`; guild-scoped data "
            "(combats, notes, timers) is purged when the bot leaves a server; for "
            "anything else, removal is available on request."
        ),
        inline=False,
    )

    invite_text = (
        f"[Add this bot to your server]({invite_url})"
        if invite_url
        else _INVITE_PLACEHOLDER
    )
    support_text = (
        f"[Support / contact]({support_url})" if support_url else _SUPPORT_PLACEHOLDER
    )
    embed.add_field(
        name="Invite & Contact",
        value=f"{invite_text}\n{support_text}",
        inline=False,
    )

    embed.set_footer(text="Released for free distribution under the SJG Online Policy.")
    return embed


def _legal_embed_from_env() -> discord.Embed:
    author = os.getenv(AUTHOR_ENV, _AUTHOR_PLACEHOLDER)
    invite_url = os.getenv("BOT_INVITE_URL") or None
    support_url = os.getenv("BOT_SUPPORT_URL") or None
    return build_legal_embed(author=author, invite_url=invite_url, support_url=support_url)


class LegalCog(commands.Cog):
    "Legal Notice, Credits, and Privacy Information."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="legal",
        description="Legal Notice, Credits, Trademark, and Privacy Information",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def legal(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=_legal_embed_from_env(), ephemeral=True
        )

    @app_commands.command(
        name="about",
        description="About This Bot — Credits, Trademark, and Privacy",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def about(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=_legal_embed_from_env(), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LegalCog(bot))
