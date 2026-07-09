"""/support and /donate — operator-configured donation links."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Mapping

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)

_SUPPORT_COLOR = discord.Color.magenta()

# (env var, label) per platform; list order is render order
_PLATFORMS: tuple[tuple[str, str], ...] = (
    ("KOFI_URL", "Ko-fi"),
    ("BUYMEACOFFEE_URL", "Buy Me a Coffee"),
    ("PATREON_URL", "Patreon"),
    ("GITHUB_SPONSORS_URL", "GitHub Sponsors"),
    ("PAYPAL_URL", "PayPal"),
    ("LIBERAPAY_URL", "Liberapay"),
)

SUPPORT_MESSAGE_ENV = "SUPPORT_MESSAGE"

_DEFAULT_MESSAGE = (
    "This bot is free and always will be. If it adds something to your game and "
    "you'd like to chip in toward hosting costs, it's genuinely appreciated — "
    "and never expected."
)

_NO_LINKS_VALUE = (
    "No donation links are set up yet. The best support right now costs nothing: "
    "share the bot with your group, report bugs, and suggest features."
)

_FOOTER = "Thank you! — the bot never handles payments; links go to the platforms."

# discord field-value hard cap
_FIELD_CAP = 1024


def _safe_url(url: str | None) -> str | None:
    """None unless url is a clean https:// link (kills http/javascript/data and whitespace)."""
    if not url:
        return None
    u = url.strip()
    if not u.lower().startswith("https://"):
        return None
    if any(c.isspace() for c in u):
        return None
    # ) or ] would break the markdown link
    if ")" in u or "]" in u:
        return None
    return u


def collect_support_links(env: Mapping[str, str] | None = None) -> list[tuple[str, str]]:
    """Return (label, url) for each configured https-valid platform; env param overrides os.environ for tests."""
    source: Mapping[str, str] = os.environ if env is None else env
    links: list[tuple[str, str]] = []
    for var, label in _PLATFORMS:
        url = _safe_url(source.get(var))
        if url:
            links.append((label, url))
    return links


def build_support_embed(
    links: list[tuple[str, str]],
    message: str | None = None,
) -> discord.Embed:
    """Render the support embed; pure, no discord runtime or I/O."""
    embed = discord.Embed(
        title="Support GURPS Bot",
        description=(message or _DEFAULT_MESSAGE),
        color=_SUPPORT_COLOR,
    )
    if links:
        lines = [f"[{label}]({url})" for label, url in links]
        value = "\n".join(lines)
        if len(value) > _FIELD_CAP:
            value = value[:_FIELD_CAP]
        embed.add_field(name="Ways to Support", value=value, inline=False)
    else:
        embed.add_field(name="Ways to Support", value=_NO_LINKS_VALUE, inline=False)
    embed.set_footer(text=_FOOTER)
    return embed


def _support_embed_from_env() -> discord.Embed:
    message = os.getenv(SUPPORT_MESSAGE_ENV) or None
    return build_support_embed(collect_support_links(), message=message)


class SupportCog(commands.Cog):
    "Support the bot — donation and contribution links."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="support",
        description="Ways to support the bot (donation links + how to help)",
    )
    @app_commands.checks.cooldown(2, 10.0)
    async def support(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=_support_embed_from_env())

    @app_commands.command(
        name="donate",
        description="Donation links to support the bot's hosting",
    )
    @app_commands.checks.cooldown(2, 10.0)
    async def donate(self, interaction: discord.Interaction) -> None:
        # same embed as /support, intentional
        await interaction.response.send_message(embed=_support_embed_from_env())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SupportCog(bot))
