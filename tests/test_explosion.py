"""Explosion math: concussion falloff + fragmentation (B414-415)."""

import pytest

from gurps_bot.mechanics.explosion import (
    CollateralAtRange,
    ExplosionResult,
    FragmentationAttack,
    explosion_collateral,
    explosion_report,
    fragmentation_attack,
    fragmentation_radius,
    fragments_hitting,
)


def _dmg_map(collateral: tuple[CollateralAtRange, ...]) -> dict[int, int]:
    return {c.distance: c.damage for c in collateral}


class TestExplosionCollateral:
    """Concussion falloff: floor(basic / (divisor_per_yard * distance)). B414-415."""

    def test_core_falloff(self):
        # 6d explosion rolling 21 -> 0:21, 1:7, 2:3, 3:2, 7:1, 8:0
        result = explosion_collateral(21, [0, 1, 2, 3, 7, 8])
        assert _dmg_map(result) == {0: 21, 1: 7, 2: 3, 3: 2, 7: 1, 8: 0}

    def test_distance_zero_is_full_damage(self):
        # blast center: no division, full damage
        result = explosion_collateral(21, [0])
        assert result[0].distance == 0
        assert result[0].damage == 21

    def test_rounds_down(self):
        # floor(21/6)=3 not 3.5; floor(21/9)=2 not 2.33
        result = explosion_collateral(21, [2, 3])
        assert _dmg_map(result) == {2: 3, 3: 2}

    def test_returns_one_entry_per_distance(self):
        result = explosion_collateral(21, [0, 1, 2, 3, 7, 8])
        assert len(result) == 6
        assert all(isinstance(c, CollateralAtRange) for c in result)

    def test_preserves_distance_order(self):
        result = explosion_collateral(30, [3, 1, 5])
        assert [c.distance for c in result] == [3, 1, 5]

    def test_underwater_divisor_is_range_only(self):
        # B415 underwater: divisor is 1*range; floor(21/2) = 10
        result = explosion_collateral(21, [2], environment="underwater")
        assert _dmg_map(result) == {2: 10}

    def test_vacuum_divisor_is_ten_times_range(self):
        # B415 vacuum: divisor is 10*range; floor(21/20) = 1
        result = explosion_collateral(21, [2], environment="vacuum")
        assert _dmg_map(result) == {2: 1}

    def test_environment_only_changes_constant_at_distance_zero(self):
        # distance 0 never divides, whatever the environment
        for env in ("normal", "underwater", "vacuum"):
            result = explosion_collateral(21, [0], environment=env)
            assert result[0].damage == 21

    def test_long_range_floors_to_zero(self):
        # floor(21/24) = 0 -> legit zero entry
        result = explosion_collateral(21, [8])
        assert result[0].damage == 0

    def test_zero_basic_damage(self):
        result = explosion_collateral(0, [0, 1, 2])
        assert _dmg_map(result) == {0: 0, 1: 0, 2: 0}

    def test_damage_never_negative(self):
        result = explosion_collateral(1, [100])
        assert result[0].damage == 0
        assert result[0].damage >= 0

    def test_empty_distances(self):
        result = explosion_collateral(21, [])
        assert result == ()

    def test_negative_distance_raises(self):
        with pytest.raises(ValueError):
            explosion_collateral(10, [-1])

    def test_negative_distance_in_middle_raises(self):
        with pytest.raises(ValueError):
            explosion_collateral(21, [0, 1, -3])

    def test_unknown_environment_raises(self):
        with pytest.raises(ValueError):
            explosion_collateral(21, [1], environment="lava")


class TestFragmentationRadius:
    """Danger radius (yards) = 5 * frag_dice. B414."""

    def test_two_dice(self):
        # book example: 2d -> 5*2 = 10 yd
        assert fragmentation_radius(2) == 10

    def test_four_dice(self):
        # linear 5x: a subtraction misread gives 1, multiplication gives 20
        assert fragmentation_radius(4) == 20

    def test_one_die(self):
        assert fragmentation_radius(1) == 5

    def test_zero_dice_raises(self):
        with pytest.raises(ValueError):
            fragmentation_radius(0)

    def test_negative_dice_raises(self):
        with pytest.raises(ValueError):
            fragmentation_radius(-2)


