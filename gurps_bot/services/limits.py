"""Row-count caps on everything a user can create, in one place.

Characters have been capped at 20 per user since early on. Notes, macros,
timers and study logs were not capped at all, which was fine while the only
people who could reach them were at the operator's own table. A public bot
changes who "a user" is: unbounded rows from strangers land on the operator's
own disk, and SQLite on a NAS array is where they land.

These are engineering caps, not GURPS numbers, and they are set well above any
plausible real use — the goal is to bound abuse, not to ration. A player who
hits one of these is doing something the bot was not built for, and gets a
message saying so rather than a silent failure.

Kept together rather than one per service so the whole storage surface can be
read at once, and so `tests/test_storage_caps.py` can assert every user-writable
table has one.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

#: A character sheet import. Predates this module; named here for completeness.
MAX_CHARACTERS_PER_USER = 20

#: Notes are per user per guild. A campaign's worth of session notes is dozens.
MAX_NOTES_PER_USER_PER_GUILD = 250

#: Dice shorthand. A heavily-optimised character has a handful.
MAX_MACROS_PER_USER = 100

#: Timers are channel-scoped GM furniture; more than this is not a table, it is
#: a stress test.
MAX_TIMERS_PER_CHANNEL = 50

#: Study logs are an append-only journal, so this is the one that a legitimate
#: long campaign could eventually approach. Set high, and note that the failure
#: mode is a refusal to add rather than losing history.
MAX_STUDY_LOGS_PER_USER = 1000

# Deliberately NOT capped: note body length.
#
# Storage is uncapped and only the *display* is truncated — that is a design
# decision from 2026-07-12, and `test_trackers_caps` pins it. A cap was tried
# here and reverted: Discord's own input limits already bound a single
# submission (~4000 chars via a modal), so the marginal bytes saved are small,
# and the cost is silently cutting the end off a GM's session notes. The row
# caps above address the actual vector, which is row count rather than row size.


class StorageLimitExceeded(Exception):
    """A user hit a row cap. Message is user-facing — say what and how many."""


async def enforce_row_cap(
    session: AsyncSession,
    model,
    cap: int,
    what: str,
    **filters,
) -> None:
    """Raise if creating one more row would exceed `cap`.

    Counts rather than tracking a running total: a count is always right, and a
    denormalised counter is one more thing to keep true through deletes.
    """
    stmt = select(func.count()).select_from(model)
    for column, value in filters.items():
        stmt = stmt.where(getattr(model, column) == value)
    current = await session.scalar(stmt)
    if current is not None and current >= cap:
        raise StorageLimitExceeded(
            f"You have {current} {what} (maximum {cap}). Delete some first."
        )
