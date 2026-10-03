from gurps_bot.mechanics.combat_constants import (
    STATUS_ICONS,
    Maneuver,
    StatusEffect,
    hp_bar,
    hp_status_label,
)


class TestHpBar:
    def test_full_hp(self):
        bar = hp_bar(10, 10, width=10)
        assert bar == "[##########] 10/10"

    def test_half_hp(self):
        bar = hp_bar(5, 10, width=10)
        assert bar == "[#####-----] 5/10"

    def test_zero_hp(self):
        bar = hp_bar(0, 10, width=10)
        assert bar == "[----------] 0/10"

    def test_negative_hp(self):
        bar = hp_bar(-5, 10, width=10)
        assert bar == "[----------] -5/10"

    def test_over_max(self):
        bar = hp_bar(15, 10, width=10)
        assert bar == "[##########] 15/10"

    def test_zero_max(self):
        bar = hp_bar(0, 0, width=10)
        assert "[----------]" in bar


class TestHpStatusLabel:
    def test_healthy(self):
        assert hp_status_label(10, 10) == ""

    def test_reeling(self):
        assert hp_status_label(3, 10) == "Reeling"

    def test_collapsing(self):
        assert hp_status_label(0, 10) == "Collapsing"

    def test_dying(self):
        assert hp_status_label(-10, 10) == "Dying"

    def test_dead(self):
        assert hp_status_label(-50, 10) == "Dead"

    def test_zero_max(self):
        assert hp_status_label(0, 0) == ""


class TestEnums:
    def test_maneuver_values(self):
        assert len(Maneuver) == 9
        assert Maneuver.ATTACK == "Attack"
        assert Maneuver.DO_NOTHING == "Do Nothing"

    def test_status_effect_values(self):
        assert len(StatusEffect) == 6
        assert StatusEffect.STUNNED == "Stunned"
        assert StatusEffect.DEAD == "Dead"

    def test_status_icons_cover_all_effects(self):
        # drift guard for new StatusEffect members
        assert set(STATUS_ICONS.keys()) == set(StatusEffect)
