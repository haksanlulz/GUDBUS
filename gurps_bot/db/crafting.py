from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class ProjectVocabulary:
    """One domain's persistence vocabulary: its live stages, in order; what a
    charge can buy; and what `/craft work` logs, if the domain has a calendar.

    Shared SHAPE, per-domain DATA — the line `ModifierBreakdown` draws for the
    rules. Five domains disagree on nearly every rule, and they
    disagree here too: repair has no calendar because an attempt is its clock,
    alchemy has a stage invention lacks (the pending disaster roll), and no two
    charge-kind lists are the same.
    """

    domain: str
    stages: tuple[str, ...]
    charge_kinds: tuple[str, ...]
    progress_unit: str | None


INVENTION = ProjectVocabulary("invention", STAGES, CHARGE_KINDS, "days")
#: LTC3 ch. 5 — materials up front, hours logged, one roll for quality.
CRAFTING = ProjectVocabulary("crafting", ("working",), ("materials", "roll"), "hours")
#: Magic ch. 28 — ingredients up front, the calendar, one roll; a critical
#: failure parks the batch at `disaster` until the second roll is made.
ALCHEMY = ProjectVocabulary(
    "alchemy", ("brewing", "disaster"), ("ingredients", "roll"), "weeks"
)
#: Magic pp. 16-18 — Slow and Sure logs mage-days; the ceremonial roll ends it.
ENCHANTMENT = ProjectVocabulary("enchantment", ("enchanting",), ("materials", "casting"), "days")
#: B484 — spare parts first for a major repair, then half-hour attempts.
REPAIR = ProjectVocabulary("repair", ("parts", "repairing"), ("parts", "attempt"), None)

VOCABULARIES: dict[str, ProjectVocabulary] = {
    v.domain: v for v in (INVENTION, CRAFTING, ALCHEMY, ENCHANTMENT, REPAIR)
}


class CraftingProject(Base):
    """A crafting project in progress, across sessions.

    B473-474 projects run in real campaign time — a Complex prototype is 1d
    months per attempt — so the interesting state is not a single roll but
    what has accumulated: which stage, how long, how much, and whether the GM
    is sitting on a flawed theory the player must not be told about. Since
    2026-09-25 the other four domains live on this table too: ``domain`` says
    whose vocabulary applies, and ``state_json`` holds that domain's own
    figures. The typed columns below ``retail_price`` are invention's.
    """

    __tablename__ = "crafting_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    guild_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    character_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Which crafting domain's rules govern this project — a key of
    #: ``VOCABULARIES``. The column exists because alchemy, repair, enchantment
    #: and mundane crafting disagree with invention on nearly every rule, so a
    #: project that does not say which domain it belongs to cannot be resolved.
    domain: Mapped[str] = mapped_column(String(32), nullable=False, default="invention")
    #: B473's rating. Invention's alone, and NULL for every other domain —
    #: nullable since b6c2d9e4f1a7, because a domain-specific string stored here
    #: would be a naming lie.
    complexity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stage: Mapped[str] = mapped_column(String(16), nullable=False, default="concept")

    skill: Mapped[int] = mapped_column(Integer, nullable=False)
    retail_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: The situation flags and GM bonuses that produced the modifier, so a
    #: project resumed weeks later shows the same breakdown rather than a bare
    #: number nobody can argue with.
    modifiers_json: Mapped[dict] = mapped_column(JSON, default=dict)

    #: A non-invention project's own figures, progress and result, in the shape
    #: its ``services/crafting_<domain>.py`` module owns — never read across
    #: domains. NULL for invention, which keeps its typed columns. Reassigned
    #: whole on every change (a JSON column does not track in-place mutation).
    state_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

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
