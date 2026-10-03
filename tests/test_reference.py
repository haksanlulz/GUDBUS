"""ReferenceIndex ranking/limit/miss behaviour, against a hand-built catalog — never touches disk."""

from __future__ import annotations

import pytest

from gurps_bot.gcs.library import (
    CatalogEquipment,
    CatalogSkill,
    CatalogSpell,
    CatalogTechnique,
    CatalogTrait,
)
from gurps_bot.services.reference import ReferenceIndex


def _skill(name: str, **kw) -> CatalogSkill:
    return CatalogSkill(
        name=name,
        attribute=kw.get("attribute", "DX"),
        difficulty=kw.get("difficulty", "Average"),
        page=kw.get("page", "B100"),
        points=kw.get("points", 1),
        defaults=kw.get("defaults", []),
        book=kw.get("book", "Basic Set"),
    )


@pytest.fixture
def fake_catalog() -> dict[str, list]:
    """Skills mix an exact target, prefix neighbours, a substring hit, and fuzzy noise."""
    return {
        "skills": [
            _skill("Sword"),
            _skill("Swordsmanship"),
            _skill("Sword Art"),
            _skill("Two-Handed Sword"),
            _skill("Broadsword"),
            _skill("Shield"),
            _skill("Stealth"),
            _skill("First Aid", attribute="IQ", difficulty="Easy"),
        ],
        "traits": [
            CatalogTrait(name="Combat Reflexes", points=15, page="B43", book="Basic Set"),
            CatalogTrait(name="Bad Temper", points=-10, page="B124", book="Basic Set"),
        ],
        "spells": [
            CatalogSpell(
                name="Fireball",
                college=["Fire"],
                difficulty="Hard",
                page="M74",
                casting_cost="Varies",
                maintenance="",
                casting_time="1 sec",
                duration="Instantaneous",
                spell_class="Missile",
                book="Magic",
            ),
        ],
        "techniques": [
            CatalogTechnique(
                name="Disarming",
                difficulty="Hard",
                page="MA70",
                default={"type": "skill", "name": "@Skill@", "modifier": -4},
                book="Martial Arts",
            ),
        ],
        "equipment": [
            CatalogEquipment(
                name="Broadsword",
                cost="500",
                weight="3 lb",
                damage="sw+1 cut",
                reach="1",
                page="B271",
                legality="3",
                book="Basic Set",
            ),
            CatalogEquipment(
                name="Dagger",
                cost="20",
                weight="0.25 lb",
                damage="thr-1 imp",
                reach="C,1",
                page="B272",
                legality="4",
                book="Basic Set",
            ),
        ],
    }


@pytest.fixture
def index(fake_catalog) -> ReferenceIndex:
    return ReferenceIndex(fake_catalog)


class TestRanking:
    def test_exact_match_ranks_first(self, index):
        results = index.search("skills", "Sword")
        assert results, "expected at least one result"
        assert results[0].name == "Sword"

    def test_exact_match_is_case_insensitive(self, index):
        results = index.search("skills", "sWoRd")
        assert results[0].name == "Sword"

    def test_prefix_ranks_above_pure_fuzzy(self, index):
        # "Broadsword" only contains the substring; "Sword"/"Swordsmanship"/
        # "Sword Art" are exact-or-prefix and must all out-rank it.
        results = index.search("skills", "Sword", limit=10)
        names = [r.name for r in results]
        assert names.index("Sword") < names.index("Broadsword")
        assert names.index("Swordsmanship") < names.index("Broadsword")
        assert names.index("Sword Art") < names.index("Broadsword")

    def test_prefix_query_returns_prefix_matches(self, index):
        results = index.search("skills", "Swords")  # prefix of Swordsmanship
        names = [r.name for r in results]
        assert "Swordsmanship" in names
        # the exact/prefix family ranks ahead of the unrelated noise
        assert names[0] in {"Swordsmanship", "Sword", "Sword Art"}

    def test_fuzzy_still_finds_typo(self, index):
        # a transposed-letter typo should still surface the intended skill via
        # the rapidfuzz fallback tier
        results = index.search("skills", "Stelath")  # -> Stealth
        assert any(r.name == "Stealth" for r in results)


