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

import importlib
import sys

import discord
from discord.ext import commands

from gurps_bot.bot import EXTENSIONS, GURPSBot


def _restore_extension_modules() -> None:
    """Put the cog modules back into sys.modules after closing a bot.

    ``Bot.close()`` unloads every loaded extension, and discord.py's
    ``unload_extension`` does ``sys.modules.pop(key)`` plus the same for each
    submodule. The parent package keeps its attribute, though, still pointing
    at the now-orphaned module object. That split is invisible until something
    patches a cog:

      * ``mock.patch("gurps_bot.cogs.combat.check")`` resolves its target by
        ``getattr`` on the parent package, which succeeds without importing —
        so it patches the orphan;
      * any later ``from gurps_bot.cogs.combat import ...`` misses the cache
        and executes the module afresh, producing a second module object whose
        globals hold the real function;
      * the callback then runs in that second object, and the mock records
        zero calls while the code under test behaves perfectly.

    That cost a session: it presented as a knockdown wiring bug, was declared
    root-cause-unknown, and was worked around by asserting on rendered output.
    Re-importing here restores both the cache and the parent attribute, so a
    patch and a call refer to the same module again.
    """
    for ext in EXTENSIONS:
        importlib.import_module(ext)


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
        _restore_extension_modules()


async def test_closing_the_bot_leaves_the_cog_modules_importable():
    """Regression: closing a bot must not leave the cog modules uncached.

    Without the restore, every module here is popped from sys.modules while
    the parent package still names the orphaned object — and the next test in
    the session that patches a cog attribute patches something the code will
    not execute in. The failure is silent and lands on whichever test happens
    to come first.
    """
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    try:
        for ext in EXTENSIONS:
            await bot.load_extension(ext)
    finally:
        await bot.close()
        _restore_extension_modules()

    missing = [ext for ext in EXTENSIONS if ext not in sys.modules]
    assert not missing, f"not back in sys.modules after close: {missing}"

    # The other half of the split: the parent package must name the SAME
    # object the cache holds, or patch and import still disagree.
    for ext in EXTENSIONS:
        pkg_name, _, leaf = ext.rpartition(".")
        parent = sys.modules[pkg_name]
        assert getattr(parent, leaf) is sys.modules[ext], (
            f"{ext}: parent package attribute and sys.modules disagree"
        )
