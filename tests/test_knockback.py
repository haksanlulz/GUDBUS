"""Knockback (B378)."""

import pytest
from gurps_bot.mechanics.knockback import (
    KnockbackResult,
    _knockback_eligible,
    calc_knockback,
)


class TestEligibility:
    """_knockback_eligible: cr always; cut only when it failed to penetrate DR."""

    def test_crushing_always_eligible(self):
        assert _knockback_eligible("cr", penetrated_dr=True) is True
        assert _knockback_eligible("cr", penetrated_dr=False) is True

    def test_cutting_eligible_only_when_not_penetrated(self):
        assert _knockback_eligible("cut", penetrated_dr=False) is True
        assert _knockback_eligible("cut", penetrated_dr=True) is False

    def test_impaling_never_eligible(self):
        assert _knockback_eligible("imp", penetrated_dr=False) is False
        assert _knockback_eligible("imp", penetrated_dr=True) is False

    @pytest.mark.parametrize(
        "dtype", ["pi", "pi-", "pi+", "pi++", "burn", "tox", "cor"]
    )
    def test_other_types_never_eligible(self, dtype):
        assert _knockback_eligible(dtype, penetrated_dr=False) is False
        assert _knockback_eligible(dtype, penetrated_dr=True) is False

    def test_case_and_whitespace_normalized(self):
        assert _knockback_eligible("CR ", penetrated_dr=True) is True
        assert _knockback_eligible(" Cut", penetrated_dr=False) is True


class TestSpecTestCases:
    def test_rulebook_example_st10_8_damage(self):
        # ST 10 -> denom 8 -> exactly 1 yard per 8 points; 1 yard => check at 0 penalty.
        r = calc_knockback(basic_damage=8, damage_type="cr", target_st=10)
        assert r.yards == 1
        assert r.fall_check_triggered is True
        assert r.fall_check_modifier == 0
        assert r.eligible is True
        assert r.effective_denom == 8

    def test_two_yards_st10_16_damage(self):
        # Two full multiples of 8 => 2 yards; -1 per yard after the first => -1.
        r = calc_knockback(basic_damage=16, damage_type="cr", target_st=10)
        assert r.yards == 2
        assert r.fall_check_triggered is True
        assert r.fall_check_modifier == -1

    def test_below_threshold_st10_7_damage(self):
        # 7 < denom 8 => no full multiple => no knockback, no fall check.
        r = calc_knockback(basic_damage=7, damage_type="cr", target_st=10)
        assert r.yards == 0
        assert r.fall_check_triggered is False
        assert r.fall_check_modifier == 0

    def test_low_st_collapse_st3(self):
        # ST<=3 collapses denom to 1 => 1 yard/point => 5 yards; -1 per yard after first => -4.
        r = calc_knockback(basic_damage=5, damage_type="cr", target_st=3)
        assert r.yards == 5
        assert r.fall_check_triggered is True
        assert r.fall_check_modifier == -4
        assert r.effective_denom == 1

    def test_cutting_not_penetrating_eligible(self):
        # Cutting that FAILS to penetrate DR is eligible; 10/8 floors to 1 yard.
        r = calc_knockback(
            basic_damage=10, damage_type="cut", target_st=10, penetrated_dr=False
        )
        assert r.yards == 1
        assert r.eligible is True
        assert r.fall_check_triggered is True
        assert r.fall_check_modifier == 0

    def test_cutting_penetrating_not_eligible(self):
        # Cutting that PENETRATES DR causes no knockback.
        r = calc_knockback(
            basic_damage=10, damage_type="cut", target_st=10, penetrated_dr=True
        )
        assert r.yards == 0
        assert r.eligible is False
        assert r.fall_check_triggered is False

    def test_impaling_no_knockback(self):
        # Impaling (and all non-cr/cut types) never cause knockback under core B378.
        r = calc_knockback(basic_damage=12, damage_type="imp", target_st=10)
        assert r.yards == 0
        assert r.eligible is False
        assert r.fall_check_triggered is False

    def test_double_knockback_halves_denom(self):
        # Double Knockback halves the denom (8->4) => doubles distance (1->2).
        r = calc_knockback(
            basic_damage=8, damage_type="cr", target_st=10, double_knockback=True
        )
        assert r.yards == 2
        assert r.effective_denom == 4
        assert r.fall_check_triggered is True
        assert r.fall_check_modifier == -1

    def test_perfect_balance_adds_four(self):
        # 2 yards => base penalty -1, plus Perfect Balance +4 => net +3.
        r = calc_knockback(
            basic_damage=16, damage_type="cr", target_st=10, perfect_balance=True
        )
        assert r.yards == 2
        assert r.fall_check_triggered is True
        assert r.fall_check_modifier == 3

    def test_generic_st12_anchor(self):
        # denom = ST-2 = 10; 20/10 = 2 full multiples => 2 yards; confirms (ST-2) anchor.
        r = calc_knockback(basic_damage=20, damage_type="cr", target_st=12)
        assert r.yards == 2
        assert r.effective_denom == 10
        assert r.fall_check_triggered is True
        assert r.fall_check_modifier == -1


