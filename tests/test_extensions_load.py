"""Integration guard: every bot extension must load into ONE command tree.

This is the coverage gap that let a top-level slash-command name-collision ship to
deploy. The per-cog unit tests load each cog in isolation, so two cogs both
registering the same top-level name (calc_magic's `/spell …` calculators vs the
reference `/spell` lookup) only collided when the real bot loaded BOTH into one
`app_commands` tree at startup — surfaced by actually running the bot, not by the
suite. This test reproduces that combined load and asserts:

  * every extension in ``EXTENSIONS`` loads without ``CommandAlreadyRegistered``;
  * no two top-level commands/groups share a name.

It needs no Discord connection and no DB — ``load_extension`` only runs each
module's ``setup(bot)`` (which calls ``add_cog`` → registers the cog's app
commands); the cogs touch the DB / reference catalog lazily at invoke time.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from gurps_bot.bot import EXTENSIONS, GURPSBot


class TestMentionDefaults:
    """Mentions are denied client-wide; only the turn announcement opts back in.

    Sheet-derived text (character names, weapon descriptions) reaches public
    embeds, so a default-allow client would let an imported .gcs ping a role.
    """

    def test_client_default_denies_all_mentions(self):
        # Construction only — no gateway connection, nothing to tear down.
        bot = GURPSBot()
        assert bot.allowed_mentions.everyone is False
        assert bot.allowed_mentions.users is False
        assert bot.allowed_mentions.roles is False

    def test_turn_announcement_still_opts_into_user_pings(self):
        # The per-message value overrides the client default, so the deny above
        # must not silence the "your turn" ping (combat-automation slice 5).
        import inspect

        from gurps_bot.ui import views

        src = inspect.getsource(views.CombatTrackerView.next_turn_btn)
        assert "AllowedMentions(users=True)" in src


async def test_all_extensions_load_without_command_collision():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    try:
        for ext in EXTENSIONS:
            # Raises ExtensionFailed / CommandAlreadyRegistered on a name clash.
            await bot.load_extension(ext)

        assert len(bot.extensions) == len(EXTENSIONS), "not every extension loaded"

        names = [c.name for c in bot.tree.get_commands()]
        dupes = sorted({n for n in names if names.count(n) > 1})
        assert not dupes, f"duplicate top-level command names across cogs: {dupes}"
    finally:
        await bot.close()
