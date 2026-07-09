"""Study-log rows (B292-294); aggregation lives in services/study.py."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from gurps_bot.db.models import Base


class StudyLog(Base):
    __tablename__ = "study_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_user_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True
    )
    # SET NULL so study history survives character deletion (falls to the user bucket)
    character_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # free text — study can target skills not yet on the sheet
    skill_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # one of: self_teaching | on_the_job | education | intensive | adventuring
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    # raw hours as entered, uncapped — audit trail
    real_hours: Mapped[float] = mapped_column(Float, nullable=False)
    # post-cap learning hours; the value get_skill_progress SUMs
    learning_hours: Mapped[float] = mapped_column(Float, nullable=False)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
