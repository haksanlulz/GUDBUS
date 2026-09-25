"""Crafting rules are per-DOMAIN data, never one shared abstraction.

The scan the arc has owed since 2026-08-01. It could not be written honestly
until a second domain existed: a differential whose population is one subject
cannot fail, and would have read green while proving nothing. Repair
is that second domain, so this file finally has something to disagree about.

The invariant's own wording, from the domains' worked scenarios laid side by
side: each
domain has its own facility ladder, its own reading of "multiple units", its own
"assistant", its own skill-selection rule, and its own answer to what the roll
even means. Every test below names one such rule and asserts the two
implemented domains give different answers to it.

⬜ **Two domains still missing** — enchantment and mundane crafting — so this
scan is real but not yet complete. Its population is 3 of 5, and the count is
stated here rather than left for a reader to assume otherwise.

⚑ Adding alchemy broke the two-domain shape, as a population of two
predicts. Two of these tests had been written as "invention does X, repair does
not", which reads as a rule and was really a coincidence of a population of
two — alchemy has a facility ladder like invention's and a batch concept like
neither. They are now three-way comparisons.
"""

from __future__ import annotations

import inspect

from gurps_bot import mechanics
from gurps_bot.mechanics import crafting as invention
from gurps_bot.mechanics import crafting_alchemy as alchemy
from gurps_bot.mechanics import crafting_repair as repair
from gurps_bot.mechanics.crafting import Complexity
from gurps_bot.mechanics.crafting_repair import RepairTier

#: The domains implemented so far, with the module that owns each. A domain
#: added without a row here is a domain nothing compares.
DOMAIN_MODULES = {
    "invention": invention,
    "repair": repair,
    "alchemy": alchemy,
}

#: What the arc will eventually hold. Named so the gap is a number rather than
#: an impression.
PLANNED_DOMAINS = ("invention", "repair", "alchemy", "enchantment", "crafting")


class TestThePopulationIsHonest:
    """FAIL CLOSED, and in the differential's specific shape: it is only worth
    reading if its subjects can disagree."""

    def test_there_are_at_least_two_domains_to_compare(self):
        assert len(DOMAIN_MODULES) >= 2, (
            "one domain cannot disagree with itself — every assertion below "
            "would pass by construction"
        )

    def test_the_scan_reports_its_own_coverage(self):
        missing = [d for d in PLANNED_DOMAINS if d not in DOMAIN_MODULES]
        assert missing, (
            "PLANNED_DOMAINS and DOMAIN_MODULES agree — if every domain really "
            "has landed, delete this test and say so in this file's docstring rather than "
            "letting it keep asserting a gap that closed"
        )
        assert len(DOMAIN_MODULES) < len(PLANNED_DOMAINS)

    def test_each_domain_owns_its_own_module(self):
        """Separate modules are the structural half of the invariant. One module
        with a `domain=` switch is the shape this forbids."""
        assert len({m.__name__ for m in DOMAIN_MODULES.values()}) == len(DOMAIN_MODULES)


