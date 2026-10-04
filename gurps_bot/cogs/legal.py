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
# The Online Policy notice credits the game aid's author: whoever wrote the code,
# not whoever hosts it. A consistent handle or pen name is fine.
AUTHOR_ENV = "BOT_AUTHOR_NAME"
LEGACY_AUTHOR_ENV = "BOT_AUTHOR_LEGAL_NAME"
DEFAULT_AUTHOR = "haksanlulz"

DEFAULT_PRIVACY_URL = "https://github.com/haksanlulz/GUDBUS/blob/main/PRIVACY.md"
DEFAULT_TERMS_URL = "https://github.com/haksanlulz/GUDBUS/blob/main/TERMS.md"

_INVITE_PLACEHOLDER = "*(invite link not configured — set BOT_INVITE_URL)*"
_SUPPORT_PLACEHOLDER = "*(support link not configured — set BOT_SUPPORT_URL)*"

_LEGAL_COLOR = discord.Color.dark_grey()


def _env(name: str) -> str | None:
    value = (os.getenv(name) or "").strip()
    return value or None


def resolve_author() -> str:
    """BOT_AUTHOR_NAME, else the legacy BOT_AUTHOR_LEGAL_NAME, else the default."""
    return _env(AUTHOR_ENV) or _env(LEGACY_AUTHOR_ENV) or DEFAULT_AUTHOR


def build_legal_embed(
    author: str,
    invite_url: str | None,
    support_url: str | None,
    operator: str | None = None,
    privacy_url: str = DEFAULT_PRIVACY_URL,
    terms_url: str = DEFAULT_TERMS_URL,
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
            "(https://github.com/richardwilkes/gcs_master_library)), compiled by "
            "Richard A. Wilkes and contributors, licensed MPL-2.0. GCS: "
            "[gurpscharactersheet.com]"
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
            "Discord intents). Keyed to your Discord user ID, it stores what you "
            "create through commands: imported characters (including the "
            "uploaded sheet, so `/char export` can return it), macros, notes, "
            "study logs, timers, wealth, crafting projects and combat-tracker "
            "entries, plus the server, channel and message IDs that scope them. "
            "`/char delete` removes a character; `/privacy delete-my-data` "
            "removes everything keyed to you. When the bot leaves a server, that "
            "server's combats, notes, timers, house rules and crafting projects "
            f"are deleted. Full text: [Privacy Policy]({privacy_url}) · "
            f"[Terms]({terms_url})."
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
    contact_lines = [invite_text, support_text]
    if operator:
        contact_lines.append(f"Hosted by {operator}")
    embed.add_field(
        name="Invite & Contact",
        value="\n".join(contact_lines),
        inline=False,
    )

    embed.set_footer(text="Released for free distribution under the SJG Online Policy.")
    return embed


def _legal_embed_from_env() -> discord.Embed:
    return build_legal_embed(
        author=resolve_author(),
        invite_url=_env("BOT_INVITE_URL"),
        support_url=_env("BOT_SUPPORT_URL"),
        operator=_env("BOT_OPERATOR_NAME"),
        privacy_url=_env("BOT_PRIVACY_URL") or DEFAULT_PRIVACY_URL,
        terms_url=_env("BOT_TERMS_URL") or DEFAULT_TERMS_URL,
    )


class LegalCog(commands.Cog):
    "Legal Notice, Credits, and Privacy Information."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="legal",
        description="Legal notice, credits, trademark, and privacy information",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def legal(self, interaction: discord.Interaction[GURPSBot]) -> None:
        await interaction.response.send_message(
            embed=_legal_embed_from_env(), ephemeral=True
        )

    @app_commands.command(
        name="about",
        description="About this bot — credits, trademark, and privacy",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def about(self, interaction: discord.Interaction[GURPSBot]) -> None:
        await interaction.response.send_message(
            embed=_legal_embed_from_env(), ephemeral=True
        )


async def setup(bot: GURPSBot) -> None:
    await bot.add_cog(LegalCog(bot))
