"""COPYRIGHT WALL — the rung that runs on every checkout.

The wall invariants (facts-only catalog, no SJG prose, no ``@token@`` leaks,
Discord caps) were enforced only by tests gated on the vendored GCS snapshot at
``gurps_bot/data/gcs_library/`` — a gitignored directory reproduced by
``tools/sync_gcs_library.py``. On a fresh clone or in CI that directory is
absent, all eleven gated tests ``pytest.skip``, and the LEGAL invariant is
unenforced and green. A skipping legal rung is worse than no rung: the suite
reports success.

This module closes that hole with a committed synthetic mini-catalog
(``tests/fixtures/gcs_mini/`` — every name, number, page cite and sentence in it
is invented; see its README) driven through the REAL chain, not stubs:

    load_library(fixture) -> Catalog* dataclasses      (gcs/library.py)
      -> ReferenceLookup / entry_to_dict               (services/reference.py)
        -> build_*_embed / ReferenceCog._suggest       (cogs/reference.py)

The real-data deep scans are untouched and still run when the snapshot IS
present; ``TestDeepRungVisibility`` makes their absence LOUD instead of silent,
so a done-report can never claim the deep rung passed when it never ran.

The fixture's field names are grounded in the loader's own builders
(``_build_skill`` / ``_build_trait`` / ``_build_spell`` / ``_build_technique`` /
``_build_equipment``), and :class:`TestFixtureIsActuallyParsed` proves it: a
fixture the loader silently ignores would be a fail-open rung — the exact class
of failure this module exists to kill.
"""

from __future__ import annotations

import dataclasses
import json
import re
import warnings
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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
from gurps_bot.gcs.library import DEFAULT_LIBRARY_ROOT, load_library
from gurps_bot.services.reference import ReferenceLookup, entry_to_dict

# The fails-closed field allowlist is OWNED by tests/test_library.py — imported,
# never re-declared, so a new dataclass field has exactly one place to be blessed.
from tests.test_library import EXPECTED_FACT_FIELDS

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "gcs_mini"

_CATEGORY_BUILDERS = {
    "skills": build_skill_embed,
    "traits": build_trait_embed,
    "spells": build_spell_embed,
    "techniques": build_technique_embed,
    "equipment": build_equipment_embed,
}

#: Source keys holding rulebook-shaped prose. The loader must never read them.
_PROSE_KEYS = ("local_notes", "usage_notes")

_TEMPLATE_TOKEN = re.compile(r"@[^@]*@")

# Discord hard limits (embed title/field caps; the Choice cap is the same 100).
_TITLE_MAX = 256
_FIELD_NAME_MAX = 256
_FIELD_VALUE_MAX = 1024
_EMBED_TOTAL_MAX = 6000
_CHOICE_MAX = 100
_NAME_MAX = 100
#: Terse-label bound for tags, matching tests/test_reference_factfields.py.
_TAG_MAX_LEN = 64


# --- helpers ----------------------------------------------------------------


def _raw_rows() -> list[dict]:
    """Every source row in the fixture, flattened (children included)."""
    rows: list[dict] = []

    def _walk(items):
        for row in items:
            if not isinstance(row, dict):
                continue
            rows.append(row)
            _walk(row.get("children") or [])

    for path in sorted(FIXTURE_ROOT.rglob("*")):
        if path.suffix.lower() in (".skl", ".adq", ".spl", ".eqp"):
            _walk(json.loads(path.read_text(encoding="utf-8")).get("rows", []))
    return rows


def _prose_sentinels() -> list[str]:
    """Every prose sentence the fixture plants for the wall to drop."""
    found: list[str] = []

    def _walk(value):
        if isinstance(value, dict):
            for key, val in value.items():
                if key in _PROSE_KEYS and isinstance(val, str) and val:
                    found.append(val)
                else:
                    _walk(val)
        elif isinstance(value, (list, tuple)):
            for item in value:
                _walk(item)

    for path in sorted(FIXTURE_ROOT.rglob("*")):
        if path.suffix.lower() in (".skl", ".adq", ".spl", ".eqp"):
            _walk(json.loads(path.read_text(encoding="utf-8")))
    return found


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


def _embed_text(embed) -> str:
    parts = [embed.title or ""]
    if embed.footer and embed.footer.text:
        parts.append(embed.footer.text)
    for f in embed.fields:
        parts.append(str(f.name))
        parts.append(str(f.value))
    return "\n".join(parts)


@pytest.fixture(scope="module")
def catalog() -> dict[str, list]:
    return load_library(FIXTURE_ROOT)


@pytest.fixture(scope="module")
def lookup(catalog) -> ReferenceLookup:
    return ReferenceLookup(catalog)


