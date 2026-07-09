"""Discord bot class and startup."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gurps_bot.config import DEV_GUILD_ID, DISCORD_TOKEN, SYNC_ON_START
from gurps_bot.db.engine import dispose_engine, init_db, init_engine

if TYPE_CHECKING:
    from gurps_bot.services.reference import ReferenceLookup

log = logging.getLogger(__name__)

EXTENSIONS = [
    "gurps_bot.cogs.error_handler",
    "gurps_bot.cogs.admin",
    "gurps_bot.cogs.characters",
    "gurps_bot.cogs.rolling",
    "gurps_bot.cogs.combat",
    "gurps_bot.cogs.calc_combat",
    "gurps_bot.cogs.calc_movement",
    "gurps_bot.cogs.calc_character",
    "gurps_bot.cogs.calc_magic",
    "gurps_bot.cogs.trackers",
    "gurps_bot.cogs.gmscreen",
    "gurps_bot.cogs.body_ref",
    "gurps_bot.cogs.legal",
    "gurps_bot.cogs.support",
    "gurps_bot.cogs.reference",
    "gurps_bot.cogs.macros",
]


class GURPSBot(commands.Bot):
    db: async_sessionmaker[AsyncSession]
    start_time: datetime
    # built in setup_hook; cogs read it as bot.reference
    reference: "ReferenceLookup"

    def __init__(self) -> None:
        intents = discord.Intents.default()
        # user text (macro/npc/note names) is echoed into public replies; never let it ping
        super().__init__(
            command_prefix="",
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.start_time = datetime.now(timezone.utc)

    async def setup_hook(self) -> None:
        self.db = init_engine()
        log.info("Initializing database...")
        await init_db()

        from gurps_bot.services.reference import get_reference_index

        # first call walks the vendored library (~179ms); keep it off the loop
        self.reference = await asyncio.to_thread(get_reference_index)
        skills = len(self.reference.names("skills"))
        spells = len(self.reference.names("spells"))
        if skills or spells:
            log.info("Reference catalog loaded: %d skills, %d spells", skills, spells)
        else:
            log.warning(
                "Reference catalog is EMPTY — run tools/sync_gcs_library.py to "
                "vendor the GCS master library snapshot."
            )

        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                log.info("Loaded extension: %s", ext)
            except Exception:
                log.exception("Failed to load extension: %s", ext)

        from gurps_bot.ui.tracker import get_tracker_view
        self.add_view(get_tracker_view())

        # SJG Online Policy: /legal + /about need a real author name
        import os
        if not os.getenv("BOT_AUTHOR_LEGAL_NAME"):
            log.warning(
                "BOT_AUTHOR_LEGAL_NAME is not set — /legal and /about will show a "
                "PLACEHOLDER instead of a legal name, which is NOT compliant with "
                "the SJG Online Policy. Set it in .env before any public use."
            )

        if DEV_GUILD_ID and SYNC_ON_START:
            guild = discord.Object(id=DEV_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Dev-synced %d commands to guild %s", len(synced), DEV_GUILD_ID)

        log.info("Bot is ready.")

    async def on_ready(self) -> None:
        log.info(
            "Logged in as %s (ID: %s)",
            self.user,
            self.user.id if self.user else "?",
        )

    async def close(self) -> None:
        log.info("Shutting down — disposing database engine...")
        await dispose_engine()
        await super().close()


def run_bot() -> None:
    import logging.handlers

    from gurps_bot.config import DATA_DIR

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

    file_handler = logging.handlers.RotatingFileHandler(
        DATA_DIR / "gurps_bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    console_handler = logging.StreamHandler()

    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[file_handler, console_handler],
    )

    if not DISCORD_TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN not set. Copy .env.example to .env and add your token."
        )

    bot = GURPSBot()
    bot.run(DISCORD_TOKEN, log_handler=None)
