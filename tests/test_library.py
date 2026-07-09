"""Master Library loader — the copyright wall: catalog dataclasses carry facts only, never prose."""

from __future__ import annotations

import dataclasses
import json
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

# fixture rows shaped like real GCS data; each carries prose fields the loader must drop

_PROSE = (
    "Once adrift in your own thoughts, you must roll against Perception-5 "
    "to notice anything short of an actual attack."
)

SKILL_ROW = {
    "id": "abc",
    "name": "Broadsword",
    "specialization": "@Specialty@",
    "difficulty": "dx/h",
    "points": 8,
    "reference": "B208",
    "tech_level": "",
    "tags": ["Combat", "Melee Combat"],
    "defaults": [
        {"type": "dx", "modifier": -5},
        {"type": "skill", "name": "Shortsword", "modifier": -2},
    ],
    # prose/bulk that must be dropped:
    "local_notes": _PROSE,
    "reference_highlight": "Broadsword",
    "features": [{"type": "skill_bonus"}],
    "weapons": [{"id": "w", "usage_notes": _PROSE}],
    "prereqs": {"type": "prereq_list"},
    "calc": {"level": 14, "rsl": "DX+2"},
}

SPELL_ROW = {
    "id": "def",
    "name": "Animate Plant",
    "difficulty": "iq/vh",
    "college": ["Plant"],
    "power_source": "Arcane",
    "spell_class": "Regular",
    "resist": "Special",
    "casting_cost": "Varies",
    "maintenance_cost": "Varies",
    "casting_time": "2 sec",
    "duration": "1 min",
    "reference": "M86",
    "points": 4,
    "tags": ["Plant"],
    # prose that must be dropped:
    "local_notes": "Double casting cost if plant moves.",
    "reference_highlight": "Animate Plant",
    "prereqs": {"type": "prereq_list"},
}

TRAIT_ROW = {
    "id": "ghi",
    "name": "Absent-Mindedness",
    "base_points": -15,
    "cr": 12,
    "cr_adj": "action_penalty",
    "reference": "B122",
    "tags": ["Disadvantage", "Mental"],
    "modifiers": [
        {"id": "m1", "name": "Mitigator", "cost_adj": "-20%", "local_notes": _PROSE},
    ],
    # prose that must be dropped:
    "local_notes": _PROSE,
    "reference_highlight": "Absent-Mindedness",
    "features": [],
    "calc": {"points": -15},
}

TECHNIQUE_ROW = {
    "id": "jkl",
    "name": "Disarming",
    "difficulty": "h",  # bare code => technique discriminator
    "default": {"type": "skill", "name": "@Skill@", "modifier": -4},
    "limit": 0,
    "points": 2,
    "reference": "B232",
    "tags": ["Combat"],
    "weapons": [{"id": "w"}],
    "prereqs": {"type": "prereq_list"},
}

EQUIPMENT_ROW = {
    "id": "mno",
    "description": "Thrusting Broadsword",  # gcs equipment name lives in 'description'
    "base_value": "600",
    "base_weight": "3 lb",
    "legality_class": "3",
    "tech_level": "3",
    "reference": "B271",
    "tags": ["Melee Weapon"],
    "weapons": [
        {
            "id": "w1",
            "damage": {"type": "cut", "st": "sw", "base": "1"},
            "usage": "Swung",
            "reach": "1",
            "parry": "0",
            "usage_notes": _PROSE,
            "defaults": [{"type": "skill", "name": "Broadsword"}],
            "calc": {"damage": "sw+1 cut", "parry": "10", "reach": "1"},
        }
    ],
    # prose/bulk that must be dropped:
    "local_notes": _PROSE,
    "reference_highlight": "Thrusting Broadsword",
    "modifiers": [],
    "calc": {"extended_value": "600"},
}

# group header (no difficulty/points): never emitted itself; children recursed
SKL_CONTAINER = {
    "id": "grp",
    "name": "Melee Weapon Techniques",
    "children": [TECHNIQUE_ROW],
}


_ALL_DATACLASSES = (
    CatalogSkill,
    CatalogTrait,
    CatalogSpell,
    CatalogTechnique,
    CatalogEquipment,
)

