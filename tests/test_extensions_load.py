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

import contextlib
import importlib
import sys

import pytest
import discord
from discord.ext import commands

from gurps_bot.bot import EXTENSIONS, GURPSBot

pytestmark = pytest.mark.integration


def _snapshot_extension_modules() -> dict[str, object]:
    """Capture the cog module objects as they stand right now.

    ⚠️ Capture must happen immediately before the load, NOT at module import.
    This used to be a module-level ``_PRESERVED`` dict built at import time, and
    measured 2026-08-07 it held **zero of eighteen** entries: pytest imports
    every test module during collection, before any test runs, and at that point
    no cog has been imported. So the identity-preserving branch never had
    anything to preserve and every call silently took the re-import fallback
    below — the weaker fix its own docstring warns about. It stayed green only
    because this module runs late enough alphabetically that the objects it
    orphaned were re-imported before anything patched them. A second caller
    earlier in the alphabet is all it took to surface: adding a tree-loading
    test to ``test_conventions`` broke the same nine error-handler tests named
    below, from the same cause, on the fix that was supposed to have closed it.
    """
    return {ext: sys.modules[ext] for ext in EXTENSIONS if ext in sys.modules}


def _restore_extension_modules(snapshot: dict[str, object]) -> None:
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

    ⚠️ This used to re-import, which restores the NAMES but builds NEW module
    objects. That is a weaker fix than it looks: it works only while everything
    downstream consistently uses the new objects, and it breaks the moment a
    second fixture does the same thing — a test that imported a class at
    collection time and then patches by string ends up patching a different
    module than the code runs in. `test_cold_guild` reproduced exactly that in
    nine error-handler tests. Restoring the ORIGINAL objects preserves identity
    and has no such window.
    """
    for ext, module in snapshot.items():
        sys.modules[ext] = module
    for ext in EXTENSIONS:
        # Anything not captured (first load in a process, or a genuinely new
        # extension) still needs an import to exist at all. Nothing held a
        # reference to the popped object in that case, so a fresh one is fine.
        if ext not in sys.modules:
            importlib.import_module(ext)
        # Close the other half of the split explicitly rather than relying on
        # the import machinery to have set it: the parent package attribute and
        # the cache must name the SAME object, or patch-by-string and
        # import-by-name still resolve differently.
        pkg_name, _, leaf = ext.rpartition(".")
        setattr(sys.modules[pkg_name], leaf, sys.modules[ext])


@contextlib.asynccontextmanager
async def loaded_bot():
    """Every extension in ONE bot, with the module cache put back afterwards.

    The snapshot/restore pair only works if the snapshot is taken immediately
    before the load, so the pairing lives here rather than at each call site —
    four fixtures across the suite were open-coding this dance, which is four
    places for the ordering to drift.
    """
    snapshot = _snapshot_extension_modules()
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    try:
        for ext in EXTENSIONS:
            await bot.load_extension(ext)
        yield bot
    finally:
        await bot.close()
        _restore_extension_modules(snapshot)


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
    # loaded_bot() raises ExtensionFailed / CommandAlreadyRegistered on a clash.
    async with loaded_bot() as bot:
        assert len(bot.extensions) == len(EXTENSIONS), "not every extension loaded"

        names = [c.name for c in bot.tree.get_commands()]
        dupes = sorted({n for n in names if names.count(n) > 1})
        assert not dupes, f"duplicate top-level command names across cogs: {dupes}"


async def test_closing_the_bot_leaves_the_cog_modules_importable():
    """Regression: closing a bot must not leave the cog modules uncached.

    Without the restore, every module here is popped from sys.modules while
    the parent package still names the orphaned object — and the next test in
    the session that patches a cog attribute patches something the code will
    not execute in. The failure is silent and lands on whichever test happens
    to come first.
    """
    async with loaded_bot():
        pass

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


async def test_the_snapshot_actually_captures_something():
    """The identity fix must not go inert again.

    It already did once: the snapshot was a module-level dict built at import
    time, and pytest imports every test module during COLLECTION — before any
    cog exists — so it captured 0 of 18 and every restore silently took the
    re-import fallback. Nothing asserted the fix did anything, so the suite
    stayed green for as long as no second caller ran early enough to expose it.

    This pins the capture POINT: a snapshot is only worth taking where the
    modules exist. ``test_module_identity_survives_a_load_close_cycle`` is the
    one that binds ``loaded_bot`` to actually taking it there.
    """
    async with loaded_bot():
        pass

    captured = _snapshot_extension_modules()
    assert len(captured) == len(EXTENSIONS), (
        f"snapshot captured {len(captured)} of {len(EXTENSIONS)} extensions — "
        f"a snapshot taken where nothing is loaded preserves nothing, which is "
        f"exactly how this fix was inert before"
    )


async def test_module_identity_survives_a_load_close_cycle():
    """The property the whole restore exists for, asserted directly.

    ``missing`` and the parent-attribute check above both pass if the modules
    were REBUILT — that is the weaker fix. What downstream tests need is the
    same objects, because they bound references to them at collection time.
    """
    async with loaded_bot():
        pass
    before = {ext: sys.modules[ext] for ext in EXTENSIONS}

    async with loaded_bot():
        pass

    rebuilt = [ext for ext in EXTENSIONS if sys.modules[ext] is not before[ext]]
    assert not rebuilt, (
        f"these cog modules are NEW objects after a load/close cycle: {rebuilt}. "
        f"Any test holding a collection-time reference into them now patches "
        f"one module while the code runs in another."
    )
