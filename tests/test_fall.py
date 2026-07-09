"""Fall damage (B431); expected velocities come from v = round(sqrt(21.4*g*d))."""

from __future__ import annotations

import pytest

from gurps_bot.mechanics import fall
from gurps_bot.mechanics.dice import DiceSpec, RollResult
from gurps_bot.mechanics.fall import (
    FallResult,
    compute_fall,
    fall_damage_dice,
    fall_velocity,
    feet_to_yards,
)


def test_velocity_lower_bound():
    # sqrt(21.4*1) = 4.63 -> 5  (smallest table entry)
    assert fall_velocity(1) == 5


def test_velocity_at_100():
    # sqrt(21.4*100) = 46.26 -> 46
    assert fall_velocity(100) == 46


def test_formula_diverges_from_printed_table_at_100():
    # printed table says 100-103yd -> 47; the formula gives 46. deliberate:
    # the formula wins, not the table's range-midpoint rounding
    assert fall_velocity(100) == 46


def test_velocity_bill_example():
    # book example: Bill's 17yd fall -> v19
    assert fall_velocity(17) == 19


def test_velocity_zero_distance():
    assert fall_velocity(0) == 0


def test_velocity_negative_distance():
    assert fall_velocity(-10) == 0


def test_velocity_terminal_default_cap_60():
    # sqrt(21.4*200) = 65.4 -> 65 uncapped, clamped to the default 60
    assert fall_velocity(200) == 60


def test_velocity_terminal_cap_swan_dive_100():
    # swan-dive ceiling 100 -> the uncapped 65 passes through
    assert fall_velocity(200, terminal_velocity=100) == 65


def test_velocity_terminal_cap_disabled():
    assert fall_velocity(200, terminal_velocity=None) == 65


def test_velocity_gravity_scales_sqrt():
    # velocity scales with sqrt(g): 4x gravity doubles it
    base = fall_velocity(10, gravity=1.0, terminal_velocity=None)
    quad = fall_velocity(10, gravity=4.0, terminal_velocity=None)
    assert quad == round(base * 2) or quad == fall_velocity(40, terminal_velocity=None)


def test_velocity_gravity_zero():
    assert fall_velocity(100, gravity=0.0) == 0


def test_velocity_gravity_negative_no_impact():
    # g <= 0 -> product <= 0 -> velocity 0, nothing negative under the sqrt
    assert fall_velocity(100, gravity=-1.0) == 0


def test_feet_to_yards_exact():
    assert feet_to_yards(51) == 17.0


def test_feet_to_yards_fractional_not_rounded():
    # 3.333yd must stay fractional for the sqrt
    assert feet_to_yards(10) == pytest.approx(10 / 3.0)


def test_feet_to_yards_fractional_velocity_25ft():
    # 25ft = 8.333yd -> round(sqrt(21.4*8.333)) = round(13.35) = 13
    assert fall_velocity(feet_to_yards(25)) == 13


def test_feet_to_yards_fractional_velocity_10ft():
    # 10ft = 3.333yd -> round(sqrt(21.4*3.333)) = round(8.45) = 8
    assert fall_velocity(feet_to_yards(10)) == 8


def test_dice_bill_example():
    dice_float, spec = fall_damage_dice(hp=10, velocity=19, hp_multiplier=2)
    assert dice_float == pytest.approx(3.8)
    assert spec == DiceSpec(count=4, sides=6, modifier=0)
    assert str(spec) == "4d"


def test_dice_round_up_to_whole_die():
    # 3.2d -> ceil -> 4d, one rollable attack
    dice_float, spec = fall_damage_dice(hp=10, velocity=16, hp_multiplier=2)
    assert dice_float == pytest.approx(3.2)
    assert spec.count == 4


def test_dice_soft_surface_multiplier_1():
    dice_float, spec = fall_damage_dice(hp=10, velocity=19, hp_multiplier=1)
    assert dice_float == pytest.approx(1.9)
    assert spec.count == 2


def test_dice_zero_velocity_no_dice():
    dice_float, spec = fall_damage_dice(hp=10, velocity=0)
    assert dice_float == 0
    assert spec.count == 0


def test_dice_min_one_die_when_positive():
    # ceil of any positive float -> at least 1 die
    dice_float, spec = fall_damage_dice(hp=1, velocity=1, hp_multiplier=2)
    assert dice_float == pytest.approx(0.02)
    assert spec.count == 1


def test_dice_spec_always_d6_no_modifier():
    _, spec = fall_damage_dice(hp=10, velocity=19)
    assert spec.sides == 6
    assert spec.modifier == 0


def test_compute_requires_exactly_one_distance_neither():
    with pytest.raises(ValueError):
        compute_fall(hp=10)


def test_compute_requires_exactly_one_distance_both():
    with pytest.raises(ValueError):
        compute_fall(distance_yards=17, distance_feet=51, hp=10)


def test_compute_bill_example_hard():
    r = compute_fall(distance_yards=17, hp=10, surface="hard")
    assert r.velocity == 19
    assert r.dice_float == pytest.approx(3.8)
    assert r.dice == DiceSpec(4, 6, 0)
    assert str(r.dice) == "4d"
    assert r.damage_type == "cr"
    assert r.hp_multiplier == 2
    assert r.surface == "hard"
    assert r.distance_yards == 17
    assert r.effective_distance_yards == 17


def test_compute_acrobatics_reduces_distance():
    r = compute_fall(distance_yards=17, hp=10, acrobatics_success=True)
    assert r.effective_distance_yards == 12
    assert r.velocity == 16
    assert r.dice_float == pytest.approx(3.2)
    assert str(r.dice) == "4d"
    assert r.acrobatics_success is True


