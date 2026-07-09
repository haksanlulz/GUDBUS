"""GURPS collision & slam damage (B430, B371)."""

import pytest

from gurps_bot.mechanics.collision import (
    CollisionAngle,
    CollisionParty,
    CollisionResult,
    collision_dice,
    collision_velocity,
    immovable_collision,
    resolve_collision,
    resolve_slam,
)
from gurps_bot.mechanics.dice import DiceSpec, roll


# collision_dice: core formula + B430 sub-1d banding
class TestCollisionDice:
    def test_car_example_12d(self):
        # B431: 60 HP * 20 yd/s / 100 = 12.0 -> 12d crushing
        assert collision_dice(hp=60, velocity=20) == DiceSpec(count=12, sides=6, modifier=0)

    def test_pedestrian_example_2d(self):
        # B431: 10 HP * 20 / 100 = 2.0 -> 2d
        assert collision_dice(hp=10, velocity=20) == DiceSpec(count=2, sides=6, modifier=0)

    def test_bill_fall_hard_surface_round_up(self):
        # B431: 2 * 10 HP * 19 / 100 = 3.8 -> round-half-up -> 4d
        assert collision_dice(hp=10, velocity=19, hard_multiplier=2) == DiceSpec(
            count=4, sides=6, modifier=0
        )

    def test_lowest_subband_1d_minus_3(self):
        # x = 0.2 -> within (0, 0.25] -> 1d-3
        assert collision_dice(hp=10, velocity=2) == DiceSpec(count=1, sides=6, modifier=-3)

    def test_upper_subband_1d_minus_1(self):
        # x = 0.7 -> >0.5 and <1.0 -> 1d-1 ("any larger fraction")
        assert collision_dice(hp=10, velocity=7) == DiceSpec(count=1, sides=6, modifier=-1)

    def test_mid_subband_1d_minus_2(self):
        # x = 0.4 -> (0.25, 0.5] -> 1d-2
        assert collision_dice(hp=10, velocity=4) == DiceSpec(count=1, sides=6, modifier=-2)

    def test_boundary_quarter_rounds_into_lower_band(self):
        # x = 5 * 5 / 100 = 0.25 exactly -> <=0.25 -> 1d-3 (not 1d-2)
        assert collision_dice(hp=5, velocity=5) == DiceSpec(count=1, sides=6, modifier=-3)

    def test_boundary_half_rounds_into_lower_band(self):
        # x = 5 * 10 / 100 = 0.5 exactly -> <=0.5 -> 1d-2 (not 1d-1)
        assert collision_dice(hp=5, velocity=10) == DiceSpec(count=1, sides=6, modifier=-2)

    def test_just_above_half_is_1d_minus_1(self):
        # 6 * 10 / 100 = 0.6 -> >0.5 -> 1d-1
        assert collision_dice(hp=6, velocity=10) == DiceSpec(count=1, sides=6, modifier=-1)

    def test_round_half_up_exactly_half(self):
        # x = 14 * 25 / 100 = 3.5 -> round-half-up -> 4d
        assert collision_dice(hp=14, velocity=25) == DiceSpec(count=4, sides=6, modifier=0)

    def test_round_half_up_just_below_half_rounds_down(self):
        assert collision_dice(hp=12, velocity=29) == DiceSpec(count=3, sides=6, modifier=0)
        # 12*29 = 348 -> 3.48 -> 3d

    def test_exact_integer_no_banding(self):
        # x = 12.0 exactly -> 12d, modifier 0
        spec = collision_dice(hp=60, velocity=20)
        assert spec.count == 12
        assert spec.modifier == 0

    def test_just_at_one_is_full_die(self):
        # x = 10 * 10 / 100 = 1.0 -> exactly 1 die, modifier 0 (NOT 1d-1)
        assert collision_dice(hp=10, velocity=10) == DiceSpec(count=1, sides=6, modifier=0)

    def test_half_damage_halves_before_rounding(self):
        # full x = 20*20/100 = 4.0 -> 4d; with half_damage x = 2.0 -> 2d
        assert collision_dice(hp=20, velocity=20, half_damage=True) == DiceSpec(
            count=2, sides=6, modifier=0
        )

    def test_half_damage_can_drop_into_subband(self):
        # full x = 1.4 (14*10/100); half -> 0.7 -> 1d-1, NOT half of "1d"
        assert collision_dice(hp=14, velocity=10, half_damage=True) == DiceSpec(
            count=1, sides=6, modifier=-1
        )

    def test_zero_velocity_raises(self):
        with pytest.raises(ValueError):
            collision_dice(hp=10, velocity=0)

    def test_negative_velocity_raises(self):
        with pytest.raises(ValueError):
            collision_dice(hp=10, velocity=-5)

    def test_zero_hp_raises(self):
        with pytest.raises(ValueError):
            collision_dice(hp=0, velocity=20)

    def test_excessive_dice_count_raises(self):
        # locomotive: 1000 HP * 60 / 100 = 600 dice -> exceeds dice.py max of 100
        with pytest.raises(ValueError):
            collision_dice(hp=1000, velocity=60)

    def test_max_dice_at_limit_ok(self):
        # 500 HP * 20 / 100 = 100 dice -> exactly at the cap, allowed
        assert collision_dice(hp=500, velocity=20) == DiceSpec(count=100, sides=6, modifier=0)

    def test_returned_spec_is_rollable(self):
        spec = collision_dice(hp=60, velocity=20)
        result = roll(spec)
        assert 12 <= result.total <= 72  # 12d6 range

    def test_subband_spec_str_format(self):
        # "1d-3" formatting comes from DiceSpec.__str__
        assert str(collision_dice(hp=10, velocity=2)) == "1d-3"
        assert str(collision_dice(hp=10, velocity=7)) == "1d-1"


