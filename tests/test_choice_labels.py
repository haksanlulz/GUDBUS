"""The /combat hp location labels must show the numbers the engine applies.

The labels are hand-written Choice names while the modifiers live in
mechanics/injury; nothing coupled them, and the labels kept the pre-correction
B420 values (Groin/Vitals -10) for weeks after the engine moved to -5 — the
picker taught penalties the code never applied. Parse the number out of each
label and compare it to the single owner.
"""

import re

from gurps_bot.cogs.combat import CombatTrackerGroup
from gurps_bot.mechanics.injury import knockdown_modifier


def _hp_location_choices():
    for param in CombatTrackerGroup.hp_cmd.parameters:
        if param.name == "location":
            assert param.choices, "/combat hp location lost its choices"
            return param.choices
    raise AssertionError("/combat hp has no location parameter")


def test_hp_location_labels_match_engine_modifiers():
    choices = _hp_location_choices()
    assert len(choices) >= 5
    for choice in choices:
        m = re.search(r"\((-\d+)\)", choice.name)
        assert m, f"label {choice.name!r} shows no (-N) modifier"
        assert int(m.group(1)) == knockdown_modifier(choice.value), (
            f"label {choice.name!r} advertises {m.group(1)} but the engine "
            f"applies {knockdown_modifier(choice.value)}"
        )


def test_hp_location_labels_carry_no_stale_qualifiers():
    # the old "Vitals (-10, crushing)" carried a qualifier B420 doesn't have
    for choice in _hp_location_choices():
        assert "crushing" not in choice.name.lower(), (
            f"label {choice.name!r} carries a qualifier B420's knockdown "
            "rule does not"
        )
