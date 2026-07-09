from gurps_bot.mechanics.combat_constants import STATUS_ICONS, StatusEffect
from gurps_bot.ui.formatters import (
    format_attr_block,
    format_combatant_line,
    format_equipment_line,
    format_modifier_suffix,
    format_skill_line,
    format_spell_line,
    format_trait_line,
    paginate,
)

# masked-link phishing payload a crafted .gcs could plant in any name/desc field
_INJECT = "[Click here](https://evil.example)"


class TestFormatSkillLine:
    def test_basic_skill(self):
        line = format_skill_line("Broadsword", None, 14, "DX+2", 8)
        assert "`14`" in line
        assert "Broadsword" in line
        assert "[DX+2]" in line
        assert "8pts" in line

    def test_with_specialization(self):
        line = format_skill_line("Shield", "Shield", 13, "DX+1", 4)
        assert "Shield (Shield)" in line

    def test_escapes_markdown_link_injection_in_name(self):
        line = format_skill_line(_INJECT, None, 1, "DX", 1)
        # the live masked-link form must not survive — brackets/parens escaped
        assert "[Click here](https://evil.example)" not in line
        assert "\\[" in line or "\\(" in line


class TestFormatSpellLine:
    def test_with_college_and_cost(self):
        line = format_spell_line("Ignite Fire", 10, "Fire", "1-3")
        assert "`10`" in line
        assert "Ignite Fire" in line
        assert "Fire" in line
        assert "1-3" in line

    def test_without_college(self):
        line = format_spell_line("Generic Spell", 12, "", "2")
        assert "Generic Spell" in line
        assert "`12`" in line


class TestFormatTraitLine:
    def test_positive_points(self):
        line = format_trait_line("Combat Reflexes", 15, None)
        assert "Combat Reflexes" in line
        assert "[+15]" in line

    def test_negative_points(self):
        line = format_trait_line("Bad Temper", -10, None)
        assert "[-10]" in line

    def test_zero_points(self):
        line = format_trait_line("Feature", 0, None)
        assert "[0]" in line

    def test_with_level(self):
        line = format_trait_line("Magery", 35, 3)
        assert "Magery 3" in line
        assert "[+35]" in line

    def test_does_not_render_trait_notes(self):
        # copyright wall: trait local_notes are often verbatim SJG prose — never rendered
        line = format_trait_line("Acrophobia", -10, None)
        assert "fear" not in line.lower()  # no description prose anywhere

    def test_escapes_markdown_link_injection_in_name(self):
        line = format_trait_line(_INJECT, 1, None)
        assert "[Click here](https://evil.example)" not in line


class TestFormatEquipmentLine:
    def test_equipped(self):
        line = format_equipment_line("Broadsword", 1, "3 lb", True)
        assert line.startswith("+")
        assert "Broadsword" in line
        assert "3 lb" in line

    def test_unequipped(self):
        line = format_equipment_line("Rations", 1, "1 lb", False)
        assert line.startswith("-")

    def test_quantity(self):
        line = format_equipment_line("Arrows", 20, "1 lb", True)
        assert "x20" in line

    def test_escapes_markdown_link_injection_in_desc(self):
        line = format_equipment_line(_INJECT, 1, "1 lb", True)
        assert "[Click here](https://evil.example)" not in line


class TestFormatAttrBlock:
    def test_basic_output(self):
        attrs = {"st": 13, "dx": 12, "iq": 10, "ht": 11, "will": 10, "per": 10,
                 "hp": 13, "hp_current": 13, "fp": 11, "fp_current": 11,
                 "basic_speed": 5.75, "basic_move": 5}
        calc = {"swing": "2d", "thrust": "1d"}
        block = format_attr_block(attrs, calc)
        assert "**ST** 13" in block
        assert "**DX** 12" in block
        assert "**HP** 13/13" in block
        assert "**Speed** 5.75" in block
        assert "**Swing** 2d" in block


