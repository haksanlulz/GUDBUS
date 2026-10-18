"""GCS fillable rows: @Key@ placeholders are rendered from the row's `replacements`.

GCS keeps the library text ("@Quirk@", "Social Stigma (@Stigma@)", "Area Knowledge" with a
"@Barony, County, Duchy, or Small Nation@" specialization) and the chosen values in a
`replacements` map on the same row; the app renders the substitution. A sheet imported
2026-10-18 showed the raw `@Quirk@` in `/char`.
"""

from __future__ import annotations

from gurps_bot.gcs.parser import parse_gcs


def _sheet(**parts: object) -> dict:
    return {"version": 5, "profile": {"name": "Tester"}, **parts}


def test_trait_name_placeholder_is_filled():
    sheet = _sheet(traits=[
        {"name": "@Quirk@", "replacements": {"Quirk": "Hums while working"}, "calc": {"points": -1}},
        {"name": "Social Stigma (@Stigma@)", "replacements": {"Stigma": "Savage"}, "calc": {"points": -10}},
    ])
    names = [t.name for t in parse_gcs(sheet).traits]
    assert names == ["Hums while working", "Social Stigma (Savage)"]


def test_skill_name_and_specialization_are_filled():
    sheet = _sheet(skills=[{
        "name": "Area Knowledge", "difficulty": "iq/e", "points": 1,
        "specialization": "@Barony, County, Duchy, or Small Nation@",
        "replacements": {"Barony, County, Duchy, or Small Nation": "the Brambleholt reach"},
        "calc": {"level": 10, "rsl": "IQ+0"},
    }, {
        "name": "Talent (@Small@)", "difficulty": "iq/e", "points": 1,
        "replacements": {"Small": "Widget-Worker"}, "calc": {"level": 10, "rsl": "IQ+0"},
    }])
    skills = parse_gcs(sheet).skills
    assert (skills[0].name, skills[0].specialization) == ("Area Knowledge", "the Brambleholt reach")
    assert skills[1].name == "Talent (Widget-Worker)"


def test_spell_equipment_and_group_names_are_filled():
    sheet = _sheet(
        spells=[{"name": "Seek @Thing@", "replacements": {"Thing": "Water"}, "calc": {"level": 12}}],
        equipment=[{"description": "Tools (@Skill@)", "replacements": {"Skill": "Armoury"}, "quantity": 1}],
        traits=[{"name": "@Lens@", "replacements": {"Lens": "Warren-Born"},
                 "children": [{"name": "Empathy", "calc": {"points": 15}}]}],
    )
    parsed = parse_gcs(sheet)
    assert parsed.spells[0].name == "Seek Water"
    assert parsed.equipment[0]["description"] == "Tools (Armoury)"
    assert parsed.traits[0].group_name == "Warren-Born"


def test_unfilled_and_malformed_placeholders_pass_through():
    """No replacements, a missing key, or a non-string value: the text is left as GCS shows it."""
    sheet = _sheet(traits=[
        {"name": "Limited: @Advantage@ Only", "calc": {"points": 0}},
        {"name": "@Quirk@", "replacements": {"Other": "x"}, "calc": {"points": -1}},
        {"name": "@Quirk@", "replacements": {"Quirk": 7}, "calc": {"points": -1}},
        {"name": "@Quirk@", "replacements": "not a map", "calc": {"points": -1}},
    ])
    assert [t.name for t in parse_gcs(sheet).traits] == ["Limited: @Advantage@ Only", "@Quirk@", "@Quirk@", "@Quirk@"]
