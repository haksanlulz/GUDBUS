"""parse GCS v5 .gcs JSON into database-ready objects"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gurps_bot.utils.sanitize import sanitize_name as _sanitize_name

#: real sheets nest a few levels; deeper is malformed/adversarial — fail with a
#: clean GCSParseError instead of a RecursionError
_MAX_NEST_DEPTH = 64

#: the 5MB import limit alone permits ~250k minimal items (one INSERT each, one
#: transaction); a real character has a few hundred
_MAX_ITEMS_PER_CATEGORY = 4000

#: the name becomes an embed title (256 max); unbounded -> HTTP 400 on send
_MAX_NAME_LEN = 100

#: local_notes on library traits is frequently verbatim SJG prose — dropped at
#: the parser boundary, never persisted or rendered; named so the empty string
#: reads as deliberate
_COPYRIGHT_DROPPED_NOTES = ""


class GCSParseError(Exception):
    """Raised when a .gcs file cannot be parsed."""


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


#: OverflowError is the easy miss: JSON 1e400 parses to inf and int(inf) raises
#: it (NaN raises ValueError)
_COERCE_ERRORS = (TypeError, ValueError, OverflowError)


def _as_int(value: object, default: int = 0) -> int:
    """junk points/quantity/level ('3.7', 'abc', 1e400) would store uncoerced and crash at render time — coerce at parse"""
    try:
        return int(value)  # type: ignore[arg-type]
    except _COERCE_ERRORS:
        return default


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except _COERCE_ERRORS:
        return default


def _guard_depth(depth: int) -> None:
    if depth > _MAX_NEST_DEPTH:
        raise GCSParseError("GCS file nests containers too deeply")


def _guard_item_cap(out: list, kind: str) -> None:
    if len(out) >= _MAX_ITEMS_PER_CATEGORY:
        raise GCSParseError(
            f"character has too many {kind} (max {_MAX_ITEMS_PER_CATEGORY})"
        )


def _has_calc_or_difficulty(item: dict, calc: dict) -> bool:
    """container/placeholder rows have neither calc nor difficulty — skip, don't emit junk"""
    return bool(calc) or "difficulty" in item


@dataclass
class ParsedAttribute:
    attr_id: str
    value: float
    current: float | None  # only for pools (hp, fp)
    points: int


@dataclass
class ParsedSkill:
    name: str
    specialization: str | None
    difficulty: str
    level: int
    relative_level: str
    points: int
    defaults: list


@dataclass
class ParsedSpell:
    name: str
    college: str
    difficulty: str
    level: int
    relative_level: str
    points: int
    casting_cost: str
    maintenance_cost: str
    casting_time: str
    duration: str
    spell_class: str


@dataclass
class ParsedTrait:
    name: str
    group_name: str | None
    points: int
    level: int | None
    tags: list
    has_weapon: bool
    weapons: list
    notes: str


@dataclass
class ParsedCharacter:
    name: str
    total_points: int
    profile: dict
    calc: dict
    equipment: list
    settings: dict
    attributes: list[ParsedAttribute] = field(default_factory=list)
    skills: list[ParsedSkill] = field(default_factory=list)
    spells: list[ParsedSpell] = field(default_factory=list)
    traits: list[ParsedTrait] = field(default_factory=list)


def parse_gcs(data: dict[str, Any]) -> ParsedCharacter:
    """GCS v5 dict -> ParsedCharacter; GCSParseError on anything invalid"""
    if not isinstance(data, dict):
        raise GCSParseError("GCS file must be a JSON object")

    version = data.get("version")
    if version != 5:
        raise GCSParseError(f"Unsupported GCS version: {version} (expected 5)")

    name = _parse_name(_as_dict(data.get("profile")))

    char = ParsedCharacter(
        name=name,
        total_points=_as_int(data.get("total_points", 0)),
        profile=_as_dict(data.get("profile")),
        # pre-computed swing/thrust/basic_lift/move[]/dodge[]
        calc=_as_dict(data.get("calc")),
        equipment=_parse_equipment(data),
        # body_type feeds hit-location/DR lookups
        settings={"body_type": _as_dict(data.get("settings")).get("body_type", {})},
    )

    _parse_attributes(_as_list(data.get("attributes")), char.attributes)
    _parse_skills(_as_list(data.get("skills")), char.skills)
    _parse_spells(_as_list(data.get("spells")), char.spells)
    _parse_traits(_as_list(data.get("traits")), char.traits, group_name=None)

    return char


