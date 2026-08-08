"""Convention contract scans — conventions that were docstring-only.

Two invariants this project relies on were written down but never enforced, so
nothing stopped the next edit from breaking them:

* **DB access layering** — cogs open sessions through the sanctioned
  ``interaction.client.db()`` / ``self.bot.db()`` context and delegate queries to
  ``services/``; the cog owns the transaction (``session.commit()``), the service
  owns the query.
* **Top-level command count** — Discord caps an application at 100 top-level
  entries, and the post-launch arc's whole premise is breadth. New commands land
  inside groups; a new top-level is a deliberate re-pin here, not a drift.
* **Skill-cache single-owner invalidation** — ``skill_cache`` is defined in
  ``utils/_cache_instances.py`` and invalidated ONLY by ``services/characters.py``,
  at the service layer, so every caller of ``set_active_character`` /
  ``delete_character`` / ``import_character`` gets invalidation without having to
  remember it. ``cogs/rolling.py`` reads and fills the cache; that is the
  producer/consumer side and is fine.

Both are encoded here as AST scans over the real source tree: parse the files,
collect violations as ``path:line: source``, assert with a message naming every
offender.

Scans FAIL CLOSED. Each scan asserts it actually visited files and — where a
known-positive exists — that it can still see one, because an empty result from a
broken probe and an empty result from a clean tree look identical.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from discord import app_commands

from tests.test_extensions_load import loaded_bot

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "gurps_bot"
COGS_DIR = PACKAGE_ROOT / "cogs"


# --- shared helpers ---------------------------------------------------------


def _sources(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _rel(path: Path) -> str:
    """Repo-relative posix path; absolute for the scanners' own tmp_path probes."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _line(path: Path, lineno: int) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[lineno - 1].strip() if 0 < lineno <= len(lines) else "<?>"


def _violation(path: Path, node: ast.AST, note: str) -> str:
    lineno = getattr(node, "lineno", 0)
    return f"{_rel(path)}:{lineno}: {_line(path, lineno)}   <-- {note}"


# ---------------------------------------------------------------------------
# (a) DB access layering.
# ---------------------------------------------------------------------------

#: SQLAlchemy names that BUILD or RUN a query. A cog importing one is doing data
#: access itself rather than calling a service.
_QUERY_API = frozenset({
    "select", "insert", "update", "delete", "func", "text", "and_", "or_",
    "not_", "exists", "union", "union_all", "join", "case", "cast", "literal",
    "desc", "asc", "distinct", "over", "bindparam", "table", "column",
})

#: The ONE sqlalchemy name a cog may import: the AsyncSession TYPE, used purely
#: in annotations (``fetch: Callable[[AsyncSession, ...]]``). Importing a type is
#: not data access; CONSTRUCTING one is, and that is caught separately below.
_ALLOWED_SQLALCHEMY_IMPORTS = {("sqlalchemy.ext.asyncio", "AsyncSession")}

#: Session methods that RUN a query. ``commit`` / ``rollback`` / ``close`` are
#: deliberately absent: the cog owns the transaction and the service never
#: commits — the documented contract in cogs/trackers.py and cogs/macros.py.
_SESSION_QUERY_METHODS = frozenset({
    "execute", "scalar", "scalars", "stream", "stream_scalars", "add",
    "add_all", "flush", "merge", "refresh", "get", "get_one", "delete",
})

#: Calling any of these in a cog means the cog is minting its own session or
#: engine instead of using the bot's ``db()`` context.
_SESSION_CONSTRUCTORS = frozenset({
    "init_engine", "get_session_factory", "create_async_engine",
    "async_sessionmaker", "sessionmaker", "AsyncSession", "Session",
})

#: EXPLICIT exemptions, one file each, with the reason it is legitimate. An
#: entry here is a standing debt, not a blessing:
#: ``test_data_access_allowlist_is_not_stale`` removes the exemption's cover the
#: moment the file stops needing it. Currently empty — every cog delegates.
_DATA_ACCESS_ALLOWLIST: dict[str, str] = {}


def _is_session_receiver(node: ast.expr) -> bool:
    """True for ``session`` / ``ctx.session`` / ``self.session`` style receivers.

    Deliberately narrow: without it, every ``dict.get(...)`` in a cog would
    register as a session query.
    """
    try:
        rendered = ast.unparse(node)
    except Exception:  # pragma: no cover - unparse covers every real expression
        return False
    return rendered == "session" or rendered.endswith(".session")


