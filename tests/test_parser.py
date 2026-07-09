"""Tests for GCS v5 JSON parser."""

import pytest
from gurps_bot.gcs.parser import GCSParseError, parse_gcs


class TestParseGCSRobustness:
    """Malformed-but-valid JSON must surface as GCSParseError (which the import
    command catches cleanly) or be tolerated — never an uncaught
    AttributeError / TypeError / RecursionError reaching the user."""

    @pytest.mark.parametrize("bad", [["a", "list"], "a string", 42, None])
    def test_non_dict_top_level_raises_gcsparseerror(self, bad):
        with pytest.raises(GCSParseError):
            parse_gcs(bad)

    def test_collection_field_wrong_type_is_tolerated(self):
        # attributes/skills/traits as a non-list must NOT crash (the old code did
        # `for attr in "nope"` -> AttributeError); coerce to empty, parse the rest.
        char = parse_gcs({
            "version": 5, "profile": {"name": "X"},
            "attributes": "nope", "skills": 42, "traits": None, "spells": {},
        })
        assert char.name == "X"
        assert char.attributes == [] and char.skills == []
        assert char.traits == [] and char.spells == []

    def test_non_dict_items_in_list_are_skipped(self):
        char = parse_gcs({
            "version": 5, "profile": {"name": "X"},
            "skills": ["junk", 42, None,
                       {"name": "Real", "difficulty": "dx/a", "calc": {"level": 12}}],
        })
        assert [s.name for s in char.skills] == ["Real"]

    def test_deeply_nested_children_raises_not_recursionerror(self):
        node = {"name": "leaf", "difficulty": "dx/a", "calc": {"level": 10}}
        for _ in range(500):
            node = {"name": "grp", "children": [node]}
        with pytest.raises(GCSParseError):
            parse_gcs({"version": 5, "profile": {"name": "X"}, "skills": [node]})

    def test_trait_local_notes_dropped_copyright_wall(self):
        char = parse_gcs({
            "version": 5, "profile": {"name": "X"},
            "traits": [{
                "name": "Acrophobia", "base_points": -10,
                "local_notes": "You suffer from fear of heights; roll vs self-control.",
                "calc": {"points": -10},
            }],
        })
        assert char.traits[0].notes == ""

    def test_numeric_fields_coerced_to_int(self):
        char = parse_gcs({
            "version": 5, "profile": {"name": "X"}, "total_points": "150",
            "skills": [{"name": "S", "difficulty": "dx/a", "points": 3.7,
                        "calc": {"level": 12}}],
            "traits": [{"name": "T", "calc": {"points": "abc"}}],
            "equipment": [{"description": "E", "quantity": 2.9, "calc": {}}],
        })
        assert char.total_points == 150
        assert char.skills[0].points == 3 and char.skills[0].level == 12
        assert char.traits[0].points == 0          # junk 'abc' -> default
        assert char.equipment[0]["quantity"] == 2

    def test_coerced_values_render_without_crash(self):
        from gurps_bot.ui.formatters import format_equipment_line, format_trait_line
        char = parse_gcs({
            "version": 5, "profile": {"name": "X"},
            "traits": [{"name": "T", "calc": {"points": 2.9}}],
            "equipment": [{"description": "E", "quantity": 3.5, "calc": {}}],
        })
        # :+d (trait) and qty>1 (equipment) would raise on a float; coercion fixes it
        format_trait_line(char.traits[0].name, char.traits[0].points, char.traits[0].level)
        format_equipment_line(char.equipment[0]["description"],
                              char.equipment[0]["quantity"], "1 lb", True)

    def test_item_count_cap_rejects_dos_sized_sheet(self):
        # A 5MB file can declare ~250k minimal items -> ~250k ORM inserts; cap it.
        skills = [{"name": f"S{i}", "difficulty": "dx/e", "calc": {"level": 1}}
                  for i in range(4100)]
        with pytest.raises(GCSParseError):
            parse_gcs({"version": 5, "profile": {"name": "X"}, "skills": skills})

    def test_long_character_name_capped(self):
        # An unbounded name overflows the embed title (256) -> post-commit HTTP 400.
        char = parse_gcs({"version": 5, "profile": {"name": "A" * 500}})
        assert len(char.name) <= 100


