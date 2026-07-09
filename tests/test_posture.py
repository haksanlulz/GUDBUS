"""B551 Posture table — coverage, lookup, and sign invariants."""

from __future__ import annotations

import pytest

from gurps_bot.mechanics import posture as P
from gurps_bot.mechanics.posture import POSTURES, Posture, posture, posture_names


class TestCoverage:
    def test_at_least_the_six_canonical_postures(self):
        # B551 lists Standing, Crouching, Kneeling, Sitting, Crawling, Lying Down.
        assert len(POSTURES) >= 6

    def test_canonical_names_present(self):
        names_lower = {p.name.lower() for p in POSTURES}
        for expected in ("standing", "crouching", "kneeling", "sitting", "crawling"):
            assert expected in names_lower, expected
        assert any("lying" in n for n in names_lower), names_lower

    def test_names_are_unique(self):
        names = [p.name for p in POSTURES]
        assert len(names) == len(set(names))

    def test_posture_names_matches_tuple_order(self):
        assert posture_names() == [p.name for p in POSTURES]

    def test_every_posture_is_frozen_dataclass(self):
        for p in POSTURES:
            assert isinstance(p, Posture)
            with pytest.raises((AttributeError, Exception)):
                p.move_fraction = 0.0  # frozen → cannot reassign


class TestLookup:
    def test_exact_name(self):
        assert posture("Standing").name == "Standing"

    def test_case_insensitive(self):
        assert posture("standing") is posture("STANDING")
        assert posture("CrOuChInG").name == "Crouching"

    def test_whitespace_tolerated(self):
        assert posture("  kneeling  ").name == "Kneeling"

    def test_lookup_total_over_tuple(self):
        for p in POSTURES:
            assert posture(p.name) is p
            assert posture(p.name.lower()) is p

    def test_unknown_raises_keyerror(self):
        with pytest.raises(KeyError):
            posture("levitating")


class TestSignInvariants:
    def test_standing_is_the_all_zero_full_move_baseline(self):
        s = posture("Standing")
        assert s.attack_penalty == 0
        assert s.defense_modifier == 0
        assert s.ranged_to_hit_you == 0
        assert s.melee_to_hit_you == 0
        assert s.move_fraction == 1.0

    def test_your_attack_penalty_never_a_bonus(self):
        for p in POSTURES:
            assert p.attack_penalty <= 0, p.name

    def test_your_defense_modifier_never_a_bonus(self):
        for p in POSTURES:
            assert p.defense_modifier <= 0, p.name

    def test_attacker_modifiers_never_help_the_defender(self):
        # sign convention: < 0 on the attacker's roll helps YOU. lower postures
        # penalize a ranged attacker (smaller profile) so ranged <= 0; melee is
        # never penalized — a downed defender is easier to hit — so melee >= 0
        for p in POSTURES:
            assert p.ranged_to_hit_you <= 0, p.name
            assert p.melee_to_hit_you >= 0, p.name

    def test_move_fraction_in_unit_range(self):
        for p in POSTURES:
            assert 0.0 <= p.move_fraction <= 1.0, p.name

    def test_only_standing_keeps_full_move(self):
        for p in POSTURES:
            if p.name != "Standing":
                assert p.move_fraction < 1.0, p.name

    def test_non_standing_postures_cost_something(self):
        for p in POSTURES:
            if p.name == "Standing":
                continue
            drawback = (
                p.attack_penalty < 0
                or p.defense_modifier < 0
                or p.move_fraction < 1.0
                or p.melee_to_hit_you > 0
            )
            assert drawback, p.name

    def test_effect_notes_present_and_short(self):
        for p in POSTURES:
            assert p.effect.strip(), p.name
            # Concise original summaries — a hard cap keeps them note-length.
            assert len(p.effect) <= 200, p.name


# B551 spot-checks
class TestCanonicalValues:
    def test_crouching_costs_attack_not_defense(self):
        c = posture("Crouching")
        assert c.attack_penalty == -2
        assert c.defense_modifier == 0  # crouch keeps full defense
        assert c.ranged_to_hit_you == -2  # smaller profile vs ranged
        assert c.melee_to_hit_you == 0

    def test_kneeling_values(self):
        k = posture("Kneeling")
        assert k.attack_penalty == -2
        assert k.defense_modifier == -2
        assert k.ranged_to_hit_you == -2

    def test_lying_down_is_worst_for_defense_and_easiest_to_hit_in_melee(self):
        ld = posture(P.LYING_DOWN_NAME)
        assert ld.attack_penalty == -4
        assert ld.defense_modifier == -3
        assert ld.ranged_to_hit_you == -2
        assert ld.melee_to_hit_you == +4  # prone → easy point-blank target


# regression: an over-strict "every modifier <= 0" normalization once zeroed
# the whole melee_to_hit_you column — prone is +4 to a melee attacker
# (B551/B399), and an all-zero column passes every sign test. pin values.
class TestPostureMeleeBonusRegression:
    def test_melee_column_is_not_degenerate_all_zero(self):
        # the column must carry information; all-zero is the erased-bonus bug
        melee = [p.melee_to_hit_you for p in POSTURES]
        assert any(v > 0 for v in melee), (
            "melee_to_hit_you is all-zero — the prone melee BONUS was erased "
            "(the jam/idio liability); a downed defender must be easier to hit"
        )

    def test_prone_confers_the_canonical_plus_four_melee_bonus(self):
        # B551: prone gives a melee attacker +4. pinned by value so a
        # sign-normalization or transcription flip can't zero it
        prone = posture(P.LYING_DOWN_NAME)
        assert prone.melee_to_hit_you == +4

    def test_only_prone_eases_the_melee_hit(self):
        # the bonus must not leak onto any non-prone posture
        for p in POSTURES:
            if p.name == P.LYING_DOWN_NAME:
                assert p.melee_to_hit_you == +4, p.name
            else:
                assert p.melee_to_hit_you == 0, p.name
