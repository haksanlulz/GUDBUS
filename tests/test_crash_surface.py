"""Crash surface hardness (B430 Immovable Objects).

Printed, verbatim:

  "Hard Objects: If the immovable object is hard, use twice the HP of the moving
   object to calculate damage. Clay, concrete, ordinary soil, and sand are all
   'hard,' as is a building, mountain, or similar obstacle."

  "Soft Objects: If the immovable object is soft - e.g., forest litter, hay,
   swamp, or water - damage is normal. However, elastic objects (mattresses,
   nets, airbags, etc.) give extra DR against collision damage, ranging from
   DR 2 for a feather bed to DR 10 for a safety net, trampoline, or airbag."

The module hardcoded the hard case, so ditching a vehicle into water took double
damage — the book says normal.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics.vehicles import CrashSurface, crash


class TestHardIsStillTheDefault:
    def test_default_surface_is_hard(self):
        """Crashing into road or ground is the common case; don't change it."""
        assert crash(20, 60).dice_float == crash(20, 60, surface=CrashSurface.HARD).dice_float

    def test_hard_doubles_hp(self):
        hard = crash(20, 60, surface=CrashSurface.HARD)
        soft = crash(20, 60, surface=CrashSurface.SOFT)
        assert hard.dice_float == pytest.approx(soft.dice_float * 2)


class TestSoftIsNormalDamage:
    def test_soft_uses_hp_unmultiplied(self):
        """"damage is normal" - the x2 is the hard-object exception, not a base."""
        soft = crash(20, 60, surface=CrashSurface.SOFT)
        # 60 HP at 20 yd/s -> (60*20)/100 = 12d, undoubled
        assert soft.dice_float == pytest.approx(12.0)

    def test_surface_is_recorded_on_the_result(self):
        assert crash(20, 60, surface=CrashSurface.SOFT).surface is CrashSurface.SOFT
        assert crash(20, 60).surface is CrashSurface.HARD


class TestElasticGivesExtraDr:
    def test_elastic_dr_adds_to_supplied_dr(self):
        """"elastic objects ... give extra DR against collision damage,
        ranging from DR 2 for a feather bed to DR 10 for a safety net"."""
        result = crash(20, 60, dr=5, surface=CrashSurface.SOFT, elastic_dr=10)
        assert result.dr == 15

    def test_elastic_is_soft_damage_too(self):
        """An airbag is a soft object, so it must not also double HP."""
        result = crash(20, 60, surface=CrashSurface.SOFT, elastic_dr=10)
        assert result.dice_float == pytest.approx(12.0)

    def test_elastic_dr_defaults_to_zero(self):
        assert crash(20, 60, dr=3).dr == 3

    def test_elastic_dr_rejects_negative(self):
        with pytest.raises(ValueError):
            crash(20, 60, elastic_dr=-1)


class TestSkidUnchanged:
    """B469: "skids or rolls for a distance equal to 1/3 its current velocity"."""

    @pytest.mark.parametrize("velocity,expected", [(30, 10), (20, 6), (7, 2), (2, 0)])
    def test_skid_is_a_third_of_velocity(self, velocity, expected):
        assert crash(velocity, 60).skid_yards == expected

    def test_surface_does_not_change_the_skid(self):
        assert crash(30, 60, surface=CrashSurface.SOFT).skid_yards == 10
