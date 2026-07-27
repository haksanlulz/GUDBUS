"""Provenance pins for hit locations (operator ruling 2026-07-27).

Four deliberate-only locations are NOT Basic Set content — "vein" and "artery"
appear zero times in either Basic Set volume. They come from GURPS Martial Arts
p.137 "New Hit Locations", where all four penalties verify:

  Jaw (-6): "only valid as a separate target from in front ... a crushing blow
    gives the victim an extra -1 to knockdown rolls."
  Spine (-8): "The spine (in the torso) is a hard target."
  Veins and Arteries (-5 or -8): "The attack has an extra -3: -5 for a limb,
    -8 for the neck."

Operator ruled: keep them, cite Martial Arts, mark optional so a GM reading the
bot can tell core from supplement.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics.hit_location import (
    LOCATIONS,
    MARTIAL_ARTS_SOURCE,
    deliberate_locations,
    hit_location,
)

_MA_LOCATIONS = {
    "Ear",
    "Jaw",
    "Nose",
    "Spine",
    "Limb Joint",
    "Extremity Joint",
    "Limb Vein/Artery",
    "Neck Vein/Artery",
}


class TestMartialArtsLocationsAreMarked:
    @pytest.mark.parametrize("name", sorted(_MA_LOCATIONS))
    def test_marked_with_the_martial_arts_source(self, name):
        loc = hit_location(name)
        assert loc.source == MARTIAL_ARTS_SOURCE
        assert loc.is_optional is True

    @pytest.mark.parametrize(
        "name,penalty",
        [
            # every penalty quoted from MA p.137 "New Hit Locations"
            ("Ear", -7),              # "Ear (-7)"
            ("Jaw", -6),              # "Jaw (-6)"
            ("Nose", -7),             # "Nose (-7)"
            ("Spine", -8),            # "Spine (-8)"
            ("Limb Joint", -5),       # "extra -3: -5 for an arm or a leg ..."
            ("Extremity Joint", -7),  # "... -7 for a hand or a foot"
            ("Limb Vein/Artery", -5), # "extra -3: -5 for a limb ..."
            ("Neck Vein/Artery", -8), # "... -8 for the neck"
        ],
    )
    def test_penalties_verified_against_martial_arts_p137(self, name, penalty):
        assert hit_location(name).penalty == penalty

    def test_joint_pair_mirrors_the_vein_artery_pair(self):
        """Both MA entries split one rule into a limb row and a narrower row;
        keep the naming and the -3-from-base relationship visible."""
        assert hit_location("Limb Joint").penalty == hit_location("Limb Vein/Artery").penalty
        assert hit_location("Extremity Joint").penalty < hit_location("Limb Joint").penalty

    def test_source_string_names_the_book_and_page(self):
        assert "Martial Arts" in MARTIAL_ARTS_SOURCE
        assert "137" in MARTIAL_ARTS_SOURCE


class TestBasicSetLocationsAreNotMarked:
    def test_no_basic_set_location_is_flagged_optional(self):
        for loc in LOCATIONS:
            if loc.name in _MA_LOCATIONS:
                continue
            assert loc.is_optional is False, loc.name
            assert loc.source is None, loc.name

    @pytest.mark.parametrize(
        "name,penalty",
        [("Eye", -9), ("Vitals", -3), ("Skull", -7), ("Torso", 0), ("Neck", -5)],
    )
    def test_core_penalties_unchanged(self, name, penalty):
        assert hit_location(name).penalty == penalty

    def test_eye_and_vitals_stay_deliberate_only_but_core(self):
        """Deliberate-only is orthogonal to optional: both are printed B552."""
        for name in ("Eye", "Vitals"):
            loc = hit_location(name)
            assert loc.deliberate_only is True
            assert loc.is_optional is False


class TestDeliberateSetComposition:
    def test_deliberate_set_is_core_plus_martial_arts(self):
        names = {loc.name for loc in deliberate_locations()}
        assert names == {"Eye", "Vitals"} | _MA_LOCATIONS

    def test_every_optional_location_is_accounted_for(self):
        optional = [loc.name for loc in LOCATIONS if loc.is_optional]
        assert set(optional) == _MA_LOCATIONS
        assert len(optional) == 8

    def test_choice_lists_stay_under_discords_cap(self):
        """/target builds a Choice per deliberate location; Discord allows 25."""
        assert len(deliberate_locations()) <= 25
