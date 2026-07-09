"""Deterministic edge sweeps for gcs.parser (no Hypothesis); boundaries pinned relative to the module caps."""

from __future__ import annotations

import math

import pytest

from gurps_bot.gcs.parser import (
    _MAX_ITEMS_PER_CATEGORY,
    _MAX_NEST_DEPTH,
    GCSParseError,
    _as_float,
    _as_int,
    parse_gcs,
)


def _char(**extra) -> dict:
    d = {"version": 5, "profile": {"name": "X"}}
    d.update(extra)
    return d


def _wrap_in_containers(leaf: dict, depth: int, child_key: str = "children") -> dict:
    node = leaf
    for _ in range(depth):
        node = {"name": "grp", child_key: [node]}
    return node


class TestAsIntCoercion:
    """Pin _as_int's exact rounding/parsing; the example suite only checks 3.7 and 'abc'."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            # ints pass through
            (0, 0),
            (-7, -7),
            (42, 42),
            # floats truncate TOWARD ZERO (int(), not floor/round)
            (3.9, 3),
            (-3.9, -3),
            (2.0, 2),
            (-0.5, 0),
            # numeric strings: plain integers parse (int() strips surrounding ws)
            ("15", 15),
            ("  3  ", 3),
            ("-8", -8),
            # bool is an int subclass -> True/False coerce to 1/0
            (True, 1),
            (False, 0),
        ],
    )
    def test_recognized_numeric_inputs(self, value, expected):
        assert _as_int(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            "abc",          # non-numeric text
            "3.7",          # int() rejects a decimal STRING (contrast float 3.7)
            "0x10",         # hex string not parsed in base-10
            "1e3",          # scientific string not an int literal
            "",             # empty
            "   ",          # whitespace only
            None,           # missing
            [],             # wrong-typed collection
            {},
            ("tuple",),
            object(),
        ],
    )
    def test_junk_falls_back_to_default(self, value):
        assert _as_int(value) == 0
        # the explicit default is honored, not just the implicit 0
        assert _as_int(value, default=-1) == -1

    def test_default_only_applies_on_failure(self):
        # a real value ignores the supplied default
        assert _as_int(5, default=99) == 5
        assert _as_int("5", default=99) == 5


class TestAsFloatCoercion:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (0, 0.0),
            (3, 3.0),
            (5.75, 5.75),
            ("5.75", 5.75),
            ("  1.5 ", 1.5),
            ("1e3", 1000.0),
            (True, 1.0),
            (False, 0.0),
        ],
    )
    def test_recognized_numeric_inputs(self, value, expected):
        assert _as_float(value) == expected

    @pytest.mark.parametrize("value", ["abc", "", None, [], {}, "0x10"])
    def test_junk_falls_back_to_default(self, value):
        assert _as_float(value) == 0.0
        assert _as_float(value, default=-1.5) == -1.5

    def test_ieee_specials_pass_through_as_documented_behavior(self):
        # float() accepts 'inf'/'nan', so a crafted sheet can land a non-finite
        # attribute value; pinned so a future hardening is a conscious change
        assert _as_float("inf") == math.inf
        assert _as_float("-inf") == -math.inf
        assert math.isnan(_as_float("nan"))


class TestCoercionThroughParse:
    def test_bool_quantity_coerces_like_an_int(self):
        char = parse_gcs(_char(equipment=[{"description": "E", "quantity": True, "calc": {}}]))
        assert char.equipment[0]["quantity"] == 1

    def test_float_attribute_value_preserved_as_float(self):
        char = parse_gcs(_char(attributes=[{"attr_id": "spd", "calc": {"value": 5.75}}]))
        spd = next(a for a in char.attributes if a.attr_id == "spd")
        assert spd.value == 5.75
        assert isinstance(spd.value, float)

    @pytest.mark.parametrize("raw, expected", [("3.7", 0), (3.7, 3), ("12", 12), (True, 1)])
    def test_skill_points_coercion_matrix(self, raw, expected):
        char = parse_gcs(_char(skills=[
            {"name": "S", "difficulty": "dx/a", "points": raw, "calc": {"level": 1}}]))
        assert char.skills[0].points == expected

    def test_attribute_current_none_stays_none_but_zero_coerces(self):
        # 'current' is only set when present and not None; a present 0 must coerce
        # to 0.0 (a pool at 0 HP), NOT collapse to None.
        char = parse_gcs(_char(attributes=[
            {"attr_id": "hp", "calc": {"value": 10, "current": 0}},
            {"attr_id": "st", "calc": {"value": 10}},
        ]))
        by_id = {a.attr_id: a for a in char.attributes}
        assert by_id["hp"].current == 0.0
        assert by_id["st"].current is None


class TestNestingDepthBoundary:
    """Pin the exact depth edge; an off-by-one in the guard passes the 70/500-level tests."""

    SKILL_LEAF = {"name": "L", "difficulty": "dx/a", "calc": {"level": 1}}
    SPELL_LEAF = {"name": "L", "difficulty": "iq/e", "calc": {"level": 1}}
    TRAIT_LEAF = {"name": "L", "calc": {"points": 1}}
    EQUIP_LEAF = {"description": "L", "calc": {}}

    @pytest.mark.parametrize(
        "category, leaf",
        [
            ("skills", SKILL_LEAF),
            ("spells", SPELL_LEAF),
            ("traits", TRAIT_LEAF),
            ("equipment", EQUIP_LEAF),
        ],
    )
    def test_at_max_depth_parses(self, category, leaf):
        # deepest allowed shape. skills/spells/traits flatten containers away
        # (one leaf out); equipment keeps each container as a row -> depth+1
        node = _wrap_in_containers(leaf, _MAX_NEST_DEPTH)
        char = parse_gcs(_char(**{category: [node]}))
        produced = getattr(char, category)
        if category == "equipment":
            assert len(produced) == _MAX_NEST_DEPTH + 1
        else:
            assert len(produced) == 1

    @pytest.mark.parametrize(
        "category, leaf",
        [
            ("skills", SKILL_LEAF),
            ("spells", SPELL_LEAF),
            ("traits", TRAIT_LEAF),
            ("equipment", EQUIP_LEAF),
        ],
    )
    def test_one_past_max_depth_raises(self, category, leaf):
        node = _wrap_in_containers(leaf, _MAX_NEST_DEPTH + 1)
        with pytest.raises(GCSParseError, match="too deeply"):
            parse_gcs(_char(**{category: [node]}))


class TestItemCapBoundary:
    def _flat_skills(self, n):
        return [{"name": f"S{i}", "difficulty": "dx/e", "calc": {"level": 1}} for i in range(n)]

    def test_exactly_at_cap_is_accepted(self):
        # the cap is "reject when len >= MAX before appending"; a list of exactly
        # MAX items therefore fits (the MAX-th append sees len == MAX-1).
        char = parse_gcs(_char(skills=self._flat_skills(_MAX_ITEMS_PER_CATEGORY)))
        assert len(char.skills) == _MAX_ITEMS_PER_CATEGORY

    def test_one_over_cap_raises(self):
        with pytest.raises(GCSParseError, match="too many skills"):
            parse_gcs(_char(skills=self._flat_skills(_MAX_ITEMS_PER_CATEGORY + 1)))

    @pytest.mark.parametrize("kind", ["skills", "spells", "traits", "attributes"])
    def test_cap_message_names_the_category(self, kind):
        if kind == "attributes":
            items = [{"attr_id": f"a{i}", "calc": {"value": 1}}
                     for i in range(_MAX_ITEMS_PER_CATEGORY + 1)]
        elif kind == "skills":
            items = self._flat_skills(_MAX_ITEMS_PER_CATEGORY + 1)
        elif kind == "spells":
            items = [{"name": f"S{i}", "difficulty": "e", "calc": {"level": 1}}
                     for i in range(_MAX_ITEMS_PER_CATEGORY + 1)]
        else:  # traits
            items = [{"name": f"T{i}", "calc": {"points": 1}}
                     for i in range(_MAX_ITEMS_PER_CATEGORY + 1)]
        with pytest.raises(GCSParseError, match=f"too many {kind}"):
            parse_gcs(_char(**{kind: items}))

    def test_skills_cap_counts_across_containers_shared_accumulator(self):
        # skills/spells/traits thread ONE `out` list through recursion, so items
        # split across sibling containers still sum toward the cap. Pin it.
        half = _MAX_ITEMS_PER_CATEGORY - 1
        data = _char(skills=[
            {"name": "g1", "children": self._flat_skills(half)},
            {"name": "g2", "children": self._flat_skills(5)},
        ])
        with pytest.raises(GCSParseError, match="too many skills"):
            parse_gcs(data)

    def test_equipment_cap_is_per_recursion_level_not_global(self):
        # _flatten_equipment builds a fresh `result` per call: children are
        # capped per level, so the grand total can exceed the per-level cap —
        # unlike the shared-accumulator categories above
        top = [{"description": f"E{i}", "calc": {}} for i in range(3)]
        top[0]["children"] = [{"description": f"C{j}", "calc": {}} for j in range(4)]
        char = parse_gcs(_char(equipment=top))
        assert len(char.equipment) == 3 + 4  # parent appears before its children


class TestMixedJunkAtDepth:
    @pytest.mark.parametrize("junk", ["str", 42, 3.14, None, True, ["nested"], {"no": "marker"}])
    def test_junk_sibling_does_not_drop_the_real_skill(self, junk):
        char = parse_gcs(_char(skills=[
            junk,
            {"name": "Real", "difficulty": "dx/a", "calc": {"level": 9}},
        ]))
        assert [s.name for s in char.skills] == ["Real"]

    def test_junk_inside_container_children_is_skipped_group_preserved(self):
        char = parse_gcs(_char(traits=[
            {"name": "Disadvantages", "children": [
                "junk", 99, None,
                {"name": "Bad Temper", "calc": {"points": -10}},
            ]},
        ]))
        assert [t.name for t in char.traits] == ["Bad Temper"]
        assert char.traits[0].group_name == "Disadvantages"

    def test_children_that_is_wrong_typed_collection_coerced_to_empty(self):
        # `children` present but not a list: _as_list -> [] -> the container
        # recurses over nothing rather than crashing.
        char = parse_gcs(_char(traits=[{"name": "Grp", "children": "oops"}]))
        assert char.traits == []

    def test_weapons_field_with_non_dict_entries_skipped(self):
        char = parse_gcs(_char(traits=[{
            "name": "T", "calc": {"points": 1},
            "weapons": ["junk", None, 5, {"usage": "Bite", "calc": {"damage": "1d"}}],
        }]))
        weapons = char.traits[0].weapons
        assert len(weapons) == 1
        assert weapons[0]["usage"] == "Bite"
        # has_weapon reflects the RAW presence of a weapons list, not parsed count
        assert char.traits[0].has_weapon is True


class TestUnicodeAndNames:
    @pytest.mark.parametrize(
        "name",
        ["Frodo", "Élodie", "Ñoño", "武士", "Σωκράτης", "Ívarr the Boneless"],
    )
    def test_unicode_names_survive(self, name):
        char = parse_gcs(_char(profile={"name": name}))
        assert char.name  # non-empty, not raised
        assert len(char.name) <= 100

    def test_long_unicode_name_capped_to_100_codepoints(self):
        char = parse_gcs(_char(profile={"name": "é" * 500}))
        assert len(char.name) == 100
        assert set(char.name) == {"é"}

    def test_unicode_in_skill_and_trait_names_passes_through(self):
        char = parse_gcs(_char(
            skills=[{"name": "Épée", "difficulty": "dx/a", "calc": {"level": 12}}],
            traits=[{"name": "高貴", "calc": {"points": 5}}],
        ))
        assert char.skills[0].name == "Épée"
        assert char.traits[0].name == "高貴"

    @pytest.mark.parametrize("bad_name", [123, ["a"], {"x": 1}, None, 3.5, True])
    def test_non_string_profile_name_raises_no_name(self, bad_name):
        with pytest.raises(GCSParseError, match="no name"):
            parse_gcs(_char(profile={"name": bad_name}))

    def test_whitespace_only_name_is_rejected_after_sanitize(self):
        with pytest.raises(GCSParseError, match="no name"):
            parse_gcs(_char(profile={"name": "   "}))

    def test_profile_not_a_dict_is_tolerated_then_no_name(self):
        # _as_dict("oops") -> {} -> no name -> clean GCSParseError, not AttributeError
        with pytest.raises(GCSParseError, match="no name"):
            parse_gcs(_char(profile="oops"))


class TestVersionGate:
    @pytest.mark.parametrize("version", [1, 2, 3, 4, 6, "5", None, "five", True])
    def test_non_five_versions_rejected(self, version):
        # The gate is value-inequality (`version != 5`). A string "5" and bool
        # True (True != 5) are rejected; the numeric-equality cases are pinned
        # separately below.
        with pytest.raises(GCSParseError, match="version"):
            parse_gcs({"version": version, "profile": {"name": "X"}})

    @pytest.mark.parametrize("version", [5, 5.0])
    def test_numeric_five_accepted_via_value_equality(self, version):
        # the gate is `!= 5`, so float 5.0 also passes; pinned so tightening to
        # a type check is a conscious change
        char = parse_gcs({"version": version, "profile": {"name": "X"}})
        assert char.name == "X"

    def test_missing_version_key_rejected(self):
        with pytest.raises(GCSParseError, match="version"):
            parse_gcs({"profile": {"name": "X"}})


class TestWeaponFieldPrecedence:
    def _trait_with_weapon(self, weapon):
        char = parse_gcs(_char(traits=[
            {"name": "T", "calc": {"points": 1}, "weapons": [weapon]}]))
        return char.traits[0].weapons[0]

    def test_calc_reach_wins_over_top_level(self):
        w = self._trait_with_weapon(
            {"usage": "U", "reach": "TOP", "calc": {"reach": "CALC", "damage": "1d"}})
        assert w["reach"] == "CALC"

    def test_top_level_reach_used_when_calc_absent(self):
        w = self._trait_with_weapon({"usage": "U", "reach": "TOP", "calc": {"damage": "1d"}})
        assert w["reach"] == "TOP"

    def test_parry_same_precedence_calc_then_top(self):
        w = self._trait_with_weapon(
            {"usage": "U", "parry": "TOP", "calc": {"parry": "CALC", "damage": "1d"}})
        assert w["parry"] == "CALC"
        w2 = self._trait_with_weapon({"usage": "U", "parry": "TOP", "calc": {"damage": "1d"}})
        assert w2["parry"] == "TOP"

    def test_trait_weapon_omits_ranged_only_fields(self):
        # trait weapons parse melee-only; ranged keys must NOT appear.
        w = self._trait_with_weapon({"usage": "U", "accuracy": "3", "calc": {"damage": "1d"}})
        for ranged_key in ("strength", "accuracy", "range", "rate_of_fire", "shots", "bulk"):
            assert ranged_key not in w

    def test_equipment_weapon_includes_ranged_fields(self):
        char = parse_gcs(_char(equipment=[{
            "description": "Bow", "calc": {},
            "weapons": [{"usage": "Shoot", "accuracy": "3", "range": "100",
                         "bulk": "-7", "calc": {"damage": "1d"}}],
        }]))
        w = char.equipment[0]["weapons"][0]
        assert w["accuracy"] == "3" and w["range"] == "100" and w["bulk"] == "-7"


class TestLeveledAndMetaTraits:
    def test_can_level_false_means_no_level(self):
        char = parse_gcs(_char(traits=[
            {"name": "T", "can_level": False, "levels": 3, "calc": {"points": 1}}]))
        assert char.traits[0].level is None

    def test_levels_zero_short_circuits_to_current_level(self):
        # `levels or calc.current_level`: a falsy levels:0 falls through to
        # current_level; with neither, level is None
        char = parse_gcs(_char(traits=[
            {"name": "T", "can_level": True, "levels": 0, "calc": {"points": 1}}]))
        assert char.traits[0].level is None

    def test_levels_zero_falls_through_to_current_level_when_present(self):
        char = parse_gcs(_char(traits=[
            {"name": "T", "can_level": True, "levels": 0,
             "calc": {"points": 1, "current_level": 4}}]))
        assert char.traits[0].level == 4

    def test_explicit_levels_win_over_current_level(self):
        char = parse_gcs(_char(traits=[
            {"name": "T", "can_level": True, "levels": 2,
             "calc": {"points": 1, "current_level": 9}}]))
        assert char.traits[0].level == 2

    def test_meta_trait_emits_self_and_drops_children(self):
        char = parse_gcs(_char(traits=[{
            "name": "Vampirism", "container_type": "meta_trait",
            "calc": {"points": -10},
            "children": [
                {"name": "Dependency", "calc": {"points": -5}},
                {"name": "Dread", "calc": {"points": -5}},
            ],
        }]))
        names = [t.name for t in char.traits]
        assert names == ["Vampirism"]
        assert char.traits[0].points == -10
        assert char.traits[0].level is None
        assert char.traits[0].notes == ""  # copyright wall

    def test_meta_trait_with_empty_children_still_emits_container(self):
        char = parse_gcs(_char(traits=[{
            "name": "Meta", "container_type": "meta_trait",
            "children": [], "calc": {"points": -7}}]))
        assert [t.name for t in char.traits] == ["Meta"]

    def test_plain_container_with_empty_children_emits_nothing(self):
        char = parse_gcs(_char(traits=[{"name": "Grp", "children": []}]))
        assert char.traits == []


class TestSpellCollege:
    def test_list_college_joined_with_comma_space(self):
        char = parse_gcs(_char(spells=[
            {"name": "S", "difficulty": "e", "calc": {"level": 1},
             "college": ["Fire", "Air"]}]))
        assert char.spells[0].college == "Fire, Air"

    def test_string_college_passes_through(self):
        char = parse_gcs(_char(spells=[
            {"name": "S", "difficulty": "e", "calc": {"level": 1}, "college": "Necromancy"}]))
        assert char.spells[0].college == "Necromancy"

    def test_non_string_college_members_stringified(self):
        # the join uses str(c); int/None members survive as text rather than crashing
        char = parse_gcs(_char(spells=[
            {"name": "S", "difficulty": "e", "calc": {"level": 1},
             "college": ["Fire", 1, None]}]))
        assert char.spells[0].college == "Fire, 1, None"

    def test_empty_college_list_becomes_empty_string(self):
        char = parse_gcs(_char(spells=[
            {"name": "S", "difficulty": "e", "calc": {"level": 1}, "college": []}]))
        assert char.spells[0].college == ""

    def test_missing_college_defaults_to_empty_list_then_empty_string(self):
        char = parse_gcs(_char(spells=[
            {"name": "S", "difficulty": "e", "calc": {"level": 1}}]))
        assert char.spells[0].college == ""


class TestCopyrightWall:
    @pytest.mark.parametrize(
        "trait",
        [
            {"name": "Leaf", "local_notes": "SJG prose here", "calc": {"points": 1}},
            {"name": "Leveled", "can_level": True, "levels": 2,
             "local_notes": "SJG prose", "calc": {"points": 5}},
            {"name": "Meta", "container_type": "meta_trait",
             "local_notes": "SJG prose", "calc": {"points": -10}, "children": []},
        ],
    )
    def test_local_notes_never_survives_on_any_trait_shape(self, trait):
        char = parse_gcs(_char(traits=[trait]))
        assert char.traits[0].notes == ""

    def test_notes_dropped_for_trait_nested_in_container(self):
        char = parse_gcs(_char(traits=[
            {"name": "Grp", "children": [
                {"name": "Inner", "local_notes": "drop me", "calc": {"points": 3}}]}]))
        inner = next(t for t in char.traits if t.name == "Inner")
        assert inner.notes == ""


class TestPlaceholderSkipRule:
    @pytest.mark.parametrize("category", ["skills", "spells"])
    @pytest.mark.parametrize("item_extra", [
        {},                              # neither calc nor difficulty
        {"calc": "not a dict"},          # calc present but wrong-typed -> {} -> empty
        {"calc": {}},                    # empty calc, no difficulty
    ])
    def test_item_without_calc_or_difficulty_skipped(self, category, item_extra):
        item = {"name": "Placeholder"}
        item.update(item_extra)
        char = parse_gcs(_char(**{category: [item]}))
        assert getattr(char, category) == []

    @pytest.mark.parametrize("category", ["skills", "spells"])
    def test_difficulty_alone_keeps_the_item(self, category):
        # difficulty present (even with empty calc) is enough to emit the row.
        char = parse_gcs(_char(**{category: [
            {"name": "Kept", "difficulty": "dx/a"}]}))
        produced = getattr(char, category)
        assert [getattr(x, "name") for x in produced] == ["Kept"]

    @pytest.mark.parametrize("category", ["skills", "spells"])
    def test_calc_alone_keeps_the_item(self, category):
        char = parse_gcs(_char(**{category: [
            {"name": "Kept", "calc": {"level": 5}}]}))
        produced = getattr(char, category)
        assert [getattr(x, "name") for x in produced] == ["Kept"]


class TestEquipmentMerge:
    def test_equipment_precedes_other_equipment_in_order(self):
        char = parse_gcs(_char(
            equipment=[{"description": "Carried", "calc": {}}],
            other_equipment=[{"description": "Stored", "calc": {}}],
        ))
        assert [e["description"] for e in char.equipment] == ["Carried", "Stored"]

    def test_other_equipment_wrong_typed_is_tolerated(self):
        char = parse_gcs(_char(
            equipment=[{"description": "Carried", "calc": {}}],
            other_equipment="oops",
        ))
        assert [e["description"] for e in char.equipment] == ["Carried"]

    def test_nested_equipment_flattens_parent_before_child(self):
        char = parse_gcs(_char(equipment=[{
            "description": "Backpack", "calc": {},
            "children": [{"description": "Rope", "calc": {}}],
        }]))
        assert [e["description"] for e in char.equipment] == ["Backpack", "Rope"]

    def test_equipment_defaults_when_calc_missing_keys(self):
        char = parse_gcs(_char(equipment=[{"description": "Bare", "calc": {}}]))
        e = char.equipment[0]
        assert e["quantity"] == 1            # default 1, not 0
        assert e["weight"] == "0 lb"
        assert e["value"] == 0
        assert e["equipped"] is False
        assert e["weapons"] == []
