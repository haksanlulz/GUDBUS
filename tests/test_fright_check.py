"""/fright-check procedure (cogs/rolling.py).

B360, verified against the printed Basic Set:
  1. Roll vs Will — with the Rule of 14: modified Will above 13 is reduced to 13
     for the check, so a roll of 14+ always fails (Fright Checks only).
  2. On a failure, roll 3d, ADD the margin of failure, and consult the Fright
     Check Table (4-40+).

Rolling vs uncapped Will, or feeding the bare margin into the table, are both
wrong. These drive the real callback with a patched check / roll_3d6 so every
branch is deterministic. guild_id=None routes to the no-character path (Will 10),
so no DB is needed — same harness as test_rolling_hidden.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from gurps_bot.mechanics.checks import CheckResult, _determine_outcome
from gurps_bot.mechanics.dice import DiceSpec, RollResult
from gurps_bot.mechanics.tables import FRIGHT_CHECK_TABLE, fright_table_effect


def _interaction():
    interaction = MagicMock()
    interaction.guild_id = None
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    return interaction


def _cog():
    from gurps_bot.cogs.rolling import RollingCog

    return RollingCog(bot=MagicMock())


def _check_result(rolled: int, target: int) -> CheckResult:
    """Deterministic CheckResult through the real outcome engine."""
    rr = RollResult(spec=DiceSpec(3, 6, 0), dice=(rolled,), total=rolled)
    return CheckResult(
        roll_result=rr,
        target=target,
        margin=target - rolled,
        outcome=_determine_outcome(rolled, target),
    )


def _fright_roll(total: int) -> RollResult:
    return RollResult(spec=DiceSpec(3, 6, 0), dice=(total,), total=total)


def _sent_embed(interaction):
    return interaction.response.send_message.await_args.kwargs["embed"]


def _field(embed, name):
    for f in embed.fields:
        if f.name == name:
            return f.value
    return None


class TestRuleOf14:
    async def test_modified_will_above_13_is_capped(self):
        # Will 10 (no character) + 6 = 16 -> capped to 13 before the roll.
        cog, interaction = _cog(), _interaction()
        with patch(
            "gurps_bot.cogs.rolling.check", return_value=_check_result(7, 13)
        ) as mock_check:
            await cog.fright_check.callback(cog, interaction, modifier=6)
        mock_check.assert_called_once_with(13, 0)

    async def test_modified_will_at_or_below_13_is_untouched(self):
        cog, interaction = _cog(), _interaction()
        with patch(
            "gurps_bot.cogs.rolling.check", return_value=_check_result(7, 12)
        ) as mock_check:
            await cog.fright_check.callback(cog, interaction, modifier=2)
        mock_check.assert_called_once_with(12, 0)

    async def test_negative_modifier_passes_through(self):
        cog, interaction = _cog(), _interaction()
        with patch(
            "gurps_bot.cogs.rolling.check", return_value=_check_result(7, 7)
        ) as mock_check:
            await cog.fright_check.callback(cog, interaction, modifier=-3)
        mock_check.assert_called_once_with(7, 0)

    async def test_capped_check_is_labelled(self):
        cog, interaction = _cog(), _interaction()
        with patch("gurps_bot.cogs.rolling.check", return_value=_check_result(7, 13)):
            await cog.fright_check.callback(cog, interaction, modifier=6)
        embed = _sent_embed(interaction)
        assert "Rule of 14" in (embed.title or "")

    async def test_uncapped_check_is_not_labelled(self):
        cog, interaction = _cog(), _interaction()
        with patch("gurps_bot.cogs.rolling.check", return_value=_check_result(7, 10)):
            await cog.fright_check.callback(cog, interaction, modifier=0)
        embed = _sent_embed(interaction)
        assert "Rule of 14" not in (embed.title or "")


class TestFrightRollComposition:
    async def test_failure_rolls_3d_plus_margin(self):
        # Fail by 3 (16 vs 13); fright roll 10 -> total 13 -> that row.
        cog, interaction = _cog(), _interaction()
        with (
            patch("gurps_bot.cogs.rolling.check", return_value=_check_result(16, 13)),
            patch(
                "gurps_bot.cogs.rolling.roll_3d6", return_value=_fright_roll(10)
            ) as mock_3d,
        ):
            await cog.fright_check.callback(cog, interaction, modifier=6)
        mock_3d.assert_called_once()
        effect = _field(_sent_embed(interaction), "Effect")
        assert effect is not None
        assert "13" in effect
        assert fright_table_effect(13) in effect

    async def test_huge_total_reads_the_40_plus_row(self):
        # Fail by 25 (never plausible with the cap in place, but the row has to
        # hold): fright roll 18 -> total 43 -> the 40+ row.
        cog, interaction = _cog(), _interaction()
        with (
            patch("gurps_bot.cogs.rolling.check", return_value=_check_result(16, -9)),
            patch("gurps_bot.cogs.rolling.roll_3d6", return_value=_fright_roll(18)),
        ):
            await cog.fright_check.callback(cog, interaction, modifier=-19)
        effect = _field(_sent_embed(interaction), "Effect")
        assert fright_table_effect(43) in effect
        assert FRIGHT_CHECK_TABLE[40] in effect

    async def test_success_rolls_no_fright_dice(self):
        cog, interaction = _cog(), _interaction()
        with (
            patch("gurps_bot.cogs.rolling.check", return_value=_check_result(7, 10)),
            patch("gurps_bot.cogs.rolling.roll_3d6") as mock_3d,
        ):
            await cog.fright_check.callback(cog, interaction, modifier=0)
        mock_3d.assert_not_called()
        assert _field(_sent_embed(interaction), "Effect") is None
