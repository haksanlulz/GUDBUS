"""Wallet rows (B265): balance + Status tier per (discord_user_id, character_id); tables live in mechanics/wealth.py."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from gurps_bot.db.models import Base


class Wealth(Base):
    __tablename__ = "wealth"
    # sqlite treats NULL character_id rows as distinct, so this does NOT stop
    # duplicate default wallets — get_wealth's limit(1) is the real guard
    # against the first-touch race; the constraint only covers per-character
    # wallets (and create_all only applies it to fresh DBs)
    __table_args__ = (
        UniqueConstraint("discord_user_id", "character_id", name="uq_wealth_owner"),
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
