# numbers only, no SJG text reproduced; GURPS is a Steve Jackson Games trademark
"""B345 Equipment Modifiers — the quality of the tools you are working with.

A GENERAL success-roll rule, not a crafting rule, which is why it lives outside
``mechanics/crafting*``. B345 lists the skill families it governs — tools of the
trade, a backpack's contents, instruments or a lab, a shop or toolkit, a studio
— and B484's repair rules cite it rather than restating it. Alchemy, Surgery,
Engineer and the rest cite it too, so a domain reaching for this is following
the book's own cross-reference and not sharing another domain's rule data.

⚠️ **The technological split is the part that gets lost.** "No equipment" and
"improvised equipment" each carry TWO numbers, and which applies depends on
whether the skill is technological. Armoury, Electronics Repair, Machinist and
Mechanic are; Survival and Fishing are not. Collapsing the pair loses 5 points
of modifier on exactly the skills a crafting bot is used for.
"""

from __future__ import annotations

from enum import Enum


class EquipmentQuality(Enum):
    """B345's ladder, worst to best."""

    NONE = "No equipment"
    IMPROVISED = "Improvised"
    BASIC = "Basic"
    GOOD = "Good quality"
    FINE = "Fine quality"
    BEST = "Best at your TL"


#: B345: "No equipment: -10 for technological skills, -5 for other skills."
#: "Improvised equipment: -5 for technological skills, -2 for other skills."
_TECHNOLOGICAL = {
    EquipmentQuality.NONE: -10,
    EquipmentQuality.IMPROVISED: -5,
}
_NON_TECHNOLOGICAL = {
    EquipmentQuality.NONE: -5,
    EquipmentQuality.IMPROVISED: -2,
}

#: The rungs that do not care what kind of skill it is.
_FLAT = {
    EquipmentQuality.BASIC: 0,
    EquipmentQuality.GOOD: 1,
    EquipmentQuality.FINE: 2,
}

#: B345: "Best equipment possible at your TL: +TL/2, round down (minimum +2)."
BEST_MINIMUM = 2

#: B345 prices the middle rungs. ⚠️ The 10th-printing markdown renders these as
#: "about 5— basic price" and "about 20— basic price" — the same em-dash-for-x
#: mangling this extraction commits on "-5xHP", "1dx10%" and "1dx10 minutes".
#: Read as multipliers.
GOOD_PRICE_MULTIPLIER = 5
FINE_PRICE_MULTIPLIER = 20


def modifier(
    quality: EquipmentQuality,
    *,
    technological: bool = True,
    tech_level: int | None = None,
) -> int:
    """The skill modifier for working with equipment of this quality.

    ``technological`` defaults to True because the callers that exist are
    repair and crafting skills, all of which are — but it is an argument rather
    than an assumption, since the same ladder serves Survival and Fishing.

    ``tech_level`` is required only for :attr:`EquipmentQuality.BEST`, whose
    value is derived from it. Demanding it there rather than defaulting to
    something plausible keeps the caller from getting a confidently wrong +2.
    """
    if quality is EquipmentQuality.BEST:
        if tech_level is None:
            raise ValueError(
                "BEST equipment is +TL/2, so it needs a tech level; there is no "
                "sensible default"
            )
        if tech_level < 0:
            raise ValueError(f"tech_level cannot be negative, got {tech_level}")
        return max(BEST_MINIMUM, tech_level // 2)

    if quality in _FLAT:
        return _FLAT[quality]

    ladder = _TECHNOLOGICAL if technological else _NON_TECHNOLOGICAL
    return ladder[quality]


def is_worse_than_basic(quality: EquipmentQuality) -> bool:
    """True for the two rungs whose penalty depends on the skill's kind."""
    return quality in (EquipmentQuality.NONE, EquipmentQuality.IMPROVISED)


def price_multiplier(quality: EquipmentQuality) -> int | None:
    """What the kit costs relative to basic, where B345 says.

    Returns None for the rungs it does not price — BEST is "not usually for
    sale", and the two below basic have no price because they are what you have
    when you have nothing.
    """
    return {
        EquipmentQuality.GOOD: GOOD_PRICE_MULTIPLIER,
        EquipmentQuality.FINE: FINE_PRICE_MULTIPLIER,
    }.get(quality)
