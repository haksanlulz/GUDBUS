"""Reference cog (/skill /trait /spell /technique /item) against a stub service — no real library."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from gurps_bot.cogs.reference import (
    CATEGORIES,
    ReferenceCog,
    build_equipment_embed,
    build_skill_embed,
    build_spell_embed,
    build_technique_embed,
    build_trait_embed,
)

# Each sample carries prose fields on purpose; the wall must never surface them.

PROSE_SENTINELS = [
    "Once adrift in your own thoughts, you must roll",  # a local_notes sentence
    "p. 174 in the printed book",  # a reference_highlight sentence
    "Treat as a swung weapon when",  # a weapon usage_notes sentence
]

SAMPLE_SKILL = {
    "name": "Broadsword",
    "specialization": "",
    "difficulty": "dx/a",
    "reference": "B208",
    "points": 8,
    "tech_level": "",
    "tags": ["Combat", "Melee Weapon"],
    "defaults": [
        {"type": "dx", "modifier": -5},
        {"type": "skill", "name": "Shortsword", "modifier": -2},
    ],
    # prose — MUST be dropped:
    "local_notes": "Once adrift in your own thoughts, you must roll against Will.",
    "reference_highlight": "p. 174 in the printed book",
    "features": [{"type": "skill_bonus"}],
    "id": "abc-123",
}

SAMPLE_TRAIT = {
    "name": "Absent-Mindedness",
    "base_points": -15,
    "points_per_level": None,
    "can_level": False,
    "cr": 12,
    "cr_adj": "action_penalty",
    "reference": "B122",
    "tags": ["Disadvantage", "Mental"],
    "modifiers": [
        {"id": "m1", "name": "Mitigator", "cost_adj": "-20%",
         "local_notes": "Once adrift in your own thoughts, you must roll vs IQ."},
    ],
    # prose — MUST be dropped:
    "local_notes": "Once adrift in your own thoughts, you must roll against Perception-5.",
    "reference_highlight": "p. 174 in the printed book",
}

SAMPLE_SPELL = {
    "name": "Animate Plant",
    "difficulty": "iq/h",
    "college": ["Plant"],
    "power_source": "Arcane",
    "spell_class": "Regular",
    "resist": "Special",
    "casting_cost": "Varies",
    "maintenance_cost": "2",
    "casting_time": "2 sec",
    "duration": "1 min",
    "reference": "M86",
    "points": 1,
    "tags": ["Plant"],
    # prose — MUST be dropped:
    "local_notes": "Double casting cost if plant moves. p. 174 in the printed book.",
    "reference_highlight": "p. 174 in the printed book",
}

SAMPLE_EQUIPMENT = {
    # NOTE: equipment uses 'description' as the name field, not 'name'.
    "description": "Thrusting Broadsword",
    "base_value": "600",
    "base_weight": "3 lb",
    "legality_class": "3",
    "tech_level": "1",
    "reference": "B271",
    "tags": ["Melee Weapon"],
    "weapons": [
        {
            "id": "w1",
            "damage": {"type": "cut", "st": "sw", "base": "1"},
            "usage": "Swung",
            "reach": "1",
            "parry": "0",
            "calc": {"damage": "sw+1 cut"},
            # prose inside a weapon — MUST be dropped:
            "usage_notes": "Treat as a swung weapon when used two-handed.",
            "defaults": [{"type": "skill", "name": "Broadsword"}],
        },
    ],
    # prose — MUST be dropped:
    "local_notes": "Once adrift in your own thoughts, you must roll.",
    "reference_highlight": "p. 174 in the printed book",
    "modifiers": [],
}

SAMPLE_TECHNIQUE = {
    "name": "Targeted Attack",
    "difficulty": "h",  # bare code (no attribute prefix) = technique
    "default": {"type": "skill", "name": "Broadsword", "modifier": -6},
    "limit": 0,
    "points": 5,
    "reference": "MA68",
    "tags": ["Technique"],
    # prose — MUST be dropped:
    "reference_highlight": "p. 174 in the printed book",
}


class StubReferenceService:
    """Implements only the surface the cog calls: names(category) and get(category, name)."""

    def __init__(self) -> None:
        self._data: dict[str, list[dict]] = {
            "skills": [SAMPLE_SKILL, {"name": "Shortsword", "difficulty": "dx/a",
                                      "reference": "B209", "points": 4}],
            "traits": [SAMPLE_TRAIT, {"name": "Acute Vision", "base_points": 2,
                                      "reference": "B35"}],
            "spells": [SAMPLE_SPELL, {"name": "Animate Object", "difficulty": "iq/h",
                                      "college": ["Plant"], "reference": "M87",
                                      "points": 2}],
            "equipment": [SAMPLE_EQUIPMENT, {"description": "Short Bow",
                                             "base_value": "50", "base_weight": "2 lb",
                                             "reference": "B275"}],
            "techniques": [SAMPLE_TECHNIQUE, {"name": "Disarming", "difficulty": "h",
                                              "default": {"type": "skill",
                                                          "name": "Broadsword",
                                                          "modifier": -4},
                                              "reference": "MA70"}],
        }

    def _name_of(self, category: str, entry: dict) -> str:
        return entry["description"] if category == "equipment" else entry["name"]

    def names(self, category: str) -> list[str]:
        return [self._name_of(category, e) for e in self._data.get(category, [])]

    def get(self, category: str, name: str) -> dict | None:
        for e in self._data.get(category, []):
            if self._name_of(category, e) == name:
                return e
        return None


def _embed_text(embed: discord.Embed) -> str:
    """Concatenate every user-visible string in an embed for wall scanning."""
    parts: list[str] = []
    if embed.title:
        parts.append(embed.title)
    if embed.description:
        parts.append(embed.description)
    if embed.footer and embed.footer.text:
        parts.append(embed.footer.text)
    for f in embed.fields:
        parts.append(str(f.name))
        parts.append(str(f.value))
    return "\n".join(parts)


def _assert_no_prose(embed: discord.Embed) -> None:
    text = _embed_text(embed)
    for sentinel in PROSE_SENTINELS:
        assert sentinel not in text, f"COPYRIGHT WALL leak: {sentinel!r} reached the embed"


def _make_cog() -> ReferenceCog:
    return ReferenceCog(bot=MagicMock(), service=StubReferenceService())


def _make_interaction(guild_id: int | None = 12345, service=None) -> MagicMock:
    """Mock interaction whose response.send_message is awaitable + recorded."""
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.user.id = 99
    interaction.response.send_message = AsyncMock()
    interaction.client.reference = service or StubReferenceService()
    return interaction


class TestBuildersProduceEmbeds:
    def test_skill_embed_facts(self):
        embed = build_skill_embed(SAMPLE_SKILL)
        text = _embed_text(embed)
        assert "Broadsword" in embed.title
        assert "DX/Average" in text  # difficulty decoded as a fact
        assert "8" in text  # points
        assert "B208" in text  # page cite
        assert "Shortsword" in text  # default relation surfaced
        _assert_no_prose(embed)

    def test_trait_embed_facts(self):
        embed = build_trait_embed(SAMPLE_TRAIT)
        text = _embed_text(embed)
        assert "Absent-Mindedness" in embed.title
        assert "-15" in text  # base_points (flat cost) as a fact
        assert "12" in text  # self-control rating
        assert "B122" in text  # page
        _assert_no_prose(embed)

    def test_spell_embed_facts(self):
        embed = build_spell_embed(SAMPLE_SPELL)
        text = _embed_text(embed)
        assert "Animate Plant" in embed.title
        assert "Plant" in text  # college
        assert "IQ/Hard" in text  # difficulty decoded
        assert "2 sec" in text  # casting time
        assert "M86" in text  # page
        _assert_no_prose(embed)

    def test_equipment_embed_facts(self):
        embed = build_equipment_embed(SAMPLE_EQUIPMENT)
        text = _embed_text(embed)
        # name comes from 'description', not 'name'
        assert "Thrusting Broadsword" in embed.title
        assert "600" in text  # base_value (cost)
        assert "3 lb" in text  # base_weight
        assert "B271" in text  # page
        assert "sw+1 cut" in text  # resolved weapon damage (a fact)
        _assert_no_prose(embed)

    def test_technique_embed_facts(self):
        embed = build_technique_embed(SAMPLE_TECHNIQUE)
        text = _embed_text(embed)
        assert "Targeted Attack" in embed.title
        assert "Hard" in text  # bare difficulty decoded
        assert "Broadsword" in text  # base skill from singular 'default'
        assert "MA68" in text  # page
        _assert_no_prose(embed)


class TestCopyrightWall:
    @pytest.mark.parametrize(
        "builder,entry",
        [
            (build_skill_embed, SAMPLE_SKILL),
            (build_trait_embed, SAMPLE_TRAIT),
            (build_spell_embed, SAMPLE_SPELL),
            (build_equipment_embed, SAMPLE_EQUIPMENT),
            (build_technique_embed, SAMPLE_TECHNIQUE),
        ],
    )
    def test_no_prose_leaks(self, builder, entry):
        _assert_no_prose(builder(entry))

    def test_footer_points_to_legal(self):
        # Footer is the short policy cite, not the rulebook text.
        embed = build_skill_embed(SAMPLE_SKILL)
        assert embed.footer.text is not None
        assert "/legal" in embed.footer.text
        assert "SJG Online Policy" in embed.footer.text

    def test_comma_separated_reference_split(self):
        entry = dict(SAMPLE_SKILL, reference="B208,MA54")
        text = _embed_text(build_skill_embed(entry))
        assert "B208" in text and "MA54" in text

    def test_tags_filter_template_tokens(self):
        # @template@ tokens must be filtered from the Tags field like every other
        # user-facing field; real tags survive.
        entry = dict(SAMPLE_SKILL, tags=["Combat", "@Specialty@", "Melee Weapon"])
        text = _embed_text(build_skill_embed(entry))
        assert "@Specialty@" not in text
        assert "Combat" in text and "Melee Weapon" in text


class TestDecoding:
    def test_spell_multi_college(self):
        entry = dict(SAMPLE_SPELL, college=["Air", "Knowledge"])
        text = _embed_text(build_spell_embed(entry))
        assert "Air" in text and "Knowledge" in text

    def test_template_token_passthrough(self):
        # specialization template tokens pass through verbatim (not resolved).
        entry = dict(SAMPLE_SKILL, specialization="@Specialty@")
        text = _embed_text(build_skill_embed(entry))
        assert "@Specialty@" in text

    def test_leveled_trait_cost(self):
        entry = {
            "name": "Damage Resistance",
            "base_points": None,
            "points_per_level": 5,
            "can_level": True,
            "reference": "B46",
        }
        text = _embed_text(build_trait_embed(entry))
        assert "5" in text  # per-level cost surfaces even with null base_points

    def test_defaults_omit_template_token_base_skill(self):
        # A default whose base skill NAME is an unfilled @token@ (e.g. the generic
        # "@Average Skill@" wildcat-skill default) must be dropped — never leaked
        # into the Defaults field — while the concrete defaults survive.
        entry = dict(
            SAMPLE_SKILL,
            defaults=[
                {"type": "skill", "name": "@Average Skill@", "modifier": -3},
                {"type": "skill", "name": "Combat Sport", "modifier": -3},
                {"type": "dx", "modifier": -5},
            ],
        )
        text = _embed_text(build_skill_embed(entry))
        assert "@" not in text  # no template token leaks anywhere in the embed
        assert "Combat Sport-3" in text
        assert "DX-5" in text


class TestCommandPath:
    async def test_skill_command_sends_embed(self):
        cog = _make_cog()
        interaction = _make_interaction()
        await cog.skill.callback(cog, interaction, name="Broadsword")
        interaction.response.send_message.assert_awaited_once()
        kwargs = interaction.response.send_message.await_args.kwargs
        assert "embed" in kwargs
        assert isinstance(kwargs["embed"], discord.Embed)
        assert "Broadsword" in kwargs["embed"].title
        _assert_no_prose(kwargs["embed"])

    async def test_item_command_uses_description_name(self):
        cog = _make_cog()
        interaction = _make_interaction()
        await cog.item.callback(cog, interaction, name="Thrusting Broadsword")
        kwargs = interaction.response.send_message.await_args.kwargs
        assert "Thrusting Broadsword" in kwargs["embed"].title

    @pytest.mark.parametrize(
        "command_name,sample_name",
        [
            ("skill", "Broadsword"),
            ("trait", "Absent-Mindedness"),
            ("spell", "Animate Plant"),
            ("technique", "Targeted Attack"),
            ("item", "Thrusting Broadsword"),
        ],
    )
    async def test_each_command_builds_clean_embed(self, command_name, sample_name):
        cog = _make_cog()
        interaction = _make_interaction()
        command = getattr(cog, command_name)
        await command.callback(cog, interaction, name=sample_name)
        kwargs = interaction.response.send_message.await_args.kwargs
        assert isinstance(kwargs["embed"], discord.Embed)
        _assert_no_prose(kwargs["embed"])

    async def test_miss_yields_clean_ephemeral(self):
        cog = _make_cog()
        interaction = _make_interaction()
        await cog.skill.callback(cog, interaction, name="No Such Skill")
        interaction.response.send_message.assert_awaited_once()
        args, kwargs = interaction.response.send_message.await_args
        # No embed on a miss — a plain ephemeral text message.
        assert "embed" not in kwargs or kwargs["embed"] is None
        assert kwargs.get("ephemeral") is True
        message = args[0] if args else kwargs.get("content", "")
        assert "No Such Skill" in message
        assert "not found" in message.lower()


class TestAutocomplete:
    async def test_returns_ranked_names(self):
        cog = _make_cog()
        interaction = _make_interaction()
        choices = await _run_autocomplete(cog, "skill", interaction, "Broad")
        names = [c.name for c in choices]
        assert names, "expected at least one ranked match"
        assert names[0] == "Broadsword"  # best fuzzy match ranks first

    async def test_empty_query_lists_candidates(self):
        cog = _make_cog()
        interaction = _make_interaction()
        choices = await _run_autocomplete(cog, "skill", interaction, "")
        names = [c.name for c in choices]
        assert "Broadsword" in names and "Shortsword" in names

    async def test_case_insensitive_match(self):
        # Lower-case query must surface the capitalised name — locks that the
        # autocomplete scorer (whatever its internals) stays case-insensitive.
        cog = _make_cog()
        interaction = _make_interaction()
        choices = await _run_autocomplete(cog, "skill", interaction, "broadsword")
        names = [c.name for c in choices]
        assert "Broadsword" in names

    async def test_miss_returns_empty(self):
        cog = _make_cog()
        interaction = _make_interaction()
        choices = await _run_autocomplete(cog, "skill", interaction, "zzzzzzz")
        assert choices == []

    async def test_equipment_autocomplete_uses_description(self):
        cog = _make_cog()
        interaction = _make_interaction()
        choices = await _run_autocomplete(cog, "item", interaction, "Thrust")
        names = [c.name for c in choices]
        assert "Thrusting Broadsword" in names

    async def test_outside_guild_returns_empty(self):
        cog = _make_cog()
        interaction = _make_interaction(guild_id=None)
        choices = await _run_autocomplete(cog, "skill", interaction, "Broad")
        assert choices == []


async def _run_autocomplete(cog: ReferenceCog, command_name: str,
                            interaction, current: str):
    """Invoke the autocomplete callback bound to a command's 'name' param."""
    command = getattr(cog, command_name)
    callback = command._params["name"].autocomplete
    return await callback(cog, interaction, current)


def test_categories_cover_all_commands():
    # the five user-facing commands map to the five catalog categories
    assert set(CATEGORIES) == {"skill", "trait", "spell", "technique", "item"}
    assert CATEGORIES["item"] == "equipment"  # /item queries the 'equipment' catalog
