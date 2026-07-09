"""character service against a real in-memory sqlite db"""

from __future__ import annotations

import pytest

from gurps_bot.gcs.parser import parse_gcs
from gurps_bot.services.characters import (
    delete_character,
    get_active_character,
    get_character_attrs,
    get_character_skills,
    get_character_spells,
    get_character_traits,
    get_user_character_names,
    import_character,
    set_active_character,
)

USER_ID = 123456789
GUILD_ID = 987654321


class TestImportCharacter:
    async def test_import_new_character(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char, was_replacement = await import_character(
            db_session, USER_ID, parsed, "test.gcs",
        )
        await db_session.commit()

        assert char.name == "Sir Brannar"
        assert char.total_points == 150
        assert char.discord_user_id == USER_ID
        assert was_replacement is False

    async def test_reimport_preserves_id(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char1, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await db_session.commit()
        original_id = char1.id

        char2, was_replacement = await import_character(
            db_session, USER_ID, parsed, "test_v2.gcs",
        )
        await db_session.commit()

        assert char2.id == original_id
        assert was_replacement is True

    async def test_import_creates_attributes(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await db_session.commit()

        attrs = await get_character_attrs(db_session, char.id)
        assert attrs["st"] == 13
        assert attrs["dx"] == 12
        assert attrs["hp_current"] == 13

    async def test_import_creates_skills(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await db_session.commit()

        skills = await get_character_skills(db_session, char.id)
        skill_names = {s.name for s in skills}
        assert "Broadsword" in skill_names
        assert "Stealth" in skill_names

    async def test_import_creates_spells(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await db_session.commit()

        spells = await get_character_spells(db_session, char.id)
        assert len(spells) == 1
        assert spells[0].name == "Ignite Fire"

    async def test_import_creates_traits(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await db_session.commit()

        traits = await get_character_traits(db_session, char.id)
        trait_names = {t.name for t in traits}
        assert "Combat Reflexes" in trait_names
        assert "Bad Temper" in trait_names

    async def test_reimport_clears_old_children(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await db_session.commit()

        skills_before = await get_character_skills(db_session, char.id)
        count_before = len(skills_before)

        char2, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await db_session.commit()

        skills_after = await get_character_skills(db_session, char2.id)
        assert len(skills_after) == count_before


class TestStableIdentityReimport:
    """regression: a renamed re-import must replace via the stable gcs id, not orphan a duplicate"""

    async def test_reimport_after_rename_replaces_not_orphans(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char1, _ = await import_character(
            db_session, USER_ID, parsed, "knight.gcs", raw_data=sample_gcs_data,
        )
        await db_session.commit()
        original_id = char1.id
        assert char1.gcs_id == "test_char_001"

        # rename in gcs — same character id
        sample_gcs_data["profile"]["name"] = "Sir Brannar the Bold"
        parsed2 = parse_gcs(sample_gcs_data)
        char2, was_replacement = await import_character(
            db_session, USER_ID, parsed2, "knight.gcs", raw_data=sample_gcs_data,
        )
        await db_session.commit()

        assert was_replacement is True
        assert char2.id == original_id  # same row — no orphan
        assert char2.name == "Sir Brannar the Bold"
        names = await get_user_character_names(db_session, USER_ID)
        assert names == ["Sir Brannar the Bold"]  # exactly one, renamed

    async def test_legacy_import_without_id_still_name_matches(self, db_session, sample_gcs_data):
        # no raw_data → no gcs_id; the legacy name-keyed path must still replace
        parsed = parse_gcs(sample_gcs_data)
        char1, _ = await import_character(db_session, USER_ID, parsed, "k.gcs")
        await db_session.commit()
        assert char1.gcs_id is None

        char2, was_replacement = await import_character(db_session, USER_ID, parsed, "k.gcs")
        await db_session.commit()
        assert was_replacement is True
        assert char2.id == char1.id

    async def test_gcs_id_backfilled_then_rename_matches(self, db_session, sample_gcs_data):
        # pre-column import: gcs_id NULL
        parsed = parse_gcs(sample_gcs_data)
        char1, _ = await import_character(db_session, USER_ID, parsed, "k.gcs")
        await db_session.commit()
        assert char1.gcs_id is None

        # re-import with raw_data adopts by name and backfills the id
        char2, repl = await import_character(
            db_session, USER_ID, parsed, "k.gcs", raw_data=sample_gcs_data,
        )
        await db_session.commit()
        assert repl is True
        assert char2.id == char1.id
        assert char2.gcs_id == "test_char_001"

        # rename now matches by the backfilled id
        sample_gcs_data["profile"]["name"] = "Renamed Knight"
        parsed3 = parse_gcs(sample_gcs_data)
        char3, repl3 = await import_character(
            db_session, USER_ID, parsed3, "k.gcs", raw_data=sample_gcs_data,
        )
        await db_session.commit()
        assert repl3 is True
        assert char3.id == char1.id
        names = await get_user_character_names(db_session, USER_ID)
        assert names == ["Renamed Knight"]


class TestActiveCharacter:
    async def test_no_active_returns_none(self, db_session):
        char = await get_active_character(db_session, USER_ID, GUILD_ID)
        assert char is None

    async def test_set_and_get_active(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await set_active_character(db_session, USER_ID, GUILD_ID, char.id)
        await db_session.commit()

        active = await get_active_character(db_session, USER_ID, GUILD_ID)
        assert active is not None
        assert active.id == char.id
        assert active.name == "Sir Brannar"

    async def test_set_active_upsert(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await set_active_character(db_session, USER_ID, GUILD_ID, char.id)
        await db_session.commit()

        sample_gcs_data["profile"]["name"] = "Sir Brannar II"
        parsed2 = parse_gcs(sample_gcs_data)
        char2, _ = await import_character(db_session, USER_ID, parsed2, "test2.gcs")
        await set_active_character(db_session, USER_ID, GUILD_ID, char2.id)
        await db_session.commit()

        active = await get_active_character(db_session, USER_ID, GUILD_ID)
        assert active.id == char2.id


class TestGetUserCharacterNames:
    async def test_empty_for_new_user(self, db_session):
        names = await get_user_character_names(db_session, USER_ID)
        assert names == []

    async def test_returns_all_names(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        await import_character(db_session, USER_ID, parsed, "test.gcs")

        sample_gcs_data["profile"]["name"] = "Another Knight"
        parsed2 = parse_gcs(sample_gcs_data)
        await import_character(db_session, USER_ID, parsed2, "test2.gcs")
        await db_session.commit()

        names = await get_user_character_names(db_session, USER_ID)
        assert set(names) == {"Sir Brannar", "Another Knight"}


class TestDeleteCharacter:
    async def test_delete_existing(self, db_session, sample_gcs_data):
        parsed = parse_gcs(sample_gcs_data)
        char, _ = await import_character(db_session, USER_ID, parsed, "test.gcs")
        await db_session.commit()

        deleted = await delete_character(db_session, char.id)
        await db_session.commit()
        assert deleted is True

        names = await get_user_character_names(db_session, USER_ID)
        assert names == []

    async def test_delete_nonexistent(self, db_session):
        deleted = await delete_character(db_session, 99999)
        assert deleted is False
