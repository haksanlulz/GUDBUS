from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gurps_bot.db.models import Base

#: Where a project currently sits. The first four are B473-474's stages; the
#: last two are ends rather than stages, and are stored in the same column so a
#: project has exactly one status and no way to be both.
STAGES = ("concept", "prototype", "testing", "production")
ENDINGS = ("abandoned", "complete")

#: What a charge bought. Kept as data rather than three columns because the
#: three figures must never be summed into one — a ledger of typed rows keeps
#: them addable only on purpose.
CHARGE_KINDS = ("facilities", "attempt", "copy", "rebuild")


class CraftingProject(Base):
    """An invention in progress, across sessions.

    B473-474 projects run in real campaign time — a Complex prototype is 1d
    months per attempt — so the interesting state is not a single roll but
    what has accumulated: which stage, how long, how much, and whether the GM
    is sitting on a flawed theory the player must not be told about.
    """

    __tablename__ = "crafting_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    guild_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    character_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Which crafting domain's rules govern this project. Invention is the only
    #: one implemented; the column exists because alchemy, repair, enchantment
    #: and mundane crafting disagree with it on nearly every rule, so a project
    #: that does not say which domain it belongs to cannot be resolved later.
    domain: Mapped[str] = mapped_column(String(32), nullable=False, default="invention")
    complexity: Mapped[str] = mapped_column(String(16), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False, default="concept")

    skill: Mapped[int] = mapped_column(Integer, nullable=False)
    retail_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: The situation flags and GM bonuses that produced the modifier, so a
    #: project resumed weeks later shows the same breakdown rather than a bare
    #: number nobody can argue with.
    modifiers_json: Mapped[dict] = mapped_column(JSON, default=dict)

    #: ⚠️ GM-only. B473 makes the Concept roll secret precisely so this can be
    #: true without the player knowing: the project advances, looks healthy, and
    #: can never produce a prototype. Never render this to a channel.
    flawed_theory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    elapsed_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    major_bugs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minor_bugs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    charges: Mapped[list[CraftingCharge]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="CraftingCharge.id",
    )

    @property
    def is_finished(self) -> bool:
        return self.stage in ENDINGS


class CraftingCharge(Base):
    """One spend, with what it bought.

    A running total would lose the half that matters. B474's three figures have
    different payers and triggers, and the money is spent whether or not the
    roll worked — so a charge row carries its outcome, and the pair is written
    in one transaction before anything is said to the user.

    The precedent is in this repo: 2026-07-29, `hp_cmd` committed an HP change
    before replying, the reply path broke, and the damage had landed while the
    user was told the command failed. At $500,000 a prototype attempt, being
    told an attempt failed while the money is already gone is the same bug with
    a worse blast radius.
    """

    __tablename__ = "crafting_charges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("crafting_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The roll this spend bought, if it bought one. None for facilities, which
    #: are paid up front and buy the right to roll at all.
    outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    project: Mapped[CraftingProject] = relationship(back_populates="charges")