_FORBIDDEN_FIELD_SUBSTRINGS = (
    "note",
    "notes",
    "local_notes",
    "description",  # equipment name is 'name', never 'description'
    "desc",
    "prose",
    "flavor",
    "text",
    "highlight",
    "summary",
)

_PROSE_STRINGS = (
    _PROSE,
    "Double casting cost if plant moves.",
)

# fails closed: any new field must be whitelisted here or the structural test
# fails; specialization is a fact (skill spec), allowed deliberately
EXPECTED_FACT_FIELDS: dict[type, set[str]] = {
    CatalogSkill: {
        "name", "attribute", "difficulty", "page", "points", "defaults",
        "book", "specialization", "tags",
    },
    CatalogTrait: {
        "name", "points", "page", "book", "cr", "cr_adj",
        "points_per_level", "levels", "tags",
    },
    CatalogSpell: {
        "name", "college", "difficulty", "page", "casting_cost",
        "maintenance", "casting_time", "duration", "spell_class", "book",
        "resist", "power_source", "points", "tags",
    },
    CatalogTechnique: {
        "name", "difficulty", "page", "default", "book", "limit", "points", "tags",
    },
    CatalogEquipment: {
        "name", "cost", "weight", "damage", "reach", "page", "legality", "book",
        "tech_level", "rated_strength", "tags",
    },
}


class TestCopyrightWallStructure:
    def test_no_dataclass_declares_a_prose_field(self):
        for dc in _ALL_DATACLASSES:
            for f in dataclasses.fields(dc):
                lowered = f.name.lower()
                for bad in _FORBIDDEN_FIELD_SUBSTRINGS:
                    assert bad not in lowered, (
                        f"{dc.__name__}.{f.name} looks like a prose field "
                        f"(matched forbidden substring {bad!r}) — THE WALL forbids it"
                    )

    def test_dataclass_fields_are_a_whitelisted_fact_subset(self):
        for dc in _ALL_DATACLASSES:
            actual = {f.name for f in dataclasses.fields(dc)}
            allowed = EXPECTED_FACT_FIELDS[dc]
            extra = actual - allowed
            assert not extra, (
                f"{dc.__name__} declares non-whitelisted field(s) {sorted(extra)} — "
                f"add them to EXPECTED_FACT_FIELDS only after confirming each is a "
                f"FACT (never prose), per THE WALL"
            )

    def test_equipment_name_field_is_name_not_description(self):
        field_names = {f.name for f in dataclasses.fields(CatalogEquipment)}
        assert "name" in field_names
        assert "description" not in field_names


class TestSkillFacts:
    def test_attribute_difficulty_split(self):
        s = library._build_skill(SKILL_ROW, book="Basic Set")
        assert s.attribute == "DX"
        assert s.difficulty == "Hard"

    def test_average_code_maps(self):
        row = dict(SKILL_ROW, difficulty="iq/a")
        s = library._build_skill(row, book="Basic Set")
        assert s.attribute == "IQ"
        assert s.difficulty == "Average"

    def test_reference_mapped_verbatim_to_page(self):
        s = library._build_skill(SKILL_ROW, book="Basic Set")
        assert s.page == "B208"

    def test_core_facts_preserved(self):
        s = library._build_skill(SKILL_ROW, book="Basic Set")
        assert s.name == "Broadsword"
        assert s.points == 8
        assert s.book == "Basic Set"
        # defaults are a mechanical relation, kept
        assert s.defaults == SKILL_ROW["defaults"]

    def test_specialization_template_token_passthrough(self):
        s = library._build_skill(SKILL_ROW, book="Basic Set")
        assert "@Specialty@" not in (s.name or "")  # token never corrupts the name

    def test_template_token_span_stripped_from_name_not_mangled(self):
        # sanitize_name alone leaves residue ("Bind Spirit (@Spirit@)" -> "Bind
        # Spirit Spirit"); the whole token span must be stripped first
        s = library._build_skill(
            {"name": "Bind Spirit (@Spirit@)", "difficulty": "iq/h", "reference": "M1"},
            book="Magic",
        )
        assert s.name == "Bind Spirit"
        assert "@" not in s.name and "Spirit (" not in s.name

    def test_embedded_template_token_name_no_residue(self):
        s = library._build_skill(
            {"name": "Wrench @Limb@", "difficulty": "dx/h", "reference": "B1"}, book="B"
        )
        assert s.name == "Wrench"

    def test_equipment_template_token_description_cleaned(self):
        e = library._build_equipment({"description": "Potion of @Effect@", "reference": "B1"}, book="B")
        assert "@" not in e.name and "Effect" not in e.name

    def test_no_prose_value_anywhere_on_skill(self):
        s = library._build_skill(SKILL_ROW, book="Basic Set")
        _assert_no_prose(s)


