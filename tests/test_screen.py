"""every number on the GM screen is imported from the module that owns it — it retypes nothing"""

from __future__ import annotations

import discord

from gurps_bot.mechanics import encumbrance as enc
from gurps_bot.mechanics import hiking
from gurps_bot.mechanics import speed_range as sr
from gurps_bot.mechanics.combat_constants import STATUS_ICONS, Maneuver, StatusEffect
from gurps_bot.mechanics.reaction import REACTION_BANDS
from gurps_bot.mechanics.tables import (
    CRITICAL_HIT_TABLE,
    CRITICAL_MISS_TABLE,
    FRIGHT_CHECK_TABLE,
)
from gurps_bot.ui import screen

_EMBED_FIELD_LIMIT = 1024


class TestSourcing:
    def test_maneuvers_from_enum(self):
        assert screen.maneuver_names() == [m.value for m in Maneuver]

    def test_status_effects_cover_enum_with_icons(self):
        rows = screen.status_effects()
        assert [r[0] for r in rows] == [s.value for s in StatusEffect]
        for s in StatusEffect:
            assert (s.value, STATUS_ICONS[s]) in rows

    def test_encumbrance_reference_sources_move_multiplier(self):
        rows = {r[0]: r for r in screen.encumbrance_reference()}
        # light band: move x0.8, dodge -1, <= 2xBL
        name, move_mult, dodge_pen, bl_mult = rows["Light"]
        assert move_mult == enc.move_multiplier(1)
        assert dodge_pen == 1
        assert bl_mult == 2.0

    def test_terrain_reference_sources_mult(self):
        rows = dict(screen.terrain_reference())
        assert rows["Average"] == hiking.Terrain.AVERAGE.mult
        assert rows["Good"] == hiking.Terrain.GOOD.mult

    def test_weather_reference_sources_mult(self):
        rows = dict(screen.weather_reference())
        assert rows["Rain"] == hiking.Weather.RAIN.mult

    def test_speed_range_reference_matches_function(self):
        ref = screen.speed_range_reference()
        assert (2.0, 0) in ref
        for dist, penalty in ref:
            assert penalty == sr.speed_range_penalty(dist)

    def test_size_reference_matches_function(self):
        ref = screen.size_reference()
        assert (2.0, 0) in ref
        for length, sm in ref:
            assert sm == sr.size_modifier(length)

    def test_reaction_reference_names_and_ranges(self):
        rows = screen.reaction_reference()
        assert [r[0] for r in rows] == [b.name for b in REACTION_BANDS]
        rng = dict(rows)
        assert rng["Neutral"] == "10-12"
        assert rng["Disastrous"].startswith("≤")
        assert rng["Excellent"].startswith("≥")

    def test_crit_and_fright_reference_are_the_owned_tables(self):
        assert screen.crit_hit_reference() == CRITICAL_HIT_TABLE
        assert screen.crit_miss_reference() == CRITICAL_MISS_TABLE
        assert screen.fright_reference()[0] == FRIGHT_CHECK_TABLE[0]


class TestPages:
    def test_build_returns_embeds_with_titles(self):
        pages = screen.build_screen_pages()
        assert len(pages) == len(screen.CATEGORIES)
        for p in pages:
            assert isinstance(p, discord.Embed)
            assert p.title

    def test_every_field_within_discord_cap(self):
        for p in screen.build_screen_pages():
            for field in p.fields:
                assert len(field.value) <= _EMBED_FIELD_LIMIT, field.name

    def test_category_index_maps_to_valid_pages(self):
        pages = screen.build_screen_pages()
        for cat in screen.CATEGORIES:
            idx = screen.CATEGORY_INDEX[cat]
            assert 0 <= idx < len(pages)


from gurps_bot.mechanics import damage
from gurps_bot.mechanics.hit_location import deliberate_locations
from gurps_bot.mechanics.posture import POSTURES


class TestBodySourcing:
    def test_posture_reference_reflects_owner(self):
        rows = screen.posture_reference()
        assert [r["name"] for r in rows] == [p.name for p in POSTURES]
        by_name = {p.name: p for p in POSTURES}
        for r in rows:
            p = by_name[r["name"]]
            assert r["attack"] == p.attack_penalty
            assert r["defense"] == p.defense_modifier
            assert r["ranged"] == p.ranged_to_hit_you
            assert r["melee"] == p.melee_to_hit_you
            assert r["move"] == p.move_fraction
            assert r["effect"] == p.effect

    def test_targeting_reference_reflects_owner_and_is_deliberate_only(self):
        rows = screen.targeting_reference()
        owned = {loc.name: loc for loc in deliberate_locations()}
        assert {r["name"] for r in rows} == set(owned)
        for r in rows:
            loc = owned[r["name"]]
            assert r["penalty"] == loc.penalty
            assert r["effect"] == loc.effect

    def test_targeting_reference_does_not_retype_random_table_numbers(self):
        # deliberate-only rows are disjoint from the random table by construction
        table_locs = {loc for _, loc, _ in damage.HIT_LOCATION_TABLE}
        for r in screen.targeting_reference():
            assert r["name"] not in table_locs, r["name"]

    def test_eye_and_vitals_appear_on_body_targeting(self):
        names = {r["name"] for r in screen.targeting_reference()}
        assert "Eye" in names
        assert "Vitals" in names

    def test_gross_target_penalties_sourced_from_damage_table(self):
        # gross aim penalties must equal damage.py's table, location-for-location
        owner = {loc: pen for _rng, loc, pen in damage.HIT_LOCATION_TABLE}
        shown = {g["name"]: g["penalty"] for g in screen.gross_target_reference()}
        assert shown, "body page should list gross aim penalties"
        for name, pen in shown.items():
            assert pen == owner[name], name
        # B552 anchors: catch a transcription flip even if both sides moved together
        assert shown["Skull"] == -7
        assert shown["Face"] == -5
        assert shown["Torso"] == 0

    def test_gross_targets_cover_every_random_table_location_once(self):
        # sided rows (arm/leg span two 3d6 ranges) collapse to one entry per location
        table_locs = {loc for _, loc, _ in damage.HIT_LOCATION_TABLE}
        shown = [g["name"] for g in screen.gross_target_reference()]
        assert sorted(set(shown)) == sorted(table_locs)
        assert len(shown) == len(set(shown)), "a location was listed twice"


class TestBodyPage:
    def test_body_in_categories_and_index(self):
        assert "body" in screen.CATEGORIES
        assert "body" in screen.CATEGORY_INDEX
        idx = screen.CATEGORY_INDEX["body"]
        pages = screen.build_screen_pages()
        assert 0 <= idx < len(pages)

    def test_body_page_title_contains_body(self):
        page = screen.body_page()
        assert "Body" in page.title

    def test_body_page_resolved_via_category_index(self):
        pages = screen.build_screen_pages()
        page = pages[screen.CATEGORY_INDEX["body"]]
        assert "Body" in page.title

    def test_body_page_fields_within_cap(self):
        page = screen.body_page()
        assert page.fields, "body page should have fields"
        for f in page.fields:
            assert len(f.value) <= _EMBED_FIELD_LIMIT, f.name

    def test_body_page_mentions_a_posture_and_a_deliberate_location(self):
        # guard against an empty-shell embed
        page = screen.body_page()
        blob = page.title + "\n" + "\n".join(
            f.name + "\n" + f.value for f in page.fields
        )
        assert "Standing" in blob
        assert "Eye" in blob
