"""Wallet persistence — the money math lives in mechanics.wealth (B265). Callers own the transaction — nothing here commits."""

from __future__ import annotations

import logging
import math

log = logging.getLogger(__name__)

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.wealth import Wealth
from gurps_bot.mechanics.wealth import cost_of_living


def _require_finite(value: float, label: str) -> float:
    """SQLite stores inf as REAL and binds nan as NULL — a non-finite value would brick the wallet, so reject it here."""
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number.")
    return value


async def get_wealth(
    session: AsyncSession,
    discord_user_id: int,
    character_id: int | None = None,
) -> Wealth | None:
    """Wallet row for (user, character_id), or None; character_id None is the default wallet."""
    # limit(1): NULL character_id rows are distinct under UNIQUE, so a first-touch
    # race can leave duplicate default-wallet rows — without the cap,
    # scalar_one_or_none raises MultipleResultsFound on every later wallet command
    stmt = (
        select(Wealth)
        .where(
            Wealth.discord_user_id == discord_user_id,
            Wealth.character_id == character_id,
        )
        .order_by(Wealth.id)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_or_create_wealth(
    session: AsyncSession,
    discord_user_id: int,
    character_id: int | None = None,
) -> Wealth:
    """Existing wallet row, or a fresh zero-balance one (flushed, not committed)."""
    existing = await get_wealth(session, discord_user_id, character_id)
    if existing is not None:
        return existing

    log.info(
        "Creating wallet for user=%d character_id=%s", discord_user_id, character_id
    )
    wealth = Wealth(
        discord_user_id=discord_user_id,
        character_id=character_id,
        balance=0.0,
        status=0,
    )
    session.add(wealth)
    await session.flush()
    # first-touch race: uq_wealth_owner rejects a duplicate per-character wallet
    # (one transient error, retry finds the winner); duplicate default wallets are
    # defused by get_wealth's limit(1)
    return wealth


async def set_balance(
    session: AsyncSession,
    discord_user_id: int,
    balance: float,
    character_id: int | None = None,
) -> Wealth:
    """Absolute balance overwrite (GM correction); creates the row on first touch."""
    _require_finite(balance, "Balance")
    w = await get_or_create_wealth(session, discord_user_id, character_id)
    w.balance = float(balance)
    return w


async def adjust_balance(
    session: AsyncSession,
    discord_user_id: int,
    delta: float,
    character_id: int | None = None,
) -> Wealth:
    """Add a signed delta to the balance; debt allowed, no clamp."""
    _require_finite(delta, "Amount")
    w = await get_or_create_wealth(session, discord_user_id, character_id)
    # atomic UPDATE — the old `w.balance += delta` read-modify-write dropped one
    # of two concurrent adjusts
    await session.execute(
        update(Wealth)
        .where(Wealth.id == w.id)
        .values(balance=Wealth.balance + float(delta))
    )
    await session.refresh(w)
    # two huge-but-finite values can still sum to inf — reject it so the rollback
    # keeps the prior balance instead of persisting "$inf" forever
    if not math.isfinite(w.balance):
        raise ValueError(
            "That change would overflow the wallet balance — use a smaller amount."
        )
    return w


async def set_status(
    session: AsyncSession,
    discord_user_id: int,
    status: int,
    character_id: int | None = None,
) -> Wealth:
    """Set the wallet's Status tier (drives cost-of-living upkeep)."""
    # cost_of_living raises on a bad tier — validate before any row is created/mutated
    cost_of_living(status)
    w = await get_or_create_wealth(session, discord_user_id, character_id)
    w.status = int(status)
    return w


async def apply_cost_of_living(
    session: AsyncSession,
    discord_user_id: int,
    character_id: int | None = None,
    living_status: int | None = None,
) -> Wealth:
    """Deduct a month's upkeep (B265) at living_status — you may live above or below your stored Status, which is left unchanged."""
    w = await get_or_create_wealth(session, discord_user_id, character_id)
    effective_status = w.status if living_status is None else int(living_status)
    # validate + price the tier before touching balance — no partial deduct on a bad override
    cost = cost_of_living(effective_status)
    # atomic decrement — same race as adjust_balance
    await session.execute(
        update(Wealth)
        .where(Wealth.id == w.id)
        .values(balance=Wealth.balance - cost)
    )
    await session.refresh(w)
    return w
