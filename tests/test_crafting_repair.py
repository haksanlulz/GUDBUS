"""B484-485 Repairs.

⚠️ **Sealed probe 3 was NOT consulted while writing this.** It is the second of
the two clean held-out checks (ATTACK.md records the provenance gradient), and
reading it during the build would convert it into a differential — which is
exactly what happened to probes 4 and 5. Re-verify after the module is frozen.

⬜ Scope, stated rather than implied: this is the **Basic Set core only**.
GAUNTLET's ledger row names Low/High/Ultra-Tech for repair and none of that is
read yet, so the module is deliberately incomplete rather than quietly partial.
The critical-failure damage-tier escalation ATTACK.md records from probe-3
elicitation is not on B484-485 and is not implemented here.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics import crafting_repair as repair
from gurps_bot.mechanics.crafting_repair import RepairTier


class TestThePriceLadder:
    """B484's answer to "how hard is this?" — and it is the item's price."""

    @pytest.mark.parametrize(
        "price,modifier",
        [
            (0, 1),
            (999, 1),
            (1_000, 1),
            (1_001, 0),
            (10_000, 0),
            (10_001, -1),
            (100_000, -1),
            (100_001, -2),
            (1_000_000, -2),
            (1_000_001, -3),
            (50_000_000, -3),
        ],
    )
    def test_the_bands(self, price, modifier):
        assert repair.price_modifier(price) == modifier

    def test_the_unmodified_band_is_real_and_not_an_off_by_one(self):
        """B484 names a +1 band up to $1,000 and then starts again at $10,001.

        Everything between is at NO modifier. A ladder written as "one step per
        decade" reads plausibly and is wrong precisely here, so the gap is
        asserted rather than left to the parametrize table to imply.
        """
        assert repair.price_modifier(5_000) == 0

    def test_a_negative_price_is_refused(self):
        with pytest.raises(ValueError):
            repair.price_modifier(-1)


class TestTheTiers:
    @pytest.mark.parametrize(
        "hp,expected",
        [
            (10, RepairTier.MINOR),
            (1, RepairTier.MINOR),
            (0, RepairTier.MAJOR),
            (-9, RepairTier.MAJOR),
            (-50, RepairTier.BEYOND_REPAIR),
            (-51, RepairTier.BEYOND_REPAIR),
        ],
    )
    def test_hp_decides_the_tier(self, hp, expected):
        """max_hp 10, so the destruction threshold is -5x10 = -50."""
        assert repair.repair_tier(hp, max_hp=10) == expected

    def test_the_boundary_is_zero_not_below_zero(self):
        """"reduced to zero or negative HP requires spare parts" — zero is
        already major."""
        assert repair.repair_tier(0, max_hp=10) is RepairTier.MAJOR
        assert repair.repair_tier(1, max_hp=10) is RepairTier.MINOR

    def test_a_failed_ht_roll_destroys_it_at_any_hp(self):
        """Two independent routes to destruction; HP is only one of them."""
        assert (
            repair.repair_tier(5, max_hp=10, destroyed=True)
            is RepairTier.BEYOND_REPAIR
        )

    def test_max_hp_must_be_positive(self):
        with pytest.raises(ValueError):
            repair.repair_tier(1, max_hp=0)


class TestTheRollReturnsAQuantity:
    """The difference that kills the shared abstraction.

    An invention Prototype roll succeeds or fails. A repair roll answers "how
    much" — and a bare success with margin 0 still fixes something.
    """

    @pytest.mark.parametrize("margin,hp", [(0, 1), (1, 1), (2, 2), (7, 7)])
    def test_hp_restored_is_the_margin_with_a_floor_of_one(self, margin, hp):
        assert repair.hp_restored(margin) == hp

    def test_a_bare_success_still_restores_one(self):
        """The floor is part of B484's rule, not a guard against a silly value."""
        assert repair.hp_restored(0) == 1

    def test_a_failed_roll_has_no_quantity_at_all(self):
        with pytest.raises(ValueError):
            repair.hp_restored(-1)


class TestModifiers:
    def test_a_cheap_minor_repair_is_a_plus_one(self):
        mod = repair.repair_modifier(500, RepairTier.MINOR)
        assert mod.total == 1

    def test_major_repairs_add_a_further_minus_two(self):
        """"use the rules above, except that all rolls are at an extra -2"."""
        minor = repair.repair_modifier(500_000, RepairTier.MINOR).total
        major = repair.repair_modifier(500_000, RepairTier.MAJOR).total
        assert minor == -2
        assert major == -4

    def test_the_cited_modifiers_are_gm_supplied(self):
        """B484 cites B345 and B346 rather than restating them, so the engine
        takes the numbers instead of reimplementing two other tables."""
        mod = repair.repair_modifier(
            500, RepairTier.MINOR, equipment_modifier=-2, time_spent_modifier=1
        )
        assert mod.total == 1 - 2 + 1
        labels = [label for label, _ in mod.terms]
        assert any("B345" in label for label in labels)
        assert any("B346" in label for label in labels)

    def test_a_destroyed_item_has_no_roll_to_modify(self):
        with pytest.raises(ValueError):
            repair.repair_modifier(500, RepairTier.BEYOND_REPAIR)

    def test_the_breakdown_names_its_terms(self):
        mod = repair.repair_modifier(2_000_000, RepairTier.MAJOR)
        assert any("price" in label for label, _ in mod.terms)
        assert sum(v for _, v in mod.terms) == mod.total


