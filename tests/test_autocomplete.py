from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from gurps_bot.cogs._autocomplete import make_autocomplete
from gurps_bot.cogs.rolling import _skill_attr_autocomplete
from gurps_bot.db.engine import (
    dispose_engine,
    get_session_factory,
    init_db,
    init_engine,
)
from gurps_bot.db.models import ActiveCharacter, Character, Skill
from gurps_bot.services.characters import (
    delete_character,
    import_character,
    set_active_character,
)
from gurps_bot.utils._cache_instances import skill_cache


def _make_interaction(guild_id: int | None = 12345) -> MagicMock:
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.user.id = 99

    session = AsyncMock()

    @asynccontextmanager
    async def fake_db():
        yield session

    interaction.client.db = fake_db
    return interaction, session


class TestMakeAutocomplete:
    @pytest.fixture
    def candidates(self):
        return ["Broadsword", "Shortsword", "Shield", "Bow"]

    @pytest.fixture
    def autocomplete_fn(self, candidates):
        async def fetch(session, interaction):
            return candidates

        return make_autocomplete(fetch)

    async def test_returns_empty_outside_guild(self, autocomplete_fn):
        interaction, _ = _make_interaction(guild_id=None)
        result = await autocomplete_fn(interaction, "Broad")
        assert result == []

    async def test_returns_all_when_no_current(self, autocomplete_fn):
        interaction, _ = _make_interaction()
        result = await autocomplete_fn(interaction, "")
        assert len(result) == 4
        assert result[0].name == "Broadsword"

    async def test_fuzzy_filters_by_current(self, autocomplete_fn):
        interaction, _ = _make_interaction()
        result = await autocomplete_fn(interaction, "sword")
        names = [c.name for c in result]
        assert "Broadsword" in names
        assert "Shortsword" in names
        assert "Shield" not in names

    async def test_skill_attr_autocomplete_caps_at_100(self):
        # The hand-rolled sibling in rolling.py has the same Discord cap.
        # Seed the cache so no DB is touched.
        long_name = "Y" * 150
        interaction, _ = _make_interaction()
        skill_cache.set((interaction.user.id, interaction.guild_id), [long_name])
        try:
            for query in ("", long_name[:40]):
                result = await _skill_attr_autocomplete(interaction, query)
                assert len(result) == 1, f"query={query!r}"
                assert len(result[0].name) <= 100
                assert len(result[0].value) <= 100
        finally:
            skill_cache.invalidate_user(interaction.user.id)

    async def test_choice_name_and_value_capped_at_100(self):
        # Discord rejects the whole autocomplete payload when any Choice
        # name/value exceeds 100 chars — one over-long imported skill name
        # silently kills suggestions.
        long_name = "X" * 150

        async def fetch(session, interaction):
            return [long_name]

        fn = make_autocomplete(fetch)
        interaction, _ = _make_interaction()
        for query in ("", long_name[:40]):
            result = await fn(interaction, query)
            assert len(result) == 1, f"query={query!r}"
            assert len(result[0].name) <= 100
            assert len(result[0].value) <= 100

    async def test_limits_to_25(self):
        big_list = [f"Skill {i}" for i in range(50)]

        async def fetch(session, interaction):
            return big_list

        fn = make_autocomplete(fetch)
        interaction, _ = _make_interaction()
        result = await fn(interaction, "")
        assert len(result) == 25

    async def test_custom_score_cutoff(self):
        candidates = ["Broadsword", "Axe"]

        async def fetch(session, interaction):
            return candidates

        fn = make_autocomplete(fetch, score_cutoff=95)
        interaction, _ = _make_interaction()
        result = await fn(interaction, "xyzzy")
        assert result == []

    async def test_fetch_receives_session_and_interaction(self):
        received = {}

        async def fetch(session, interaction):
            received["session"] = session
            received["interaction"] = interaction
            return ["Item"]

        fn = make_autocomplete(fetch)
        interaction, session = _make_interaction()
        await fn(interaction, "")
        assert received["session"] is session
        assert received["interaction"] is interaction


# --- Skill-cache invalidation ------------------------------------------------
#
# rolling.py caches a user's rollable skill/attribute names under
# (user_id, guild_id) for 10s. The cache is keyed on the USER, not the character,
# so anything that changes WHICH character is active — or removes one — has to
# drop it, or /check autocompletes (and the fuzzy skill resolution behind /check
# itself) keep serving the previous character's sheet.

