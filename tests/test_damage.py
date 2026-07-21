"""Tests for GURPS damage rolling and hit locations."""

import pytest
from gurps_bot.mechanics.damage import (
    DAMAGE_TYPE_DISPLAY,
    HIT_LOCATION_NAMES,
    WOUNDING_MULTIPLIERS,
    roll_damage,
    roll_hit_location,
)


class TestB399LocationWounding:
    """Wounding modifiers by hit location, straight off B399.

    Asserts the multiplier only (never the rolled total), so these are
    deterministic without patching the dice. Complements TestLocationMultiplierRaw
    below, which pins the same table through a forced roll.
    """

    def _mult(self, damage_type: str, location: str) -> float:
        return roll_damage("2d", damage_type, location=location).wounding_multiplier

    # --- Skull / Eye: x4 for all attacks, EXCEPT toxic ---------------------
    @pytest.mark.parametrize("location", ["Skull", "Eye"])
    @pytest.mark.parametrize("damage_type", ["cr", "cut", "imp", "pi", "burn", "cor"])
    def test_skull_and_eye_are_x4(self, location, damage_type):
        assert self._mult(damage_type, location) == 4.0

    @pytest.mark.parametrize("location", ["Skull", "Eye"])
    def test_toxic_is_exempt_from_the_x4(self, location):
        # B399 Skull: "Exception: None of these effects apply to toxic damage."
        # B399 Eye: "As with skull hits, toxic damage has no special effect."
        assert self._mult("tox", location) == 1.0

    # --- Face: corrosion ONLY ----------------------------------------------
    def test_face_corrosion_is_x1_5(self):
        # "Corrosion damage (only) gets a x1.5 wounding modifier"
        assert self._mult("cor", "Face") == 1.5

    @pytest.mark.parametrize("damage_type", ["cr", "cut", "imp", "pi"])
    def test_face_is_otherwise_unmodified(self, damage_type):
        assert self._mult(damage_type, "Face") == WOUNDING_MULTIPLIERS[damage_type]

    # --- Groin: a torso hit for wounding purposes --------------------------
    @pytest.mark.parametrize("damage_type", ["cr", "cut", "imp", "pi"])
    def test_groin_wounds_exactly_as_torso(self, damage_type):
        # "Treat as a torso hit, except that human males ... suffer double the
        # usual SHOCK from crushing damage ... and get -5 to knockdown rolls."
        # Doubled shock is not a wounding multiplier — there is no x1.5 here.
        assert self._mult(damage_type, "Groin") == self._mult(damage_type, "Torso")

    # --- Vitals: impaling and ANY piercing ---------------------------------
    @pytest.mark.parametrize("damage_type", ["imp", "pi-", "pi", "pi+", "pi++"])
    def test_vitals_x3_covers_every_piercing_size(self, damage_type):
        # "Increase the wounding modifier for an impaling or ANY piercing
        # attack to x3." pi- is small piercing — still piercing.
        assert self._mult(damage_type, "Vitals") == 3.0

    @pytest.mark.parametrize("damage_type", ["cr", "cut"])
    def test_vitals_ignores_non_targeting_types(self, damage_type):
        assert self._mult(damage_type, "Vitals") == WOUNDING_MULTIPLIERS[damage_type]

    # --- Limbs and extremities: large piercing / impaling reduced to x1 -----
    LIMBS = ["Right Arm", "Left Arm", "Right Leg", "Left Leg", "Hand", "Foot"]

    @pytest.mark.parametrize("location", LIMBS)
    @pytest.mark.parametrize("damage_type", ["pi+", "pi++", "imp"])
    def test_limbs_reduce_large_piercing_and_impaling(self, location, damage_type):
        # "reduce the wounding multiplier of large piercing, huge piercing,
        # and impaling damage to x1"
        assert self._mult(damage_type, location) == 1.0

    @pytest.mark.parametrize("location", LIMBS)
    @pytest.mark.parametrize("damage_type", ["cr", "cut", "pi", "pi-"])
    def test_limbs_leave_other_types_alone(self, location, damage_type):
        assert self._mult(damage_type, location) == WOUNDING_MULTIPLIERS[damage_type]

    # --- Neck ---------------------------------------------------------------
    @pytest.mark.parametrize(
        "damage_type,expected", [("cr", 1.5), ("cor", 1.5), ("cut", 2.0)]
    )
    def test_neck(self, damage_type, expected):
        assert self._mult(damage_type, "Neck") == expected