class TestEdgeCases:
    @pytest.mark.parametrize("st", [1, 2, 3])
    def test_st_1_2_3_all_collapse_to_denom_1(self, st):
        # ST 1/2/3 all behave identically: denom 1, yards == basic_damage.
        r = calc_knockback(basic_damage=4, damage_type="cr", target_st=st)
        assert r.effective_denom == 1
        assert r.yards == 4

    def test_st_minus_2_never_zero_or_negative(self):
        # Guard: never divide by zero/negative — denom floored at 1.
        for st in (1, 2, 3):
            r = calc_knockback(basic_damage=1, damage_type="cr", target_st=st)
            assert r.effective_denom >= 1

    def test_basic_damage_zero(self):
        r = calc_knockback(basic_damage=0, damage_type="cr", target_st=10)
        assert r.yards == 0
        assert r.fall_check_triggered is False
        assert r.fall_check_modifier == 0

    def test_basic_damage_below_denominator(self):
        # 3 < denom 8 => yards 0, no fall check.
        r = calc_knockback(basic_damage=3, damage_type="cr", target_st=10)
        assert r.yards == 0
        assert r.fall_check_triggered is False

    def test_exactly_one_yard_triggers_check_at_zero_penalty(self):
        # yards == 1 => check IS triggered, penalty 0.
        r = calc_knockback(basic_damage=8, damage_type="cr", target_st=10)
        assert r.yards == 1
        assert r.fall_check_triggered is True
        assert r.fall_check_modifier == 0

    def test_exactly_one_yard_with_perfect_balance(self):
        # yards == 1, penalty 0, +4 perfect balance => +4 net.
        r = calc_knockback(
            basic_damage=8,
            damage_type="cr",
            target_st=10,
            perfect_balance=True,
        )
        assert r.yards == 1
        assert r.fall_check_triggered is True
        assert r.fall_check_modifier == 4

    def test_double_knockback_odd_denominator(self):
        # denom 7 (ST 9) -> max(1, 7//2) = 3.
        r = calc_knockback(
            basic_damage=9, damage_type="cr", target_st=9, double_knockback=True
        )
        assert r.effective_denom == 3
        assert r.yards == 3

    def test_double_knockback_with_low_st_stays_one(self):
        # denom already 1 (ST<=3) -> halving floors to 1; 1 yd/point unchanged.
        r = calc_knockback(
            basic_damage=5,
            damage_type="cr",
            target_st=3,
            double_knockback=True,
        )
        assert r.effective_denom == 1
        assert r.yards == 5

    def test_wall_unliving_target_uses_hp_as_st(self):
        # Caller passes object HP as target_st; same formula. HP 20 -> denom 18.
        r = calc_knockback(basic_damage=18, damage_type="cr", target_st=20)
        assert r.effective_denom == 18
        assert r.yards == 1

    def test_wall_low_hp_fires_per_point_branch(self):
        # HP<=3 fires the per-point branch, matching the ST<=3 rule.
        r = calc_knockback(basic_damage=6, damage_type="cr", target_st=2)
        assert r.effective_denom == 1
        assert r.yards == 6

    def test_penetrated_dr_ignored_for_crushing(self):
        # penetrated_dr only matters for cut; ignored for cr.
        r_pen = calc_knockback(
            basic_damage=8, damage_type="cr", target_st=10, penetrated_dr=True
        )
        r_no = calc_knockback(
            basic_damage=8, damage_type="cr", target_st=10, penetrated_dr=False
        )
        assert r_pen.yards == r_no.yards == 1
        assert r_pen.eligible is r_no.eligible is True

    def test_damage_type_case_and_whitespace_normalized(self):
        # "CR " -> "cr" so UI display values still resolve.
        r = calc_knockback(basic_damage=8, damage_type="CR ", target_st=10)
        assert r.eligible is True
        assert r.yards == 1

    def test_not_eligible_has_zero_modifier_and_denom_echo(self):
        # Non-eligible: yards 0, no check, modifier 0.
        r = calc_knockback(basic_damage=30, damage_type="tox", target_st=10)
        assert r.yards == 0
        assert r.eligible is False
        assert r.fall_check_triggered is False
        assert r.fall_check_modifier == 0


class TestResultShape:
    """KnockbackResult dataclass contract: frozen, slotted, correct fields."""

    def test_is_frozen(self):
        r = calc_knockback(basic_damage=8, damage_type="cr", target_st=10)
        with pytest.raises((AttributeError, Exception)):
            r.yards = 99  # type: ignore[misc]

    def test_has_slots(self):
        r = calc_knockback(basic_damage=8, damage_type="cr", target_st=10)
        assert not hasattr(r, "__dict__")

    def test_double_knockback_flag_echoed(self):
        r = calc_knockback(
            basic_damage=8, damage_type="cr", target_st=10, double_knockback=True
        )
        assert r.double_knockback is True
        r2 = calc_knockback(basic_damage=8, damage_type="cr", target_st=10)
        assert r2.double_knockback is False

    def test_all_fields_present(self):
        r = calc_knockback(basic_damage=8, damage_type="cr", target_st=10)
        assert isinstance(r, KnockbackResult)
        assert isinstance(r.yards, int)
        assert isinstance(r.fall_check_triggered, bool)
        assert isinstance(r.fall_check_modifier, int)
        assert isinstance(r.eligible, bool)
        assert isinstance(r.effective_denom, int)
        assert isinstance(r.double_knockback, bool)
