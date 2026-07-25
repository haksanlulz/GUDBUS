"""Command registration: fingerprint-gated global auto-sync + the rescue path.

Born from the 2026-07-25 escape: /sync's guild default + clear:true left every
registration guild-scoped with the global set deliberately emptied; a kick then
wiped all of them, and the repair tool (/sync) was itself one of the wiped
commands. The redesign is single-scope (global), synced at startup when the
command set actually changed, with a mention-prefixed text command as the
registration-proof rescue channel.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from gurps_bot.cogs.admin import AdminCog
from gurps_bot.command_sync import auto_sync, tree_fingerprint
from gurps_bot.config import _parse_flag


def _tree_with(*names: str) -> app_commands.CommandTree:
    client = discord.Client(intents=discord.Intents.default())
    tree = app_commands.CommandTree(client)
    for n in names:
        @app_commands.command(name=n, description=f"{n} desc")
        async def _cmd(interaction: discord.Interaction) -> None:
            ...
        _cmd.name = n
        tree.add_command(_cmd)
    return tree


class TestFingerprint:
    def test_same_command_set_same_fingerprint(self):
        assert tree_fingerprint(_tree_with("a", "b")) == tree_fingerprint(_tree_with("a", "b"))

    def test_order_of_registration_is_irrelevant(self):
        assert tree_fingerprint(_tree_with("a", "b")) == tree_fingerprint(_tree_with("b", "a"))

    def test_added_command_changes_fingerprint(self):
        assert tree_fingerprint(_tree_with("a")) != tree_fingerprint(_tree_with("a", "b"))

    def test_changed_description_changes_fingerprint(self):
        t1 = _tree_with("a")
        client = discord.Client(intents=discord.Intents.default())
        t2 = app_commands.CommandTree(client)

        @t2.command(name="a", description="different words")
        async def _a(interaction: discord.Interaction) -> None:
            ...

        assert tree_fingerprint(t1) != tree_fingerprint(t2)


class TestAutoSync:
    async def test_first_boot_syncs_and_writes_fingerprint(self, tmp_path):
        tree = _tree_with("a")
        tree.sync = AsyncMock(return_value=[MagicMock()])
        path = tmp_path / ".command_fingerprint"

        assert await auto_sync(tree, path) == "synced"
        tree.sync.assert_awaited_once_with()  # global: no guild kwarg
        assert path.read_text().strip() == tree_fingerprint(tree)

    async def test_unchanged_set_skips_the_api_call(self, tmp_path):
        tree = _tree_with("a")
        tree.sync = AsyncMock(return_value=[])
        path = tmp_path / ".command_fingerprint"
        path.write_text(tree_fingerprint(tree))

        assert await auto_sync(tree, path) == "unchanged"
        tree.sync.assert_not_awaited()

    async def test_changed_set_resyncs(self, tmp_path):
        tree = _tree_with("a", "b")
        tree.sync = AsyncMock(return_value=[MagicMock(), MagicMock()])
        path = tmp_path / ".command_fingerprint"
        path.write_text("stale-fingerprint")

        assert await auto_sync(tree, path) == "synced"
        tree.sync.assert_awaited_once_with()
        assert path.read_text().strip() == tree_fingerprint(tree)

    async def test_failed_sync_keeps_stale_fingerprint_and_does_not_raise(self, tmp_path):
        # a failed sync must retry on the NEXT boot, so the fingerprint stays stale;
        # and it must not kill the boot — the gateway session is still useful
        tree = _tree_with("a")
        tree.sync = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=429), "rate limited"))
        path = tmp_path / ".command_fingerprint"
        path.write_text("stale-fingerprint")

        assert await auto_sync(tree, path) == "failed"
        assert path.read_text().strip() == "stale-fingerprint"


class TestAutoSyncFlag:
    def test_default_is_on(self):
        assert _parse_flag(None, True) is True
        assert _parse_flag("", True) is True

    def test_explicit_off_values(self):
        for raw in ("0", "false", "no", "off", "False", " NO "):
            assert _parse_flag(raw, True) is False, raw

    def test_truthy_values(self):
        for raw in ("1", "true", "yes", "anything-else"):
            assert _parse_flag(raw, True) is True, raw


class TestSlashSyncIsThin:
    def test_signature_has_no_scope_or_clear(self):
        # the scope/clear machinery is the escape's root cause; its absence is the fix
        params = inspect.signature(AdminCog.sync_commands.callback).parameters
        assert "scope" not in params
        assert "clear" not in params

    async def test_owner_gate_refuses_non_owner(self):
        cog = AdminCog(bot=MagicMock())
        interaction = MagicMock()
        interaction.client.is_owner = AsyncMock(return_value=False)
        interaction.response.send_message = AsyncMock()
        interaction.client.tree.sync = AsyncMock()

        await AdminCog.sync_commands.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        interaction.client.tree.sync.assert_not_awaited()

    async def test_owner_forces_a_global_sync(self):
        cog = AdminCog(bot=MagicMock())
        interaction = MagicMock()
        interaction.client.is_owner = AsyncMock(return_value=True)
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.client.tree.sync = AsyncMock(return_value=[MagicMock()])

        await AdminCog.sync_commands.callback(cog, interaction)

        interaction.client.tree.sync.assert_awaited_once_with()


class TestRescueTextCommand:
    def test_exists_and_is_owner_gated(self):
        cmd = AdminCog.sync_rescue
        assert isinstance(cmd, commands.Command)
        assert cmd.name == "sync"
        # is_owner attaches the gate as a check; an ungated rescue would let
        # anyone in the guild re-register commands
        assert cmd.checks

    async def test_default_action_is_global_sync(self):
        cog = AdminCog(bot=MagicMock())
        ctx = MagicMock()
        ctx.bot.tree.sync = AsyncMock(return_value=[MagicMock(), MagicMock()])
        ctx.reply = AsyncMock()

        await AdminCog.sync_rescue.callback(cog, ctx, action=None)

        ctx.bot.tree.sync.assert_awaited_once_with()
        ctx.reply.assert_awaited_once()

    async def test_purge_clears_only_the_invoking_guild(self):
        cog = AdminCog(bot=MagicMock())
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.bot.tree.clear_commands = MagicMock()
        ctx.bot.tree.sync = AsyncMock(return_value=[])
        ctx.reply = AsyncMock()

        await AdminCog.sync_rescue.callback(cog, ctx, action="purge")

        ctx.bot.tree.clear_commands.assert_called_once_with(guild=ctx.guild)
        ctx.bot.tree.sync.assert_awaited_once_with(guild=ctx.guild)

    async def test_purge_outside_a_guild_refuses(self):
        cog = AdminCog(bot=MagicMock())
        ctx = MagicMock()
        ctx.guild = None
        ctx.bot.tree.clear_commands = MagicMock()
        ctx.bot.tree.sync = AsyncMock()
        ctx.reply = AsyncMock()

        await AdminCog.sync_rescue.callback(cog, ctx, action="purge")

        ctx.bot.tree.clear_commands.assert_not_called()
        ctx.bot.tree.sync.assert_not_awaited()


class TestRescueChannelIsRegistrationProof:
    def test_bot_prefix_is_when_mentioned(self):
        # message-content intent is off; mention-prefixed messages are the carve-out
        # Discord still delivers content for, so @<bot> sync works with zero slash
        # commands registered and zero privileged intents
        from gurps_bot.bot import GURPSBot

        bot = GURPSBot()
        assert bot.command_prefix is commands.when_mentioned
