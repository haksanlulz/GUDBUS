"""Regression pins for _join_college's non-list passthrough and int(inf) coercion."""

from __future__ import annotations

import math

import pytest

from gurps_bot.gcs.parser import (
    GCSParseError,
    _as_float,
    _as_int,
    _join_college,
    parse_gcs,
)


def _spell_sheet(college: object) -> dict:
    """Minimal v5 sheet with one calc-bearing spell carrying the given college."""
    return {
        "version": 5,
        "profile": {"name": "Tester"},
        "spells": [
            {"name": "Ignite", "calc": {"level": 15, "rsl": "IQ+3"}, "college": college},
        ],
    }


# _join_college's non-list passthrough is pinned on purpose — don't "fix" it
# without updating these assertions deliberately


def test_join_college_list_is_joined_to_string():
    assert _join_college(["Fire", "Air"]) == "Fire, Air"


def test_join_college_list_stringifies_non_str_members():
    assert _join_college(["Fire", 1, None]) == "Fire, 1, None"


def test_join_college_bare_string_passes_through_unchanged():
    assert _join_college("Necromantic") == "Necromantic"


def test_join_college_non_list_non_str_passes_through_raw():
    """Pinned: a non-list, non-str college returns raw — coercing to str is a behavior change."""
    result = _join_college(5)
    assert result == 5
    assert isinstance(result, int)  # NOT coerced to "5"


def test_parse_gcs_spell_int_college_reaches_parsedspell_raw():
    char = parse_gcs(_spell_sheet(5))
    assert len(char.spells) == 1
    assert char.spells[0].college == 5
    assert isinstance(char.spells[0].college, int)


def test_parse_gcs_spell_list_college_normalized_end_to_end():
    char = parse_gcs(_spell_sheet(["Fire", "Air"]))
    assert char.spells[0].college == "Fire, Air"


# regression: the OverflowError / inf fail-open hole stays closed


def test_as_int_inf_coerces_to_default_not_overflow():
    """JSON 1e400 -> inf; int(inf) raises OverflowError and must coerce to the default."""
    assert 1e400 == float("inf")
    assert _as_int(1e400) == 0
    assert _as_int(float("inf"), 7) == 7


def test_as_int_nan_coerces_to_default():
    """nan was already caught (ValueError); pin it so the widening didn't drop it."""
    assert _as_int(float("nan")) == 0


def test_as_float_inf_still_passes_through():
    """float(inf) succeeds, so _as_float still passes inf through."""
    assert _as_float(1e400) == float("inf")
    assert math.isinf(_as_float(float("inf")))


def test_parse_gcs_inf_points_does_not_crash():
    """End-to-end: inf points coerce to 0 mid-parse instead of raising OverflowError."""
    sheet = {
        "version": 5,
        "profile": {"name": "Tester"},
        "traits": [{"name": "Cursed", "calc": {"points": 1e400}}],
    }
    char = parse_gcs(sheet)
    assert len(char.traits) == 1
    assert char.traits[0].points == 0


def test_parse_gcs_still_rejects_bad_version():
    """Sanity: the regression file's helpers don't accidentally weaken the gate."""
    with pytest.raises(GCSParseError):
        parse_gcs({"version": 4, "profile": {"name": "X"}})
