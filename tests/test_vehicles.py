"""vehicle calculators (B462-470); pure math, no db, no discord"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics.dice import DiceSpec
from gurps_bot.mechanics.vehicles import (
    Locomotion,
    Terrain,
    VehicleKind,
    classify_control_failure,
    control_effective_skill,
    crash,
    cruising_speed,
    damage_scale,
    deceleration,
    endurance,
    vehicle_dodge,
    yards_per_sec_to_mph,
)


# B462: double yds/sec to get mph
class TestUnitConversion:
    def test_double(self):
        assert yards_per_sec_to_mph(10) == 20.0


# B463/466: cruising speed
class TestCruisingSpeed:
    def test_good_terrain_all_locomotion(self):
        # luxury car Move 3/57 on a road (Good) -> 57 x 1.25 ~ 71 mph (B466 example)
        assert cruising_speed(57, Terrain.GOOD) == 71.25

    def test_average_on_wheels(self):
        # dirt road (Average) on wheels -> x0.5
        assert cruising_speed(57, Terrain.AVERAGE, locomotion=Locomotion.WHEELS) == 28.5

    def test_average_otherwise_full(self):
        # Average terrain, non-wheels -> x1.0
        assert cruising_speed(20, Terrain.AVERAGE, locomotion=Locomotion.TRACKS) == 20.0

    def test_road_bound_off_road_uses_accel_cap(self):
        # off road (Average), road-bound car: min(57, 4*3=12) -> x0.5 = 6 mph (B466 example)
        assert (
            cruising_speed(
                57,
                Terrain.AVERAGE,
                locomotion=Locomotion.WHEELS,
                road_bound=True,
                off_road=True,
                acceleration=3,
            )
            == 6.0
        )

    def test_very_bad_tracks_vs_legs(self):
        assert cruising_speed(20, Terrain.VERY_BAD, locomotion=Locomotion.TRACKS) == 3.0
        assert cruising_speed(20, Terrain.VERY_BAD, locomotion=Locomotion.LEGS) == 4.0

    def test_road_bound_off_road_without_accel_raises(self):
        with pytest.raises(ValueError):
            cruising_speed(
                57, Terrain.AVERAGE, road_bound=True, off_road=True
            )

    def test_negative_top_speed_raises(self):
        with pytest.raises(ValueError):
            cruising_speed(-1, Terrain.GOOD)


# B463: endurance
class TestEndurance:
    def test_hours(self):
        assert endurance(360, 60) == 6.0

    def test_zero_speed_raises(self):
        with pytest.raises(ValueError):
            endurance(360, 0)


# B470: vehicle dodge
class TestVehicleDodge:
    def test_book_example(self):
        # Driving-14 on a motorcycle with Handling +1 -> 14/2 + 1 = 8
        assert vehicle_dodge(14, 1) == 8

    def test_negative_handling(self):
        assert vehicle_dodge(14, -2) == 5

    def test_odd_skill_floors(self):
        assert vehicle_dodge(15, 0) == 7  # floor(15/2)

    def test_negative_skill_raises(self):
        with pytest.raises(ValueError):
            vehicle_dodge(-1, 0)


# B466-467: control rolls
class TestControlRoll:
    def test_effective_skill(self):
        assert control_effective_skill(12, -1, visibility=-3) == 8

    def test_minor_failure_within_sr(self):
        assert classify_control_failure(2, sr=4) == "minor"
        assert classify_control_failure(4, sr=4) == "minor"

    def test_major_failure_beyond_sr(self):
        assert classify_control_failure(6, sr=4) == "major"

    def test_critical_is_major(self):
        assert classify_control_failure(1, sr=4, critical=True) == "major"


# B468: deceleration
class TestDeceleration:
    def test_wheeled_powered(self):
        assert deceleration(0, VehicleKind.WHEELED_POWERED) == 5

    def test_animal_tracked_walking(self):
        assert deceleration(2, VehicleKind.ANIMAL_TRACKED_WALKING) == 10

    def test_air_water_adds_handling(self):
        assert deceleration(2, VehicleKind.AIR_WATER) == 7

    def test_air_water_minimum_one(self):
        assert deceleration(-10, VehicleKind.AIR_WATER) == 1


# B468/430: crash = collision with an immovable object at velocity
class TestCrash:
    def test_velocity_impact_dice(self):
        # immovable object = hard surface (2x HP): (2*10*20)/100 = 4.0d crushing
        r = crash(20, 10)
        assert r.dice_float == 4.0
        assert r.dice == DiceSpec(4, 6, 0)
        assert r.damage_type == "cr"

    def test_ground_skid_third_of_velocity(self):
        # a ground crash skids 1/3 of its velocity before stopping (B469)
        assert crash(20, 10).skid_yards == 6

    def test_zero_velocity_no_damage(self):
        r = crash(0, 10)
        assert r.dice == DiceSpec(0, 6, 0)

    def test_flying_flag_set(self):
        assert crash(30, 10, flying=True).flying is True

    def test_negative_velocity_raises(self):
        with pytest.raises(ValueError):
            crash(-1, 10)


# B470: damage scale
class TestDamageScale:
    def test_decade_scale(self):
        assert damage_scale(150, "D") == 15

    def test_round_half_up(self):
        assert damage_scale(14, "D") == 1   # 1.4 -> 1
        assert damage_scale(15, "D") == 2   # 1.5 -> 2 (0.5 rounds up)

    def test_under_1d(self):
        assert damage_scale(10, "D") == 1

    def test_century_scale(self):
        assert damage_scale(1000, "C") == 10

    def test_unknown_scale_raises(self):
        with pytest.raises(ValueError):
            damage_scale(100, "X")


class TestVehicleGuardsAndRendering:
    """input guards + the crash __str__ (display-layer smoke)"""

    def test_crash_str_grounded(self):
        s = str(crash(40, 20))
        assert "crash @ 40" in s and "skid" in s and "+altitude" not in s

    def test_crash_str_flying_notes_altitude(self):
        assert "+altitude fall" in str(crash(40, 20, flying=True))

    def test_endurance_negative_range_raises(self):
        with pytest.raises(ValueError, match="range_miles"):
            endurance(-1, 100)

    def test_classify_negative_margin_raises(self):
        with pytest.raises(ValueError, match="margin_of_failure"):
            classify_control_failure(-1, 2)

    def test_classify_negative_sr_raises(self):
        with pytest.raises(ValueError, match="sr"):
            classify_control_failure(1, -1)

    def test_crash_nonpositive_hp_raises(self):
        with pytest.raises(ValueError, match="hp"):
            crash(40, 0)

    def test_crash_negative_dr_raises(self):
        with pytest.raises(ValueError, match="dr"):
            crash(40, 20, dr=-1)