@pytest.fixture(scope="module")
def rendered(lookup) -> list[tuple[str, str, str]]:
    """(category, selectable_name, rendered_text) for EVERY fixture entry."""
    out: list[tuple[str, str, str]] = []
    for category, builder in _CATEGORY_BUILDERS.items():
        for name in lookup.names(category):
            entry = lookup.get(category, name)
            assert entry is not None, f"{category}:{name!r} did not round-trip"
            out.append((category, name, _embed_text(builder(entry))))
    return out


# ---------------------------------------------------------------------------
# The fixture must actually be READ. A fixture the loader ignores asserts
# nothing while looking green — the fail-open shape this whole module targets.
# ---------------------------------------------------------------------------


class TestFixtureIsActuallyParsed:
    def test_every_category_is_populated(self, catalog):
        for category in _CATEGORY_BUILDERS:
            assert catalog.get(category), (
                f"the mini catalog produced no {category} — the loader is not "
                f"reading {FIXTURE_ROOT}; check the file extension and field names "
                f"against gcs/library.py's builders"
            )

    def test_entry_counts_are_pinned(self, catalog):
        # Pinned so a fixture row that silently stops parsing (renamed key, wrong
        # extension, mis-shaped container) fails here instead of quietly shrinking
        # the corpus every other test in this module scans.
        assert {k: len(v) for k, v in catalog.items()} == {
            "skills": 6,
            "traits": 5,
            "spells": 3,
            "equipment": 3,
            "techniques": 2,
        }

    def test_skill_facts_are_grounded(self, catalog):
        skill = next(s for s in catalog["skills"] if s.name == "Glasswright")
        assert (skill.attribute, skill.difficulty) == ("DX", "Average")
        assert skill.points == 4
        assert skill.page == "SYN14"
        assert skill.book == "Synthetic Set"
        assert skill.tags == ["Craft", "Synthetic Craft"]

    def test_self_control_rows_are_grounded(self, catalog):
        by_name = {t.name: t for t in catalog["traits"]}
        assert (by_name["Hoardsickness"].cr, by_name["Hoardsickness"].cr_adj) == (
            12,
            "action_penalty",
        )
        assert by_name["Nightdread"].cr == 6
        assert (by_name["Stonehide"].points_per_level, by_name["Stonehide"].levels) == (4, 3)

    def test_multi_college_and_string_college_both_land(self, catalog):
        by_name = {s.name: s for s in catalog["spells"]}
        assert by_name["Lantern of Quiet Hours"].college == ["Ember", "Veil"]
        # A bare string college is coerced to a one-item list, never iterated as chars.
        assert by_name["Mend the Weeping Seam"].college == ["Veil"]

    def test_equipment_facts_are_grounded(self, catalog):
        item = next(e for e in catalog["equipment"] if e.name == "Notched Falchion")
        assert (item.cost, item.weight) == ("410", "3 lb")
        assert (item.damage, item.reach) == ("sw+1 cut", "1")
        assert (item.tech_level, item.rated_strength, item.legality) == ("3", 11, "3")

    def test_grouping_container_is_never_emitted(self, catalog):
        names = {e.name for entries in catalog.values() for e in entries}
        assert "Bladework Techniques" not in names, "a group header leaked as an entry"
        # …but its children WERE recursed into, as techniques.
        assert {t.name for t in catalog["techniques"]} == {"Off-Guard Riposte", "Rote Feint"}

    def test_placeholder_trait_is_filtered_but_meta_trait_survives(self, catalog):
        names = {t.name for t in catalog["traits"]}
        assert "Assorted Oddments" not in names  # no points, no page => scaffolding
        assert "Frame of Brass" in names  # named container WITH a page cite
        assert "Ceramic Lungs" in names  # …and its child was recursed into


# ---------------------------------------------------------------------------
# THE WALL — no prose survives the chain.
# ---------------------------------------------------------------------------


