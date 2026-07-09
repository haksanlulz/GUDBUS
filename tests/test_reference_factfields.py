"""fact fields must survive loader -> mapper -> embed; prose must never ride along"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from gurps_bot.gcs import library
from gurps_bot.gcs.library import (
    CatalogEquipment,
    CatalogSkill,
    CatalogSpell,
    CatalogTechnique,
    CatalogTrait,
    load_library,
)
from gurps_bot.services.reference import (
    ReferenceLookup,
    entry_to_dict,
)
from gurps_bot.cogs.reference import (
    build_equipment_embed,
    build_skill_embed,
    build_spell_embed,
    build_technique_embed,
    build_trait_embed,
)

# bounds calibrated vs the real library: longest real tag 47 chars, resist 41
_TAG_MAX_LEN = 64
_RESIST_MAX_LEN = 64
_VALID_CR = {6, 9, 12, 15}

_PROSE = (
    "Once adrift in your own thoughts, you must roll against Perception-5 "
    "to notice anything short of an actual attack."
)

# fixture rows carry the new facts plus prose that must not survive the chain

SKILL_ROW = {
    "name": "Broadsword",
    "difficulty": "dx/a",
    "points": 8,
    "reference": "B208",
    "tags": ["Combat", "Melee Combat"],
    "local_notes": _PROSE,
}

TRAIT_ROW = {
    "name": "Absent-Mindedness",
    "base_points": -15,
    "cr": 12,
    "cr_adj": "action_penalty",
    "reference": "B122",
    "tags": ["Disadvantage", "Mental"],
    "local_notes": _PROSE,
}

LEVELED_TRAIT_ROW = {
    "name": "Damage Resistance",
    "base_points": None,
    "points_per_level": 5,
    "levels": 4,
    "reference": "B46",
    "tags": ["Advantage", "Exotic"],
}

SPELL_ROW = {
    "name": "Animate Plant",
    "difficulty": "iq/vh",
    "college": ["Plant"],
    "resist": "Special",
    "power_source": "Arcane",
    "points": 4,
    "casting_cost": "Varies",
    "maintenance_cost": "Varies",
    "casting_time": "2 sec",
    "duration": "1 min",
    "spell_class": "Regular",
    "reference": "M86",
    "tags": ["Plant"],
    "local_notes": "Double casting cost if plant moves.",
}

TECHNIQUE_ROW = {
    "name": "Disarming",
    "difficulty": "h",  # bare code => technique
    "default": {"type": "skill", "name": "Broadsword", "modifier": -4},
    "limit": 4,
    "points": 2,
    "reference": "B232",
    "tags": ["Combat"],
}

EQUIPMENT_ROW = {
    "description": "Thrusting Broadsword",  # gcs equipment name lives in 'description'
    "base_value": "600",
    "base_weight": "3 lb",
    "legality_class": "3",
    "tech_level": "3",
    "rated_strength": 11,
    "reference": "B271",
    "tags": ["Melee Weapon"],
    "weapons": [{"calc": {"damage": "sw+1 cut", "reach": "1"}, "usage_notes": _PROSE}],
    "local_notes": _PROSE,
}


def _no_prose(obj) -> None:
    for f in dataclasses.fields(obj):
        val = getattr(obj, f.name)
        assert _PROSE not in _flatten(val), f"{type(obj).__name__}.{f.name} leaked prose: {val!r}"


def _flatten(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return " ".join(_flatten(v) for v in val.values())
    if isinstance(val, (list, tuple, set)):
        return " ".join(_flatten(v) for v in val)
    return str(val)


class TestLoaderExtractsNewFacts:
    def test_skill_tags(self):
        s = library._build_skill(SKILL_ROW, book="Basic Set")
        assert s.tags == ["Combat", "Melee Combat"]
        _no_prose(s)

    def test_trait_self_control_and_tags(self):
        t = library._build_trait(TRAIT_ROW, book="Basic Set")
        assert t.cr == 12
        assert t.cr_adj == "action_penalty"
        assert t.tags == ["Disadvantage", "Mental"]
        _no_prose(t)

    def test_trait_leveled_cost(self):
        t = library._build_trait(LEVELED_TRAIT_ROW, book="Basic Set")
        assert t.points_per_level == 5
        assert t.levels == 4

    def test_spell_resist_source_points_tags(self):
        sp = library._build_spell(SPELL_ROW, book="Magic")
        assert sp.resist == "Special"
        assert sp.power_source == "Arcane"
        assert sp.points == 4
        assert sp.tags == ["Plant"]
        _no_prose(sp)

    def test_technique_limit_points_tags(self):
        tch = library._build_technique(TECHNIQUE_ROW, book="Basic Set")
        assert tch.limit == 4
        assert tch.points == 2
        assert tch.tags == ["Combat"]
        _no_prose(tch)

    def test_equipment_tl_rated_st_tags(self):
        e = library._build_equipment(EQUIPMENT_ROW, book="Basic Set")
        assert e.tech_level == "3"
        assert e.rated_strength == 11
        assert e.tags == ["Melee Weapon"]
        _no_prose(e)

    def test_missing_new_facts_default_cleanly(self):
        s = library._build_skill({"name": "Bare", "difficulty": "dx/e"}, book="B")
        assert s.tags == []
        t = library._build_trait({"name": "Bare", "base_points": 1}, book="B")
        assert t.cr is None and t.cr_adj is None and t.tags == []
        sp = library._build_spell({"name": "Bare", "difficulty": "iq/h"}, book="B")
        assert sp.resist == "" and sp.power_source == "" and sp.points is None
        e = library._build_equipment({"description": "Bare"}, book="B")
        assert e.tech_level == "" and e.rated_strength is None and e.tags == []


class TestMapperEmitsNewFacts:
    def test_skill_mapper_emits_tags(self):
        s = library._build_skill(SKILL_ROW, book="Basic Set")
        d = entry_to_dict(s)
        assert d["tags"] == ["Combat", "Melee Combat"]

    def test_trait_mapper_emits_self_control_and_levels(self):
        t = library._build_trait(TRAIT_ROW, book="Basic Set")
        d = entry_to_dict(t)
        assert d["cr"] == 12
        assert d["cr_adj"] == "action_penalty"
        assert d["tags"] == ["Disadvantage", "Mental"]
        lev = entry_to_dict(library._build_trait(LEVELED_TRAIT_ROW, book="B"))
        assert lev["points_per_level"] == 5
        assert lev["levels"] == 4

    def test_spell_mapper_emits_resist_source_points(self):
        sp = library._build_spell(SPELL_ROW, book="Magic")
        d = entry_to_dict(sp)
        assert d["resist"] == "Special"
        assert d["power_source"] == "Arcane"
        assert d["points"] == 4
        assert d["tags"] == ["Plant"]

    def test_technique_mapper_emits_limit_points(self):
        tch = library._build_technique(TECHNIQUE_ROW, book="Basic Set")
        d = entry_to_dict(tch)
        assert d["limit"] == 4
        assert d["points"] == 2
        assert d["tags"] == ["Combat"]

    def test_equipment_mapper_emits_tl_rated_st_tags(self):
        e = library._build_equipment(EQUIPMENT_ROW, book="Basic Set")
        d = entry_to_dict(e)
        assert d["tech_level"] == "3"
        assert d["rated_strength"] == 11
        assert d["tags"] == ["Melee Weapon"]


def _embed_text(embed) -> str:
    parts = [embed.title or ""]
    for f in embed.fields:
        parts.append(str(f.name))
        parts.append(str(f.value))
    return "\n".join(parts)


class TestEndToEndRendersNewFacts:
    def _lookup(self, category, entry) -> dict:
        lk = ReferenceLookup({category: [entry]})
        d = lk.get(category, entry.name)
        assert d is not None
        return d

    def test_skill_tags_render(self):
        d = self._lookup("skills", library._build_skill(SKILL_ROW, book="B"))
        text = _embed_text(build_skill_embed(d))
        assert "Tags" in text
        assert "Combat" in text and "Melee Combat" in text

    def test_trait_self_control_renders(self):
        d = self._lookup("traits", library._build_trait(TRAIT_ROW, book="B"))
        text = _embed_text(build_trait_embed(d))
        assert "Self-Control" in text
        assert "12" in text
        assert "Mental" in text  # a tag

    def test_spell_resist_and_source_render(self):
        d = self._lookup("spells", library._build_spell(SPELL_ROW, book="M"))
        text = _embed_text(build_spell_embed(d))
        assert "Resist" in text and "Special" in text
        assert "Power Source" in text and "Arcane" in text

    def test_technique_max_bonus_renders(self):
        d = self._lookup("techniques", library._build_technique(TECHNIQUE_ROW, book="B"))
        text = _embed_text(build_technique_embed(d))
        assert "Max Bonus" in text and "+4" in text

    def test_equipment_tl_renders(self):
        d = self._lookup("equipment", library._build_equipment(EQUIPMENT_ROW, book="B"))
        text = _embed_text(build_equipment_embed(d))
        assert "Tech Level" in text
        assert "Melee Weapon" in text  # a tag

    def test_no_prose_through_full_chain(self):
        for category, row, builder, factory in [
            ("skills", SKILL_ROW, build_skill_embed, library._build_skill),
            ("traits", TRAIT_ROW, build_trait_embed, library._build_trait),
            ("spells", SPELL_ROW, build_spell_embed, library._build_spell),
            ("equipment", EQUIPMENT_ROW, build_equipment_embed, library._build_equipment),
        ]:
            entry = factory(row, book="B")
            d = self._lookup(category, entry)
            assert _PROSE not in _embed_text(builder(d))


class TestRealDataFactFields:
    @pytest.fixture(scope="class")
    def catalog(self):
        if not Path(library.DEFAULT_LIBRARY_ROOT).is_dir():
            pytest.skip("vendored GCS library not present")
        return load_library()

    def test_tags_populate_on_real_entries(self, catalog):
        tagged = sum(1 for cat in catalog.values() for e in cat if getattr(e, "tags", None))
        assert tagged > 1000, f"expected the live 'tags' key to populate broadly, got {tagged}"

    def test_real_tags_are_short_facts_not_prose(self, catalog):
        for cat in catalog.values():
            for e in cat:
                for tag in getattr(e, "tags", []) or []:
                    assert isinstance(tag, str)
                    assert len(tag) <= _TAG_MAX_LEN, f"tag too long (prose?): {tag!r}"
                    assert "\n" not in tag
                    assert _PROSE not in tag

    def test_real_self_control_in_canonical_set(self, catalog):
        crs = [e.cr for e in catalog["traits"] if getattr(e, "cr", None) is not None]
        assert crs, "expected some self-control traits in the real library"
        assert all(cr in _VALID_CR for cr in crs), f"non-canonical cr values: {sorted(set(crs))}"

    def test_real_resist_is_short(self, catalog):
        resists = [e.resist for e in catalog["spells"] if getattr(e, "resist", "")]
        assert resists, "expected some resisted spells in the real library"
        assert all(len(r) <= _RESIST_MAX_LEN for r in resists)

    def test_real_power_source_and_points_populate(self, catalog):
        assert sum(1 for e in catalog["spells"] if getattr(e, "power_source", "")) > 100
        assert sum(1 for e in catalog["spells"] if getattr(e, "points", None) is not None) > 100

    def test_real_equipment_tech_level_populates(self, catalog):
        assert sum(1 for e in catalog["equipment"] if getattr(e, "tech_level", "")) > 100

    def test_real_chain_renders_a_self_control_trait(self, catalog):
        trait = next((e for e in catalog["traits"] if getattr(e, "cr", None) is not None), None)
        assert trait is not None
        d = entry_to_dict(trait)
        text = _embed_text(build_trait_embed(d))
        assert "Self-Control" in text
        assert _PROSE not in text

    def test_no_at_token_leaks_in_real_stored_facts(self, catalog):
        """no stored fact may carry an unfilled @token@; defaults excluded — their tokens strip at render"""
        import re

        token = re.compile(r"@[^@]*@")
        for cat in catalog.values():
            for e in cat:
                for f in dataclasses.fields(e):
                    if f.name in ("defaults", "default", "specialization"):
                        continue
                    assert not token.search(_flatten(getattr(e, f.name))), (
                        f"@token leak in {type(e).__name__}.{f.name}: {getattr(e, f.name)!r}"
                    )
