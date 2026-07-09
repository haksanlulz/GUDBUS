from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BOT_DIR / "data"

DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{(DATA_DIR / 'gurps_bot.db').as_posix()}",
)
def _parse_dev_guild_id(raw: str | None) -> int | None:
    """None on a malformed value — runs at import, before logging is configured, so warn via print instead of crashing."""
    if not raw:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        print(
            f"WARNING: DEV_GUILD_ID={raw!r} is not a valid integer — ignoring it. "
            "Set it to a numeric guild ID or leave it blank."
        )
        return None


DEV_GUILD_ID: int | None = _parse_dev_guild_id(os.getenv("DEV_GUILD_ID"))
SYNC_ON_START: bool = os.getenv("SYNC_ON_START", "").lower() in ("1", "true", "yes")
