"""Importing the service at module top registers the Note model, so create_all picks up `notes`."""

from __future__ import annotations

import pytest

from gurps_bot.gcs.parser import parse_gcs
from gurps_bot.services.characters import import_character
from gurps_bot.services.notes import (
    MAX_TAGS,
    TAG_MAX,
    TITLE_MAX,
    NoteNotFound,
    _normalize_tags,
    add_note,
    delete_note,
    edit_note,
    get_note,
    list_notes,
    search_notes,
)

USER_ID = 111111111
OTHER_USER = 333333333
GM_ID = 222222222
GUILD_ID = 999999999
OTHER_GUILD = 777777777
CHANNEL_ID = 888888888


class TestDMScopeLeak:
    """None guild_id (DM) must scope to DM notes only, never leak notes across guilds."""

    async def test_dm_list_does_not_leak_guild_notes(self, db_session):
        await add_note(db_session, discord_user_id=USER_ID, title="guild plot",
                       body="x", guild_id=GUILD_ID)
        await add_note(db_session, discord_user_id=USER_ID, title="dm note",
                       body="y", guild_id=None)
        await db_session.commit()
        # another user's DM listing must never see the guild note
        results = await list_notes(db_session, requesting_user_id=OTHER_USER, guild_id=None)
        titles = [n.title for n in results]
        assert "guild plot" not in titles


class TestAddNote:
    async def test_happy_path_create_and_roundtrip(self, db_session):
        note = await add_note(
            db_session,
            discord_user_id=USER_ID,
            title="Plot",
            body="the duke is a vampire",
            tags=["NPC", "Lead"],
        )
        await db_session.commit()

        assert note.id is not None
        assert note.title == "Plot"
        assert note.tags_json == ["npc", "lead"]
        assert note.discord_user_id == USER_ID
        assert note.gm_secret is False

        rows = await list_notes(db_session, requesting_user_id=USER_ID)
        assert len(rows) == 1
        assert rows[0].title == "Plot"
        assert rows[0].tags_json == ["npc", "lead"]

    async def test_flush_populates_id_not_committed(self, db_session):
        note = await add_note(
            db_session, discord_user_id=USER_ID, title="X", body="y",
        )
        # flushed => id present even before commit
        assert note.id is not None

    async def test_blank_title_raises(self, db_session):
        with pytest.raises(ValueError):
            await add_note(db_session, discord_user_id=USER_ID, title="   ", body="b")

    async def test_empty_title_raises(self, db_session):
        with pytest.raises(ValueError):
            await add_note(db_session, discord_user_id=USER_ID, title="", body="b")

    async def test_title_too_long_raises(self, db_session):
        with pytest.raises(ValueError):
            await add_note(
                db_session,
                discord_user_id=USER_ID,
                title="z" * (TITLE_MAX + 1),
                body="b",
            )

    async def test_title_at_cap_ok(self, db_session):
        note = await add_note(
            db_session, discord_user_id=USER_ID, title="z" * TITLE_MAX, body="b",
        )
        assert len(note.title) == TITLE_MAX

    async def test_body_defaults_empty(self, db_session):
        note = await add_note(db_session, discord_user_id=USER_ID, title="t")
        assert note.body == ""

    async def test_tags_none_is_empty_list(self, db_session):
        note = await add_note(db_session, discord_user_id=USER_ID, title="t")
        assert note.tags_json == []


class TestVisibility:
    async def test_secret_visible_only_to_author(self, db_session):
        await add_note(
            db_session,
            discord_user_id=GM_ID,
            title="Twist",
            body="secret",
            gm_secret=True,
        )
        await db_session.commit()

        gm_view = await list_notes(db_session, requesting_user_id=GM_ID)
        user_view = await list_notes(db_session, requesting_user_id=USER_ID)
        assert len(gm_view) == 1
        assert user_view == []

    async def test_non_secret_visible_to_all(self, db_session):
        await add_note(
            db_session, discord_user_id=GM_ID, title="Public", body="b", gm_secret=False,
        )
        await db_session.commit()

        user_view = await list_notes(db_session, requesting_user_id=USER_ID)
        assert len(user_view) == 1

    async def test_include_secret_false_hides_own_secret(self, db_session):
        await add_note(
            db_session, discord_user_id=USER_ID, title="MySecret", body="s", gm_secret=True,
        )
        await add_note(
            db_session, discord_user_id=USER_ID, title="MyPublic", body="p",
        )
        await db_session.commit()

        # default: viewer sees their own secret + public
        default_view = await list_notes(db_session, requesting_user_id=USER_ID)
        assert len(default_view) == 2

        # public-board view: even the viewer's own secret is excluded
        board = await list_notes(
            db_session, requesting_user_id=USER_ID, include_secret=False,
        )
        titles = {n.title for n in board}
        assert titles == {"MyPublic"}


