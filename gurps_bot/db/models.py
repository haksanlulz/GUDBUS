"""Core ORM tables plus the shared declarative Base."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (
        UniqueConstraint("discord_user_id", "name", name="uq_user_character"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # stable .gcs sheet id so a renamed sheet re-imports in place instead of
    # duplicating; NULL on pre-column imports until a re-import backfills it
    gcs_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True, default=None)
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    profile_json: Mapped[dict] = mapped_column(JSON, default=dict)
    calc_json: Mapped[dict] = mapped_column(JSON, default=dict)
    equipment_json: Mapped[list] = mapped_column(JSON, default=list)
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_gcs_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_filename: Mapped[str] = mapped_column(String(300), default="")
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    attributes: Mapped[list[Attribute]] = relationship(
        back_populates="character", cascade="all, delete-orphan"
    )
    skills: Mapped[list[Skill]] = relationship(
        back_populates="character", cascade="all, delete-orphan"
    )
    spells: Mapped[list[Spell]] = relationship(
        back_populates="character", cascade="all, delete-orphan"
    )
    traits: Mapped[list[Trait]] = relationship(
        back_populates="character", cascade="all, delete-orphan"
    )
    active_selections: Mapped[list[ActiveCharacter]] = relationship(
        back_populates="character", cascade="all, delete-orphan"
    )


class ActiveCharacter(Base):
    __tablename__ = "active_characters"
    __table_args__ = (
        UniqueConstraint("discord_user_id", "guild_id", name="uq_user_guild_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )

    character: Mapped[Character] = relationship(back_populates="active_selections")


class Attribute(Base):
    __tablename__ = "attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attr_id: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[float] = mapped_column(Float, default=10)
    current: Mapped[float | None] = mapped_column(Float, nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=0)

    character: Mapped[Character] = relationship(back_populates="attributes")


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    specialization: Mapped[str | None] = mapped_column(String(200), nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="")
    level: Mapped[int] = mapped_column(Integer, default=0)
    relative_level: Mapped[str] = mapped_column(String(20), default="")
    points: Mapped[int] = mapped_column(Integer, default=0)
    defaults_json: Mapped[list] = mapped_column(JSON, default=list)

    character: Mapped[Character] = relationship(back_populates="skills")

    @property
    def display_name(self) -> str:
        if self.specialization:
            return f"{self.name} ({self.specialization})"
        return self.name


class Spell(Base):
    __tablename__ = "spells"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    college: Mapped[str] = mapped_column(String(200), default="")
    difficulty: Mapped[str] = mapped_column(String(20), default="")
    level: Mapped[int] = mapped_column(Integer, default=0)
    relative_level: Mapped[str] = mapped_column(String(20), default="")
    points: Mapped[int] = mapped_column(Integer, default=0)
    casting_cost: Mapped[str] = mapped_column(String(100), default="")
    maintenance_cost: Mapped[str] = mapped_column(String(100), default="")
    casting_time: Mapped[str] = mapped_column(String(100), default="")
    duration: Mapped[str] = mapped_column(String(100), default="")
    spell_class: Mapped[str] = mapped_column(String(50), default="")

    character: Mapped[Character] = relationship(back_populates="spells")


class Trait(Base):
    __tablename__ = "traits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    group_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags_json: Mapped[list] = mapped_column(JSON, default=list)
    has_weapon: Mapped[bool] = mapped_column(Boolean, default=False)
    weapon_json: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")

    character: Mapped[Character] = relationship(back_populates="traits")


class Combat(Base):
    __tablename__ = "combats"
    __table_args__ = (
        UniqueConstraint("guild_id", "channel_id", name="uq_guild_channel_combat"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    started_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, default=1)
    # derived display cache; current_combatant_id below is the source of truth
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    # anchors whose turn it is: the initiative list re-sorts on every read, so a
    # bare index re-points the turn when a faster combatant joins mid-combat.
    # not an FK — combats<->combatants would go circular; the service layer
    # keeps it consistent on add/remove/advance
    current_combatant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    combatants: Mapped[list[Combatant]] = relationship(
        back_populates="combat", cascade="all, delete-orphan",
    )


class Combatant(Base):
    __tablename__ = "combatants"
    __table_args__ = (
        UniqueConstraint("combat_id", "slot", name="uq_combat_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    combat_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("combats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    character_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    discord_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_npc: Mapped[bool] = mapped_column(Boolean, default=False)

    basic_speed: Mapped[float] = mapped_column(Float, nullable=False)
    dx: Mapped[int] = mapped_column(Integer, default=10)
    tiebreaker: Mapped[int] = mapped_column(Integer, default=0)

    hp_max: Mapped[int] = mapped_column(Integer, nullable=False)
    hp_current: Mapped[int] = mapped_column(Integer, nullable=False)
    fp_max: Mapped[int] = mapped_column(Integer, nullable=False)
    fp_current: Mapped[int] = mapped_column(Integer, nullable=False)
    ht: Mapped[int] = mapped_column(Integer, default=10)
    will: Mapped[int] = mapped_column(Integer, default=10)

    maneuver: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status_effects: Mapped[list] = mapped_column(JSON, default=list)
    parries_this_turn: Mapped[int] = mapped_column(Integer, default=0)
    blocks_this_turn: Mapped[int] = mapped_column(Integer, default=0)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)

    combat: Mapped[Combat] = relationship(back_populates="combatants")


class DiceMacro(Base):
    """Saved named dice expression ('greatsword' -> '2d+4'); names stored lowercased, unique per user."""

    __tablename__ = "dice_macros"
    __table_args__ = (
        UniqueConstraint("discord_user_id", "name", name="uq_macro_user_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    expression: Mapped[str] = mapped_column(String(50), nullable=False)