class TestParseGCS:
    def test_parse_basic_fields(self, sample_gcs_data):
        char = parse_gcs(sample_gcs_data)
        assert char.name == "Sir Brannar"
        assert char.total_points == 150

    def test_parse_profile(self, sample_gcs_data):
        char = parse_gcs(sample_gcs_data)
        assert char.profile["name"] == "Sir Brannar"
        assert char.profile["gender"] == "Male"

    def test_parse_attributes(self, sample_gcs_data):
        char = parse_gcs(sample_gcs_data)
        attrs = {a.attr_id: a for a in char.attributes}
        assert attrs["st"].value == 13
        assert attrs["dx"].value == 12
        assert attrs["iq"].value == 10
        assert attrs["ht"].value == 11
        assert attrs["hp"].current == 13
        assert attrs["fp"].current == 11
        assert attrs["basic_speed"].value == 5.75
        assert attrs["basic_move"].value == 5

    def test_parse_skills(self, sample_gcs_data):
        char = parse_gcs(sample_gcs_data)
        skills = {s.name: s for s in char.skills}
        assert "Broadsword" in skills
        assert skills["Broadsword"].level == 14
        assert skills["Broadsword"].relative_level == "DX+2"
        assert skills["Broadsword"].difficulty == "dx/a"
        assert skills["Broadsword"].points == 8

    def test_parse_skills_in_container(self, sample_gcs_data):
        char = parse_gcs(sample_gcs_data)
        skills = {s.name: s for s in char.skills}
        assert "Stealth" in skills
        assert skills["Stealth"].level == 12

    def test_parse_skill_specialization(self, sample_gcs_data):
        char = parse_gcs(sample_gcs_data)
        shield = next(s for s in char.skills if s.name == "Shield")
        assert shield.specialization == "Shield"

    def test_parse_spells(self, sample_gcs_data):
        char = parse_gcs(sample_gcs_data)
        assert len(char.spells) == 1
        spell = char.spells[0]
        assert spell.name == "Ignite Fire"
        assert spell.college == "Fire"
        assert spell.casting_cost == "1-3"
        assert spell.level == 10

    def test_parse_traits(self, sample_gcs_data):
        char = parse_gcs(sample_gcs_data)
        traits = {t.name: t for t in char.traits}
        assert "Combat Reflexes" in traits
        assert traits["Combat Reflexes"].points == 15
        assert "Sense of Duty" in traits
        assert traits["Sense of Duty"].points == -5

    def test_parse_trait_in_container(self, sample_gcs_data):
        char = parse_gcs(sample_gcs_data)
        bad_temper = next(t for t in char.traits if t.name == "Bad Temper")
        assert bad_temper.group_name == "Disadvantages"
        assert bad_temper.points == -10

    def test_parse_trait_with_weapon(self, sample_gcs_data):
        char = parse_gcs(sample_gcs_data)
        claws = next(t for t in char.traits if t.name == "Claws, Sharp")
        assert claws.has_weapon is True
        assert len(claws.weapons) == 1
        assert claws.weapons[0]["usage"] == "Slash"
        assert claws.weapons[0]["damage"] == "1d-1 cut"

    def test_parse_equipment(self, sample_gcs_data):
        char = parse_gcs(sample_gcs_data)
        assert len(char.equipment) == 2
        sword = next(e for e in char.equipment if e["description"] == "Thrusting Broadsword")
        assert sword["equipped"] is True
        assert len(sword["weapons"]) == 2

    def test_parse_calc(self, sample_gcs_data):
        char = parse_gcs(sample_gcs_data)
        assert char.calc["swing"] == "2d"
        assert char.calc["thrust"] == "1d"
        assert char.calc["dodge"] == [8, 7, 6, 5, 4]

    def test_reject_wrong_version(self, sample_gcs_data):
        sample_gcs_data["version"] = 4
        with pytest.raises(GCSParseError, match="version"):
            parse_gcs(sample_gcs_data)

    def test_reject_no_name(self, sample_gcs_data):
        sample_gcs_data["profile"]["name"] = ""
        with pytest.raises(GCSParseError, match="no name"):
            parse_gcs(sample_gcs_data)

    def test_handles_missing_optional_fields(self):
        data = {
            "version": 5,
            "id": "minimal",
            "total_points": 0,
            "profile": {"name": "Minimal"},
            "attributes": [],
        }
        char = parse_gcs(data)
        assert char.name == "Minimal"
        assert char.skills == []
        assert char.spells == []
        assert char.traits == []