class TestSpellFacts:
    def test_attribute_difficulty_split_very_hard(self):
        sp = library._build_spell(SPELL_ROW, book="Magic")
        assert sp.difficulty == "Very Hard"

    def test_college_is_kept_as_fact(self):
        sp = library._build_spell(SPELL_ROW, book="Magic")
        # array preserved or joined — either way "Plant" is present
        assert "Plant" in (sp.college if isinstance(sp.college, str) else ",".join(sp.college))

    def test_spell_specific_facts_verbatim(self):
        sp = library._build_spell(SPELL_ROW, book="Magic")
        assert sp.casting_cost == "Varies"
        assert sp.maintenance == "Varies"
        assert sp.casting_time == "2 sec"
        assert sp.duration == "1 min"
        assert sp.spell_class == "Regular"
        assert sp.page == "M86"
        assert sp.book == "Magic"

    def test_no_prose_value_anywhere_on_spell(self):
        sp = library._build_spell(SPELL_ROW, book="Magic")
        _assert_no_prose(sp)


class TestTraitFacts:
    def test_points_and_page(self):
        t = library._build_trait(TRAIT_ROW, book="Basic Set")
        assert t.name == "Absent-Mindedness"
        assert t.points == -15
        assert t.page == "B122"
        assert t.book == "Basic Set"

    def test_no_prose_value_anywhere_on_trait(self):
        t = library._build_trait(TRAIT_ROW, book="Basic Set")
        _assert_no_prose(t)
        for f in dataclasses.fields(t):
            assert getattr(t, f.name) != _PROSE


class TestTechniqueFacts:
    def test_bare_difficulty_decoded(self):
        tch = library._build_technique(TECHNIQUE_ROW, book="Basic Set")
        assert tch.difficulty == "Hard"

    def test_default_base_skill_kept(self):
        tch = library._build_technique(TECHNIQUE_ROW, book="Basic Set")
        # default (singular) is a mechanical fact — base skill name preserved
        assert tch.default == TECHNIQUE_ROW["default"]
        assert tch.page == "B232"
        assert tch.book == "Basic Set"

    def test_no_prose_value_anywhere_on_technique(self):
        tch = library._build_technique(TECHNIQUE_ROW, book="Basic Set")
        _assert_no_prose(tch)


