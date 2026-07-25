"""Saved dice macros. Names normalize to lowercase; callers own the transaction."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.models import DiceMacro
from gurps_bot.mechanics.dice import parse_dice
from gurps_bot.utils.sanitize import sanitize_name

MAX_NAME_LEN = 50


class InvalidMacroName(ValueError):
    """The name normalizes to nothing usable.

    Subclasses ValueError so existing ``except ValueError`` callers still work,
    but distinguishable — the cog has to tell a bad name from a bad expression.
    """


def normalize_macro_name(name: str) -> str:
    """The stored form of a macro name — the one owner of the naming rule.

    Strips mention/markdown chars, lowercases, caps length. Callers use it to
    echo the key that was really stored instead of re-deriving a near-miss.
    Raises InvalidMacroName if nothing usable survives.
    """
    cleaned = sanitize_name(name).lower()[:MAX_NAME_LEN].strip()
    if not cleaned:
        raise InvalidMacroName(
            "Macro name must contain at least one usable character."
        )
    return cleaned


async def save_macro(
    session: AsyncSession, discord_user_id: int, name: str, expression: str,
) -> DiceMacro:
    """Create or replace a macro; bad dice notation raises so a stored macro always rolls.

    The name is normalized FIRST, so with both arguments bad the caller reports
    the name — that's the actionable half, since the name indexes the row.
    """
    key = normalize_macro_name(name)
    parse_dice(expression)  # validate; raises ValueError on bad notation
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
    """Raises InvalidMacroName for a name that normalizes to nothing — callers
    taking the name from user input must normalize (or catch) up front."""
    stmt = select(DiceMacro).where(
        DiceMacro.discord_user_id == discord_user_id,
        DiceMacro.name == normalize_macro_name(name),
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