class TestScopeFilters:
    async def test_guild_filter(self, db_session):
        await add_note(
            db_session, discord_user_id=USER_ID, title="A", body="b", guild_id=GUILD_ID,
        )
        await add_note(
            db_session, discord_user_id=USER_ID, title="B", body="b", guild_id=OTHER_GUILD,
        )
        await db_session.commit()

        rows = await list_notes(
            db_session, requesting_user_id=USER_ID, guild_id=GUILD_ID,
        )
        assert len(rows) == 1
        assert rows[0].title == "A"

    async def test_channel_filter(self, db_session):
        await add_note(
            db_session, discord_user_id=USER_ID, title="Here", body="b", channel_id=CHANNEL_ID,
        )
        await add_note(
            db_session, discord_user_id=USER_ID, title="Elsewhere", body="b", channel_id=12345,
        )
        await db_session.commit()

        rows = await list_notes(
            db_session, requesting_user_id=USER_ID, channel_id=CHANNEL_ID,
        )
        assert [n.title for n in rows] == ["Here"]

    async def test_character_filter(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await db_session.commit()

        await add_note(
            db_session, discord_user_id=USER_ID, title="Linked", body="b", character_id=char.id,
        )
        await add_note(db_session, discord_user_id=USER_ID, title="Unlinked", body="b")
        await db_session.commit()

        rows = await list_notes(
            db_session, requesting_user_id=USER_ID, character_id=char.id,
        )
        assert [n.title for n in rows] == ["Linked"]

    async def test_tag_filter_normalized_both_sides(self, db_session):
        await add_note(
            db_session, discord_user_id=USER_ID, title="T", body="b", tags=["fire", "ice"],
        )
        await db_session.commit()

        rows = await list_notes(
            db_session, requesting_user_id=USER_ID, tag="FIRE",
        )
        assert len(rows) == 1

    async def test_tag_filter_no_match(self, db_session):
        await add_note(
            db_session, discord_user_id=USER_ID, title="T", body="b", tags=["fire"],
        )
        await db_session.commit()

        rows = await list_notes(
            db_session, requesting_user_id=USER_ID, tag="water",
        )
        assert rows == []


class TestAuthorFilterVisibilityInterplay:
    async def test_gm_lists_players_public_not_secret(self, db_session):
        await add_note(db_session, discord_user_id=USER_ID, title="PlayerPublic", body="b")
        await add_note(
            db_session, discord_user_id=USER_ID, title="PlayerSecret", body="s", gm_secret=True,
        )
        await db_session.commit()

        rows = await list_notes(
            db_session, requesting_user_id=GM_ID, author_user_id=USER_ID,
        )
        titles = {n.title for n in rows}
        assert titles == {"PlayerPublic"}

    async def test_author_filter_excludes_other_authors(self, db_session):
        await add_note(db_session, discord_user_id=USER_ID, title="Mine", body="b")
        await add_note(db_session, discord_user_id=OTHER_USER, title="Theirs", body="b")
        await db_session.commit()

        rows = await list_notes(
            db_session, requesting_user_id=GM_ID, author_user_id=USER_ID,
        )
        assert [n.title for n in rows] == ["Mine"]


class TestOrdering:
    async def test_newest_first(self, db_session):
        await add_note(db_session, discord_user_id=USER_ID, title="First", body="b")
        await add_note(db_session, discord_user_id=USER_ID, title="Second", body="b")
        await db_session.commit()

        rows = await list_notes(db_session, requesting_user_id=USER_ID)
        assert rows[0].title == "Second"
        assert rows[1].title == "First"


class TestSearch:
    async def test_substring_body_case_insensitive(self, db_session):
        await add_note(
            db_session, discord_user_id=USER_ID, title="t", body="The DRAGON sleeps",
        )
        await db_session.commit()

        rows = await search_notes(
            db_session, requesting_user_id=USER_ID, query="dragon",
        )
        assert len(rows) == 1

    async def test_substring_title(self, db_session):
        await add_note(db_session, discord_user_id=USER_ID, title="DragonLord", body="b")
        await db_session.commit()

        rows = await search_notes(
            db_session, requesting_user_id=USER_ID, query="dragon",
        )
        assert len(rows) == 1

    async def test_substring_tag(self, db_session):
        await add_note(
            db_session, discord_user_id=USER_ID, title="t", body="b", tags=["Dragon"],
        )
        await db_session.commit()

        rows = await search_notes(
            db_session, requesting_user_id=USER_ID, query="dragon",
        )
        assert len(rows) == 1

    async def test_search_honors_visibility(self, db_session):
        await add_note(
            db_session,
            discord_user_id=GM_ID,
            title="t",
            body="a dragon hoards gold",
            gm_secret=True,
        )
        await db_session.commit()

        rows = await search_notes(
            db_session, requesting_user_id=USER_ID, query="dragon",
        )
        assert rows == []

    async def test_search_author_sees_own_secret(self, db_session):
        await add_note(
            db_session,
            discord_user_id=GM_ID,
            title="t",
            body="a dragon hoards gold",
            gm_secret=True,
        )
        await db_session.commit()

        rows = await search_notes(
            db_session, requesting_user_id=GM_ID, query="dragon",
        )
        assert len(rows) == 1

    async def test_search_respects_scope(self, db_session):
        await add_note(
            db_session, discord_user_id=USER_ID, title="t", body="dragon", guild_id=GUILD_ID,
        )
        await add_note(
            db_session, discord_user_id=USER_ID, title="t2", body="dragon", guild_id=OTHER_GUILD,
        )
        await db_session.commit()

        rows = await search_notes(
            db_session, requesting_user_id=USER_ID, query="dragon", guild_id=GUILD_ID,
        )
        assert len(rows) == 1

    async def test_blank_query_raises(self, db_session):
        with pytest.raises(ValueError):
            await search_notes(db_session, requesting_user_id=USER_ID, query="   ")

    async def test_empty_query_raises(self, db_session):
        with pytest.raises(ValueError):
            await search_notes(db_session, requesting_user_id=USER_ID, query="")


class TestEditNote:
    async def test_edit_title_and_body(self, db_session):
        note = await add_note(db_session, discord_user_id=USER_ID, title="Old", body="old")
        await db_session.commit()

        updated = await edit_note(
            db_session,
            note_id=note.id,
            requesting_user_id=USER_ID,
            title="New",
            body="new",
        )
        assert updated.title == "New"
        assert updated.body == "new"

    async def test_edit_by_non_author_reports_not_found(self, db_session):
        # a foreign-owned id must look exactly like a missing one — no existence oracle
        note = await add_note(db_session, discord_user_id=USER_ID, title="Mine", body="b")
        await db_session.commit()

        with pytest.raises(NoteNotFound):
            await edit_note(
                db_session,
                note_id=note.id,
                requesting_user_id=OTHER_USER,
                title="hax",
            )
        # unchanged
        await db_session.refresh(note)
        assert note.title == "Mine"

    async def test_edit_missing_raises(self, db_session):
        with pytest.raises(NoteNotFound):
            await edit_note(
                db_session, note_id=999999, requesting_user_id=USER_ID, title="x",
            )

    async def test_edit_empty_tags_clears(self, db_session):
        note = await add_note(
            db_session,
            discord_user_id=USER_ID,
            title="t",
            body="body",
            tags=["a", "b"],
        )
        await db_session.commit()

        updated = await edit_note(
            db_session, note_id=note.id, requesting_user_id=USER_ID, tags=[],
        )
        assert updated.tags_json == []
        assert updated.body == "body"
        assert updated.title == "t"

    async def test_edit_tags_none_leaves_unchanged(self, db_session):
        note = await add_note(
            db_session, discord_user_id=USER_ID, title="t", body="b", tags=["keep"],
        )
        await db_session.commit()

        updated = await edit_note(
            db_session, note_id=note.id, requesting_user_id=USER_ID, body="changed",
        )
        assert updated.tags_json == ["keep"]
        assert updated.body == "changed"

    async def test_edit_blank_title_raises(self, db_session):
        note = await add_note(db_session, discord_user_id=USER_ID, title="t", body="b")
        await db_session.commit()

        with pytest.raises(ValueError):
            await edit_note(
                db_session, note_id=note.id, requesting_user_id=USER_ID, title="   ",
            )

    async def test_edit_toggle_gm_secret(self, db_session):
        note = await add_note(db_session, discord_user_id=USER_ID, title="t", body="b")
        await db_session.commit()

        updated = await edit_note(
            db_session, note_id=note.id, requesting_user_id=USER_ID, gm_secret=True,
        )
        assert updated.gm_secret is True

    async def test_edit_refreshes_updated_at(self, db_session):
        note = await add_note(db_session, discord_user_id=USER_ID, title="t", body="b")
        await db_session.commit()
        before = note.updated_at

        updated = await edit_note(
            db_session, note_id=note.id, requesting_user_id=USER_ID, body="new",
        )
        assert updated.updated_at >= before


class TestDeleteNote:
    async def test_delete_owned(self, db_session):
        note = await add_note(db_session, discord_user_id=USER_ID, title="t", body="b")
        await db_session.commit()

        ok = await delete_note(
            db_session, note_id=note.id, requesting_user_id=USER_ID,
        )
        await db_session.commit()
        assert ok is True

        rows = await list_notes(db_session, requesting_user_id=USER_ID)
        assert rows == []

    async def test_delete_missing_returns_false(self, db_session):
        ok = await delete_note(
            db_session, note_id=999999, requesting_user_id=USER_ID,
        )
        assert ok is False

    async def test_delete_other_users_reports_not_found(self, db_session):
        # foreign-owned id returns False as if absent — no existence oracle
        note = await add_note(db_session, discord_user_id=USER_ID, title="t", body="b")
        await db_session.commit()

        ok = await delete_note(
            db_session, note_id=note.id, requesting_user_id=OTHER_USER,
        )
        assert ok is False
        # still present
        rows = await list_notes(db_session, requesting_user_id=USER_ID)
        assert len(rows) == 1


class TestGetNote:
    async def test_get_visible(self, db_session):
        note = await add_note(db_session, discord_user_id=USER_ID, title="t", body="b")
        await db_session.commit()

        got = await get_note(
            db_session, note_id=note.id, requesting_user_id=USER_ID,
        )
        assert got is not None
        assert got.id == note.id

    async def test_get_secret_other_user_is_none(self, db_session):
        note = await add_note(
            db_session, discord_user_id=GM_ID, title="t", body="b", gm_secret=True,
        )
        await db_session.commit()

        got = await get_note(
            db_session, note_id=note.id, requesting_user_id=USER_ID,
        )
        assert got is None

    async def test_get_missing_is_none(self, db_session):
        got = await get_note(
            db_session, note_id=999999, requesting_user_id=USER_ID,
        )
        assert got is None

    async def test_get_public_other_user_ok(self, db_session):
        note = await add_note(db_session, discord_user_id=GM_ID, title="t", body="b")
        await db_session.commit()

        got = await get_note(
            db_session, note_id=note.id, requesting_user_id=USER_ID,
        )
        assert got is not None


class TestCharacterFKSetNull:
    async def test_note_survives_character_deletion(self, db_session, sample_gcs_data):
        """SET NULL is declared, but sqlite FK enforcement is off here — assert survival, not the nulled link."""
        from gurps_bot.services.characters import delete_character

        parsed = parse_gcs(sample_gcs_data)
        char, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await db_session.commit()

        note = await add_note(
            db_session, discord_user_id=USER_ID, title="Linked", body="b", character_id=char.id,
        )
        await db_session.commit()
        note_id = note.id

        await delete_character(db_session, char.id)
        await db_session.commit()

        got = await get_note(
            db_session, note_id=note_id, requesting_user_id=USER_ID,
        )
        assert got is not None


class TestNormalizeTags:
    def test_lowercase_strip_dedupe_orderpreserving(self):
        assert _normalize_tags(["Fire", "fire", " FIRE "]) == ["fire"]

    def test_drop_empties(self):
        assert _normalize_tags(["a", "", "   ", "b"]) == ["a", "b"]

    def test_none_is_empty(self):
        assert _normalize_tags(None) == []

    def test_order_preserved(self):
        assert _normalize_tags(["c", "a", "b"]) == ["c", "a", "b"]

    def test_cap_to_max_tags(self):
        many = [f"t{i}" for i in range(MAX_TAGS + 10)]
        out = _normalize_tags(many)
        assert len(out) == MAX_TAGS

    def test_each_capped_to_tag_max(self):
        out = _normalize_tags(["z" * (TAG_MAX + 5)])
        assert len(out[0]) == TAG_MAX

    def test_non_str_coerced(self):
        assert _normalize_tags([123, 456]) == ["123", "456"]
