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
def _parse_flag(raw: str | None, default: bool) -> bool:
    """Env boolean with a real default: unset/blank -> default, only explicit
    negatives turn it off."""
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


# Fingerprint-gated global command registration at startup. On by default:
# registration is deploy behavior, not a chat command (an in-Discord /sync
# cannot fix a bot whose commands are gone — 2026-07-25 escape).
AUTO_SYNC: bool = _parse_flag(os.getenv("AUTO_SYNC"), True)

# Written only after a successful global sync; lives in the data volume so a
# container recreate keeps it and an image with a changed command set re-syncs.
COMMAND_FINGERPRINT_PATH = DATA_DIR / ".command_fingerprint"
