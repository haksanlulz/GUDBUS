"""hidden rolls go ephemeral; raw-number targets + guild_id None skip the db"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


def _interaction(*, guild_id=None):
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _cog():
    from gurps_bot.cogs.rolling import RollingCog

    return RollingCog(bot=MagicMock())


class TestRollHidden:
    async def test_roll_hidden_is_ephemeral(self):
        cog, interaction = _cog(), _interaction()
        await cog.roll_dice.callback(cog, interaction, dice="3d6", hidden=True)
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True

    async def test_roll_default_is_public(self):
        cog, interaction = _cog(), _interaction()
        await cog.roll_dice.callback(cog, interaction, dice="3d6")
        assert interaction.response.send_message.await_args.kwargs.get("ephemeral") in (None, False)


class TestCheckHidden:
    async def test_check_hidden_is_ephemeral(self):
        cog, interaction = _cog(), _interaction()
        await cog.check_roll.callback(cog, interaction, target="10", modifier=0, hidden=True)
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True

    async def test_check_default_is_public(self):
        cog, interaction = _cog(), _interaction()
        await cog.check_roll.callback(cog, interaction, target="10")
        assert interaction.response.send_message.await_args.kwargs.get("ephemeral") in (None, False)


class TestFrightCheckHidden:
    async def test_fright_hidden_is_ephemeral(self):
        cog, interaction = _cog(), _interaction(guild_id=None)
        await cog.fright_check.callback(cog, interaction, modifier=0, hidden=True)
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True

    async def test_fright_default_is_public(self):
        cog, interaction = _cog(), _interaction(guild_id=None)
        await cog.fright_check.callback(cog, interaction)
        assert interaction.response.send_message.await_args.kwargs.get("ephemeral") in (None, False)


class TestDamageHidden:
    async def test_damage_hidden_is_ephemeral(self):
        cog, interaction = _cog(), _interaction()
        await cog.damage_roll.callback(cog, interaction, dice="2d", damage_type="cr", hidden=True)
        assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True

    async def test_damage_default_is_public(self):
        cog, interaction = _cog(), _interaction()
        await cog.damage_roll.callback(cog, interaction, dice="2d", damage_type="cr")
        assert interaction.response.send_message.await_args.kwargs.get("ephemeral") in (None, False)


class TestContestHidden:
    """contest defers first, then sends via followup — both must carry the flag"""

    async def test_contest_hidden_is_ephemeral(self):
        cog, interaction = _cog(), _interaction()
        await cog.contest_roll.callback(cog, interaction, target_a="10", target_b="12", hidden=True)
        assert interaction.response.defer.await_args.kwargs.get("ephemeral") is True
        assert interaction.followup.send.await_args.kwargs["ephemeral"] is True

    async def test_contest_default_is_public(self):
        cog, interaction = _cog(), _interaction()
        await cog.contest_roll.callback(cog, interaction, target_a="10", target_b="12")
        assert interaction.response.defer.await_args.kwargs.get("ephemeral") in (None, False)
        assert interaction.followup.send.await_args.kwargs.get("ephemeral") in (None, False)
