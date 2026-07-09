"""Every extension must load into one shared command tree."""

from __future__ import annotations

import discord
from discord.ext import commands

from gurps_bot.bot import EXTENSIONS


# regression: per-cog tests load cogs in isolation, so two cogs claiming the
# same top-level name (two /spell) only collide when the real bot loads them
# all. no connection/db needed — load_extension just runs each setup(bot).
async def test_all_extensions_load_without_command_collision():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    try:
        for ext in EXTENSIONS:
            # raises ExtensionFailed / CommandAlreadyRegistered on a clash
            await bot.load_extension(ext)

        assert len(bot.extensions) == len(EXTENSIONS), "not every extension loaded"

        names = [c.name for c in bot.tree.get_commands()]
        dupes = sorted({n for n in names if names.count(n) > 1})
        assert not dupes, f"duplicate top-level command names across cogs: {dupes}"
    finally:
        await bot.close()
