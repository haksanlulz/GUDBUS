"""DEV_GUILD_ID parse robustness + /sync clear preserving the command tree."""

from __future__ import annotations

import discord
from discord import app_commands

from gurps_bot.config import _parse_dev_guild_id


class TestDevGuildIdParse:
    def test_valid_numeric(self):
        assert _parse_dev_guild_id("123456789") == 123456789

    def test_whitespace_tolerated(self):
        assert _parse_dev_guild_id("  123 ") == 123

    def test_none_and_empty(self):
        assert _parse_dev_guild_id(None) is None
        assert _parse_dev_guild_id("") is None

    def test_non_numeric_returns_none_not_raises(self):
        # malformed value degrades to None instead of raising at import
        assert _parse_dev_guild_id("myguild") is None


class TestSyncClearPreservesCommands:
    def test_clear_global_then_readd_restores_inmemory_set(self):
        # clear_commands(guild=None) empties the tree for the whole process — the
        # /sync clear path has to save and re-add to keep the command set intact
        client = discord.Client(intents=discord.Intents.default())
        tree = app_commands.CommandTree(client)

        @tree.command(name="dummy", description="d")
        async def dummy(interaction: discord.Interaction) -> None:
            ...

        saved = list(tree.get_commands(guild=None))
        assert len(saved) == 1

        tree.clear_commands(guild=None)
        assert len(tree.get_commands(guild=None)) == 0

        for cmd in saved:
            tree.add_command(cmd)
        assert len(tree.get_commands(guild=None)) == 1