# collision_velocity: B431 angle rules
class TestCollisionVelocity:
    def test_rear_end_subtracts(self):
        assert collision_velocity(v_striker=25, v_struck=5, angle=CollisionAngle.REAR_END) == 20

    def test_head_on_sums(self):
        assert collision_velocity(v_striker=25, v_struck=15, angle=CollisionAngle.HEAD_ON) == 40

    def test_side_on_uses_striker_only(self):
        assert collision_velocity(v_striker=30, v_struck=99, angle=CollisionAngle.SIDE_ON) == 30

    def test_rear_end_struck_faster_clamps_to_zero(self):
        # struck faster than striker -> negative closing -> clamp to 0
        assert collision_velocity(v_striker=10, v_struck=25, angle=CollisionAngle.REAR_END) == 0

    def test_head_on_with_stationary(self):
        assert collision_velocity(v_striker=20, v_struck=0, angle=CollisionAngle.HEAD_ON) == 20


# resolve_collision: end-to-end with B431 cap
class TestResolveCollision:
    def test_car_vs_pedestrian_rear_end(self):
        result = resolve_collision(
            striker=CollisionParty(hp=60, velocity=25),
            struck=CollisionParty(hp=10, velocity=5),
            angle=CollisionAngle.REAR_END,
        )
        assert result.collision_velocity == 20
        assert result.striker_damage == DiceSpec(count=12, sides=6, modifier=0)
        assert result.struck_damage == DiceSpec(count=2, sides=6, modifier=0)
        assert result.struck_dice_capped is False
        assert result.striker_type == "cr"
        assert result.struck_type == "cr"

    def test_heavy_struck_dice_capped_to_striker(self):
        # light striker (5 HP) vs heavy struck (200 HP) -> struck would do 60d, cap to striker's 2d
        result = resolve_collision(
            striker=CollisionParty(hp=5, velocity=30),
            struck=CollisionParty(hp=200, velocity=0),
            angle=CollisionAngle.SIDE_ON,
        )
        assert result.collision_velocity == 30
        # striker: 5*30/100 = 1.5 -> 2d
        assert result.striker_damage == DiceSpec(count=2, sides=6, modifier=0)
        # struck raw: 200*30/100 = 60 -> 60d, capped down to 2d
        assert result.struck_damage.count == 2
        assert result.struck_dice_capped is True

    def test_no_cap_when_struck_fewer_dice(self):
        result = resolve_collision(
            striker=CollisionParty(hp=60, velocity=25),
            struck=CollisionParty(hp=10, velocity=5),
            angle=CollisionAngle.REAR_END,
        )
        assert result.struck_dice_capped is False

    def test_cap_compares_whole_die_counts_subband_equal(self):
        # SIDE_ON -> both parties use striker's v=7: 10*7/100 = 0.7 -> 1d-1 each
        result = resolve_collision(
            striker=CollisionParty(hp=10, velocity=7),
            struck=CollisionParty(hp=10, velocity=2),
            angle=CollisionAngle.SIDE_ON,
        )
        # equal counts (1 == 1) -> no cap
        assert result.struck_dice_capped is False

    def test_streamlined_striker_half_damage_and_type(self):
        # streamlined striker: half damage, type becomes imp (provided)
        result = resolve_collision(
            striker=CollisionParty(
                hp=20, velocity=20, streamlined=True, damage_type="imp"
            ),
            struck=CollisionParty(hp=10, velocity=0),
            angle=CollisionAngle.SIDE_ON,
        )
        # striker full x = 20*20/100 = 4.0; half -> 2.0 -> 2d
        assert result.striker_damage == DiceSpec(count=2, sides=6, modifier=0)
        assert result.striker_type == "imp"
        # struck not streamlined -> cr
        assert result.struck_type == "cr"

    def test_default_angle_is_side_on(self):
        result = resolve_collision(
            striker=CollisionParty(hp=10, velocity=20),
            struck=CollisionParty(hp=10, velocity=99),
        )
        # default SIDE_ON -> velocity = striker's 20, struck speed ignored
        assert result.collision_velocity == 20

    def test_overrun_thrust_st_when_sm_diff_ge_2(self):
        # striker SM 4, struck SM 1 -> diff 3 >= 2 -> overrun; thrust ST = half striker HP
        result = resolve_collision(
            striker=CollisionParty(hp=30, velocity=20, size_modifier=4),
            struck=CollisionParty(hp=10, velocity=0, size_modifier=1),
            angle=CollisionAngle.SIDE_ON,
        )
        assert result.overrun_thrust_st == 15  # half of 30

    def test_no_overrun_when_sm_diff_lt_2(self):
        result = resolve_collision(
            striker=CollisionParty(hp=30, velocity=20, size_modifier=1),
            struck=CollisionParty(hp=10, velocity=0, size_modifier=0),
            angle=CollisionAngle.SIDE_ON,
        )
        assert result.overrun_thrust_st is None

    def test_result_is_collision_result_type(self):
        result = resolve_collision(
            striker=CollisionParty(hp=10, velocity=20),
            struck=CollisionParty(hp=10, velocity=0),
        )
        assert isinstance(result, CollisionResult)


