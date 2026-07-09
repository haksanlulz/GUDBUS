"""/support and /donate cog"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from gurps_bot.cogs.support import (
    SupportCog,
    _safe_url,
    build_support_embed,
    collect_support_links,
)


class TestSafeUrl:
    def test_https_passes(self):
        assert _safe_url("https://ko-fi.com/me") == "https://ko-fi.com/me"

    def test_strips_whitespace_then_validates(self):
        assert _safe_url("  https://ko-fi.com/me  ") == "https://ko-fi.com/me"

    @pytest.mark.parametrize(
        "bad",
        [
            None, "", "   ",
            "http://ko-fi.com/me",            # not https
            "javascript:alert(1)",            # scheme injection
            "data:text/html,<script>",        # data URL
            "ftp://x/y",
            "ko-fi.com/me",                   # no scheme
            "https://x.com/a b",              # embedded space
            "https://x.com/a\nhttps://evil",  # newline smuggling a 2nd link
            "https://x.com/a)more",           # closing paren breaks markdown link
            "https://x.com/a]more",           # closing bracket breaks markdown link
        ],
    )
    def test_rejects_unsafe(self, bad):
        assert _safe_url(bad) is None


class TestCollectLinks:
    def test_collects_only_configured_https_in_order(self):
        env = {
            "PATREON_URL": "https://patreon.com/me",
            "KOFI_URL": "https://ko-fi.com/me",
            "PAYPAL_URL": "http://paypal.me/me",  # http -> dropped
            "GITHUB_SPONSORS_URL": "",            # empty -> dropped
        }
        links = collect_support_links(env)
        # render order follows _PLATFORMS: Ko-fi before Patreon; http/empty dropped
        assert links == [
            ("Ko-fi", "https://ko-fi.com/me"),
            ("Patreon", "https://patreon.com/me"),
        ]

    def test_empty_env_yields_no_links(self):
        assert collect_support_links({}) == []


class TestBuildEmbed:
    def test_renders_each_link_as_markdown(self):
        links = [("Ko-fi", "https://ko-fi.com/me"), ("Patreon", "https://patreon.com/me")]
        embed = build_support_embed(links)
        field = next(f for f in embed.fields if f.name == "Ways to Support")
        assert "[Ko-fi](https://ko-fi.com/me)" in field.value
        assert "[Patreon](https://patreon.com/me)" in field.value

    def test_no_links_shows_friendly_message(self):
        embed = build_support_embed([])
        field = next(f for f in embed.fields if f.name == "Ways to Support")
        assert "share the bot" in field.value.lower()
        # never an empty/placeholder-looking field
        assert field.value.strip()

    def test_message_override(self):
        embed = build_support_embed([], message="custom thanks!")
        assert embed.description == "custom thanks!"

    def test_field_value_capped_at_1024(self):
        # many long links must not blow the Discord 1024 field cap
        links = [(f"Platform{i}", "https://example.com/" + "x" * 60) for i in range(40)]
        embed = build_support_embed(links)
        for f in embed.fields:
            assert len(f.value) <= 1024
        assert embed.title and len(embed.title) <= 256

    def test_has_footer_and_title(self):
        embed = build_support_embed([("Ko-fi", "https://ko-fi.com/me")])
        assert embed.footer.text
        assert "Support" in embed.title


class TestCog:
    def _interaction(self):
        interaction = MagicMock()
        interaction.response.send_message = AsyncMock()
        return interaction

    async def test_support_sends_embed(self):
        cog = SupportCog(bot=MagicMock())
        interaction = self._interaction()
        await cog.support.callback(cog, interaction)
        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.await_args.kwargs
        assert isinstance(kwargs["embed"], discord.Embed)
        # donation prompt is meant to be shareable -> not forced ephemeral
        assert kwargs.get("ephemeral") in (None, False)

    async def test_donate_sends_embed(self):
        cog = SupportCog(bot=MagicMock())
        interaction = self._interaction()
        await cog.donate.callback(cog, interaction)
        kwargs = interaction.response.send_message.await_args.kwargs
        assert isinstance(kwargs["embed"], discord.Embed)