class TestParserContainerAndLevelBranches:
    """Branches the happy-path fixture doesn't reach: meta-trait containers,
    leveled traits, string-typed spell colleges, other_equipment merge,
    nested equipment, and ranged-weapon field extraction."""

    def test_meta_trait_container_emits_one_trait(self, sample_gcs_data):
        # A meta_trait container is itself one trait; its children are NOT
        # emitted separately (contrast the plain "Disadvantages" container).
        sample_gcs_data["traits"].append({
            "name": "Vampirism",
            "container_type": "meta_trait",
            "tags": ["Disadvantage"],
            "calc": {"points": -10},
            "children": [
                {"name": "Dependency", "base_points": -5, "calc": {"points": -5}},
                {"name": "Dread", "base_points": -5, "calc": {"points": -5}},
            ],
        })
        char = parse_gcs(sample_gcs_data)
        names = [t.name for t in char.traits]
        assert "Vampirism" in names
        assert "Dependency" not in names
        vamp = next(t for t in char.traits if t.name == "Vampirism")
        assert vamp.points == -10

    def test_leveled_trait_carries_its_level(self, sample_gcs_data):
        sample_gcs_data["traits"].append({
            "name": "Magery",
            "can_level": True,
            "levels": 3,
            "tags": ["Advantage"],
            "calc": {"points": 35},
        })
        char = parse_gcs(sample_gcs_data)
        magery = next(t for t in char.traits if t.name == "Magery")
        assert magery.level == 3

    def test_spell_college_as_plain_string(self, sample_gcs_data):
        # GCS normally emits college as a list; tolerate a bare string.
        sample_gcs_data["spells"].append({
            "name": "Lightning",
            "college": "Air",
            "difficulty": "iq/h",
            "casting_cost": "1-8",
            "calc": {"level": 12, "rsl": "IQ+2"},
        })
        char = parse_gcs(sample_gcs_data)
        lightning = next(s for s in char.spells if s.name == "Lightning")
        assert lightning.college == "Air"

    def test_other_equipment_folds_into_equipment(self, sample_gcs_data):
        sample_gcs_data["other_equipment"] = [
            {"description": "Torch", "quantity": 5, "equipped": False,
             "calc": {"extended_weight": "5 lb", "extended_value": 10}},
        ]
        char = parse_gcs(sample_gcs_data)
        assert "Torch" in [e["description"] for e in char.equipment]

    def test_nested_equipment_is_flattened(self, sample_gcs_data):
        sample_gcs_data["equipment"].append({
            "description": "Backpack",
            "quantity": 1,
            "equipped": True,
            "calc": {"extended_weight": "2 lb"},
            "children": [
                {"description": "Rope", "quantity": 1, "equipped": False,
                 "calc": {"extended_weight": "5 lb"}},
            ],
        })
        char = parse_gcs(sample_gcs_data)
        descs = [e["description"] for e in char.equipment]
        assert "Backpack" in descs
        assert "Rope" in descs

    def test_ranged_weapon_fields_are_extracted(self, sample_gcs_data):
        # Equipment weapons parse with include_ranged=True, so accuracy/range/
        # bulk/etc. are surfaced (trait weapons are melee-only and omit these).
        sample_gcs_data["equipment"].append({
            "description": "Longbow",
            "quantity": 1,
            "equipped": True,
            "calc": {"extended_weight": "3 lb"},
            "weapons": [
                {"id": "bow1", "usage": "Shoot", "accuracy": "3",
                 "range": "200/250", "rate_of_fire": "1", "shots": "1(2)",
                 "bulk": "-7", "strength": "11",
                 "calc": {"damage": "1d+2 imp", "level": 12}},
            ],
        })
        char = parse_gcs(sample_gcs_data)
        bow = next(e for e in char.equipment if e["description"] == "Longbow")
        w = bow["weapons"][0]
        assert w["accuracy"] == "3"
        assert w["range"] == "200/250"
        assert w["bulk"] == "-7"
        assert w["damage"] == "1d+2 imp"