def test_compute_feet_conversion_matches_bill():
    r = compute_fall(distance_feet=51, hp=10)
    assert r.distance_yards == 17.0
    assert r.velocity == 19
    assert str(r.dice) == "4d"


def test_compute_catfall_zeroes_short_fall():
    r = compute_fall(distance_yards=4, hp=10, has_catfall=True)
    assert r.effective_distance_yards == 0
    assert r.velocity == 0
    assert r.dice_float == 0
    assert r.dice.count == 0
    assert r.roll_result is None
    assert r.has_catfall is True


def test_compute_catfall_real_fall_halves_after_formula():
    # 30 -> 25yd (v23); base (2*10*23)/100 = 4.6d halved to 2.3d -> ceil 3d
    r = compute_fall(distance_yards=30, hp=10, has_catfall=True)
    assert r.effective_distance_yards == 25
    assert r.velocity == 23
    assert r.dice_float == pytest.approx(2.3)
    assert r.dice.count == 3  # ceil(2.3)


def test_compute_terminal_velocity_cap_long_fall():
    r = compute_fall(distance_yards=200, hp=10, terminal_velocity=60)
    assert r.velocity == 60


def test_compute_acrobatics_and_catfall_stack():
    # both subtract 5yd (total -10) AND catfall halves: 30 -> 20yd
    # v(20) = round(sqrt(21.4*20)) = round(20.69) = 21
    # base (2*10*21)/100 = 4.2d halved to 2.1d -> ceil 3d
    r = compute_fall(
        distance_yards=30, hp=10, acrobatics_success=True, has_catfall=True
    )
    assert r.effective_distance_yards == 20
    assert r.velocity == 21
    assert r.dice_float == pytest.approx(2.1)
    assert r.dice.count == 3


def test_compute_soft_surface_uses_1x_hp():
    hard = compute_fall(distance_yards=17, hp=10, surface="hard")
    soft = compute_fall(distance_yards=17, hp=10, surface="soft")
    assert hard.hp_multiplier == 2
    assert soft.hp_multiplier == 1
    assert soft.dice_float == pytest.approx(1.9)
    assert soft.dice.count == 2


def test_compute_surface_dr_adds_to_total_dr():
    r = compute_fall(distance_yards=17, hp=10, dr=2, surface="soft", surface_dr=10)
    assert r.total_dr == 12


def _force_roll(monkeypatch, total: int):
    def fake_roll(spec):
        return RollResult(spec=spec, dice=(total,), total=total)

    monkeypatch.setattr(fall, "roll", fake_roll)


def test_compute_roll_damage_penetrates_no_dr(monkeypatch):
    _force_roll(monkeypatch, 14)
    r = compute_fall(distance_yards=17, hp=10, dr=0, roll_damage=True)
    assert r.roll_result is not None
    assert r.roll_result.total == 14
    assert r.penetrating_damage == 14
    assert r.blunt_trauma == 0  # damage penetrated, no blunt trauma


def test_compute_roll_damage_armor_stops_all_blunt_trauma(monkeypatch):
    _force_roll(monkeypatch, 14)
    r = compute_fall(distance_yards=17, hp=10, dr=20, roll_damage=True)
    assert r.penetrating_damage == 0
    assert r.blunt_trauma == 14 // 5  # 2 HP injury through stopping armor


def test_compute_no_roll_leaves_roll_fields_none():
    r = compute_fall(distance_yards=17, hp=10)
    assert r.roll_result is None
    assert r.penetrating_damage is None
    assert r.blunt_trauma is None


def test_compute_roll_damage_zero_dice_no_roll(monkeypatch):
    # catfall-zeroed fall must not roll 0 dice even with roll_damage=True
    _force_roll(monkeypatch, 99)  # would be obviously wrong if called
    r = compute_fall(distance_yards=4, hp=10, has_catfall=True, roll_damage=True)
    assert r.dice.count == 0
    assert r.roll_result is None
    assert r.penetrating_damage is None
    assert r.blunt_trauma is None


def test_fallresult_is_frozen():
    r = compute_fall(distance_yards=17, hp=10)
    assert isinstance(r, FallResult)
    with pytest.raises((AttributeError, TypeError)):
        r.velocity = 99  # frozen dataclass


def test_fallresult_has_all_spec_fields():
    r = compute_fall(distance_yards=17, hp=10)
    for field in (
        "distance_yards",
        "effective_distance_yards",
        "velocity",
        "hp",
        "surface",
        "hp_multiplier",
        "dice_float",
        "dice",
        "damage_type",
        "acrobatics_success",
        "has_catfall",
        "total_dr",
        "roll_result",
        "penetrating_damage",
        "blunt_trauma",
    ):
        assert hasattr(r, field), f"FallResult missing field {field!r}"


class TestFallRendering:
    """FallResult.__str__ with and without a damage roll (display-layer smoke)."""

    def test_str_without_roll(self):
        s = str(compute_fall(distance_feet=30, hp=10))
        assert "fall" in s and "->" in s and "rolled" not in s

    def test_str_with_roll_includes_rolled(self):
        assert "rolled" in str(compute_fall(distance_feet=30, hp=10, roll_damage=True))

    def test_str_with_blunt_trauma(self):
        # B379: DR stops everything -> blunt trauma computed and shown
        r = compute_fall(distance_feet=30, hp=20, dr=1000, roll_damage=True)
        assert r.penetrating_damage == 0
        assert r.blunt_trauma and "blunt" in str(r)