class TestPaginate:
    def test_single_page(self):
        text, page, total = paginate(["a", "b", "c"], 0, 10)
        assert text == "a\nb\nc"
        assert page == 1
        assert total == 1

    def test_multiple_pages(self):
        items = [f"item{i}" for i in range(25)]
        text, page, total = paginate(items, 0, 10)
        assert page == 1
        assert total == 3
        assert text.count("\n") == 9  # 10 items, 9 newlines

    def test_second_page(self):
        items = [f"item{i}" for i in range(25)]
        text, page, total = paginate(items, 1, 10)
        assert page == 2
        assert "item10" in text

    def test_empty_list(self):
        text, page, total = paginate([], 0, 10)
        assert text == "*None*"
        assert page == 1
        assert total == 1

    def test_page_bounds_clamping(self):
        items = ["a", "b", "c"]
        text, page, total = paginate(items, 99, 10)
        assert page == 1
        assert text == "a\nb\nc"


class TestFormatModifierSuffix:
    def test_positive(self):
        assert format_modifier_suffix(3) == " (+3)"

    def test_negative(self):
        assert format_modifier_suffix(-2) == " (-2)"

    def test_zero_is_empty_string(self):
        assert format_modifier_suffix(0) == ""


class TestFormatAttrBlockDefaults:
    """fallbacks: will/per -> iq, hp -> st, fp -> ht, missing primaries -> 10."""

    def test_secondary_pools_fall_back(self):
        block = format_attr_block({"st": 14, "dx": 10, "iq": 12, "ht": 11}, {})
        assert "**Will** 12" in block   # = iq
        assert "**Per** 12" in block    # = iq
        assert "**HP** 14/14" in block  # = st
        assert "**FP** 11/11" in block  # = ht

    def test_missing_primaries_default_to_10(self):
        block = format_attr_block({}, {})
        assert "**ST** 10" in block
        assert "**DX** 10" in block
        assert "**IQ** 10" in block
        # empty calc -> swing/thrust render the "?" placeholder
        assert "**Swing** ?" in block
        assert "**Thrust** ?" in block

    def test_damaged_pools_show_current_over_max(self):
        attrs = {"st": 13, "hp": 13, "hp_current": 5,
                 "ht": 11, "fp": 11, "fp_current": 4}
        block = format_attr_block(attrs, {"swing": "2d", "thrust": "1d"})
        assert "**HP** 5/13" in block
        assert "**FP** 4/11" in block


class TestFormatSpellLineNoCost:
    def test_omits_cost_segment_when_blank(self):
        line = format_spell_line("Detect Magic", 11, "Knowledge", "")
        assert "Cost:" not in line
        assert "Knowledge" in line


class TestFormatCombatantLine:
    """tracker row: pointer, name styling, status icons, maneuver, HP/FP bars."""

    def _line(self, **kw):
        base = dict(
            name="Goblin", basic_speed=5.0, hp_current=8, hp_max=10,
            fp_current=10, fp_max=10, status_effects=[], maneuver=None,
            is_current=False, is_out=False,
        )
        base.update(kw)
        return format_combatant_line(**base)

    def test_current_combatant_has_pointer(self):
        assert "▶" in self._line(is_current=True)

    def test_non_current_has_no_pointer(self):
        assert "▶" not in self._line(is_current=False)

    def test_active_name_is_bold(self):
        assert "**Goblin**" in self._line(is_out=False)

    def test_out_combatant_is_struck_through(self):
        assert "~~Goblin~~" in self._line(is_out=True)

    def test_known_status_effect_renders_icon(self):
        line = self._line(status_effects=["Stunned"])
        assert STATUS_ICONS[StatusEffect.STUNNED] in line

    def test_unknown_status_effect_is_filtered(self):
        # an effect missing from STATUS_ICONS must not crash or inject a stray icon
        line = self._line(status_effects=["Bored"])
        assert "Goblin" in line

    def test_maneuver_is_appended(self):
        assert "All-Out Attack" in self._line(maneuver="All-Out Attack")

    def test_hp_bar_shows_current_over_max(self):
        assert "8/10" in self._line(hp_current=8, hp_max=10)