class TestNoProseSurvives:
    def test_fixture_actually_plants_prose(self):
        """Guard the guard: an empty sentinel set would make the scans vacuous."""
        sentinels = _prose_sentinels()
        assert len(sentinels) >= 6, (
            f"expected the fixture to plant prose in {_PROSE_KEYS} on many rows, "
            f"found {len(sentinels)}"
        )

    def test_no_prose_reaches_any_dataclass_field(self, catalog):
        sentinels = _prose_sentinels()
        for category, entries in catalog.items():
            for entry in entries:
                for field in dataclasses.fields(entry):
                    text = _flatten(getattr(entry, field.name))
                    for sentinel in sentinels:
                        assert sentinel not in text, (
                            f"COPYRIGHT WALL leak: prose reached "
                            f"{type(entry).__name__}.{field.name} in {category}"
                        )

    def test_no_prose_reaches_any_rendered_embed(self, rendered):
        sentinels = _prose_sentinels()
        for category, name, text in rendered:
            for sentinel in sentinels:
                assert sentinel not in text, (
                    f"COPYRIGHT WALL leak: prose reached the {category} embed for {name!r}"
                )

    def test_prose_shaped_spell_facts_are_dropped(self, catalog):
        """casting_cost / duration / resist can hold rules SENTENCES upstream; the
        terse-fact filter drops them so the page cite carries the detail."""
        raw = next(r for r in _raw_rows() if r.get("name") == "Mend the Weeping Seam")
        # …the source really is prose-shaped (else this test proves nothing).
        assert ";" in raw["casting_cost"]
        assert len(raw["duration"].split()) > 4
        assert len(raw["resist"].split()) > 4

        spell = next(s for s in catalog["spells"] if s.name == "Mend the Weeping Seam")
        assert spell.casting_cost == ""
        assert spell.duration == ""
        assert spell.resist == ""
        # a terse sibling fact on the same row survives — the filter is not a blanket drop
        assert spell.maintenance == "1"
        assert spell.casting_time == "4 sec"


# ---------------------------------------------------------------------------
# THE WALL — fails-CLOSED allowlist (no unreviewed field, no blanket dump).
# ---------------------------------------------------------------------------


class TestFailsClosedAllowlist:
    def test_every_loaded_entry_declares_only_whitelisted_facts(self, catalog):
        for category, entries in catalog.items():
            for entry in entries:
                actual = {f.name for f in dataclasses.fields(entry)}
                allowed = EXPECTED_FACT_FIELDS[type(entry)]
                extra = actual - allowed
                assert not extra, (
                    f"{type(entry).__name__} ({category}) declares non-whitelisted "
                    f"field(s) {sorted(extra)} — bless them in EXPECTED_FACT_FIELDS "
                    f"only after confirming each is a FACT, never prose"
                )

    def test_unmapped_type_raises_instead_of_dumping_attributes(self):
        """A future prose-bearing type must NOT fall through to a vars() dump."""

        @dataclasses.dataclass
        class ProseBearing:
            name: str
            local_notes: str

        with pytest.raises(TypeError):
            entry_to_dict(ProseBearing(name="X", local_notes="a rulebook sentence"))

    def test_mapper_covers_every_loaded_type(self, catalog):
        """Every type the loader can actually produce has an explicit facts-only
        mapper — so the fail-closed branch above is a guard, not the normal path."""
        for entries in catalog.values():
            for entry in entries:
                assert isinstance(entry_to_dict(entry), dict)


# ---------------------------------------------------------------------------
# THE WALL — no unfilled @template@ token reaches a user.
# ---------------------------------------------------------------------------


class TestNoTemplateTokenLeaks:
    def test_fixture_actually_plants_tokens(self):
        tokened = [r for r in _raw_rows() if _TEMPLATE_TOKEN.search(_flatten(r))]
        assert len(tokened) >= 4, (
            f"expected several @token@-bearing source rows, found {len(tokened)}"
        )

    def test_no_token_in_any_stored_fact(self, catalog):
        """``defaults`` / ``default`` / ``specialization`` are excluded: they are raw
        mechanical relations whose token base-skills are stripped at RENDER (the
        cog's ``_format_defaults`` / ``_renderable_spec``), not at load. Mirrors
        the real-data scan's documented carve-out."""
        for category, entries in catalog.items():
            for entry in entries:
                for field in dataclasses.fields(entry):
                    if field.name in ("defaults", "default", "specialization"):
                        continue
                    value = getattr(entry, field.name)
                    assert not _TEMPLATE_TOKEN.search(_flatten(value)), (
                        f"@token leak in {type(entry).__name__}.{field.name} "
                        f"({category}): {value!r}"
                    )

    def test_token_bearing_names_are_stripped_not_mangled(self, catalog):
        names = {e.name for entries in catalog.values() for e in entries}
        assert "Bind Servitor" in names  # was "Bind Servitor (@Servitor@)"
        assert "Summon Wisp" in names  # was "Summon @Element@ Wisp"

    def test_token_specialization_never_composes_a_selectable_name(self, lookup):
        names = lookup.names("skills")
        assert "Duskspeech" in names
        assert not any(n.startswith("Duskspeech (") for n in names)
        # …while a REAL specialization keeps same-named rows distinct.
        assert {"Latch Craft (Ironwork)", "Latch Craft (Clockwork)"} <= set(names)
        assert "Latch Craft" not in names

    def test_token_cost_expression_falls_back_or_is_omitted(self, catalog):
        by_name = {e.name: e for e in catalog["equipment"]}
        # raw is a formula, but GCS resolved it -> the resolved fact is used
        assert (by_name["Cut Gemstone"].cost, by_name["Cut Gemstone"].weight) == (
            "180",
            "0.1 lb",
        )
        # raw AND resolved both carry tokens -> the field is dropped, never leaked
        assert (by_name["Tuned Resonator"].cost, by_name["Tuned Resonator"].weight) == ("", "")

    def test_no_at_sign_in_any_rendered_string(self, rendered):
        for category, name, text in rendered:
            assert "@" not in text, (
                f"template token leaked into the {category} embed for {name!r}"
            )

    async def test_no_at_sign_in_autocomplete_choices(self, lookup):
        cog = ReferenceCog(bot=MagicMock(), service=lookup)
        interaction = MagicMock()
        interaction.guild_id = 123
        interaction.response.send_message = AsyncMock()
        for command in CATEGORIES:
            for current in ("", "a", "e"):
                choices = await cog._suggest(interaction, command, current)
                for choice in choices:
                    assert "@" not in choice.name and "@" not in choice.value, (
                        f"template token leaked into /{command} autocomplete: {choice.name!r}"
                    )