def _parse_name(profile: dict) -> str:
    raw_name = profile.get("name", "")
    name = _sanitize_name(raw_name if isinstance(raw_name, str) else "")
    if not name:
        raise GCSParseError("Character has no name in profile")
    return name[:_MAX_NAME_LEN]


def _parse_equipment(data: dict) -> list[dict]:
    carried = _flatten_equipment(_as_list(data.get("equipment")))
    other = _flatten_equipment(_as_list(data.get("other_equipment")))
    return carried + other


def _parse_attributes(items: list, out: list[ParsedAttribute]) -> None:
    for attr in items:
        _guard_item_cap(out, "attributes")
        if not isinstance(attr, dict):
            continue
        calc = _as_dict(attr.get("calc"))
        current = calc.get("current")
        out.append(ParsedAttribute(
            attr_id=attr.get("attr_id", ""),
            value=_as_float(calc.get("value", 0)),
            current=_as_float(current) if current is not None else None,
            points=_as_int(calc.get("points", 0)),
        ))


def _flatten_stat_items(
    items: list,
    out: list,
    kind: str,
    build_leaf,
    _depth: int = 0,
) -> None:
    """shared skill/spell walker, build_leaf is the per-type hook; children = container, no calc/difficulty = placeholder"""
    _guard_depth(_depth)
    for item in items:
        _guard_item_cap(out, kind)
        if not isinstance(item, dict):
            continue
        if "children" in item:
            _flatten_stat_items(_as_list(item["children"]), out, kind, build_leaf, _depth + 1)
            continue

        calc = _as_dict(item.get("calc"))
        if not _has_calc_or_difficulty(item, calc):
            continue  # container/placeholder row

        out.append(build_leaf(item, calc))


def _build_skill(item: dict, calc: dict) -> ParsedSkill:
    return ParsedSkill(
        name=item.get("name", "Unknown"),
        specialization=item.get("specialization"),
        difficulty=item.get("difficulty", ""),
        level=_as_int(calc.get("level", 0)),
        relative_level=calc.get("rsl", ""),
        points=_as_int(item.get("points", 0)),
        defaults=item.get("defaults", []),
    )


def _build_spell(item: dict, calc: dict) -> ParsedSpell:
    return ParsedSpell(
        name=item.get("name", "Unknown"),
        college=_join_college(item.get("college", [])),
        difficulty=item.get("difficulty", ""),
        level=_as_int(calc.get("level", 0)),
        relative_level=calc.get("rsl", ""),
        points=_as_int(item.get("points", 0)),
        casting_cost=item.get("casting_cost", ""),
        maintenance_cost=item.get("maintenance_cost", ""),
        casting_time=item.get("casting_time", ""),
        duration=item.get("duration", ""),
        spell_class=item.get("spell_class", ""),
    )


def _parse_skills(items: list, out: list[ParsedSkill], _depth: int = 0) -> None:
    _flatten_stat_items(items, out, "skills", _build_skill, _depth)


def _parse_spells(items: list, out: list[ParsedSpell], _depth: int = 0) -> None:
    _flatten_stat_items(items, out, "spells", _build_spell, _depth)


def _join_college(college: object) -> str:
    if isinstance(college, list):
        return ", ".join(str(c) for c in college)
    return college  # type: ignore[return-value]


