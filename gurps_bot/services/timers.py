"""Channel-scoped countdown timers (generic math — no GURPS rules content). Callers own the transaction — nothing here commits."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.timers import UNITS, Timer


async def add_timer(
    session: AsyncSession,
    guild_id: int,
    channel_id: int,
    label: str,
    total: int,
    unit: str,
    target: str | None = None,
    note: str = "",
    remaining: int | None = None,
) -> Timer:
    """Create a timer (flushed, not committed); total >= 1 keeps the remaining/total display division safe."""
    if unit not in UNITS:
        raise ValueError("Unknown unit")
    if total < 1:
        raise ValueError("total must be >= 1")

    if remaining is None:
        remaining_value = total
    else:
        remaining_value = max(0, min(remaining, total))

    log.info(
        "Adding timer '%s' (total=%d %s, target=%s) in guild=%d channel=%d",
        label.strip(), total, unit, target, guild_id, channel_id,
    )
    timer = Timer(
        guild_id=guild_id,
        channel_id=channel_id,
        label=label.strip(),
        # strip target (empty -> None) so a padded target still matches what a
        # later tick/list/clear passes (#17) — match sites strip + casefold too
        target=target.strip() if target and target.strip() else None,
        total=total,
        remaining=remaining_value,
        unit=unit,
        note=note,
    )
    session.add(timer)
    await session.flush()
    return timer


async def tick_timers(
    session: AsyncSession,
    guild_id: int,
    channel_id: int,
    unit: str,
    amount: int = 1,
    target: str | None = None,
) -> list[Timer]:
    """Tick matching live timers (units never convert); returns the newly expired — rows are kept, not auto-deleted."""
    if unit not in UNITS:
        raise ValueError("Unknown unit")
    if amount < 1:
        raise ValueError("amount must be a positive integer")

    stmt = (
        select(Timer)
        .where(
            Timer.guild_id == guild_id,
            Timer.channel_id == channel_id,
            Timer.unit == unit,
            Timer.remaining > 0,
        )
        .order_by(Timer.id.asc())
    )
    if target is not None:
        stmt = stmt.where(func.lower(Timer.target) == target.strip().lower())

    result = await session.execute(stmt)
    rows = result.scalars().all()

    expired: list[Timer] = []
    for t in rows:
        new_remaining = max(0, t.remaining - amount)
        t.remaining = new_remaining
        if new_remaining <= 0:
            expired.append(t)

    await session.flush()
    return expired


async def list_timers(
    session: AsyncSession,
    guild_id: int,
    channel_id: int,
    target: str | None = None,
    include_expired: bool = True,
) -> list[Timer]:
    """A channel's timers, soonest-to-expire first."""
    stmt = (
        select(Timer)
        .where(Timer.guild_id == guild_id, Timer.channel_id == channel_id)
        .order_by(Timer.remaining.asc(), Timer.id.asc())
    )
    if target is not None:
        stmt = stmt.where(func.lower(Timer.target) == target.strip().lower())
    if not include_expired:
        stmt = stmt.where(Timer.remaining > 0)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def remove_timer(
    session: AsyncSession,
    guild_id: int,
    channel_id: int,
    timer_id: int,
) -> bool:
    """Delete one timer by id, scoped to the channel — a foreign channel's id deletes nothing."""
    stmt = select(Timer).where(
        Timer.id == timer_id,
        Timer.guild_id == guild_id,
        Timer.channel_id == channel_id,
    )
    result = await session.execute(stmt)
    timer = result.scalar_one_or_none()
    if timer is None:
        return False
    log.info(
        "Removing timer id=%d ('%s') in guild=%d channel=%d",
        timer.id, timer.label, guild_id, channel_id,
    )
    await session.delete(timer)
    return True


async def clear_timers(
    session: AsyncSession,
    guild_id: int,
    channel_id: int,
    target: str | None = None,
    expired_only: bool = False,
) -> int:
    """Bulk-delete a channel's timers; returns rows deleted."""
    stmt = delete(Timer).where(
        Timer.guild_id == guild_id,
        Timer.channel_id == channel_id,
    )
    if target is not None:
        stmt = stmt.where(func.lower(Timer.target) == target.strip().lower())
    if expired_only:
        stmt = stmt.where(Timer.remaining <= 0)

    result = await session.execute(
        stmt.execution_options(synchronize_session=False)
    )
    return result.rowcount