class TestRollDamage:
    def test_basic_cr_damage(self):
        result = roll_damage("2d", "cr")
        assert 2 <= result.raw_damage <= 12
        assert result.wounding_multiplier == 1.0
        assert result.wound == result.raw_damage

    def test_cutting_multiplier(self):
        result = roll_damage("2d", "cut", dr=0)
        assert result.wounding_multiplier == 1.5

    def test_impaling_multiplier(self):
        result = roll_damage("1d", "imp")
        assert result.wounding_multiplier == 2.0

    def test_small_piercing_multiplier(self):
        result = roll_damage("1d", "pi-")
        assert result.wounding_multiplier == 0.5

    def test_dr_reduces_damage(self):
        # DR 100 should reduce everything to 0
        result = roll_damage("2d", "cr", dr=100)
        assert result.raw_damage == 0
        assert result.wound == 0

    def test_skull_location_override(self):
        result = roll_damage("1d", "cr", location="skull")
        assert result.wounding_multiplier == 4.0

    def test_vitals_imp_override(self):
        result = roll_damage("1d", "imp", location="vitals")
        assert result.wounding_multiplier == 3.0

    def test_neck_cut_override(self):
        result = roll_damage("1d", "cut", location="neck")
        assert result.wounding_multiplier == 2.0

    def test_unknown_type_defaults_to_1(self):
        result = roll_damage("1d", "unknown_type")
        assert result.wounding_multiplier == 1.0


class TestHitLocation:
    def test_roll_in_range(self):
        for _ in range(100):
            result = roll_hit_location()
            assert 3 <= result.rolled <= 18
            assert result.location != ""
            assert isinstance(result.hit_penalty, int)

    def test_known_locations(self):
        known = {"Skull", "Face", "Right Leg", "Right Arm", "Torso",
                 "Groin", "Left Arm", "Left Leg", "Hand", "Foot", "Neck"}
        locations_seen: set[str] = set()
        for _ in range(1000):
            result = roll_hit_location()
            locations_seen.add(result.location)
        # 1000 rolls on 3d6 should see most of the table
        assert len(locations_seen) >= 8


class TestWoundingMultipliers:
    def test_all_types_present(self):
        expected = {"pi-", "cr", "burn", "pi", "tox", "cor", "cut", "pi+", "imp", "pi++"}
        assert set(WOUNDING_MULTIPLIERS.keys()) == expected


class TestDamageTypeDisplay:
    """Drift guard: DAMAGE_TYPE_DISPLAY must cover all wounding multiplier keys."""

    def test_keys_match_wounding_multipliers(self):
        assert set(DAMAGE_TYPE_DISPLAY.keys()) == set(WOUNDING_MULTIPLIERS.keys())

    def test_display_names_nonempty(self):
        for key, display in DAMAGE_TYPE_DISPLAY.items():
            assert display, f"Empty display name for {key}"


class TestHitLocationNames:
    """Drift guard: HIT_LOCATION_NAMES covers all canonical locations."""

    def test_minimum_count(self):
        assert len(HIT_LOCATION_NAMES) >= 11

    def test_no_duplicates(self):
        assert len(HIT_LOCATION_NAMES) == len(set(HIT_LOCATION_NAMES))


class TestParseGcsDamage:
    def test_suffix_parsed(self):
        from gurps_bot.mechanics.damage import parse_gcs_damage

        assert parse_gcs_damage("8d burn") == ("8d", "burn")

    def test_suffix_with_modifier(self):
        from gurps_bot.mechanics.damage import parse_gcs_damage

        # 'imp' must win over the substring 'pi' — endswith is anchored on ' imp'
        assert parse_gcs_damage("2d+2 imp") == ("2d+2", "imp")

    def test_no_suffix_defaults_cr(self):
        from gurps_bot.mechanics.damage import parse_gcs_damage

        assert parse_gcs_damage("2d+1") == ("2d+1", "cr")