class TestFragmentationAttack:
    """Fragment attack at one distance: in_radius, effective_skill, auto_hit. B414."""

    def test_direct_strike(self):
        # distance 0: auto hit, base skill 15
        att = fragmentation_attack(2, 0)
        assert att == FragmentationAttack(
            distance=0,
            danger_radius=10,
            in_radius=True,
            auto_hit=True,
            effective_skill=15,
            frag_dice=2,
        )

    def test_inside_radius_with_all_three_mods(self):
        # 7 <= 10, not direct; 15 - 2 - 2 + 1 = 12
        att = fragmentation_attack(2, 7, range_penalty=-2, posture_mod=-2, size_mod=1)
        assert att == FragmentationAttack(
            distance=7,
            danger_radius=10,
            in_radius=True,
            auto_hit=False,
            effective_skill=12,
            frag_dice=2,
        )

    def test_beyond_radius(self):
        # 15 > radius 10: nothing reaches; skill still reported as 15
        att = fragmentation_attack(2, 15)
        assert att.in_radius is False
        assert att.effective_skill == 15
        assert att.auto_hit is False

    def test_radius_boundary_is_inclusive(self):
        att = fragmentation_attack(2, 10)
        assert att.in_radius is True

    def test_just_beyond_boundary(self):
        att = fragmentation_attack(2, 11)
        assert att.in_radius is False

    def test_auto_hit_only_at_zero(self):
        assert fragmentation_attack(3, 0).auto_hit is True
        assert fragmentation_attack(3, 1).auto_hit is False

    def test_effective_skill_can_exceed_15(self):
        att = fragmentation_attack(2, 1, size_mod=4)
        assert att.effective_skill == 19

    def test_effective_skill_can_drop_low(self):
        # raw 15+mods here; min-roll clamping lives in checks.py
        att = fragmentation_attack(2, 5, range_penalty=-14)
        assert att.effective_skill == 1

    def test_frag_dice_carried(self):
        att = fragmentation_attack(5, 3)
        assert att.frag_dice == 5
        assert att.danger_radius == 25

    def test_zero_frag_dice_raises(self):
        with pytest.raises(ValueError):
            fragmentation_attack(0, 3)

    def test_negative_distance_raises(self):
        with pytest.raises(ValueError):
            fragmentation_attack(2, -1)


class TestFragmentsHitting:
    """hits = 1 + max(0, margin) // 3. B414."""

    def test_margin_zero(self):
        assert fragments_hitting(0) == 1

    def test_margin_three(self):
        assert fragments_hitting(3) == 2

    def test_margin_seven(self):
        # 1 + 7//3 = 3
        assert fragments_hitting(7) == 3

    def test_miss_returns_zero(self):
        assert fragments_hitting(-1) == 0

    def test_large_margin_uncapped(self):
        # 1 + 30//3 = 11, no cap
        assert fragments_hitting(30) == 11

    def test_margin_one_and_two_still_one_fragment(self):
        assert fragments_hitting(1) == 1
        assert fragments_hitting(2) == 1

    def test_margin_six(self):
        assert fragments_hitting(6) == 3

    def test_very_negative_margin(self):
        assert fragments_hitting(-100) == 0


class TestExplosionReport:
    """Aggregator: collateral + optional fragmentation bundled into one result."""

    def test_with_fragmentation(self):
        # floor(24/6)=4, floor(24/15)=1; radius 5*3=15; 0,2,5 all <= 15
        result = explosion_report(24, [0, 2, 5], frag_dice=3)
        assert isinstance(result, ExplosionResult)
        assert result.basic_damage == 24
        assert result.environment == "normal"
        assert result.frag_dice == 3
        assert result.danger_radius == 15
        assert _dmg_map(result.collateral) == {0: 24, 2: 4, 5: 1}
        assert len(result.fragmentation) == 3
        assert all(f.in_radius for f in result.fragmentation)

    def test_fragmentation_distances_match(self):
        result = explosion_report(24, [0, 2, 5], frag_dice=3)
        assert [f.distance for f in result.fragmentation] == [0, 2, 5]

    def test_without_fragmentation(self):
        result = explosion_report(21, [0, 1, 2])
        assert result.frag_dice is None
        assert result.danger_radius is None
        assert result.fragmentation == ()
        assert _dmg_map(result.collateral) == {0: 21, 1: 7, 2: 3}

    def test_report_carries_environment(self):
        result = explosion_report(21, [2], environment="underwater")
        assert result.environment == "underwater"
        assert _dmg_map(result.collateral) == {2: 10}

    def test_report_auto_hit_at_zero(self):
        result = explosion_report(24, [0, 2, 5], frag_dice=3)
        frag_by_dist = {f.distance: f for f in result.fragmentation}
        assert frag_by_dist[0].auto_hit is True
        assert frag_by_dist[2].auto_hit is False

    def test_report_fragmentation_uses_zeroed_mods(self):
        # report path zeros the mods -> skill stays 15
        result = explosion_report(24, [2], frag_dice=3)
        assert result.fragmentation[0].effective_skill == 15

    def test_report_frag_beyond_radius(self):
        # radius 5*1 = 5; distance 8 is outside
        result = explosion_report(21, [8], frag_dice=1)
        assert result.danger_radius == 5
        assert result.fragmentation[0].in_radius is False
        # collateral independent of fragmentation reach
        assert result.collateral[0].damage == 0

    def test_report_negative_distance_raises(self):
        with pytest.raises(ValueError):
            explosion_report(21, [-1])

    def test_report_explicit_zero_frag_dice_raises(self):
        # absent frag is None, not 0
        with pytest.raises(ValueError):
            explosion_report(21, [0], frag_dice=0)


class TestDataclassesFrozen:
    def test_collateral_frozen(self):
        c = CollateralAtRange(distance=1, damage=7)
        with pytest.raises((AttributeError, TypeError)):
            c.damage = 99  # type: ignore[misc]

    def test_fragmentation_attack_frozen(self):
        att = fragmentation_attack(2, 0)
        with pytest.raises((AttributeError, TypeError)):
            att.effective_skill = 99  # type: ignore[misc]

    def test_explosion_result_frozen(self):
        result = explosion_report(21, [0])
        with pytest.raises((AttributeError, TypeError)):
            result.basic_damage = 99  # type: ignore[misc]
