from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from gurps_bot.db.models import Base

# no cross-unit conversion — a 'minutes' tick never touches a 'turns' timer
UNITS: tuple[str, ...] = ("turns", "seconds", "minutes", "hours")


class Timer(Base):
    __tablename__ = "timers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 'Haste', 'Bleeding', 'Stunned', ...
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    # NULL = scene-wide / untargeted
    target: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # original duration, immutable; display denominator
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    # expired at <= 0; tick floors at 0
    remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False, default="turns")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    @property
    def expired(self) -> bool:
        return self.remaining <= 0

    @property
    def progress(self) -> float:
        """remaining/total; the 0.0 branch guards display math (add_timer enforces total >= 1)."""
        if self.total > 0:
            return self.remaining / self.total
        return 0.0
