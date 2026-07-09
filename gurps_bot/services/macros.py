"""Saved dice macros. Names normalize to lowercase; callers own the transaction."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.models import DiceMacro
from gurps_bot.mechanics.dice import parse_dice
from gurps_bot.utils.sanitize import sanitize_name

MAX_NAME_LEN = 50


def _norm(name: str) -> str:
    # strip mention/markdown chars and cap length — the name is echoed into public replies
    cleaned = sanitize_name(name).lower()[:MAX_NAME_LEN].strip()
    if not cleaned:
        raise ValueError("Macro name must contain at least one usable character.")
    return cleaned


async def save_macro(
    session: AsyncSession, discord_user_id: int, name: str, expression: str,
) -> DiceMacro:
    """Create or replace a macro; bad dice notation raises so a stored macro always rolls."""
    parse_dice(expression)  # validate; raises ValueError on bad notation
    key = _norm(name)
    existing = await get_macro(session, discord_user_id, key)
    if existing is not None:
        existing.expression = expression
        return existing
    macro = DiceMacro(discord_user_id=discord_user_id, name=key, expression=expression)
    session.add(macro)
    return macro


async def get_macro(
    session: AsyncSession, discord_user_id: int, name: str,
) -> DiceMacro | None:
    stmt = select(DiceMacro).where(
        DiceMacro.discord_user_id == discord_user_id,
        DiceMacro.name == _norm(name),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_macros(
    session: AsyncSession, discord_user_id: int,
) -> list[DiceMacro]:
    stmt = (
        select(DiceMacro)
        .where(DiceMacro.discord_user_id == discord_user_id)
        .order_by(DiceMacro.name)
    )
    return list((await session.execute(stmt)).scalars().all())


async def delete_macro(
    session: AsyncSession, discord_user_id: int, name: str,
) -> bool:
    existing = await get_macro(session, discord_user_id, name)
    if existing is None:
        return False
    await session.delete(existing)
    return True