class TestEquipmentFacts:
    def test_name_comes_from_description_field(self):
        e = library._build_equipment(EQUIPMENT_ROW, book="Basic Set")
        assert e.name == "Thrusting Broadsword"

    def test_cost_weight_legality_facts(self):
        e = library._build_equipment(EQUIPMENT_ROW, book="Basic Set")
        assert e.cost == "600"
        assert e.weight == "3 lb"
        assert e.legality == "3"
        assert e.page == "B271"

    def test_damage_fact_extracted(self):
        e = library._build_equipment(EQUIPMENT_ROW, book="Basic Set")
        # resolved damage string is a fact (calc.damage) — keep it
        assert e.damage == "sw+1 cut"
        assert e.reach == "1"

    def test_no_prose_value_anywhere_on_equipment(self):
        e = library._build_equipment(EQUIPMENT_ROW, book="Basic Set")
        _assert_no_prose(e)
        # weapons[].usage_notes prose must not survive into damage/reach/etc.
        for f in dataclasses.fields(e):
            assert getattr(e, f.name) != _PROSE

    def test_formula_cost_weight_resolves_via_calc(self):
        """formula base_value/base_weight resolves via calc, never leaks the raw expression."""
        row = {
            "description": "Agate, @carats@ carat",
            "base_value": "5*(@carats@*@carats@+4*@carats@)",
            "base_weight": "`${@carats@ * 0.2}g`",
            "calc": {"value": 25, "extended_value": 25, "weight": "0.0004 lb"},
            "reference": "B1",
        }
        e = library._build_equipment(row, book="B")
        assert "@" not in e.cost and e.cost == "25"
        assert "@" not in e.weight and e.weight == "0.0004 lb"

    def test_formula_without_calc_is_omitted_not_leaked(self):
        row = {"description": "X", "base_value": "2000000 * @weight@",
               "base_weight": "100 + @users@ * 10", "reference": "B1"}
        e = library._build_equipment(row, book="B")
        assert e.cost == "" and e.weight == ""

    def test_plain_cost_weight_unchanged(self):
        e = library._build_equipment(
            {"description": "Sword", "base_value": "600", "base_weight": "3 lb",
             "reference": "B1"}, book="B")
        assert e.cost == "600" and e.weight == "3 lb"


class TestRowClassificationAndRecursion:
    def test_container_header_not_emitted_child_is(self):
        out: list = []
        library._walk_skl_rows([SKL_CONTAINER], out, book="Basic Set")
        names = [x.name for x in out]
        assert "Melee Weapon Techniques" not in names
        assert "Disarming" in names

    def test_skill_vs_technique_discrimination(self):
        out_skills: list = []
        out_techs: list = []
        library._walk_skl_rows([SKILL_ROW], out_skills, book="Basic Set")
        library._walk_skl_rows([TECHNIQUE_ROW], out_techs, book="Basic Set")
        assert any(isinstance(x, CatalogSkill) for x in out_skills)
        assert any(isinstance(x, CatalogTechnique) for x in out_techs)


class TestRealLibrary:
    def test_real_library_has_skills_if_present(self):
        default_root = library.DEFAULT_LIBRARY_ROOT
        if not Path(default_root).is_dir():
            pytest.skip(f"vendored library not present at {default_root}")
        cat = load_library()
        assert "skills" in cat
        assert len(cat["skills"]) > 0
        for sk in cat["skills"]:
            _assert_no_prose(sk)


class TestSpellTerseFactCap:
    """fact fields holding rules-sentence prose are dropped at load (the wall)."""

    def test_prose_casting_cost_dropped(self):
        sp = library._build_spell({
            "name": "Heal", "difficulty": "iq/h", "reference": "M1",
            "casting_cost": "1 to stop bleeding on a normal wound; 10 to stabilize a mortal wound",
        }, book="Magic")
        assert sp.casting_cost == ""

    def test_prose_duration_dropped(self):
        sp = library._build_spell({
            "name": "Curse", "difficulty": "iq/h", "reference": "M1",
            "duration": "Lasting, until subject dies, fails at suicide and resists, or is saved",
        }, book="Magic")
        assert sp.duration == ""

    def test_multiword_phrase_resist_dropped(self):
        sp = library._build_spell({
            "name": "Ward", "difficulty": "iq/h", "reference": "M1",
            "resist": "Attempts to tamper with its subject spell",
        }, book="Magic")
        assert sp.resist == ""

    def test_terse_facts_kept(self):
        sp = library._build_spell({
            "name": "Fireball", "difficulty": "iq/h", "reference": "M1",
            "casting_cost": "Varies", "casting_time": "1 sec",
            "duration": "Instantaneous", "resist": "HT", "maintenance_cost": "2",
        }, book="Magic")
        assert sp.casting_cost == "Varies" and sp.casting_time == "1 sec"
        assert sp.duration == "Instantaneous" and sp.resist == "HT"
        assert sp.maintenance == "2"


