"""Fuzzy reference lookup over the in-memory GCS facts catalog."""

from __future__ import annotations

import logging
import re
from typing import Any

from gurps_bot.gcs.library import (
    CatalogEquipment,
    CatalogSkill,
    CatalogSpell,
    CatalogTechnique,
    CatalogTrait,
    load_library,
)
from gurps_bot.utils.fuzzy import fuzzy_match

logger = logging.getLogger(__name__)

# mirrors the loader's catalog keys; unknown categories resolve to an empty bucket
CATEGORIES: tuple[str, ...] = ("skills", "traits", "spells", "techniques", "equipment")

# rank tiers — lower sorts first
_TIER_EXACT = 0
_TIER_PREFIX = 1
_TIER_SUBSTRING = 2
_TIER_FUZZY = 3

_FUZZY_CUTOFF = 70


# a GCS @…@ placeholder token (@Specialty@, @City@), bare or embedded in a spec
_TEMPLATE_TOKEN = re.compile(r"@[^@]*@")


def _renderable_spec(spec: str | None) -> str | None:
    """A specialization fit to show a user, else None — @token@ placeholders must never render."""
    if not spec:
        return None
    if _TEMPLATE_TOKEN.search(spec):
        return None
    return spec


def _index_name(entry: Any) -> str:
    """Display/index name: "Name (Spec)" when the spec renders, else the bare name."""
    name = getattr(entry, "name", "") or ""
    spec = _renderable_spec(getattr(entry, "specialization", None))
    if spec:
        return f"{name} ({spec})"
    return name


class ReferenceIndex:
    """Name-indexed, fuzzy-searchable view over a {category: [dataclass]} catalog."""

    def __init__(self, catalog: dict[str, list[Any]]) -> None:
        # precomputed (casefolded display name, entry) pairs + sorted names per
        # category; entries are shared by reference — a third full-catalog copy
        # was ~4.6MB of dead memory
        self._by_category: dict[str, list[tuple[str, Any]]] = {}
        self._names: dict[str, list[str]] = {}
        for cat in CATEGORIES:
            entries = catalog.get(cat, [])
            pairs = [
                (_index_name(e).casefold(), e)
                for e in entries
                if _index_name(e)
            ]
            self._by_category[cat] = pairs
            # dedupe — entries recurring across books must not emit duplicate Choices
            self._names[cat] = sorted({_index_name(e) for _, e in pairs})

    def _entries(self, category: str) -> list[tuple[str, Any]]:
        return self._by_category.get(category, [])

    def names(self, category: str) -> list[str]:
        """Sorted entry names for autocomplete; unknown category -> []."""
        return list(self._names.get(category, []))

    def search(self, category: str, query: str, limit: int = 10) -> list[Any]:
        """Up to limit entries ranked exact > prefix > substring > fuzzy."""
        q = query.strip()
        if not q or limit <= 0:
            return []
        pairs = self._entries(category)
        if not pairs:
            return []

        ql = q.casefold()

        # deterministic tiers first; the fuzzy tier only fills the remainder
        ranked: list[tuple[int, float, str, Any]] = []
        placed: set[int] = set()
        for name_l, entry in pairs:
            if name_l == ql:
                tier = _TIER_EXACT
            elif name_l.startswith(ql):
                tier = _TIER_PREFIX
            elif ql in name_l:
                tier = _TIER_SUBSTRING
            else:
                continue
            ranked.append((tier, 0.0, name_l, entry))
            placed.add(id(entry))

        # fuzz over display names so a composed "Name (Spec)" matches its
        # selectable label
        remaining = [(nl, e) for nl, e in pairs if id(e) not in placed]
        if remaining:
            candidate_names = [_index_name(e) for _, e in remaining]
            # display-name -> entry; on a within-category collision, first wins
            by_name: dict[str, Any] = {}
            for _, e in remaining:
                by_name.setdefault(_index_name(e), e)
            for matched_name, score in fuzzy_match(
                q, candidate_names, limit=len(candidate_names), score_cutoff=_FUZZY_CUTOFF
            ):
                entry = by_name.get(matched_name)
                if entry is not None:
                    ranked.append((_TIER_FUZZY, -float(score), _index_name(entry).casefold(), entry))

        # tier asc, then score — fuzzy scores stored negative so higher ranks first
        ranked.sort(key=lambda t: (t[0], t[1], t[2]))
        return [entry for _, _, _, entry in ranked[:limit]]

    def get(self, category: str, name: str):
        """Exact or unambiguous-prefix match only — a typo must miss, never return a wrong entry's cite."""
        if not name or not name.strip():
            return None
        pairs = self._entries(category)
        if not pairs:
            return None

        target = name.strip().casefold()
        prefix_hit = None
        prefix_name = None
        ambiguous = False
        for name_l, entry in pairs:
            if name_l == target:
                return entry
            if name_l.startswith(target):
                if prefix_hit is None:
                    prefix_hit, prefix_name = entry, name_l
                elif name_l != prefix_name:
                    # a second, different name shares the prefix — keep scanning
                    # for an exact hit, but the prefix tier no longer holds a
                    # single trustworthy answer (same-named entries recurring
                    # across books are one answer, not an ambiguity)
                    ambiguous = True

        # no exact hit -> only an unambiguous prefix match is trustworthy;
        # ambiguity belongs to search()/autocomplete
        return None if ambiguous else prefix_hit


