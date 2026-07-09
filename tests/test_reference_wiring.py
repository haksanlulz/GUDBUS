"""pins the ReferenceLookup adapter between catalog dataclasses and the raw-dict cog builders"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from gurps_bot.cogs.reference import (
    ReferenceCog,
    build_equipment_embed,
    build_skill_embed,
    build_spell_embed,
    build_technique_embed,
    build_trait_embed,
)
from gurps_bot.gcs.library import (
    DEFAULT_LIBRARY_ROOT,
    CatalogEquipment,
    CatalogSkill,
    CatalogSpell,
    CatalogTechnique,
    CatalogTrait,
    load_library,
)
from gurps_bot.services.reference import ReferenceLookup


def _catalog() -> dict[str, list]:
    return {
        "skills": [
            CatalogSkill(
                name="Broadsword",
                attribute="DX",
                difficulty="Average",
                page="B208",
                points=8,
                defaults=[
                    {"type": "dx", "modifier": -5},
                    {"type": "skill", "name": "Shortsword", "modifier": -2},
                ],
                book="Basic Set",
            )
        ],
        "traits": [
            CatalogTrait(name="Absent-Mindedness", points=-15, page="B122", book="Basic Set"),
        ],
        "spells": [
            CatalogSpell(
                name="Animate Plant",
                college=["Plant"],
                difficulty="Hard",
                page="M86",
                casting_cost="Varies",
                maintenance="2",
                casting_time="2 sec",
                duration="1 min",
                spell_class="Regular",
                book="Magic",
            )
        ],
        "techniques": [
            CatalogTechnique(
                name="Targeted Attack",
                difficulty="Hard",
                page="MA68",
                default={"type": "skill", "name": "Broadsword", "modifier": -6},
                book="Martial Arts",
            )
        ],
        "equipment": [
            CatalogEquipment(
                name="Thrusting Broadsword",
                cost="600",
                weight="3 lb",
                damage="sw+1 cut",
                reach="1",
                page="B271",
                legality="3",
                book="Basic Set",
            )
        ],
    }


def _lookup() -> ReferenceLookup:
    return ReferenceLookup(_catalog())


class TestAdapterSurface:
    def test_names_delegates(self):
        lk = _lookup()
        assert lk.names("skills") == ["Broadsword"]
        assert lk.names("equipment") == ["Thrusting Broadsword"]

    def test_get_returns_dict_not_dataclass(self):
        lk = _lookup()
        entry = lk.get("skills", "Broadsword")
        assert isinstance(entry, dict)

    def test_get_miss_returns_none(self):
        assert _lookup().get("skills", "No Such Skill") is None

    def test_unknown_category_is_clean(self):
        lk = _lookup()
        assert lk.get("dragons", "x") is None
        assert lk.names("dragons") == []


class TestWiredFactsRender:
    def test_skill_facts_survive(self):
        entry = _lookup().get("skills", "Broadsword")
        text = _embed_text(build_skill_embed(entry))
        assert "Broadsword" in text
        assert "DX/Average" in text  # attribute recombined with decoded difficulty
        assert "8" in text  # points
        assert "B208" in text  # page (from dataclass .page -> 'reference')
        assert "Shortsword" in text  # default relation preserved

    def test_trait_facts_survive(self):
        entry = _lookup().get("traits", "Absent-Mindedness")
        text = _embed_text(build_trait_embed(entry))
        assert "Absent-Mindedness" in text
        assert "-15" in text  # dataclass .points -> 'base_points'
        assert "B122" in text

    def test_spell_facts_survive(self):
        entry = _lookup().get("spells", "Animate Plant")
        text = _embed_text(build_spell_embed(entry))
        assert "Animate Plant" in text
        assert "Plant" in text  # college
        assert "Hard" in text  # difficulty
        assert "Varies" in text  # casting_cost
        assert "2 sec" in text  # casting_time
        assert "M86" in text

    def test_technique_facts_survive(self):
        entry = _lookup().get("techniques", "Targeted Attack")
        text = _embed_text(build_technique_embed(entry))
        assert "Targeted Attack" in text
        assert "Hard" in text
        assert "Broadsword" in text  # base skill from singular default
        assert "MA68" in text

    def test_equipment_facts_survive(self):
        entry = _lookup().get("equipment", "Thrusting Broadsword")
        text = _embed_text(build_equipment_embed(entry))
        assert "Thrusting Broadsword" in text  # dataclass .name -> 'description'
        assert "600" in text  # .cost -> 'base_value'
        assert "3 lb" in text  # .weight -> 'base_weight'
        assert "sw+1 cut" in text  # flattened weapon damage re-surfaced
        assert "B271" in text


# regression: same-name skills must stay distinct per specialization; no @token@ may render


def _spec_catalog() -> dict[str, list]:
    return {
        "skills": [
            CatalogSkill(
                name="Mechanic", attribute="IQ", difficulty="Average",
                page="B207", points=2, defaults=[], book="Basic Set",
                specialization="Automobile",
            ),
            CatalogSkill(
                name="Mechanic", attribute="IQ", difficulty="Average",
                page="B207", points=2, defaults=[], book="Basic Set",
                specialization="Helicopter",
            ),
            # a bare @token@ spec must not compose into the name or render anywhere
            CatalogSkill(
                name="Animal Handling", attribute="IQ", difficulty="Average",
                page="B175", points=2,
                defaults=[{"type": "skill", "name": "Animal Handling",
                           "specialization": "@Specialty@", "modifier": -3}],
                book="Basic Set", specialization="@Specialty@",
            ),
        ],
    }


class TestSpecializationDistinctAndNoTokenLeak:
    def test_same_name_skills_are_distinct_in_names(self):
        lk = ReferenceLookup(_spec_catalog())
        names = lk.names("skills")
        assert "Mechanic (Automobile)" in names
        assert "Mechanic (Helicopter)" in names
        assert "Mechanic" not in names  # the bare name is never the selectable one
        assert len({"Mechanic (Automobile)", "Mechanic (Helicopter)"} & set(names)) == 2

    def test_get_resolves_each_specialization_distinctly(self):
        lk = ReferenceLookup(_spec_catalog())
        auto = lk.get("skills", "Mechanic (Automobile)")
        heli = lk.get("skills", "Mechanic (Helicopter)")
        assert auto is not None and heli is not None
        assert auto["specialization"] == "Automobile"
        assert heli["specialization"] == "Helicopter"
        assert auto["specialization"] != heli["specialization"]

    def test_distinct_specializations_render_distinct_titles(self):
        lk = ReferenceLookup(_spec_catalog())
        auto = build_skill_embed(lk.get("skills", "Mechanic (Automobile)"))
        heli = build_skill_embed(lk.get("skills", "Mechanic (Helicopter)"))
        assert auto.title == "Mechanic (Automobile)"
        assert heli.title == "Mechanic (Helicopter)"
        assert auto.title != heli.title

    def test_no_template_token_in_any_rendered_field(self):
        lk = ReferenceLookup(_spec_catalog())
        for selectable in lk.names("skills"):
            embed = build_skill_embed(lk.get("skills", selectable))
            assert "@" not in _embed_text(embed), (
                f"template token leaked into rendered embed for {selectable!r}"
            )

    def test_bare_token_skill_indexes_under_bare_name(self):
        lk = ReferenceLookup(_spec_catalog())
        names = lk.names("skills")
        assert "Animal Handling" in names
        assert not any(n.startswith("Animal Handling (") for n in names)
        entry = lk.get("skills", "Animal Handling")
        assert entry is not None
        # the dict carries no renderable specialization (token was dropped)
        assert entry.get("specialization") in (None, "")


def _embed_text(embed: discord.Embed) -> str:
    parts: list[str] = []
    if embed.title:
        parts.append(embed.title)
    if embed.footer and embed.footer.text:
        parts.append(embed.footer.text)
    for f in embed.fields:
        parts.append(str(f.name))
        parts.append(str(f.value))
    return "\n".join(parts)


def _interaction(guild_id: int | None = 123) -> MagicMock:
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.response.send_message = AsyncMock()
    return interaction


class TestUnsyncedDegradesGracefully:
    async def test_empty_catalog_says_not_synced(self):
        cog = ReferenceCog(bot=MagicMock(), service=ReferenceLookup({}))
        interaction = _interaction()
        await cog.skill.callback(cog, interaction, name="Broadsword")
        interaction.response.send_message.assert_awaited_once()
        args, kwargs = interaction.response.send_message.await_args
        message = (args[0] if args else kwargs.get("content", "")).lower()
        assert "not" in message and "sync" in message
        assert "sync_gcs_library.py" in message
        assert kwargs.get("ephemeral") is True
        assert "embed" not in kwargs or kwargs["embed"] is None

    async def test_populated_catalog_real_miss_still_says_not_found(self):
        cog = ReferenceCog(bot=MagicMock(), service=_lookup())
        interaction = _interaction()
        await cog.skill.callback(cog, interaction, name="No Such Skill")
        args, kwargs = interaction.response.send_message.await_args
        message = (args[0] if args else kwargs.get("content", "")).lower()
        assert "not found" in message
        assert "sync_gcs_library.py" not in message

    async def test_empty_catalog_autocomplete_returns_empty(self):
        cog = ReferenceCog(bot=MagicMock(), service=ReferenceLookup({}))
        interaction = _interaction()
        interaction.client.reference = ReferenceLookup({})
        choices = await cog._suggest(interaction, "skill", "Bro")
        assert choices == []


# keys are ReferenceLookup category names, not /command tokens
_CATEGORY_BUILDERS = {
    "skills": build_skill_embed,
    "traits": build_trait_embed,
    "spells": build_spell_embed,
    "techniques": build_technique_embed,
    "equipment": build_equipment_embed,
}

# known upstream prose that must never reach a user
_REAL_PROSE_SENTINELS = (
    "Once adrift in your own thoughts",
    "Prevents or cures",
    "Double casting cost",
)

# cap keeps the full-library run fast
_SAMPLE_PER_CATEGORY = 80


class TestRealDataWallEndToEnd:
    def test_no_known_prose_reaches_any_rendered_embed(self):
        if not Path(DEFAULT_LIBRARY_ROOT).is_dir():
            pytest.skip(f"vendored library not present at {DEFAULT_LIBRARY_ROOT}")
        lookup = ReferenceLookup(load_library())
        checked = 0
        for category, builder in _CATEGORY_BUILDERS.items():
            names = lookup.names(category)
            assert names, f"real library has no {category} to sample"
            # head of the sorted list, not random — deterministic
            for name in names[:_SAMPLE_PER_CATEGORY]:
                entry = lookup.get(category, name)
                assert entry is not None, f"{category}:{name!r} did not round-trip"
                text = _embed_text(builder(entry))
                for sentinel in _REAL_PROSE_SENTINELS:
                    assert sentinel not in text, (
                        f"COPYRIGHT WALL leak on real data: {sentinel!r} reached the "
                        f"{category} embed for {name!r}"
                    )
                assert "@" not in text, (
                    f"template token leaked into real {category} embed for {name!r}"
                )
                checked += 1
        assert checked > 0, "real-data wall test exercised nothing"