class TestParserResilienceBranches:
    """Malformed-sheet tolerance branches (skip-and-continue, coercion)."""

    def _base(self, **extra):
        d = {"version": 5, "profile": {"name": "X"}}
        d.update(extra)
        return d

    def test_non_numeric_attr_value_coerced(self):
        char = parse_gcs(self._base(attributes=[{"attr_id": "st", "calc": {"value": "abc"}}]))
        st = next(a for a in char.attributes if a.attr_id == "st")
        assert st.value == 0.0

    def test_non_dict_attribute_skipped(self):
        char = parse_gcs(self._base(
            attributes=["not a dict", {"attr_id": "dx", "calc": {"value": 12}}]))
        assert [a.attr_id for a in char.attributes] == ["dx"]

    def test_skill_without_calc_or_difficulty_skipped(self):
        char = parse_gcs(self._base(skills=[{"name": "Placeholder"}]))
        assert char.skills == []

    def test_spell_children_flattened(self):
        char = parse_gcs(self._base(spells=[
            {"name": "Grp", "children": [
                {"name": "Fireball", "difficulty": "IH", "calc": {"level": 12}}]}]))
        assert [s.name for s in char.spells] == ["Fireball"]

    def test_non_dict_spell_skipped(self):
        char = parse_gcs(self._base(
            spells=["junk", {"name": "Light", "difficulty": "E", "calc": {"level": 10}}]))
        assert [s.name for s in char.spells] == ["Light"]

    def test_spell_without_calc_or_difficulty_skipped(self):
        char = parse_gcs(self._base(spells=[{"name": "Header"}]))
        assert char.spells == []

    def test_non_dict_trait_skipped(self):
        char = parse_gcs(self._base(traits=["junk", {"name": "Luck", "calc": {"points": 15}}]))
        assert [t.name for t in char.traits] == ["Luck"]

    def test_non_dict_equipment_skipped(self):
        char = parse_gcs(self._base(equipment=["junk", {"description": "Sword", "calc": {}}]))
        assert [e["description"] for e in char.equipment] == ["Sword"]

    def test_spell_nesting_too_deep_raises(self):
        node = {"name": "leaf", "difficulty": "E", "calc": {"level": 10}}
        for _ in range(70):
            node = {"name": "grp", "children": [node]}
        with pytest.raises(GCSParseError, match="too deeply"):
            parse_gcs(self._base(spells=[node]))

    def test_trait_nesting_too_deep_raises(self):
        node = {"name": "leaf", "calc": {"points": 1}}
        for _ in range(70):
            node = {"name": "grp", "children": [node]}
        with pytest.raises(GCSParseError, match="too deeply"):
            parse_gcs(self._base(traits=[node]))

    def test_equipment_nesting_too_deep_raises(self):
        node = {"description": "leaf", "calc": {}}
        for _ in range(70):
            node = {"description": "box", "children": [node]}
        with pytest.raises(GCSParseError, match="too deeply"):
            parse_gcs(self._base(equipment=[node]))
