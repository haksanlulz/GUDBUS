"""Campaign note CRUD; the gm_secret visibility predicate rides on every read path."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gurps_bot.db.notes import Note

# engineering caps, not GURPS numbers
TITLE_MAX = 200
TAG_MAX = 50
MAX_TAGS = 25


class NoteNotFound(Exception):
    """Missing OR foreign-owned note id — deliberately indistinguishable."""


def _normalize_tags(tags: list[str] | None) -> list[str]:
    """Canonical tag form — every write and filter path must agree on this."""
    if not tags:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = str(raw).strip().lower()
        if not tag:
            continue
        if len(tag) > TAG_MAX:
            tag = tag[:TAG_MAX]
        if tag in seen:
            continue
        seen.add(tag)
        cleaned.append(tag)
        if len(cleaned) >= MAX_TAGS:
            break
    return cleaned


def _validate_title(title: str) -> str:
    stripped = title.strip()
    if not stripped:
        raise ValueError("Note title must not be blank.")
    if len(stripped) > TITLE_MAX:
        raise ValueError(f"Note title must be <= {TITLE_MAX} characters.")
    return stripped


async def add_note(
    session: AsyncSession,
    *,
    discord_user_id: int,
    title: str,
    body: str = "",
    guild_id: int | None = None,
    channel_id: int | None = None,
    character_id: int | None = None,
    tags: list[str] | None = None,
    gm_secret: bool = False,
) -> Note:
    clean_title = _validate_title(title)
    note = Note(
        discord_user_id=discord_user_id,
        title=clean_title,
        body=body,
        guild_id=guild_id,
        channel_id=channel_id,
        character_id=character_id,
        tags_json=_normalize_tags(tags),
        gm_secret=gm_secret,
    )
    session.add(note)
    await session.flush()
    log.info(
        "Added note id=%d by user=%d (gm_secret=%s)",
        note.id, discord_user_id, gm_secret,
    )
    return note


async def list_notes(
    session: AsyncSession,
    *,
    requesting_user_id: int,
    author_user_id: int | None = None,
    guild_id: int | None = None,
    channel_id: int | None = None,
    character_id: int | None = None,
    tag: str | None = None,
    include_secret: bool = True,
) -> list[Note]:
    """Notes visible to requesting_user_id, newest first — author_user_id only scopes, the viewer drives visibility."""
    stmt = select(Note)
    if author_user_id is not None:
        stmt = stmt.where(Note.discord_user_id == author_user_id)
    if guild_id is not None:
        stmt = stmt.where(Note.guild_id == guild_id)
    else:
        # guild_id None means DM-created notes (IS NULL), never "no filter" —
        # unfiltered would return every guild's notes
        stmt = stmt.where(Note.guild_id.is_(None))
    if channel_id is not None:
        stmt = stmt.where(Note.channel_id == channel_id)
    if character_id is not None:
        stmt = stmt.where(Note.character_id == character_id)

    # visibility predicate — always applied, keyed on the viewer
    if include_secret:
        stmt = stmt.where(
            (Note.gm_secret == False)  # noqa: E712 — SQL boolean comparison
            | (Note.discord_user_id == requesting_user_id)
        )
    else:
        # public-board view — even the viewer's own secrets are excluded
        stmt = stmt.where(Note.gm_secret == False)  # noqa: E712

    normalized_tag: str | None = None
    if tag is not None:
        normalized = _normalize_tags([tag])
        # a tag that normalizes to nothing can't match anything — short-circuit
        if not normalized:
            return []
        normalized_tag = normalized[0]
        # cheap SQL pre-filter; the real match happens in python below
        stmt = stmt.where(Note.tags_json.isnot(None))

    stmt = stmt.order_by(Note.updated_at.desc(), Note.id.desc())
    result = await session.execute(stmt)
    notes = list(result.scalars().all())

    if normalized_tag is not None:
        notes = [
            n for n in notes
            if n.tags_json and normalized_tag in n.tags_json
        ]
    return notes


async def search_notes(
    session: AsyncSession,
    *,
    requesting_user_id: int,
    query: str,
    guild_id: int | None = None,
    channel_id: int | None = None,
    character_id: int | None = None,
    author_user_id: int | None = None,
) -> list[Note]:
    """Substring search over title/body/tags — scope + visibility via list_notes; blank query raises."""
    needle = query.strip().lower()
    if not needle:
        raise ValueError("Search query must not be blank.")

    scoped = await list_notes(
        session,
        requesting_user_id=requesting_user_id,
        author_user_id=author_user_id,
        guild_id=guild_id,
        channel_id=channel_id,
        character_id=character_id,
        tag=None,
        include_secret=True,
    )

    def _matches(note: Note) -> bool:
        if needle in note.title.lower():
            return True
        if needle in (note.body or "").lower():
            return True
        return any(needle in t for t in (note.tags_json or []))

    return [n for n in scoped if _matches(n)]


async def edit_note(
    session: AsyncSession,
    *,
    note_id: int,
    requesting_user_id: int,
    title: str | None = None,
    body: str | None = None,
    tags: list[str] | None = None,
    gm_secret: bool | None = None,
) -> Note:
    """Patch a note; None leaves a field alone (tags=[] clears). Foreign-owned ids read as absent."""
    result = await session.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    # foreign-owned reads as absent (#13) — a "not yours" answer over a
    # sequential pk is an existence oracle for other users' note ids
    if note is None or note.discord_user_id != requesting_user_id:
        raise NoteNotFound(f"No note with id={note_id}.")

    if title is not None:
        note.title = _validate_title(title)
    if body is not None:
        note.body = body
    if tags is not None:
        note.tags_json = _normalize_tags(tags)
    if gm_secret is not None:
        note.gm_secret = gm_secret

    # onupdate only fires when a mapped column changes — set explicitly
    note.updated_at = datetime.now(timezone.utc)
    await session.flush()
    log.info("Edited note id=%d by user=%d", note_id, requesting_user_id)
    return note


async def delete_note(
    session: AsyncSession,
    *,
    note_id: int,
    requesting_user_id: int,
) -> bool:
    """Delete own note; missing and foreign-owned ids both return False (same oracle guard as edit_note)."""
    result = await session.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if note is None or note.discord_user_id != requesting_user_id:
        return False
    log.info("Deleting note id=%d by user=%d", note_id, requesting_user_id)
    await session.delete(note)
    return True


async def get_note(
    session: AsyncSession,
    *,
    note_id: int,
    requesting_user_id: int,
) -> Note | None:
    """Fetch a note if it exists and is visible; another user's secret reads as None."""
    result = await session.execute(select(Note).where(Note.id == note_id))
    note = result.scalar_one_or_none()
    if note is None:
        return None
    if note.gm_secret and note.discord_user_id != requesting_user_id:
        return None
    return note