class TestTheDomainsDisagree:
    def test_they_modify_the_roll_on_unrelated_axes(self):
        """Invention asks about FACILITIES; repair asks about the item's PRICE.

        Both are "how hard is this", and a shared enum would have to pick one.
        """
        assert invention.FACILITY_PENALTY_RANGE == (-10, 0)
        assert not hasattr(repair, "FACILITY_PENALTY_RANGE")
        assert repair.price_modifier(500) == 1
        assert not hasattr(invention, "price_modifier")

    def test_repair_can_give_a_BONUS_where_invention_only_penalises(self):
        """B484's cheap-item +1 has no counterpart in B473-474's facility rule,
        which runs -1 to -10 and stops at zero."""
        assert repair.price_modifier(500) > 0
        low, high = invention.FACILITY_PENALTY_RANGE
        assert high == 0

    def test_the_roll_means_different_things(self):
        """Invention: succeeded or not. Repair: how much.

        No single domain shows this on its own; it only appears side by side,
        and it is why `hp_restored` returns an int while the invention outcomes
        return structures describing what happened.
        """
        assert repair.hp_restored(4) == 4  # a quantity
        bugs = invention.bugs_from_prototype(margin=4)
        assert not isinstance(bugs, int)  # an outcome

    def test_time_is_not_on_the_same_scale_or_even_rolled(self):
        """Invention time is dice by complexity, days to months. A repair
        attempt is thirty minutes, flat, and not rolled at all."""
        spec = repair.minor_repair_time()
        assert spec.dice.min == spec.dice.max  # no variance: not a roll
        for complexity in Complexity:
            proto = complexity.prototype_time
            assert proto.dice.min != proto.dice.max
            assert proto.unit != spec.unit

    def test_complexity_governs_one_domain_and_is_absent_from_the_other(self):
        """Repair has no complexity concept whatsoever — the item's price does
        that work — so a shared `Complexity` parameter would be dead weight in
        half the family."""
        assert "complexity" in inspect.signature(invention.invention_costs).parameters
        for name, obj in vars(repair).items():
            if inspect.isfunction(obj):
                assert "complexity" not in inspect.signature(obj).parameters, (
                    f"repair.{name} takes a complexity — repair is priced by the "
                    f"item's cost, not by an invention rating"
                )

    def test_multiple_units_means_three_different_things(self):
        """⚑ This test used to assert that NO domain takes a batch parameter.

        That was true, and it was not a rule — it was a coincidence of a
        population of two. Adding alchemy broke it on the first run, which is
        the population-of-two lesson arriving inside the scan written to enforce it.

        The real statement is that the three domains read "multiple units"
        three ways, so no shared parameter can serve them:
        """
        # Alchemy: one shared roll, cost multiplied by the whole batch.
        assert alchemy.batch_materials_cost(50, 4) == 200
        assert alchemy.batch_penalty(4) == -3

        # Invention: no batch concept at all. Copies come AFTER a prototype and
        # are priced per copy, which is production, not batching.
        for name, obj in vars(invention).items():
            if inspect.isfunction(obj):
                params = inspect.signature(obj).parameters
                assert "doses" not in params and "batch" not in params, (
                    f"invention.{name} grew a batch parameter — B473-474 has no "
                    f"such concept"
                )

        # Repair: full roll and full cost per unit, so batching is a no-op
        # rather than a discount, and the module offers no parameter for it.
        for name, obj in vars(repair).items():
            if inspect.isfunction(obj):
                params = inspect.signature(obj).parameters
                assert "doses" not in params and "batch" not in params, (
                    f"repair.{name} grew a batch parameter — repairs do not batch"
                )

    def test_alchemy_has_two_batch_penalties_and_they_differ(self):
        """Even INSIDE one domain the rule is not one number: the brew roll is
        -1 per extra dose, the disaster-avoidance roll is -1 per dose."""
        assert alchemy.batch_penalty(3) == -2
        assert alchemy.disaster_roll_penalty(3) == -3

    def test_an_assistant_means_opposite_things_in_two_domains(self):
        """There are five meanings across five domains. Two are here,
        and they point in opposite directions — which is why there is no shared
        helper and no shared parameter name.
        """
        # Invention: each skilled assistant ADDS to the inventor's roll.
        assert invention.ASSISTANT_BONUS_EACH > 0
        assert invention.ASSISTANT_BONUS_CAP == 4

        # Alchemy: the LOWEST-skill worker makes the final roll, so a weaker
        # helper lowers it.
        assert alchemy.final_roller_skill([18, 10]) == 10
        assert not hasattr(alchemy, "ASSISTANT_BONUS_EACH")

        # Repair's Basic Set core has no assistant rule at all, and inventing
        # one would be a sixth meaning.
        assert not hasattr(repair, "ASSISTANT_BONUS_CAP")
        assert not hasattr(repair, "final_roller_skill")

    def test_three_facility_ladders_three_shapes(self):
        """The invariant's headline example, now with three subjects.

        Invention: a GM-discretion range with no rungs. Alchemy: four named
        rungs, one of them derived from TL. Repair: no facility concept at all —
        it defers to B345, which is a general rule rather than a crafting one.
        """
        assert invention.FACILITY_PENALTY_RANGE == (-10, 0)
        assert alchemy.lab_modifier(alchemy.LabQuality.PROFESSIONAL) == 1
        assert alchemy.lab_modifier(alchemy.LabQuality.CUTTING_EDGE, 8) == 4
        assert not hasattr(repair, "lab_modifier")
        assert not hasattr(repair, "FACILITY_PENALTY_RANGE")

    def test_only_one_domain_suppresses_critical_successes(self):
        """Alchemy: "either the process works or it doesn't". The others use
        the core engine's criticals, so `checks.py` serves none of the three
        unmodified."""
        import pytest

        with pytest.raises(ValueError):
            alchemy.resolve_brew("critical_success")
        assert invention.bugs_from_prototype(0, critical_success=True).is_clean

    def test_only_one_domain_cares_where_you_are_standing(self):
        """Mana is alchemy's alone. A shared "environment" parameter would be
        meaningless in the other two."""
        assert not alchemy.can_brew(alchemy.Mana.NONE)
        for module in (invention, repair):
            assert not hasattr(module, "Mana")

    def test_neither_domain_exposes_a_generic_entry_point(self):
        """The shape the invariant forbids, checked directly: a `craft(domain=…)`
        or `do_crafting(...)` front door would erase every difference above."""
        for module in DOMAIN_MODULES.values():
            for banned in ("craft", "do_crafting", "resolve", "run_domain"):
                assert not hasattr(module, banned), (
                    f"{module.__name__}.{banned} looks like a shared front door "
                    f"across domains that agree on nothing"
                )


