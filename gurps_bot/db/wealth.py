"""Wallet rows (B265): balance + Status tier per (discord_user_id, character_id); tables live in mechanics/wealth.py."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from gurps_bot.db.models import Base


class Wealth(Base):
    __tablename__ = "wealth"
    # uq_wealth_owner covers per-character wallets only: SQLite treats two NULL
    # character_ids as distinct. The partial index covers the default wallet,
    # so a first-touch race cannot leave a second one whose money get_wealth
    # (oldest row only) would never show.
    __table_args__ = (
        UniqueConstraint("discord_user_id", "character_id", name="uq_wealth_owner"),
        Index(
            "uq_wealth_default",
            "discord_user_id",
            unique=True,
            sqlite_where=text("character_id IS NULL"),
            postgresql_where=text("character_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # discord snowflakes exceed 32-bit
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # NULL = the user's default wallet; SET NULL so deleting a character keeps
    # the money row
    character_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    # negative = debt (GM's problem); float is fine, table values are round integers
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # status tier -2..8, drives cost_of_living; default 0 = Average
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