class TestSpellCollegeShape:
    def test_multi_college_list_preserved(self):
        sp = library._build_spell(dict(SPELL_ROW, college=["Fire", "Air", "Water"]), book="Magic")
        assert sp.college == ["Fire", "Air", "Water"]

    def test_string_college_coerced_to_list(self):
        sp = library._build_spell(dict(SPELL_ROW, college="Necromantic"), book="Magic")
        assert sp.college == ["Necromantic"]

    def test_missing_college_is_empty_list(self):
        row = {k: v for k, v in SPELL_ROW.items() if k != "college"}
        sp = library._build_spell(row, book="Magic")
        assert sp.college == []


class TestLoaderEncodingAndResilience:
    @staticmethod
    def _write(root: Path, rel: str, content: str) -> Path:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def test_utf8_names_load_intact(self, tmp_path):
        """loader forces utf-8; a cp1252 default would mangle these."""
        rows = {"rows": [
            {"name": "Mêlée — Düsterland", "base_points": -5, "reference": "B1",
             "tags": ["Tëst"]},
        ]}
        self._write(tmp_path, "Basic Set/Basic Set Traits.adq",
                    json.dumps(rows, ensure_ascii=False))
        cat = load_library(tmp_path)
        names = [t.name for t in cat["traits"]]
        assert "Mêlée — Düsterland" in names
        assert cat["traits"][0].tags == ["Tëst"]

    def test_malformed_json_file_skipped_others_still_load(self, tmp_path):
        self._write(tmp_path, "Bk/Bk Skills.skl",
                    json.dumps({"rows": [{"name": "Good Skill", "difficulty": "dx/e",
                                          "reference": "B1"}]}))
        self._write(tmp_path, "Bk/Bk Spells.spl", "{ this is not valid json,,,")
        cat = load_library(tmp_path)  # must not raise
        assert any(s.name == "Good Skill" for s in cat["skills"])
        assert cat["spells"] == []

    def test_file_without_rows_key_yields_nothing(self, tmp_path):
        self._write(tmp_path, "Bk/Bk Traits.adq", json.dumps({"version": 5}))
        cat = load_library(tmp_path)
        assert cat["traits"] == []

    def test_missing_root_returns_empty_catalog(self, tmp_path):
        cat = load_library(tmp_path / "does-not-exist")
        assert cat == {"skills": [], "traits": [], "spells": [],
                       "equipment": [], "techniques": []}

    def test_skl_splits_into_skills_and_techniques(self, tmp_path):
        rows = {"rows": [
            {"name": "A Skill", "difficulty": "dx/h", "reference": "B1"},
            {"name": "A Technique", "difficulty": "h",
             "default": {"type": "skill", "name": "A Skill", "modifier": -2},
             "reference": "B2"},
        ]}
        self._write(tmp_path, "Bk/Bk Skills.skl", json.dumps(rows))
        cat = load_library(tmp_path)
        assert any(s.name == "A Skill" for s in cat["skills"])
        assert any(t.name == "A Technique" for t in cat["techniques"])
        assert not any(s.name == "A Technique" for s in cat["skills"])
        assert not any(t.name == "A Skill" for t in cat["techniques"])

    def test_non_catalog_extensions_ignored(self, tmp_path):
        self._write(tmp_path, "Bk/Bk Skills.skl",
                    json.dumps({"rows": [{"name": "Real", "difficulty": "dx/e", "reference": "B1"}]}))
        self._write(tmp_path, "Bk/notes.md", "# prose that must never load")
        self._write(tmp_path, "Bk/sheet.gcs", json.dumps({"rows": [{"name": "Nope"}]}))
        cat = load_library(tmp_path)
        names = [s.name for s in cat["skills"]]
        assert names == ["Real"]


def _assert_no_prose(obj) -> None:
    for f in dataclasses.fields(obj):
        val = getattr(obj, f.name)
        text = _stringify(val)
        for prose in _PROSE_STRINGS:
            assert prose not in text, (
                f"{type(obj).__name__}.{f.name} leaked prose: {val!r}"
            )


def _stringify(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return " ".join(_stringify(v) for v in val.values())
    if isinstance(val, (list, tuple, set)):
        return " ".join(_stringify(v) for v in val)
    return str(val)