def _data_access_violations(path: Path) -> list[str]:
    """Direct-SQLAlchemy / session-minting hits in one cog file."""
    hits: list[str] = []
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy"):
            for alias in node.names:
                if (node.module, alias.name) in _ALLOWED_SQLALCHEMY_IMPORTS:
                    continue
                note = (
                    f"imports {alias.name!r} from {node.module} — query building "
                    f"belongs in services/"
                    if alias.name in _QUERY_API
                    else f"imports {alias.name!r} from {node.module} directly"
                )
                hits.append(_violation(path, node, note))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "sqlalchemy":
                    hits.append(_violation(path, node, f"imports {alias.name} directly"))
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr in _SESSION_QUERY_METHODS and _is_session_receiver(func.value):
                    hits.append(
                        _violation(path, node, f"runs session.{func.attr}() in a cog")
                    )
            elif isinstance(func, ast.Name) and func.id in _SESSION_CONSTRUCTORS:
                hits.append(
                    _violation(
                        path, node,
                        f"constructs a session/engine via {func.id}() — use the "
                        f"bot's db() context",
                    )
                )
    return hits


class TestDbAccessLayering:
    """Cogs open sessions via ``db()`` and delegate queries to ``services/``."""

    def test_scan_sees_the_cog_tree(self):
        """FAIL CLOSED: a scan over zero files proves nothing."""
        sources = _sources(COGS_DIR)
        assert len(sources) >= 10, f"cog scan found only {len(sources)} files under {COGS_DIR}"

    def test_scanner_detects_a_planted_violation(self, tmp_path):
        """Verify the instrument before trusting a clean reading."""
        planted = tmp_path / "planted_cog.py"
        planted.write_text(
            "from sqlalchemy import select\n"
            "async def go(session):\n"
            "    return await session.execute(select(1))\n",
            encoding="utf-8",
        )
        found = _data_access_violations(planted)
        assert len(found) == 2, found
        assert any("select" in f for f in found)
        assert any("session.execute" in f for f in found)

    def test_scanner_ignores_the_sanctioned_pattern(self, tmp_path):
        """A cog doing it RIGHT must not register — no false-positive tax."""
        clean = tmp_path / "clean_cog.py"
        clean.write_text(
            "from sqlalchemy.ext.asyncio import AsyncSession\n"
            "from gurps_bot.services.characters import get_active_character\n"
            "async def go(interaction, payload: dict):\n"
            "    async with interaction.client.db() as session:\n"
            "        char = await get_active_character(session, 1, 2)\n"
            "        await session.commit()\n"
            "    return payload.get('x')\n",
            encoding="utf-8",
        )
        assert _data_access_violations(clean) == []

    def test_no_cog_does_its_own_data_access(self):
        violations: list[str] = []
        for path in _sources(COGS_DIR):
            if path.name in _DATA_ACCESS_ALLOWLIST:
                continue
            violations.extend(_data_access_violations(path))
        assert not violations, (
            "cogs must open sessions via interaction.client.db() and delegate "
            "queries to services/ — direct data access found:\n  "
            + "\n  ".join(violations)
            + "\n\nMove the query into services/, or add the file to "
            "_DATA_ACCESS_ALLOWLIST with the reason it is legitimate."
        )

    def test_data_access_allowlist_is_not_stale(self):
        """An exemption whose file no longer needs it must be DELETED, not kept.

        Otherwise the allowlist quietly grows into a second, unreviewed
        convention — the fail-open shape these scans exist to close.
        """
        for filename, reason in _DATA_ACCESS_ALLOWLIST.items():
            path = COGS_DIR / filename
            assert path.is_file(), f"_DATA_ACCESS_ALLOWLIST names a missing cog: {filename}"
            assert reason.strip(), f"_DATA_ACCESS_ALLOWLIST[{filename!r}] has no reason"
            assert _data_access_violations(path), (
                f"{filename} no longer does direct data access — remove its "
                f"_DATA_ACCESS_ALLOWLIST entry so the exemption stops covering "
                f"future edits"
            )


