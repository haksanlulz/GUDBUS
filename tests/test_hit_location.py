"""hit_location.py owns all hit-location penalties; damage.py sources them, never retypes."""

from __future__ import annotations

import pytest

from gurps_bot.mechanics import damage
from gurps_bot.mechanics import hit_location as HL
from gurps_bot.mechanics.hit_location import (
    LOCATIONS,
    HitLocation,
    deliberate_locations,
    gross_targeting_reference,
    hit_location,
    hit_location_names,
)


class TestCoverage:
    def test_eye_and_vitals_present(self):
        names = {loc.name.lower() for loc in LOCATIONS}
        assert "eye" in names
        assert "vitals" in names

    def test_random_table_locations_all_owned_here(self):
        table_locs = {loc for _, loc, _ in damage.HIT_LOCATION_TABLE}
        owned = {loc.name for loc in LOCATIONS}
        missing = table_locs - owned
        assert not missing, f"random-table locations missing from owner: {missing}"

    def test_each_location_is_frozen_dataclass(self):
        for loc in LOCATIONS:
            assert isinstance(loc, HitLocation)
            with pytest.raises((AttributeError, Exception)):
                loc.penalty = 0  # frozen

    def test_names_unique(self):
        names = [loc.name for loc in LOCATIONS]
        assert len(names) == len(set(names))

    def test_hit_location_names_helper_matches(self):
        assert hit_location_names() == [loc.name for loc in LOCATIONS]


class TestLookup:
    def test_case_insensitive(self):
        assert hit_location("eye") is hit_location("EYE")
        assert hit_location("Vitals").name == "Vitals"

    def test_total_over_tuple(self):
        for loc in LOCATIONS:
            assert hit_location(loc.name) is loc
            assert hit_location(loc.name.lower()) is loc

    def test_unknown_raises(self):
        with pytest.raises(KeyError):
            hit_location("antenna")


class TestDeliberate:
    def test_deliberate_excludes_random_table_locations(self):
        table_locs = {loc for _, loc, _ in damage.HIT_LOCATION_TABLE}
        for loc in deliberate_locations():
            assert loc.name not in table_locs, loc.name
            assert loc.deliberate_only is True

    def test_eye_and_vitals_are_deliberate(self):
        names = {loc.name for loc in deliberate_locations()}
        assert "Eye" in names
        assert "Vitals" in names

    def test_eye_penalty_is_canonical_minus_nine(self):
        assert hit_location("eye").penalty == -9  # B552

    def test_vitals_penalty_is_canonical_minus_three(self):
        assert hit_location("vitals").penalty == -3  # B552

    def test_every_location_has_an_effect_note(self):
        for loc in LOCATIONS:
            assert loc.effect.strip(), loc.name
            assert len(loc.effect) <= 200, loc.name

    def test_penalties_are_non_positive(self):
        # A hit-location to-hit modifier is never a bonus (torso 0 is the easiest).
        for loc in LOCATIONS:
            assert loc.penalty <= 0, loc.name


class TestSingleOwnership:
    def test_random_table_penalties_equal_the_owner(self):
        # every random-table penalty must equal the owner's — a retyped number fails here
        for _rng, loc_name, penalty in damage.HIT_LOCATION_TABLE:
            assert penalty == hit_location(loc_name).penalty, loc_name

    def test_roll_hit_location_reports_owned_penalty(self):
        # The live roll path must hand back the owner's penalty, not a private copy.
        for _ in range(300):
            res = damage.roll_hit_location()
            assert res.hit_penalty == hit_location(res.location).penalty

    def test_damage_hit_location_names_sourced_from_owner(self):
        # HIT_LOCATION_NAMES (consumed by cogs/rolling.py) is derived from the
        # owner, so every name it lists is a real owned location.
        for name in damage.HIT_LOCATION_NAMES:
            assert hit_location(name).name == name


class TestBackCompatRandomTable:
    def test_known_random_locations_unchanged(self):
        # The canonical random-table penalties (B552) — pinned so a refactor of
        # the owner cannot silently move them.
        expected = {
            "Skull": -7, "Face": -5, "Right Leg": -2, "Right Arm": -2,
            "Torso": 0, "Groin": -3, "Left Arm": -2, "Left Leg": -2,
            "Hand": -4, "Foot": -4, "Neck": -5,
        }
        for name, pen in expected.items():
            assert hit_location(name).penalty == pen, name

    def test_roll_stays_in_3d6_range(self):
        for _ in range(200):
            res = damage.roll_hit_location()
            assert 3 <= res.rolled <= 18
            assert isinstance(res.hit_penalty, int)


# the import-time _validate() guard must actually fire: inject bad data, assert it raises
class TestImportValidateGuard:
    def _run_with_locations(self, locations: tuple[HitLocation, ...]) -> None:
        """_validate() with swapped locations; restore in finally so failures don't leak."""
        orig_locs, orig_by_name = HL.LOCATIONS, HL._BY_NAME
        try:
            HL.LOCATIONS = locations
            HL._BY_NAME = {loc.name.lower(): loc for loc in locations}
            HL._validate()
        finally:
            HL.LOCATIONS, HL._BY_NAME = orig_locs, orig_by_name

    def test_clean_owner_passes(self):
        # The shipped tuple validates — a baseline so a future bad edit is the
        # thing that flips this class red.
        self._run_with_locations(HL.LOCATIONS)

    def test_duplicate_name_is_blocked(self):
        # Two rows claiming one location = two owners for one penalty. Forbidden.
        poisoned = HL.LOCATIONS + (
            HitLocation("Torso", -5, "a second, conflicting Torso owner"),
        )
        with pytest.raises(AssertionError, match="one owner|SSoT|duplicate"):
            self._run_with_locations(poisoned)

    def test_positive_penalty_is_blocked(self):
        poisoned = HL.LOCATIONS + (HitLocation("Halo", +2, "an illegal bonus spot"),)
        with pytest.raises(AssertionError, match="never a bonus|bonus"):
            self._run_with_locations(poisoned)

    def test_empty_effect_is_blocked(self):
        poisoned = HL.LOCATIONS + (HitLocation("Ghost", -1, "   "),)
        with pytest.raises(AssertionError, match="empty effect"):
            self._run_with_locations(poisoned)

    def test_torso_must_be_owned_at_zero(self):
        # Drop Torso entirely -> the "Torso is the easy 0 default" anchor fails.
        no_torso = tuple(loc for loc in HL.LOCATIONS if loc.name != "Torso")
        with pytest.raises(AssertionError, match="Torso"):
            self._run_with_locations(no_torso)


# gross-targeting view sources its penalties from damage.HIT_LOCATION_TABLE, never retypes them
class TestGrossTargetingReference:
    def test_gross_penalties_equal_the_damage_owner(self):
        owner = {loc: pen for _rng, loc, pen in damage.HIT_LOCATION_TABLE}
        for name, penalty, _effect in gross_targeting_reference():
            assert penalty == owner[name], name

    def test_covers_each_random_location_exactly_once(self):
        table_locs = {loc for _, loc, _ in damage.HIT_LOCATION_TABLE}
        names = [name for name, _pen, _eff in gross_targeting_reference()]
        assert sorted(set(names)) == sorted(table_locs)
        assert len(names) == len(set(names)), "a gross location was listed twice"

    def test_every_gross_row_carries_its_owned_effect_note(self):
        for name, _penalty, effect in gross_targeting_reference():
            assert effect == hit_location(name).effect
            assert effect.strip()