U = 4242
G = 909


@pytest_asyncio.fixture
async def cache_db():
    """Real in-memory DB + a clean skill_cache (the cache is a module global).

    Built through the production init_engine path, not a bare create_async_engine,
    so the FK pragma is on and deleting a character really cascades its
    ActiveCharacter row.
    """
    init_engine("sqlite+aiosqlite://")
    await init_db()
    skill_cache.clear()
    yield get_session_factory()
    skill_cache.clear()
    await dispose_engine()


async def _seed_two_characters(factory):
    """Alice active, Bob not — both owned by U, one skill each, no attributes.

    Skill names are picked to be absent from sample_gcs_data so a stale read is
    never mistaken for a fresh one.
    """
    async with factory() as s:
        alice = Character(discord_user_id=U, name="Alice")
        bob = Character(discord_user_id=U, name="Bob")
        s.add_all([alice, bob])
        await s.flush()
        s.add_all([
            Skill(character_id=alice.id, name="Alchemy", level=14),
            Skill(character_id=bob.id, name="Bartender", level=12),
        ])
        s.add(ActiveCharacter(discord_user_id=U, guild_id=G, character_id=alice.id))
        await s.commit()
        return alice.id, bob.id


def _live_interaction(factory, user_id=U, guild_id=G):
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.guild_id = guild_id
    interaction.client.db = factory
    return interaction


async def _suggestions(factory) -> list[str]:
    return [c.name for c in await _skill_attr_autocomplete(_live_interaction(factory), "")]


class TestSkillCacheInvalidation:
    async def test_cache_serves_the_active_character(self, cache_db):
        # Baseline: the cache is doing its job before any mutation.
        await _seed_two_characters(cache_db)
        assert await _suggestions(cache_db) == ["Alchemy"]
        assert skill_cache.get((U, G)) == ["Alchemy"]

    async def test_set_active_invalidates(self, cache_db):
        _, bob_id = await _seed_two_characters(cache_db)
        await _suggestions(cache_db)  # warm the cache on Alice

        async with cache_db() as s:
            await set_active_character(s, U, G, bob_id)
            await s.commit()

        assert await _suggestions(cache_db) == ["Bartender"]

    async def test_delete_invalidates(self, cache_db):
        alice_id, _ = await _seed_two_characters(cache_db)
        await _suggestions(cache_db)  # warm the cache on Alice

        async with cache_db() as s:
            await delete_character(s, alice_id)
            await s.commit()

        # Alice is gone and the ActiveCharacter row cascaded with her: no active
        # character, so nothing to suggest — not her stale skill list.
        assert await _suggestions(cache_db) == []

    async def test_delete_invalidates_the_owner_not_the_deleter(self, cache_db):
        # delete_character takes only a char_id; the cache is keyed on the
        # character's OWNER, which the service has to read off the row.
        alice_id, _ = await _seed_two_characters(cache_db)
        await _suggestions(cache_db)
        assert skill_cache.get((U, G)) is not None

        async with cache_db() as s:
            await delete_character(s, alice_id)
            await s.commit()

        assert skill_cache.get((U, G)) is None

    async def test_import_replace_invalidates(self, cache_db, sample_gcs_data):
        # Re-importing the active character swaps its whole skill list in place,
        # so the cached names are stale even though the active pointer never moved.
        from gurps_bot.gcs.parser import parse_gcs

        await _seed_two_characters(cache_db)
        await _suggestions(cache_db)

        parsed = parse_gcs(sample_gcs_data)
        async with cache_db() as s:
            char, _ = await import_character(s, U, parsed, "sheet.gcs")
            await set_active_character(s, U, G, char.id)
            await s.commit()

        names = await _suggestions(cache_db)
        # Alice carried one skill and no attributes at all, so a rollable
        # attribute in the list can only have come from the new sheet.
        assert "ST" in names
        assert "Broadsword" in names  # from the imported sheet
        assert "Alchemy" not in names  # Alice's, gone with her active status

    async def test_invalidation_is_scoped_to_the_mutating_user(self, cache_db):
        _, bob_id = await _seed_two_characters(cache_db)
        other = (99, G)
        skill_cache.set(other, ["Someone Else's Skill"])
        await _suggestions(cache_db)

        async with cache_db() as s:
            await set_active_character(s, U, G, bob_id)
            await s.commit()

        assert skill_cache.get(other) == ["Someone Else's Skill"]