#: Invention's rule DATA. Sharing any of it with another domain is the
#: abstraction the invariant forbids; sharing the presentation containers is
#: not, and they are deliberately absent from this list.
_INVENTION_RULE_DATA = (
    "GADGETEER_CONCEPT_PENALTY",
    "GADGETEER_FACILITY_BASE",
    "GADGETEER_FACILITY_TL_INCREMENT",
    "QUICK_SCROUNGING_PENALTY",
    "QUICK_ASSEMBLY_TIME",
    "FACILITY_PENALTY_RANGE",
    "ASSISTANT_BONUS_EACH",
    "ASSISTANT_BONUS_CAP",
    "TL_COST_MULTIPLIER",
    "TL_GAP_PENALTY_EACH",
    "DESCRIPTION_BONUS_RANGE",
    "VARIANT_BONUS_RANGE",
)


def _borrowed_rule_data(source: str) -> list[str]:
    """Invention rule-data names appearing in another domain's source."""
    return [name for name in _INVENTION_RULE_DATA if name in source]


#: Invention's rule DATA. Sharing any of it with another domain is the
#: abstraction the invariant forbids; the presentation containers
#: (``ModifierBreakdown``, ``TimeSpec``) are deliberately absent from this list.
#: ``test_the_name_list_covers_every_rule_constant_invention_exports`` keeps it
#: honest — the first version was hand-written, missed ``ASSISTANT_BONUS_CAP``,
#: and let a planted violation through.
_INVENTION_RULE_DATA = (
    "GADGETEER_CONCEPT_PENALTY",
    "GADGETEER_FACILITY_BASE",
    "GADGETEER_FACILITY_TL_INCREMENT",
    "QUICK_SCROUNGING_PENALTY",
    "QUICK_ASSEMBLY_TIME",
    "QUICK_PURCHASE_DIVISOR",
    "FACILITY_PENALTY_RANGE",
    "ASSISTANT_BONUS_EACH",
    "ASSISTANT_BONUS_CAP",
    "ASSISTANT_MIN_SKILL",
    "TL_COST_MULTIPLIER",
    "TL_GAP_PENALTY_EACH",
    "DESCRIPTION_BONUS_RANGE",
    "VARIANT_BONUS_RANGE",
    "TESTING_PENALTY",
    "BUG_SURFACE_MARGIN",
    "DISASTER_DAMAGE",
    "STAGES",
    # Private, and included precisely because it is: a domain reaching for
    # another domain's underscore-prefixed rule data is a worse violation than
    # one reaching for its public data, not an exempt one. Found by the derived
    # check below rather than by remembering it.
    "_COMPLEXITY_ORDER",
)


