"""README claims that can rot are pinned to the artifacts they describe.

The headline said "94 slash commands" while the tree served 97 — nothing
coupled the number to the tree, so it aged silently every time a command
landed. The count definition is _tree_descriptions' (top-level commands plus
one level of group subcommands), the same enumeration /help audits itself
against.
"""

from __future__ import annotations

import re
from pathlib import Path

import discord
import pytest_asyncio
from discord.ext import commands

from gurps_bot.bot import EXTENSIONS
from gurps_bot.cogs.help import _tree_descriptions

README = Path(__file__).resolve().parent.parent / "README.md"


@pytest_asyncio.fixture
async def tree():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    try:
        for ext in EXTENSIONS:
            await bot.load_extension(ext)
        yield bot.tree
    finally:
        await bot.close()
        # Bot.close() pops cog modules out of sys.modules; restore the same
        # objects (see test_extensions_load._restore_extension_modules).
        from tests.test_extensions_load import _restore_extension_modules

        _restore_extension_modules()


async def test_readme_command_count_matches_the_live_tree(tree):
    live = len(_tree_descriptions(tree))
    text = README.read_text(encoding="utf-8")
    m = re.search(r"(\d+) slash commands", text)
    assert m, "README no longer states the slash-command count"
    stated = int(m.group(1))
    assert stated == live, (
        f"README says {stated} slash commands, the tree serves {live} — "
        "update the README headline."
    )