# ---------------------------------------------------------------------------
# THE WALL — caps. An over-long value 400s the Discord payload, and a name
# long enough to be a rules SENTENCE is also a prose-via-name leak.
# ---------------------------------------------------------------------------


class TestCapsRespected:
    def test_overlong_source_name_is_capped(self, catalog):
        raw_names = [str(r.get("name") or r.get("description") or "") for r in _raw_rows()]
        assert any(len(n) > _NAME_MAX for n in raw_names), (
            "the fixture no longer carries an over-long name; the cap is untested"
        )
        capped = [
            e.name
            for entries in catalog.values()
            for e in entries
            if e.name.endswith("…")
        ]
        assert capped, "the over-long name was not truncated"
        assert all(len(n) <= _NAME_MAX for n in capped)

    def test_every_catalog_name_fits_a_discord_choice(self, catalog):
        for category, entries in catalog.items():
            for entry in entries:
                assert len(entry.name) <= _NAME_MAX, (
                    f"{category} name exceeds the {_NAME_MAX}-char Choice/title cap: "
                    f"{entry.name!r}"
                )

    def test_autocomplete_choices_are_bounded(self, lookup):
        for category in _CATEGORY_BUILDERS:
            for name in lookup.names(category):
                assert len(name) <= _CHOICE_MAX

    def test_rendered_embeds_respect_discord_limits(self, lookup):
        for category, builder in _CATEGORY_BUILDERS.items():
            for name in lookup.names(category):
                embed = builder(lookup.get(category, name))
                assert len(embed.title or "") <= _TITLE_MAX
                assert len(embed.fields) <= 25
                for field in embed.fields:
                    assert len(str(field.name)) <= _FIELD_NAME_MAX
                    assert len(str(field.value)) <= _FIELD_VALUE_MAX, (
                        f"{category}:{name!r} field {field.name!r} exceeds "
                        f"{_FIELD_VALUE_MAX} chars"
                    )
                assert len(embed) <= _EMBED_TOTAL_MAX

    def test_tags_are_terse_labels_not_prose(self, catalog):
        for entries in catalog.values():
            for entry in entries:
                for tag in getattr(entry, "tags", []) or []:
                    assert isinstance(tag, str)
                    assert len(tag) <= _TAG_MAX_LEN, f"tag too long (prose?): {tag!r}"
                    assert "\n" not in tag


# ---------------------------------------------------------------------------
# Deep-rung visibility. The real-data scans are the stronger rung; when the
# snapshot is absent they skip, and a done-report must not read that as "passed".
# ---------------------------------------------------------------------------


class VendoredSnapshotAbsent(UserWarning):
    """The full-catalog wall scans did not run — synthetic coverage only."""


class TestDeepRungVisibility:
    def test_report_whether_the_real_snapshot_scan_ran(self):
        """Always passes. Emits a LOUD warning when the deep rung is not running,
        so 'wall tests green' can never quietly mean 'wall tests skipped'."""
        present = Path(DEFAULT_LIBRARY_ROOT).is_dir()
        if present:
            return
        notice = (
            "NOTICE: vendored GCS snapshot ABSENT at "
            f"{DEFAULT_LIBRARY_ROOT} — the full-catalog copyright-wall scans "
            "(test_library / test_reference_factfields / test_reference_wiring / "
            "test_sync) SKIPPED. Only the synthetic mini-catalog rung ran. Run "
            "tools/sync_gcs_library.py before treating the wall as verified."
        )
        print(f"\n{'!' * 78}\n{notice}\n{'!' * 78}")
        warnings.warn(notice, VendoredSnapshotAbsent, stacklevel=2)
