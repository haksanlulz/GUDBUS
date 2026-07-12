from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from gurps_bot.cogs._autocomplete import make_autocomplete
from gurps_bot.cogs.rolling import _skill_attr_autocomplete
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