# ---------------------------------------------------------------------------
# (b) Skill-cache single-owner invalidation.
# ---------------------------------------------------------------------------

_CACHE_MODULE = "gurps_bot.utils._cache_instances"
_CACHE_NAME = "skill_cache"
#: Mutation surface. ``get`` / ``set`` are the producer/consumer side (rolling.py).
_CACHE_MUTATORS = frozenset({"invalidate", "invalidate_user"})
#: The single owner of invalidation.
_CACHE_INVALIDATION_OWNER = "gurps_bot/services/characters.py"
#: Every module allowed to import the shared instance at all, and why. Pinned so a
#: new reader is a deliberate edit here rather than a silent third stakeholder in
#: a cache whose invalidation has exactly one owner.
_CACHE_IMPORTERS = {
    "gurps_bot/services/characters.py": "owner — invalidates on every mutation",
    "gurps_bot/cogs/rolling.py": "producer/consumer — reads and fills, never invalidates",
}


def _imports_skill_cache(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == _CACHE_MODULE:
            if any(alias.name == _CACHE_NAME for alias in node.names):
                return True
    return False


def _cache_mutation_calls(path: Path) -> list[str]:
    """Calls to a skill_cache mutator in one file.

    Matches any receiver spelled ``…skill_cache`` — the bare name, the
    ``_skill_cache`` import alias used by rolling.py, and the
    ``_cache_instances.skill_cache`` module-attribute form.
    """
    hits: list[str] = []
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _CACHE_MUTATORS:
            continue
        try:
            receiver = ast.unparse(func.value)
        except Exception:  # pragma: no cover
            continue
        if receiver.endswith(_CACHE_NAME):
            hits.append(_violation(path, node, f"{receiver}.{func.attr}()"))
    return hits


class TestSkillCacheSingleOwner:
    """``skill_cache`` invalidation belongs to the service layer, nowhere else."""

    def test_scan_sees_the_package_tree(self):
        sources = _sources(PACKAGE_ROOT)
        assert len(sources) >= 30, f"package scan found only {len(sources)} files"

    def test_scanner_sees_the_known_positive(self):
        """Verify the instrument: the OWNER's calls must actually be detected.

        If this ever reads zero, the scan below is green because it is blind,
        not because the invariant holds.
        """
        owner = REPO_ROOT / _CACHE_INVALIDATION_OWNER
        assert _cache_mutation_calls(owner), (
            f"the scanner found no invalidation calls in {_CACHE_INVALIDATION_OWNER} — "
            f"the detector is broken, or invalidation moved and this contract needs "
            f"rewriting"
        )

    def test_scanner_detects_a_planted_violation(self, tmp_path):
        planted = tmp_path / "planted_cog.py"
        planted.write_text(
            "from gurps_bot.utils._cache_instances import skill_cache as _skill_cache\n"
            "def go(user_id):\n"
            "    _skill_cache.get((user_id, 1))\n"  # reads are fine
            "    _skill_cache.invalidate_user(user_id)\n",
            encoding="utf-8",
        )
        found = _cache_mutation_calls(planted)
        assert len(found) == 1, found
        assert "invalidate_user" in found[0]

    def test_only_the_service_layer_invalidates(self):
        violations: list[str] = []
        for path in _sources(PACKAGE_ROOT):
            if _rel(path) == _CACHE_INVALIDATION_OWNER:
                continue
            violations.extend(_cache_mutation_calls(path))
        assert not violations, (
            f"skill_cache invalidation has a single owner ({_CACHE_INVALIDATION_OWNER}) "
            f"so no caller has to remember it — new call site(s) found:\n  "
            + "\n  ".join(violations)
            + f"\n\nInvalidate from the service that performs the mutation instead."
        )

    def test_importers_are_the_pinned_set(self):
        importers = {
            _rel(path) for path in _sources(PACKAGE_ROOT) if _imports_skill_cache(_tree(path))
        }
        assert importers == set(_CACHE_IMPORTERS), (
            "the set of modules importing the shared skill_cache changed.\n"
            f"  expected: {sorted(_CACHE_IMPORTERS)}\n"
            f"  found:    {sorted(importers)}\n"
            "A new reader is fine — record it in _CACHE_IMPORTERS with its role, so "
            "the cache's stakeholders stay enumerable and invalidation keeps one owner."
        )

    def test_cache_instance_is_defined_where_the_contract_says(self):
        """The invariant names a definition site; pin it so a move is deliberate."""
        module = PACKAGE_ROOT / "utils" / "_cache_instances.py"
        assert module.is_file()
        assigned = {
            target.id
            for node in ast.walk(_tree(module))
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        assert _CACHE_NAME in assigned, (
            f"{_CACHE_NAME} is no longer defined in {_rel(module)} — the single-owner "
            f"contract in this module (and utils/_cache_instances.py's docstring) "
            f"names it as the definition site"
        )


# ---------------------------------------------------------------------------
# (c) Top-level command count.
# ---------------------------------------------------------------------------

#: Discord's hard limit on top-level entries per application. Not ours to raise.
_DISCORD_TOP_LEVEL_CAP = 100

#: Measured from the live tree 2026-08-07. The arc adds one subsystem at a time
#: and each one wants commands, so this number is the whole reason groups are
#: mandatory: at one top-level per feature the app hits Discord's wall inside a
#: handful of slices, and the wall has no appeal. Slice 1 takes this to 46 by
#: adding a crafting GROUP — a single entry buying a whole subsystem, which is
#: the trade the pin exists to make visible.
_TOP_LEVEL_COUNT = 45
_GROUP_COUNT = 12
_STANDALONE_COUNT = 33


async def _load_full_tree() -> tuple[list, list]:
    """(groups, standalone) from the real combined tree.

    Loading every extension into ONE bot is the only way to see the tree
    Discord sees; per-cog tests each see a fragment. ``loaded_bot`` owns the
    module-cache restore — ``Bot.close()`` pops the cog modules out of
    ``sys.modules`` while the parent package still names the orphans, which
    silently breaks any later ``mock.patch`` by string.
    """
    async with loaded_bot() as bot:
        top = list(bot.tree.get_commands())
        groups = [c for c in top if isinstance(c, app_commands.Group)]
        standalone = [c for c in top if not isinstance(c, app_commands.Group)]
        return groups, standalone


class TestTopLevelCommandCountIsPinned:
    """A new top-level entry must be ruled on, not discovered at the cap."""

    async def test_the_tree_loaded(self):
        """FAIL CLOSED: an empty tree would satisfy any 'under the cap' check."""
        groups, standalone = await _load_full_tree()
        assert groups and standalone, "the combined command tree came back empty"

    async def test_top_level_count_matches_the_pin(self):
        groups, standalone = await _load_full_tree()
        total = len(groups) + len(standalone)
        assert total == _TOP_LEVEL_COUNT, (
            f"top-level command count is {total}, pinned at {_TOP_LEVEL_COUNT} "
            f"({len(groups)} groups + {len(standalone)} standalone; pin says "
            f"{_GROUP_COUNT} + {_STANDALONE_COUNT}).\n"
            f"Groups: {sorted(g.name for g in groups)}\n"
            "If the new entry is a GROUP carrying a subsystem, re-pin here and "
            "say so in the commit. If it is a loose standalone, put it in a "
            "group instead — Discord caps the app at "
            f"{_DISCORD_TOP_LEVEL_CAP} and breadth is the point."
        )

    async def test_the_split_matches_the_pin(self):
        """Total alone would let a group silently become 12 standalones."""
        groups, standalone = await _load_full_tree()
        assert (len(groups), len(standalone)) == (_GROUP_COUNT, _STANDALONE_COUNT), (
            f"group/standalone split is {len(groups)}/{len(standalone)}, "
            f"pinned at {_GROUP_COUNT}/{_STANDALONE_COUNT} — the total can hold "
            f"while the shape degrades"
        )

    async def test_the_tree_is_under_discords_cap(self):
        """The pin's own reason, executable rather than documented."""
        groups, standalone = await _load_full_tree()
        total = len(groups) + len(standalone)
        assert total < _DISCORD_TOP_LEVEL_CAP, (
            f"{total} top-level entries against Discord's {_DISCORD_TOP_LEVEL_CAP} cap"
        )

    def test_the_pin_is_internally_consistent(self):
        assert _GROUP_COUNT + _STANDALONE_COUNT == _TOP_LEVEL_COUNT