# resolve_slam: B371 symmetric
class TestResolveSlam:
    def test_symmetric_slam_stationary_foe(self):
        result = resolve_slam(attacker_hp=14, attacker_move=5, target_hp=14, target_move_toward=0)
        assert result.collision_velocity == 5
        # 14 * 5 / 100 = 0.7 -> 1d-1 for both
        assert result.striker_damage == DiceSpec(count=1, sides=6, modifier=-1)
        assert result.struck_damage == DiceSpec(count=1, sides=6, modifier=-1)
        assert result.striker_type == "cr"
        assert result.struck_type == "cr"

    def test_head_on_slam_adds_relative_velocity(self):
        # attacker moves 3, target moves 3 toward -> relative velocity 6
        result = resolve_slam(attacker_hp=20, attacker_move=3, target_hp=20, target_move_toward=3)
        assert result.collision_velocity == 6
        # 20 * 6 / 100 = 1.2 -> 1d for both
        assert result.striker_damage == DiceSpec(count=1, sides=6, modifier=0)
        assert result.struck_damage == DiceSpec(count=1, sides=6, modifier=0)

    def test_asymmetric_hp_slam(self):
        # heavier attacker hits lighter foe; foe's lower HP -> fewer/equal dice (cap may apply)
        result = resolve_slam(attacker_hp=30, attacker_move=10, target_hp=10, target_move_toward=0)
        # attacker: 30*10/100 = 3.0 -> 3d; target: 10*10/100 = 1.0 -> 1d
        assert result.striker_damage == DiceSpec(count=3, sides=6, modifier=0)
        assert result.struck_damage == DiceSpec(count=1, sides=6, modifier=0)

    def test_slam_zero_move_raises(self):
        # no movement -> velocity 0 -> no slam damage
        with pytest.raises(ValueError):
            resolve_slam(attacker_hp=14, attacker_move=0, target_hp=14, target_move_toward=0)


# immovable_collision: B431
class TestImmovableCollision:
    def test_soft_immovable_normal_damage(self):
        # soft obstacle: normal collision damage. 10 HP * 19 / 100 = 1.9 -> 2d
        assert immovable_collision(hp=10, velocity=19) == DiceSpec(count=2, sides=6, modifier=0)

    def test_hard_immovable_doubles_hp(self):
        # Bill fall onto hard ground: 2 * 10 * 19 / 100 = 3.8 -> 4d
        assert immovable_collision(hp=10, velocity=19, hard=True) == DiceSpec(
            count=4, sides=6, modifier=0
        )

    def test_breakable_obstacle_caps_at_hp_plus_dr(self):
        # moving body would do 4d but breakable wall is HP+DR=2 -> cap die count to 2
        spec = immovable_collision(hp=10, velocity=19, hard=True, obstacle_hp_plus_dr=2)
        assert spec.count == 2

    def test_breakable_cap_not_applied_when_below(self):
        # moving body does 2d, wall HP+DR = 10 -> no cap (2 <= 10)
        spec = immovable_collision(hp=10, velocity=19, obstacle_hp_plus_dr=10)
        assert spec == DiceSpec(count=2, sides=6, modifier=0)

    def test_immovable_zero_velocity_raises(self):
        with pytest.raises(ValueError):
            immovable_collision(hp=10, velocity=0)


class TestCollisionParty:
    def test_defaults(self):
        p = CollisionParty(hp=10, velocity=20)
        assert p.weight is None
        assert p.streamlined is False
        assert p.damage_type == "cr"
        assert p.size_modifier == 0

    def test_weight_is_advisory_only(self):
        # two parties identical except weight -> identical damage (weight not in formula)
        light = resolve_collision(
            CollisionParty(hp=10, velocity=20, weight=50.0),
            CollisionParty(hp=10, velocity=0),
        )
        heavy = resolve_collision(
            CollisionParty(hp=10, velocity=20, weight=5000.0),
            CollisionParty(hp=10, velocity=0),
        )
        assert light.striker_damage == heavy.striker_damage
        assert light.struck_damage == heavy.struck_damage