class TestDamageResultStr:
    def test_str_with_location(self):
        result = roll_damage("1d", "cr", location="Skull")
        assert " to Skull" in str(result)

    def test_str_without_location(self):
        result = roll_damage("1d", "cr")
        assert " to " not in str(result)


class TestRollDamageDefaults:
    def test_empty_type_defaults_cr(self):
        result = roll_damage("1d", "")
        assert result.damage_type == "cr"
        assert result.wounding_multiplier == 1.0


class TestHitLocationFallback:
    """table covers 3-18; the defensive fallback returns Torso for an impossible roll."""

    def test_out_of_range_falls_back_to_torso(self, monkeypatch):
        from gurps_bot.mechanics import dice as dice_mod
        from gurps_bot.mechanics.dice import DiceSpec, RollResult

        forced = RollResult(spec=DiceSpec(3, 6, 0), dice=(1, 1, 1), total=2)
        monkeypatch.setattr(dice_mod, "roll_3d6", lambda: forced)
        result = roll_hit_location()
        assert result.rolled == 2
        assert result.location == "Torso"
        assert result.hit_penalty == 0


class TestNegativeDrClamped:
    """negative dr must clamp to 0, not inflate the wound."""

    def test_negative_dr_does_not_inflate_wound(self):
        # 1d6 (max 6) imp x2 on skull is at most a couple dozen; without the clamp
        # a -1,000,000 dr would balloon the wound into the millions
        res = roll_damage("1d", "imp", dr=-1_000_000, location="skull")
        assert res.wound <= 100


class TestMinimumInjuryFloor:
    """B379: any attack that penetrates DR inflicts at least 1 HP."""

    def _forced(self, monkeypatch, total):
        from gurps_bot.mechanics import damage as dmg_mod
        from gurps_bot.mechanics.dice import DiceSpec, RollResult

        forced = RollResult(spec=DiceSpec(1, 6, 0), dice=(total,), total=total)
        monkeypatch.setattr(dmg_mod, "roll", lambda expr: forced)

    def test_one_point_small_piercing_floors_to_1(self, monkeypatch):
        self._forced(monkeypatch, 1)
        res = roll_damage("1d", "pi-", dr=0)
        assert res.raw_damage == 1
        assert res.wound == 1  # 1 x 0.5 would truncate to 0 without the floor

    def test_penetrating_after_dr_floors_to_1(self, monkeypatch):
        self._forced(monkeypatch, 3)
        res = roll_damage("1d", "pi-", dr=2)
        assert res.raw_damage == 1
        assert res.wound == 1

    def test_no_penetration_stays_0(self, monkeypatch):
        self._forced(monkeypatch, 3)
        res = roll_damage("1d", "cr", dr=5)
        assert res.raw_damage == 0
        assert res.wound == 0


class TestLocationMultiplierRaw:
    """B398-400 cells: groin wounds as torso, face cor x1.5, skull/eye x4 excludes toxic."""

    def _forced(self, monkeypatch, total):
        from gurps_bot.mechanics import damage as dmg_mod
        from gurps_bot.mechanics.dice import DiceSpec, RollResult

        forced = RollResult(spec=DiceSpec(2, 6, 0), dice=(total,), total=total)
        monkeypatch.setattr(dmg_mod, "roll", lambda expr: forced)

    def test_groin_crushing_is_torso_wounding(self, monkeypatch):
        self._forced(monkeypatch, 6)
        res = roll_damage("2d", "cr", location="Groin")
        assert res.wounding_multiplier == 1.0
        assert res.wound == 6

    def test_face_corrosion_x1_5(self, monkeypatch):
        self._forced(monkeypatch, 6)
        res = roll_damage("2d", "cor", location="Face")
        assert res.wounding_multiplier == 1.5
        assert res.wound == 9

    def test_skull_toxic_not_x4(self, monkeypatch):
        self._forced(monkeypatch, 6)
        res = roll_damage("2d", "tox", location="Skull")
        assert res.wounding_multiplier == 1.0
        assert res.wound == 6

    def test_skull_crushing_x4(self, monkeypatch):
        self._forced(monkeypatch, 6)
        res = roll_damage("2d", "cr", location="Skull")
        assert res.wounding_multiplier == 4.0
        assert res.wound == 24