def _parse_traits(
    items: list,
    out: list[ParsedTrait],
    group_name: str | None,
    _depth: int = 0,
) -> None:
    """meta_trait containers ARE one trait (Vampirism) — emit, don't descend; other containers just group, so descend and tag children with the group name"""
    _guard_depth(_depth)
    for item in items:
        _guard_item_cap(out, "traits")
        if not isinstance(item, dict):
            continue

        if item.get("children") is not None:
            if item.get("container_type") == "meta_trait":
                out.append(_build_meta_trait(item, group_name))
            else:
                _parse_traits(
                    _as_list(item["children"]),
                    out,
                    group_name=item.get("name", group_name),
                    _depth=_depth + 1,
                )
            continue

        out.append(_build_leaf_trait(item, group_name))


def _build_meta_trait(item: dict, group_name: str | None) -> ParsedTrait:
    calc = _as_dict(item.get("calc"))
    return ParsedTrait(
        name=item.get("name", "Unknown"),
        group_name=group_name,
        points=_as_int(calc.get("points", 0)),
        level=None,
        tags=item.get("tags", []),
        has_weapon=False,
        weapons=[],
        notes=_COPYRIGHT_DROPPED_NOTES,
    )


def _build_leaf_trait(item: dict, group_name: str | None) -> ParsedTrait:
    calc = _as_dict(item.get("calc"))
    weapons = [w for w in _as_list(item.get("weapons")) if isinstance(w, dict)]
    return ParsedTrait(
        name=item.get("name", "Unknown"),
        group_name=group_name,
        points=_as_int(calc.get("points", 0)),
        level=_trait_level(item, calc),
        tags=item.get("tags", []),
        has_weapon=bool(weapons),
        weapons=[_parse_weapon(w) for w in weapons],
        notes=_COPYRIGHT_DROPPED_NOTES,
    )


def _trait_level(item: dict, calc: dict) -> int | None:
    if not item.get("can_level"):
        return None
    raw_level = item.get("levels") or calc.get("current_level")
    return _as_int(raw_level) if raw_level is not None else None


def _parse_weapon(w: dict, *, include_ranged: bool = False) -> dict:
    """ranged fields only when include_ranged (equipment weapons) — trait weapons are melee-only"""
    calc = _as_dict(w.get("calc"))
    result = {
        "usage": w.get("usage", ""),
        "damage": calc.get("damage", ""),
        "reach": calc.get("reach", w.get("reach", "")),
        "parry": calc.get("parry", w.get("parry", "")),
        "block": calc.get("block", ""),
        "level": calc.get("level", 0),
        "defaults": w.get("defaults", []),
    }
    if include_ranged:
        result.update({
            "strength": w.get("strength", ""),
            "accuracy": w.get("accuracy", ""),
            "range": w.get("range", ""),
            "rate_of_fire": w.get("rate_of_fire", ""),
            "shots": w.get("shots", ""),
            "bulk": w.get("bulk", ""),
        })
    return result


def _flatten_equipment(items: list, _depth: int = 0) -> list[dict]:
    """flatten, parent before children (backpack, then its contents)"""
    _guard_depth(_depth)
    result: list[dict] = []
    for item in items:
        _guard_item_cap(result, "equipment")
        if not isinstance(item, dict):
            continue

        result.append(_build_equipment_entry(item))

        children = item.get("children")
        if children:
            result.extend(_flatten_equipment(_as_list(children), _depth + 1))

    return result


def _build_equipment_entry(item: dict) -> dict:
    calc = _as_dict(item.get("calc"))
    weapons = [w for w in _as_list(item.get("weapons")) if isinstance(w, dict)]
    return {
        "description": item.get("description", ""),
        "quantity": _as_int(item.get("quantity", 1), 1),
        "weight": calc.get("extended_weight", "0 lb"),
        "value": calc.get("extended_value", 0),
        "equipped": item.get("equipped", False),
        "weapons": [_parse_weapon(w, include_ranged=True) for w in weapons],
    }