def _borrowed_rule_data(source: str) -> list[str]:
    """Invention rule-data names appearing in another domain's source."""
    return [name for name in _INVENTION_RULE_DATA if name in source]


class TestTheSharedPiecesAreDeliberate:
    """Not everything may differ, or the invariant becomes an excuse.

    Two things ARE shared, and both are presentation rather than rule. Naming
    them here keeps the line visible: a third arrival should have to justify
    itself against this list.
    """

    def test_the_modifier_container_is_shared(self):
        mod = repair.repair_modifier(500, RepairTier.MINOR)
        assert isinstance(mod, invention.ModifierBreakdown)

    def test_the_time_container_is_shared(self):
        assert isinstance(repair.minor_repair_time(), invention.TimeSpec)

    def test_no_rule_DATA_is_shared(self):
        """The container may be common; the numbers may not. Repair must not
        read any of invention's ladders."""
        borrowed = _borrowed_rule_data(inspect.getsource(repair))
        assert not borrowed, (
            f"crafting_repair reads {borrowed} — that is invention's rule data, "
            f"and sharing it is the abstraction this scan forbids"
        )

    def test_the_data_scan_sees_a_planted_violation(self):
        """Verify the instrument before trusting its clean reading.

        Runs the real checker over source that DOES borrow. An earlier draft of
        this test asserted that a string I had just written contained a
        substring of itself — tautological, and it passed while the checker it
        was supposed to vouch for had a gap in its name list.
        """
        planted = (
            "from gurps_bot.mechanics.crafting import ASSISTANT_BONUS_CAP\n"
            "def bonus():\n"
            "    return ASSISTANT_BONUS_CAP\n"
        )
        assert _borrowed_rule_data(planted) == ["ASSISTANT_BONUS_CAP"]

    def test_the_data_scan_ignores_the_sanctioned_imports(self):
        """The presentation containers must NOT register — no false-positive tax."""
        clean = "from gurps_bot.mechanics.crafting import ModifierBreakdown, TimeSpec\n"
        assert _borrowed_rule_data(clean) == []

    def test_the_name_list_covers_every_rule_constant_invention_exports(self):
        """The gap that let the first mutant through.

        The hand-written list held ASSISTANT_BONUS_EACH and not
        ASSISTANT_BONUS_CAP, so a planted import of the latter sailed past. A
        list maintained by hand against a module that keeps growing is the
        fail-open; derive it instead and let this test catch the next addition.
        """
        exported = {
            name
            for name, value in vars(invention).items()
            if name.isupper() and isinstance(value, (int, dict, tuple))
        }
        missing = exported - set(_INVENTION_RULE_DATA)
        assert not missing, (
            f"invention exports rule constants the domain scan does not know "
            f"about: {sorted(missing)}. Add them to _INVENTION_RULE_DATA, or a "
            f"future domain can borrow them unnoticed."
        )


class TestBothDomainsAreReachableFromTheMechanicsPackage:
    def test_they_are_siblings(self):
        assert invention.__name__ == "gurps_bot.mechanics.crafting"
        assert repair.__name__ == "gurps_bot.mechanics.crafting_repair"
        assert mechanics.__name__ == "gurps_bot.mechanics"
