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

# Acknowledge an interaction before touching the database. ON by default since
# 2026-07-29; it shipped off on 2026-07-28 and the day-old reasoning for that is
# kept below, because what changed was the population and not the measurements.
#
# Discord invalidates an un-deferred interaction token after 3 seconds; SQLite
# waits up to busy_timeout (5s) for a write lock. Those are ordered wrong, so a
# contended write can still be succeeding when the token is already dead and
# the user sees "The application did not respond" on a command that worked.
# Deferring moves the ceiling to 15 minutes and retires that whole class.
#
# The cost is that Discord shows "<bot> is thinking..." until the reply lands,
# on every command that defers. At one guild a combat write takes ~10ms and the
# 3-second wall is unreachable, so the flicker is pure cost and no benefit.
#
# Measured, at rising CONCURRENT WRITES (not guild count — 120 guilds is not
# 120 simultaneous writes): slowest write 0.37s at 24, 0.62s at 60, 1.58s at
# 120, where the connection pool starts queueing. Under the deadline, but by
# under 2x at the top and on a workstation SSD rather than the NAS array.
#
# The third of those conditions is what fired. Off was right while every install
# was one known table on known hardware. A published bot runs on hosts nobody
# here has measured — a Pi, an SD card, a shared VPS — and the margin above was
# already under 2x at the top, on a workstation SSD. The trade is asymmetric: the
# cost of deferring is a "thinking..." flicker, and the cost of not deferring is
# a stranger's first contended /attack reporting "The application did not
# respond" on a command that in fact worked, which reads as a broken bot.
#
# CharacterContext has defaulted to deferring since it was written, so until now
# the character commands acknowledged first and the write-heavy combat ones did
# not — the split was an oversight rather than a decision, and this ends it.
#
# Set DEFER_INTERACTIONS=0 to turn it off, which is worth doing on a single-table
# instance on a fast disk: there the 3-second wall is genuinely unreachable
# (~10ms writes) and the flicker buys nothing.
DEFER_INTERACTIONS: bool = _parse_flag(os.getenv("DEFER_INTERACTIONS"), True)
