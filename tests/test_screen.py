"""/screen is an index: it names the command that answers each row and the page
to read, and lists option names read from their owners — never a table's values
in book order."""

from __future__ import annotations

import re

import discord
import pytest_asyncio

from gurps_bot.cogs.help import _tree_descriptions
from gurps_bot.mechanics.combat_constants import STATUS_ICONS, Maneuver, StatusEffect
from gurps_bot.mechanics.hit_location import deliberate_locations, gross_targeting_reference
from gurps_bot.mechanics.posture import POSTURES
from gurps_bot.mechanics.tables import CRITICAL_TABLES, FRIGHT_TABLE_PAGES
from gurps_bot.ui import screen

_EMBED_FIELD_LIMIT = 1024

#: A signed modifier ("+2", "-4") not glued to a word or a range ("4-40").
_SIGNED_VALUE = re.compile(r"(?<![\w/])[+\-−]\d")
_COMMAND = re.compile(r"`(/[a-z][a-z0-9-]*(?: [a-z][a-z0-9-]*)?)`")


def _text(page: discord.Embed) -> str:
    parts = [page.title or "", page.description or ""]
    for f in page.fields:
        parts += [f.name or "", f.value or ""]
    if page.footer and page.footer.text:
        parts.append(page.footer.text)
    return "\n".join(parts)


@pytest_asyncio.fixture
async def tree():
    from tests.test_extensions_load import loaded_bot

    async with loaded_bot() as bot:
        yield bot.tree


class TestNoTables:
    def test_no_page_carries_a_modifier_value(self):
        for page in screen.build_screen_pages():
            hits = _SIGNED_VALUE.findall(_text(page))
            assert not hits, (page.title, hits)

    def test_the_value_check_can_fail(self):
        planted = discord.Embed(title="t", description="Kneeling Att -2 · Def -2")
        assert _SIGNED_VALUE.findall(_text(planted))

    def test_no_gm_screen_branding(self):
        for page in screen.build_screen_pages():
            assert "GM Screen" not in _text(page)

    def test_critical_tables_are_cited_not_reproduced(self):
        text = _text(screen.rolls_page())
        for t in CRITICAL_TABLES:
            assert t.name in text and t.page in text


class TestEveryCommandNamedExists:
    async def test_pages_name_only_live_commands(self, tree):
        live = {f"/{name}" for name in _tree_descriptions(tree)}
        groups = {c.rsplit(" ", 1)[0] for c in live if " " in c}
        named = set()
        for page in screen.build_screen_pages():
            named |= set(_COMMAND.findall(_text(page)))
        assert named, "the pages name no commands"
        assert not named - live - groups, sorted(named - live - groups)


class TestNamesComeFromOwners:
    def test_maneuvers(self):
        assert screen.maneuver_names() == [m.value for m in Maneuver]

    def test_status_effects(self):
        assert [n for n, _ in screen.status_effects()] == [s.value for s in StatusEffect]
        assert all(icon == STATUS_ICONS[StatusEffect(n)] for n, icon in screen.status_effects())

    def test_postures(self):
        assert screen.posture_names() == [p.name for p in POSTURES]

    def test_deliberate_locations(self):
        assert screen.deliberate_location_names() == [loc.name for loc in deliberate_locations()]

    def test_body_parts(self):
        assert screen.body_part_names() == [n for n, _, _ in gross_targeting_reference()]

    def test_the_body_page_lists_them(self):
        text = _text(screen.body_page())
        for name in (*screen.posture_names(), *screen.deliberate_location_names()):
            assert name in text, name


class TestPages:
    def test_build_returns_titled_embeds(self):
        pages = screen.build_screen_pages()
        assert len(pages) == len(screen.CATEGORIES)
        assert all(p.title for p in pages)

    def test_every_field_within_discord_cap(self):
        for page in screen.build_screen_pages():
            for f in page.fields:
                assert len(f.value) <= _EMBED_FIELD_LIMIT, (page.title, f.name)

    def test_no_page_field_is_silently_truncated(self):
        for page in screen.build_screen_pages():
            for f in page.fields:
                assert "(truncated)" not in f.value, (page.title, f.name)

    def test_category_index_maps_to_valid_pages(self):
        pages = screen.build_screen_pages()
        for cat, i in screen.CATEGORY_INDEX.items():
            assert 0 <= i < len(pages), cat

    def test_screen_cog_choices_cover_every_category(self):
        from gurps_bot.cogs.gmscreen import _CATEGORY_CHOICES

        assert {c.value for c in _CATEGORY_CHOICES} == set(screen.CATEGORIES)


class TestFrightPage:
    def test_cites_rather_than_reproduces(self):
        assert screen.fright_page().fields == []

    def test_describes_the_raw_procedure(self):
        desc = screen.fright_page().description or ""
        assert "Will" in desc
        assert "14" in desc
        assert "HT" not in desc
        assert "3d" in desc and "margin" in desc
        assert FRIGHT_TABLE_PAGES in desc