# ---------------------------------------------------------------------------
# dataclass -> cog-dict adapters: the cog's embed builders read raw GCS dict
# keys, and the mappers surface only the facts the dataclasses carry
# ---------------------------------------------------------------------------


def _combine_difficulty(attribute: str | None, difficulty: str | None) -> str | None:
    """("DX", "Hard") -> "DX/Hard" — the shape the cog's _decode_difficulty expects."""
    if not difficulty:
        return None
    if attribute:
        return f"{attribute}/{difficulty}"
    return difficulty


def _skill_to_entry(s: CatalogSkill) -> dict[str, Any]:
    return {
        "name": s.name,
        # @token@ specs are dropped here so no token can leak into the cog's title
        "specialization": _renderable_spec(s.specialization),
        "difficulty": _combine_difficulty(s.attribute, s.difficulty),
        "points": s.points,
        "reference": s.page,
        "defaults": s.defaults,
        "tags": s.tags,
    }


def _trait_to_entry(t: CatalogTrait) -> dict[str, Any]:
    return {
        "name": t.name,
        "base_points": t.points,
        "points_per_level": t.points_per_level,
        "levels": t.levels,
        "cr": t.cr,
        "cr_adj": t.cr_adj,
        "reference": t.page,
        "tags": t.tags,
    }


def _spell_to_entry(sp: CatalogSpell) -> dict[str, Any]:
    return {
        "name": sp.name,
        "difficulty": sp.difficulty,
        "college": sp.college,
        "spell_class": sp.spell_class,
        "resist": sp.resist,
        "power_source": sp.power_source,
        "points": sp.points,
        "casting_cost": sp.casting_cost,
        "maintenance_cost": sp.maintenance,
        "casting_time": sp.casting_time,
        "duration": sp.duration,
        "reference": sp.page,
        "tags": sp.tags,
    }


def _technique_to_entry(tch: CatalogTechnique) -> dict[str, Any]:
    return {
        "name": tch.name,
        "difficulty": tch.difficulty,
        "default": tch.default,
        "limit": tch.limit,
        "points": tch.points,
        "reference": tch.page,
        "tags": tch.tags,
    }


def _equipment_to_entry(e: CatalogEquipment) -> dict[str, Any]:
    # the cog builder reads an equipment name from 'description'; damage/reach
    # re-nest into a weapon block for its weapon renderer
    entry: dict[str, Any] = {
        "description": e.name,
        "base_value": e.cost,
        "base_weight": e.weight,
        "legality_class": e.legality,
        "tech_level": e.tech_level,
        "rated_strength": e.rated_strength,
        "reference": e.page,
        "tags": e.tags,
    }
    if e.damage or e.reach:
        weapon: dict[str, Any] = {"usage": "Attack"}
        if e.damage:
            weapon["calc"] = {"damage": e.damage}
        if e.reach:
            weapon["reach"] = e.reach
        entry["weapons"] = [weapon]
    return entry


_TO_ENTRY = {
    CatalogSkill: _skill_to_entry,
    CatalogTrait: _trait_to_entry,
    CatalogSpell: _spell_to_entry,
    CatalogTechnique: _technique_to_entry,
    CatalogEquipment: _equipment_to_entry,
}


def entry_to_dict(obj: Any) -> dict[str, Any] | None:
    """Catalog dataclass -> raw-key cog dict; unmapped types fail closed (TypeError, never a vars() dump)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    mapper = _TO_ENTRY.get(type(obj))
    if mapper is not None:
        return mapper(obj)
    raise TypeError(f"no facts-only mapper for {type(obj).__name__}")


class ReferenceLookup:
    """Cog-facing adapter — ReferenceIndex results converted to the raw-key dicts the cog reads."""

    def __init__(self, catalog: dict[str, list[Any]]) -> None:
        self._index = ReferenceIndex(catalog)

    @property
    def index(self) -> ReferenceIndex:
        return self._index

    def names(self, category: str) -> list[str]:
        return self._index.names(category)

    def get(self, category: str, name: str) -> dict[str, Any] | None:
        return entry_to_dict(self._index.get(category, name))

    def search(self, category: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return [
            d
            for d in (entry_to_dict(e) for e in self._index.search(category, query, limit))
            if d is not None
        ]


# ---------------------------------------------------------------------------
# lazy singleton over the disk-loaded catalog
# ---------------------------------------------------------------------------

_INDEX: ReferenceLookup | None = None


def get_reference_index() -> ReferenceLookup:
    """The shared ReferenceLookup, disk-loaded once per process."""
    global _INDEX
    if _INDEX is None:
        _INDEX = ReferenceLookup(load_library())
    return _INDEX


def reset_reference_index() -> None:
    """Drop the cached index (test/reload helper)."""
    global _INDEX
    _INDEX = None