class TestMoneyAndTime:
    def test_a_repair_attempt_is_half_an_hour_whatever_the_item(self):
        """No complexity ladder. Invention's cheapest attempt is 1d-2 DAYS."""
        spec = repair.minor_repair_time()
        assert spec.unit == "minutes"
        assert spec.dice.min == spec.dice.max == 30

    @pytest.mark.parametrize(
        "rolled,cost", [(1, 100), (3, 300), (6, 600)]
    )
    def test_major_repair_parts_are_a_tenth_per_pip(self, rolled, cost):
        """1d x 10% of $1,000."""
        assert repair.major_repair_parts_cost(1_000, rolled) == cost

    def test_the_parts_cost_spans_a_tenth_to_six_tenths(self):
        assert repair.major_repair_parts_cost(1_000_000, 1) == 100_000
        assert repair.major_repair_parts_cost(1_000_000, 6) == 600_000

    def test_an_impossible_die_roll_is_refused(self):
        with pytest.raises(ValueError):
            repair.major_repair_parts_cost(1_000, 7)

    def test_replacement_is_full_price(self):
        """"Replace it at 100% of its original cost." No salvage credit."""
        assert repair.replacement_cost(12_345) == 12_345

    def test_a_hired_technician_is_twenty_an_hour_at_nine_plus_a_die(self):
        tech = repair.hired_technician()
        assert tech.rate_per_hour == 20
        assert str(tech.skill_dice) == "1d"
        assert tech.skill_for(1) == 10
        assert tech.skill_for(6) == 15

    def test_restoring_ht_is_one_major_repair_per_point(self):
        """"Treat each point of HT restored as a separate major repair" — three
        rolls and three sets of parts, not one repair of size three."""
        assert repair.maintenance_ht_repairs(3) == 3
        assert repair.maintenance_ht_repairs(0) == 0


class TestScopeIsStatedNotImplied:
    """A partial implementation that does not say so reads as a complete one."""

    def test_the_module_names_the_tech_books_as_unread(self):
        assert "Low/High/Ultra-Tech" in (repair.__doc__ or "")

    def test_the_critical_failure_escalation_is_not_implemented(self):
        """ATTACK.md records it from probe-3 elicitation and B484-485 does not
        print it, so implementing it here would be writing a rule from memory —
        the exact failure the sealed probe exists to catch."""
        assert not hasattr(repair, "escalate_damage_tier")
        assert not hasattr(repair, "critical_failure_tier")


class TestSealedProbeThreeExercisesAnUnbuiltLayer:
    """Probe 3 re-verify, 2026-08-10. Seal hash checked; only probe 3 read.

    **The result is a negative, and it is the useful kind.** Probe 3 is a
    tech-line case — Armoury (Beam Weapons)/TL9 on a TL10 weapon — and it does
    not exercise this module at all. B484-485 and the tech-book repair rules are
    not the same rule set with more detail; they are different models:

        axis        probe 3: TL mismatch, familiarity, workspace ladder
                    B484:    the item's PRICE
        tiers       probe 3: Major -2 / Severe -5, graded penalties
                    B484:    minor / major / beyond repair, a triage
        parts       probe 3: a flat figure
                    B484:    1d x 10% of the item's price
        time        probe 3: 3d hours / workers
                    B484:    thirty minutes, flat, not rolled

    So the honest verdict is **not "the module fails probe 3"** and **not "the
    module passes"** — the probe's subject was never built. Recording it as a
    pass would be the fail-open; recording it as a failure would blame this
    module for a scope it declares it does not cover.

    ⚑ What re-verifying DID buy: the probe's workspace ladder turned out to be
    four-fifths of **B345 Equipment Modifiers**, which B484 cites by page and
    which this module had been passing through as an opaque GM integer. That
    gap was real, found in the book rather than taken from the probe, and is
    now `mechanics/equipment_quality.py`.

    ⬜ Probe 3 stays UNSPENT as a check on the tech-book layer. Its rules must
    come from Low/High/Ultra-Tech, not from the probe — implementing from a
    held-out check destroys it, which is how probes 4 and 5 became
    differentials.
    """

    def test_this_module_has_no_workspace_ladder_of_its_own(self):
        """It defers to B345, which is a general success-roll rule."""
        assert not hasattr(repair, "WORKSPACE_LADDER")
        assert not hasattr(repair, "workspace_modifier")

    def test_it_has_no_tl_or_familiarity_modifier(self):
        """B484 does not print them; B168/B169 own them and probe 3 uses them.
        Adding them here from the probe would be writing rules from a check."""
        assert not hasattr(repair, "tl_mismatch_modifier")
        assert not hasattr(repair, "familiarity_modifier")

    def test_the_tiers_are_triage_not_a_penalty_ladder(self):
        """Probe 3's Major/Severe are numbers you add. B484's tiers select
        which rules apply, and only one of them carries a modifier at all."""
        assert repair.MAJOR_REPAIR_PENALTY == -2
        assert not hasattr(repair, "SEVERE_REPAIR_PENALTY")
        assert {t.name for t in RepairTier} == {"MINOR", "MAJOR", "BEYOND_REPAIR"}

    def test_the_b345_ladder_is_reachable_from_the_book_not_the_probe(self):
        """The one thing the re-verify actually changed, wired to its source."""
        from gurps_bot.mechanics import equipment_quality
        from gurps_bot.mechanics.equipment_quality import EquipmentQuality

        # Armoury is technological: improvised is -5, not -2.
        assert equipment_quality.modifier(EquipmentQuality.IMPROVISED) == -5
        assert equipment_quality.modifier(EquipmentQuality.BASIC) == 0
        assert equipment_quality.modifier(EquipmentQuality.GOOD) == 1
        assert equipment_quality.modifier(EquipmentQuality.FINE) == 2
