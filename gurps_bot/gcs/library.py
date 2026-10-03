"""vendored GCS library -> in-memory facts-only catalog; prose source fields (local_notes etc.) are never read — a rulebook-text leak is legal exposure, not just a bug"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from gurps_bot.utils.sanitize import sanitize_name

logger = logging.getLogger(__name__)


# layout: <root>/<Book>/<Book> <Category>.<ext>; must match VENDOR_LIBRARY in
# tools/sync_gcs_library.py
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY_ROOT = _PACKAGE_ROOT / "data" / "gcs_library" / "Library"


_ATTR_MAP = {
    "st": "ST",
    "dx": "DX",
    "iq": "IQ",
    "ht": "HT",
    "per": "Per",
    "will": "Will",
}

_DIFF_MAP = {
    "e": "Easy",
    "a": "Average",
    "h": "Hard",
    "vh": "Very Hard",
}

# the file extension is the category discriminator; rows carry no type field
_EXT_CATEGORY = {
    ".skl": "skills",   # .skl also carries techniques + group containers
    ".adq": "traits",
    ".spl": "spells",
    ".eqp": "equipment",
}

CONTAINER_KEY = "rows"


def _split_difficulty(code: str | None) -> tuple[str | None, str | None]:
    """skills/spells encode "<attr>/<diff>", techniques a bare "<diff>"; unknown codes pass through"""
    if not code:
        return None, None
    raw = code.strip().lower()
    if "/" in raw:
        attr_code, _, diff_code = raw.partition("/")
        attr = _ATTR_MAP.get(attr_code, attr_code.upper() or None)
        diff = _DIFF_MAP.get(diff_code, diff_code or None)
        return attr, diff
    return None, _DIFF_MAP.get(raw, raw or None)


@dataclass(frozen=True)
class CatalogSkill:
    name: str
    attribute: str | None
    difficulty: str | None
    page: str
    points: int | None
    defaults: list
    book: str
    #: verbatim, @token@ markers included — those are stripped at render, not here
    specialization: str | None = None
    tags: list = field(default_factory=list)


@dataclass(frozen=True)
class CatalogTrait:
    name: str
    points: int | None
    page: str
    book: str
    #: self-control roll (6/9/12/15) + adjustment token; only on self-control disads
    cr: int | None = None
    cr_adj: str | None = None
    points_per_level: int | None = None
    levels: int | None = None
    tags: list = field(default_factory=list)


@dataclass(frozen=True)
class CatalogSpell:
    name: str
    college: list
    difficulty: str | None
    page: str
    casting_cost: str
    maintenance: str
    casting_time: str
    duration: str
    spell_class: str
    book: str
    resist: str = ""
    power_source: str = ""
    points: int | None = None
    tags: list = field(default_factory=list)


@dataclass(frozen=True)
class CatalogTechnique:
    name: str
    difficulty: str | None
    page: str
    default: dict | None
    book: str
    #: limit = max bonus the technique can be bought up to
    limit: int | None = None
    points: int | None = None
    tags: list = field(default_factory=list)


@dataclass(frozen=True)
class CatalogEquipment:
    name: str
    cost: str
    weight: str
    damage: str
    reach: str
    page: str
    legality: str
    book: str
    tech_level: str = ""
    rated_strength: int | None = None
    tags: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# builders — facts only; prose fields are never read
# ---------------------------------------------------------------------------

def _ref(row: dict) -> str:
    return row.get("reference", "") or ""


def _tags(row: dict) -> list:
    return [str(t) for t in (row.get("tags") or []) if t not in (None, "")]


def _terse_fact(value: str) -> str:
    """some GCS spell fields carry verbatim rules sentences — drop anything prose-shaped, keep terse tokens only"""
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) > 48 or ";" in v or len(v.split()) > 4:
        return ""
    return v


#: discord Choice/title limit; an over-long upstream name (seen at 129 chars) is
#: usually a rules sentence masquerading as a name — cap at the source or the
#: send 400s
_NAME_MAX = 100


def _cap_name(name: str) -> str:
    if len(name) > _NAME_MAX:
        return name[:99].rstrip() + "…"
    return name


#: @token@ span incl. surrounding parens; must strip BEFORE sanitize_name, which
#: deletes the @ delimiters and would leave the placeholder text in the name
#: ("Bind Spirit (@Spirit@)" -> "Bind Spirit Spirit")
_TEMPLATE_TOKEN_SPAN = re.compile(r"\s*\(?@[^@]*@\)?")


def _strip_template_tokens(s: str) -> str:
    return _TEMPLATE_TOKEN_SPAN.sub("", s or "").strip()


def _clean_name(raw: str) -> str:
    """token-strip, then sanitize, then cap — order matters (see _TEMPLATE_TOKEN_SPAN)"""
    stripped = _strip_template_tokens(raw)
    return _cap_name(sanitize_name(stripped) or stripped)


def _build_skill(row: dict, *, book: str) -> CatalogSkill:
    attr, diff = _split_difficulty(row.get("difficulty"))
    name = _clean_name(row.get("name", ""))
    specialization = row.get("specialization") or None
    return CatalogSkill(
        name=name,
        attribute=attr,
        difficulty=diff,
        page=_ref(row),
        points=row.get("points"),
        defaults=row.get("defaults", []),
        book=book,
        specialization=specialization,
        tags=_tags(row),
    )


def _build_trait(row: dict, *, book: str) -> CatalogTrait:
    name = _clean_name(row.get("name", ""))
    return CatalogTrait(
        name=name,
        points=row.get("base_points"),
        page=_ref(row),
        book=book,
        cr=row.get("cr"),
        cr_adj=row.get("cr_adj") or None,
        points_per_level=row.get("points_per_level"),
        levels=row.get("levels"),
        tags=_tags(row),
    )


def _build_spell(row: dict, *, book: str) -> CatalogSpell:
    _attr, diff = _split_difficulty(row.get("difficulty"))
    name = _clean_name(row.get("name", ""))
    college = row.get("college", [])
    if isinstance(college, str):
        college = [college]
    return CatalogSpell(
        name=name,
        college=list(college),
        difficulty=diff,
        page=_ref(row),
        casting_cost=_terse_fact(row.get("casting_cost", "")),
        maintenance=_terse_fact(row.get("maintenance_cost", "")),
        casting_time=_terse_fact(row.get("casting_time", "")),
        duration=_terse_fact(row.get("duration", "")),
        spell_class=row.get("spell_class", ""),
        book=book,
        resist=_terse_fact(row.get("resist", "") or ""),
        power_source=row.get("power_source", "") or "",
        points=row.get("points"),
        tags=_tags(row),
    )


def _build_technique(row: dict, *, book: str) -> CatalogTechnique:
    _attr, diff = _split_difficulty(row.get("difficulty"))
    name = _clean_name(row.get("name", ""))
    return CatalogTechnique(
        name=name,
        difficulty=diff,
        page=_ref(row),
        default=row.get("default"),
        book=book,
        limit=row.get("limit"),
        points=row.get("points"),
        tags=_tags(row),
    )


def _weapon_damage(row: dict) -> tuple[str, str]:
    """(damage, reach) from the first weapon block; prefers resolved calc.damage, drops usage_notes (prose)"""
    weapons = row.get("weapons") or []
    for w in weapons:
        if not isinstance(w, dict):
            continue
        calc = w.get("calc", {}) or {}
        damage = calc.get("damage", "")
        if not damage:
            dmg = w.get("damage", {}) or {}
            base = dmg.get("base", "")
            dtype = dmg.get("type", "")
            damage = f"{base} {dtype}".strip()
        reach = calc.get("reach", w.get("reach", "")) or ""
        if damage or reach:
            return damage, reach
    return "", ""


def _cost_weight_fact(raw, calc: dict, calc_key: str) -> str:
    """base_value/base_weight can be an unevaluated @token@ formula — fall back to the resolved calc value, else "" (never leak the token)"""
    raw_s = str(raw or "")
    if raw_s and "@" not in raw_s:
        return raw_s
    resolved = (calc or {}).get(calc_key)
    resolved_s = str(resolved) if resolved not in (None, "") else ""
    return resolved_s if "@" not in resolved_s else ""


def _build_equipment(row: dict, *, book: str) -> CatalogEquipment:
    # equipment names live in 'description', unlike every other category
    name = _clean_name(row.get("description", ""))
    damage, reach = _weapon_damage(row)
    calc = row.get("calc") or {}
    return CatalogEquipment(
        name=name,
        cost=_cost_weight_fact(row.get("base_value"), calc, "value"),
        weight=_cost_weight_fact(row.get("base_weight"), calc, "weight"),
        damage=damage,
        reach=reach,
        page=_ref(row),
        legality=row.get("legality_class", "") or "",
        book=book,
        tech_level=row.get("tech_level", "") or "",
        rated_strength=row.get("rated_strength"),
        tags=_tags(row),
    )


def _is_container(row: dict) -> bool:
    return (
        "children" in row
        and "difficulty" not in row
        and "points" not in row
    )


def _is_technique(row: dict) -> bool:
    """technique = bare difficulty (no '/') + a singular default dict; skills encode <attr>/<diff>"""
    diff = row.get("difficulty")
    return (
        isinstance(diff, str)
        and "/" not in diff
        and isinstance(row.get("default"), dict)
    )


def _walk_skl_rows(rows: list, out: list, *, book: str) -> None:
    """flatten .skl rows into skills/techniques; containers recurse (seen 3 deep), never emitted"""
    for row in rows:
        if _is_container(row):
            _walk_skl_rows(row.get("children", []), out, book=book)
            continue
        # a row can carry children alongside leaf fields
        children = row.get("children")
        if children and "difficulty" not in row:
            _walk_skl_rows(children, out, book=book)
            continue
        if _is_technique(row):
            out.append(_build_technique(row, book=book))
        elif isinstance(row.get("difficulty"), str):
            out.append(_build_skill(row, book=book))
        # rows with neither difficulty nor children are skipped (placeholders)


def _trait_is_placeholder(row: dict) -> bool:
    """True for grouping containers and template placeholders in .adq files.

    No base_points + no points_per_level + no reference = not a real catalog
    trait: grouping rows ("Martial Arts Abilities") and template scaffolding
    ("Must take template's Duty") match; real zero-point entries keep their
    page cite ("Contact" B44) and meta-trait containers cite theirs, so both
    survive.
    """
    return (
        not row.get("base_points")
        and not row.get("points_per_level")
        and not row.get("reference")
    )


def _walk_simple_rows(
    rows: list, out: list, *, book: str, builder, name_field: str, skip=None,
) -> None:
    """flatten traits/spells/equipment rows; recursion is defensive — Basic Set is flat but the schema allows nesting.

    ``skip`` (row -> bool) suppresses emission of matching named rows while
    still recursing their children — how trait grouping/placeholder rows are
    filtered.
    """
    for row in rows:
        children = row.get("children")
        if children is not None and not row.get(name_field):
            _walk_simple_rows(
                children, out, book=book, builder=builder,
                name_field=name_field, skip=skip,
            )
            continue
        if row.get(name_field) and not (skip is not None and skip(row)):
            out.append(builder(row, book=book))
        if children:
            # a named container still gets recursed
            _walk_simple_rows(
                children, out, book=book, builder=builder,
                name_field=name_field, skip=skip,
            )


def _load_rows(path: Path) -> list:
    """explicit utf-8 — the windows cp1252 default crashes on this data"""
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    return data.get(CONTAINER_KEY, []) or []


def _category_for(path: Path) -> str | None:
    return _EXT_CATEGORY.get(path.suffix.lower())


def load_library(root: str | Path | None = None) -> dict[str, list]:
    """walk the vendored library -> {category: [entries]}; .skl feeds both skills and techniques"""
    base = Path(root) if root is not None else DEFAULT_LIBRARY_ROOT
    catalog: dict[str, list] = {
        "skills": [],
        "traits": [],
        "spells": [],
        "equipment": [],
        "techniques": [],
    }

    if not base.is_dir():
        logger.warning("GCS library root not found: %s", base)
        return catalog

    for book_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        book = book_dir.name
        for path in sorted(book_dir.iterdir()):
            if not path.is_file():
                continue
            category = _category_for(path)
            if category is None:
                continue
            try:
                rows = _load_rows(path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                logger.warning("Failed to parse GCS file %s: %s", path, exc)
                continue

            if category == "skills":
                mixed: list = []
                _walk_skl_rows(rows, mixed, book=book)
                for entry in mixed:
                    if isinstance(entry, CatalogTechnique):
                        catalog["techniques"].append(entry)
                    else:
                        catalog["skills"].append(entry)
            elif category == "traits":
                _walk_simple_rows(
                    rows, catalog["traits"], book=book, builder=_build_trait,
                    name_field="name", skip=_trait_is_placeholder,
                )
            elif category == "spells":
                _walk_simple_rows(rows, catalog["spells"], book=book, builder=_build_spell, name_field="name")
            elif category == "equipment":
                _walk_simple_rows(
                    rows, catalog["equipment"], book=book, builder=_build_equipment, name_field="description"
                )

    return catalog


# ---------------------------------------------------------------------------
# public api — lazy-loaded catalog
# ---------------------------------------------------------------------------

_CATALOG: dict[str, list] | None = None


def _get_catalog() -> dict[str, list]:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = load_library()
    return _CATALOG


def iter_category(cat: str):
    return iter(_get_catalog().get(cat, []))


def get(cat: str, name: str):
    """case-insensitive lookup, markdown noise sanitized away; None if absent"""
    target = sanitize_name(name or "").casefold()
    for entry in _get_catalog().get(cat, []):
        if getattr(entry, "name", "").casefold() == target:
            return entry
    return None


def reset_cache() -> None:
    global _CATALOG
    _CATALOG = None
