"""High/Low Pain Threshold on the knockdown roll (B420).

Printed modifiers, verbatim: "-5 for a major wound to the face or vitals (or to
the groin, on a humanoid male); -10 for a major wound to the skull or eye; +3
for High Pain Threshold, or -4 for Low Pain Threshold."

Operator-ruled into scope 2026-07-27. It was previously unimplementable because
no mechanics call site could read traits.
"""

from __future__ import annotations

import pytest

from gurps_bot.mechanics.injury import knockdown_modifier

HPT = ["High Pain Threshold"]
LPT = ["Low Pain Threshold"]


class TestTraitAlone:
    def test_high_pain_threshold(self):
        assert knockdown_modifier(None, HPT) == 3

    def test_low_pain_threshold(self):
        assert knockdown_modifier(None, LPT) == -4

    def test_no_relevant_trait(self):
        assert knockdown_modifier(None, ["Combat Reflexes"]) == 0

    def test_omitted_traits_behaves_as_before(self):
        """Existing callers pass location only; they must not change."""
        assert knockdown_modifier(None) == 0
        assert knockdown_modifier("skull") == -10


class TestLocationAndTraitSum:
    """B420 lists both in one sentence, so they add."""

    @pytest.mark.parametrize(
        "location,base", [("face", -5), ("vitals", -5), ("groin", -5),
                          ("skull", -10), ("eye", -10)]
    )
    def test_location_plus_high(self, location, base):
        assert knockdown_modifier(location, HPT) == base + 3

    @pytest.mark.parametrize(
        "location,base", [("face", -5), ("skull", -10), ("eye", -10)]
    )
    def test_location_plus_low(self, location, base):
        assert knockdown_modifier(location, LPT) == base - 4

    def test_worst_case(self):
        """Skull wound on a Low Pain Threshold character: -10 and -4."""
        assert knockdown_modifier("eye", LPT) == -14

    def test_high_threshold_does_not_erase_a_skull_hit(self):
        assert knockdown_modifier("skull", HPT) == -7

    def test_unmodified_location_still_zero_with_traits(self):
        assert knockdown_modifier("torso", HPT) == 3