class TestLimit:
    def test_limit_honored(self, index):
        results = index.search("skills", "s", limit=3)
        assert len(results) <= 3

    def test_limit_default_is_ten(self, index):
        # 8 skills in the fake catalog, all loosely 's'-ish; default limit caps at 10
        # so we never exceed it, and here we get at most the catalog size.
        results = index.search("skills", "s")
        assert len(results) <= 10

    def test_limit_zero_returns_empty(self, index):
        results = index.search("skills", "Sword", limit=0)
        assert results == []


class TestUnknownCategory:
    def test_unknown_category_search_returns_empty(self, index):
        assert index.search("dragons", "Sword") == []

    def test_unknown_category_names_returns_empty(self, index):
        assert index.names("dragons") == []

    def test_unknown_category_get_returns_none(self, index):
        assert index.get("dragons", "Sword") is None

    def test_empty_query_returns_empty(self, index):
        assert index.search("skills", "") == []
        assert index.search("skills", "   ") == []

    def test_index_built_from_empty_catalog(self):
        idx = ReferenceIndex({})
        assert idx.search("skills", "Sword") == []
        assert idx.names("skills") == []
        assert idx.get("skills", "Sword") is None


class TestGet:
    def test_get_exact(self, index):
        result = index.get("skills", "Sword")
        assert result is not None
        assert result.name == "Sword"

    def test_get_is_case_insensitive(self, index):
        result = index.get("skills", "BROADSWORD")
        assert result is not None
        assert result.name == "Broadsword"

    def test_get_returns_none_on_miss(self, index):
        # a name that does not fuzzy-match anything in the catalog
        assert index.get("skills", "Nonexistent Zzyzx Skill") is None

    def test_get_prefers_exact_over_fuzzy_neighbour(self, index):
        # "Sword" is exact even though "Swordsmanship"/"Sword Art" are close
        result = index.get("skills", "Sword")
        assert result.name == "Sword"

    def test_get_other_category(self, index):
        result = index.get("traits", "Combat Reflexes")
        assert result is not None
        assert result.name == "Combat Reflexes"

    def test_get_ambiguous_prefix_returns_none(self, index):
        # "Sw" prefixes Sword, Swordsmanship, and Sword Art — no single answer.
        # The contract: a facts lookup must never assert an arbitrary entry's
        # page cite; ambiguity belongs to search()/autocomplete.
        assert index.get("skills", "Sw") is None

    def test_get_unambiguous_prefix_still_resolves(self, index):
        # "Steal" prefixes only Stealth — the single-hit prefix tier stays.
        result = index.get("skills", "Steal")
        assert result is not None
        assert result.name == "Stealth"

    def test_get_exact_wins_even_when_prefix_tier_is_ambiguous(self):
        # Exact match must win regardless of catalog order — an ambiguous
        # prefix tier scanned before the exact entry must not short-circuit.
        index = ReferenceIndex(
            {"skills": [_skill("Swordsmanship"), _skill("Sword Art"), _skill("Sword")]}
        )
        result = index.get("skills", "Sword")
        assert result is not None
        assert result.name == "Sword"

    def test_get_same_named_entries_are_not_ambiguous(self):
        # The same skill recurring across books is one answer, not two.
        index = ReferenceIndex(
            {"skills": [_skill("Broadsword"), _skill("Broadsword", book="Martial Arts")]}
        )
        result = index.get("skills", "Broadsw")
        assert result is not None
        assert result.name == "Broadsword"


class TestNames:
    def test_names_lists_all(self, index):
        names = index.names("skills")
        assert "Sword" in names
        assert "Broadsword" in names
        assert len(names) == 8

    def test_names_equipment(self, index):
        names = index.names("equipment")
        assert set(names) == {"Broadsword", "Dagger"}

    def test_names_are_sorted(self, index):
        names = index.names("traits")
        assert names == sorted(names)
