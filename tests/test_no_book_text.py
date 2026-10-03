"""Contract scan: no GURPS book text lives in this repo.

A standing invariant, deliberately wider than the draft it replaced: **not even
privately, not the Basic Set markdown.** The accepted consequence is that
book-checks can never run in CI, so CI green does not mean book-checked. That rung stays manual, local and dated.

The temptation this closes is specific and arrives with the crafting arc: five
domains, six books, and every one of them easier to implement with the chapter
sitting next to the module. `docs/GURPS-IP-COMPLIANCE.md` is the standing
statement of why facts ship and text does not — this file is the part that
still holds when nobody re-reads the doc.

Four layers, because each one is blind where the others see:

* **containers** — a `.pdf` / `.epub` / `.djvu` anywhere in the working tree,
  tracked or not. Catches the raw book.
* **titled extracts** — a file *named* after a GURPS volume carrying a text
  suffix. Catches `Low-Tech-ch5.md` however it got there.
* **a pinned prose set + front-matter markers** — every tracked prose file is
  enumerated with a reason, so a new one is a deliberate edit here rather than
  a silent arrival, and the enumerated ones are read for the fingerprints of a
  book's own front matter and running heads. Catches an extract that was
  renamed innocuously, and catches a chapter pasted into a file that already
  had a right to exist.
* **Python source** — every tracked `.py` under `gurps_bot/`, `tests/` and
  `tools/` is parsed with `ast`, and its comments are read with `tokenize`.
  Three sub-rules: (a) a double-quoted span (straight or curly) of eight or
  more words in a comment or docstring whose paragraph also carries a book
  cite — a page cite such as B123, M45 or B556-557, an LTC volume, a `p.`/`pp.`
  or chapter reference, or a volume named in words; (b) a Basic Set page cite
  followed by a colon and an opening quote, in a comment or any string
  literal; (c) a dict, a sequence of `(key, text)` pairs, or a call taking such
  pairs, with ten or more rows keyed inside 3-18 or 4-40 (int keys or digit
  strings such as `"40+"`), whose row text averages more than five words — the
  shape of a full result table. Rows written as names bound to string literals
  are resolved; a bare list of 16 or 37 such strings counts too. A short label
  per row passes.

Layer 4 is a shape detector, not a reader. It does not see single-quoted
spans, quotes that are neither in a comment nor a docstring (for rule a),
paraphrase, or text in non-Python files beyond what layers 1-3 cover. Its
exemptions are named in `_PY_EXEMPT` (the SJG notice the bot must reproduce,
waived for the quote rules only) and `_PLANTED_NAME` (this file's own
fixtures, proven to cover nothing else).

Layer 1 walks the working tree rather than the index on purpose: "privately"
means a gitignored `books/` directory would satisfy a tracked-only scan while
being exactly what the operator ruled out.

Every layer FAILS CLOSED and carries a planted positive, because an empty
result from a broken probe and an empty result from a clean tree render
identically.
"""

from __future__ import annotations

import ast
import functools
import io
import re
import subprocess
import tokenize
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Book containers. Their presence needs no further evidence.
_CONTAINER_SUFFIXES = frozenset({
    ".pdf", ".epub", ".mobi", ".azw", ".azw3", ".djvu", ".cbz", ".cbr",
})

#: Suffixes an extracted chapter would plausibly wear.
_TEXT_SUFFIXES = frozenset({
    ".md", ".txt", ".rst", ".htm", ".html", ".csv", ".tsv", ".tex", ".xml",
    ".json", ".docx", ".rtf",
})

#: GURPS volume names, as they appear in filenames. Matched against the file
#: NAME only — the repo says "GURPS" constantly and page-cites constantly, so a
#: content-word scan would be noise. A name is a deliberate act.
_TITLE_PATTERN = re.compile(
    r"(?ix)"
    r"basic[ _-]?set | low[ _-]?tech | high[ _-]?tech | ultra[ _-]?tech |"
    r"thaumatology | martial[ _-]?arts | dungeon[ _-]?fantasy | bio[ _-]?tech |"
    r"social[ _-]?engineering | monster[ _-]?hunters | after[ _-]?the[ _-]?end |"
    r"gurps[ _-]?(magic|powers|action|supers|space|fantasy|horror|vehicles|"
    r"characters|campaigns)"
)

#: Directories with nothing to say about this invariant.
_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    ".mypy_cache", "node_modules", "htmlcov", ".idea", ".vscode", "dist",
    "build",
})

#: The vendored GCS master library is exempt from the TITLE rule and from it
#: alone. Its directories are literally book names (`Library/Basic Set/…`)
#: because that is how upstream organizes facts-only stat data — name,
#: attribute, difficulty, page cite, no prose. It is gitignored and reproduced
#: by ``tools/sync_gcs_library.py`` from a pinned upstream ref, so its contents
#: are not authored here. The CONTAINER rule still applies inside it: no
#: library update has any business shipping a PDF.
_LIBRARY_DIR = REPO_ROOT / "gurps_bot" / "data" / "gcs_library"

#: Every tracked prose file, with why it exists. A file arriving here without a
#: reason is the shape this invariant is about. Data fixtures and code are not
#: listed: data files fall under the suffix rules, and Python source is read by
#: layer 4.
_TRACKED_PROSE: dict[str, str] = {
    "README.md": "user-facing overview and setup",
    "docs/wiki/Home.md": "wiki index, published to the GitHub wiki",
    "docs/wiki/Commands.md": "full command table, pinned to the live tree",
    "docs/wiki/A-Session.md": "worked session quoting real bot output",
    "docs/wiki/Reference-Data.md": "where the lookup facts come from",
    "docs/wiki/Architecture.md": "package layout",
    "docs/wiki/Development.md": "migrations, test layers, line counts",
    "DEPLOY.md": "operator runbook",
    "PRIVACY.md": "published policy, linked from the Discord portal",
    "TERMS.md": "published policy, linked from the Discord portal",
    "docs/GURPS-IP-COMPLIANCE.md": "why facts-only data ships; the standing argument",
    "tests/fixtures/gcs_mini/README.md": "explains the synthetic wall fixture",
    "tests/golden/magic_golden.txt": "generated golden values — numbers, not prose",
    "gurps_bot/db/migrations/README": "alembic scaffold, shipped by the template",
}

#: Fingerprints of a book's own front matter and running heads. Chosen to be
#: absent from the SJG game-aid notice the bot is REQUIRED to reproduce
#: verbatim in ``/legal`` — "All rights are reserved by Steve Jackson Games
#: Incorporated" is in that notice, so it is deliberately not a marker here.
_FRONT_MATTER_MARKERS = (
    "printing history",
    "isbn",
    "gurps line editor",
    "managing editor",
    "art director",
    "page references that begin with",
    "chief operating officer",
    "director of sales",
)

#: A running head — the volume name shouting across the top of every page. The
#: single strongest tell that a page-extraction landed somewhere.
_RUNNING_HEAD = re.compile(
    r"^\s*GURPS (BASIC SET|MAGIC|POWERS|THAUMATOLOGY|LOW-TECH|HIGH-TECH|"
    r"ULTRA-TECH|MARTIAL ARTS)\b",
    re.MULTILINE,
)


# --- collection -------------------------------------------------------------


def _tracked_files() -> list[str]:
    """Repo-relative posix paths git knows about.

    Fails rather than skips when git is unavailable: this invariant is about
    what the repository carries, so a run that cannot see the index has not
    checked it. A skip here would be the fail-open shape.
    """
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, f"git ls-files failed: {proc.stderr.strip()}"
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _intree_files() -> list[Path]:
    """Every file in the working tree, ignored ones included."""
    found: list[Path] = []
    stack = [REPO_ROOT]
    while stack:
        current = stack.pop()
        for entry in current.iterdir():
            if entry.is_dir():
                if entry.name not in _SKIP_DIRS:
                    stack.append(entry)
            elif entry.is_file():
                found.append(entry)
    return found


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


# --- the three detectors ----------------------------------------------------


def _container_hits(paths: list[Path]) -> list[str]:
    return sorted(
        f"{_rel(p)}   <-- {p.suffix} is a book container"
        for p in paths
        if p.suffix.lower() in _CONTAINER_SUFFIXES
    )


def _titled_extract_hits(paths: list[Path]) -> list[str]:
    hits = []
    for path in paths:
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        if _LIBRARY_DIR in path.parents:
            continue
        match = _TITLE_PATTERN.search(path.name)
        if match:
            hits.append(f"{_rel(path)}   <-- named after {match.group(0)!r}")
    return sorted(hits)


def _front_matter_hits(path: Path) -> list[str]:
    """Book front matter / running heads inside one file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    hits = []
    lowered = text.lower()
    for marker in _FRONT_MATTER_MARKERS:
        if marker in lowered:
            hits.append(f"{_rel(path)}   <-- book front matter: {marker!r}")
    head = _RUNNING_HEAD.search(text)
    if head:
        hits.append(f"{_rel(path)}   <-- running head: {head.group(0).strip()!r}")
    return hits


def _is_prose_path(rel_path: str) -> bool:
    suffix = Path(rel_path).suffix.lower()
    return suffix in {".md", ".txt", ".rst"} or Path(rel_path).name == "README"


# --- layer 1: containers ----------------------------------------------------


class TestNoBookContainers:
    """No PDF/EPUB anywhere in the working tree, tracked or ignored."""

    def test_the_walk_sees_the_tree(self):
        """FAIL CLOSED: a walk over nothing proves nothing."""
        found = _intree_files()
        assert len(found) >= 200, f"working-tree walk found only {len(found)} files"

    def test_detector_sees_a_planted_container(self, tmp_path):
        planted = tmp_path / "GURPS Low-Tech.pdf"
        planted.write_bytes(b"%PDF-1.4\n")
        assert _container_hits([planted])

    def test_detector_ignores_ordinary_files(self, tmp_path):
        ordinary = tmp_path / "crafting.py"
        ordinary.write_text("TARGET = 12\n", encoding="utf-8")
        assert _container_hits([ordinary]) == []

    def test_no_book_container_in_the_tree(self):
        hits = _container_hits(_intree_files())
        assert not hits, (
            "GURPS book containers found in the working tree:\n  "
            + "\n  ".join(hits)
            + "\n\nThe books stay on the operator's own disk. Book-checks are a "
            "manual, local, dated rung, never a file in the repo."
        )


# --- layer 2: titled extracts -----------------------------------------------


class TestNoTitledExtracts:
    """No text file named after a GURPS volume."""

    def test_detector_sees_a_planted_extract(self, tmp_path):
        for name in ("Low-Tech-ch5.md", "basic_set_characters.txt", "GURPS Magic.html"):
            planted = tmp_path / name
            planted.write_text("x", encoding="utf-8")
            assert _titled_extract_hits([planted]), name

    def test_detector_ignores_the_repos_own_names(self, tmp_path):
        for name in ("test_crafting_invention.py", "magic.py", "magic_golden.txt"):
            benign = tmp_path / name
            benign.write_text("x", encoding="utf-8")
            assert _titled_extract_hits([benign]) == [], name

    def test_detector_still_reads_inside_the_library_dir(self):
        """The library is exempt from the TITLE rule only — prove the walk
        reaches it, or its container exemption would be untested by accident."""
        if not _LIBRARY_DIR.is_dir():
            pytest.skip("vendored GCS library absent — run tools/sync_gcs_library.py")
        reached = [p for p in _intree_files() if _LIBRARY_DIR in p.parents]
        assert reached, "the walk never entered the vendored library directory"

    def test_no_titled_extract_in_the_tree(self):
        hits = _titled_extract_hits(_intree_files())
        assert not hits, (
            "files named after GURPS volumes found in the working tree:\n  "
            + "\n  ".join(hits)
            + "\n\nExtracted chapters live outside the repo. If this is the "
            "vendored GCS library, it belongs under gurps_bot/data/gcs_library/."
        )


# --- layer 3: the pinned prose set and its contents -------------------------


class TestTrackedProseIsEnumerated:
    """Every tracked prose file is named here with a reason."""

    def test_the_index_is_readable(self):
        assert len(_tracked_files()) >= 200, "git ls-files returned an implausible tree"

    def test_the_pinned_set_matches_the_tree(self):
        actual = {p for p in _tracked_files() if _is_prose_path(p)}
        expected = set(_TRACKED_PROSE)
        assert actual == expected, (
            "the set of tracked prose files changed.\n"
            f"  added:   {sorted(actual - expected)}\n"
            f"  removed: {sorted(expected - actual)}\n"
            "A new doc is fine — add it to _TRACKED_PROSE with the reason it "
            "exists. That entry is the review step: this invariant is exactly "
            "the case where a file arrives without one."
        )

    def test_every_pin_names_a_real_file_with_a_reason(self):
        for rel_path, reason in _TRACKED_PROSE.items():
            assert (REPO_ROOT / rel_path).is_file(), f"_TRACKED_PROSE names a missing file: {rel_path}"
            assert reason.strip(), f"_TRACKED_PROSE[{rel_path!r}] has no reason"

    def test_detector_sees_planted_front_matter(self, tmp_path):
        planted = tmp_path / "notes.md"
        planted.write_text(
            "Some heading\n\nPrinting History\nFirst edition, ISBN 978-1-55634-729-5\n",
            encoding="utf-8",
        )
        hits = _front_matter_hits(planted)
        assert len(hits) == 2, hits

    def test_detector_sees_a_planted_running_head(self, tmp_path):
        planted = tmp_path / "chapter.md"
        planted.write_text("GURPS BASIC SET: CHARACTERS 347\n\nsome text\n", encoding="utf-8")
        assert any("running head" in h for h in _front_matter_hits(planted))

    def test_detector_does_not_fire_on_the_required_sjg_notice(self):
        """The bot MUST reproduce the game-aid notice verbatim in /legal.

        If a marker ever collides with that notice this scan starts failing on
        a file it exists to protect, so the collision is asserted against, not
        assumed away.
        """
        legal = REPO_ROOT / "gurps_bot" / "cogs" / "legal.py"
        assert legal.is_file()
        assert _front_matter_hits(legal) == []

    def test_no_book_front_matter_in_tracked_prose(self):
        hits: list[str] = []
        for rel_path in _TRACKED_PROSE:
            hits.extend(_front_matter_hits(REPO_ROOT / rel_path))
        assert not hits, (
            "book front matter found in tracked prose:\n  "
            + "\n  ".join(hits)
            + "\n\nPage cites are fine. The pages are not."
        )



# --- layer 4: book text inside Python source --------------------------------

#: Roots whose tracked ``.py`` files layer 4 parses.
_PY_ROOTS = ("gurps_bot/", "tests/", "tools/")

#: This file, which holds the planted layer-4 fixtures.
_SELF_REL = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()

#: The one assignment in this file whose contents layer 4 skips: the planted
#: sources the detectors are proven against. Nothing else in this file is
#: exempt.
_PLANTED_NAME = "_PLANTED_PY"

#: Files exempt from layer 4: sub-rules skipped, and why. Keep this short —
#: every entry is a place the scan does not look. The notice is quoted text by
#: design, so only the quote rules are waived; the table rule still applies.
_PY_EXEMPT: dict[str, tuple[frozenset[str], str]] = {
    "gurps_bot/cogs/legal.py": (
        frozenset({"quote", "cite-quote"}),
        "reproduces the SJG Online Policy notice, which the policy requires verbatim",
    ),
    "tests/test_legal.py": (
        frozenset({"quote", "cite-quote"}),
        "asserts that notice word for word",
    ),
}

#: A book cite: a page cite (B123, M45, MA110, B556-557), a Low-Tech Companion
#: volume (LTC3), a bare page reference (p. 16, pp. 16-18), a chapter
#: reference, or a volume named in words.
_CITE = re.compile(
    r"(?x)"
    r"\b(?:B|M|P|MA|LT|HT|UT|BT|DF|PU|SU|MH|TS)\d{1,3}(?:-\d{1,3})?\b"
    r"| \bLTC[1-4]\b"
    r"| \bpp?\.\s?\d{1,3}"
    r"| \bch(?:apter|\.)\s?\d{1,2}\b"
    r"| \b(?:Basic\s+Set|Low-Tech|High-Tech|Ultra-Tech|Bio-Tech|Thaumatology"
    r"|Martial\s+Arts|GURPS\s+(?:Magic|Powers)|Social\s+Engineering)\b"
)

#: A quoted span: straight or curly double quotes.
_QUOTED = re.compile(r'"([^"]{1,600})"|“([^”]{1,600})”')

#: A page cite introducing a quotation, straight or curly: B + page, colon, quote.
_CITE_COLON_QUOTE = re.compile(r'\bB\d{2,3}(?:-\d{1,3})?:\s?["“]')

#: Minimum words in a cited quote before it counts as copied text.
_QUOTE_MIN_WORDS = 8

#: Result-table shape: at least this many rows ...
_TABLE_MIN_ROWS = 10
#: ... keyed inside one of these roll ranges (3d6, or Fright Check's 4-40+) ...
_TABLE_KEY_RANGES = ((3, 18), (4, 40))
#: ... averaging more words per row than this. A label of a few words passes.
_TABLE_MAX_AVG_WORDS = 5.0
#: Row counts of a full 3-18 or 4-40 table, for bare sequences with no keys.
_TABLE_FULL_ROW_COUNTS = frozenset({16, 37})

_ROW_KEY_STR = re.compile(r"^(\d{1,2})\+?$")

_LAYER4_RULES = ("quote", "cite-quote", "table", "error")


def _word_count(text: str) -> int:
    return sum(1 for token in text.split() if any(ch.isalnum() for ch in token))


def _tracked_python_files() -> list[str]:
    return sorted(
        p for p in _tracked_files()
        if p.endswith(".py") and p.startswith(_PY_ROOTS)
    )


def _paragraphs(lines: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """Split ``(line_no, text)`` rows into blank-line-separated paragraphs."""
    paras: list[list[tuple[int, str]]] = [[]]
    for line_no, text in lines:
        if text.strip():
            paras[-1].append((line_no, text))
        elif paras[-1]:
            paras.append([])
    return [p for p in paras if p]


def _cited_quote_hits(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """``(line, detail)`` per long quoted span sharing a paragraph with a cite."""
    hits = []
    for para in _paragraphs(lines):
        text = "\n".join(t for _, t in para)
        cite = _CITE.search(text)
        if not cite:
            continue
        starts = []
        offset = 0
        for line_no, t in para:
            starts.append((offset, line_no))
            offset += len(t) + 1
        for match in _QUOTED.finditer(text):
            span = match.group(1) or match.group(2) or ""
            words = _word_count(span)
            if words < _QUOTE_MIN_WORDS:
                continue
            line_no = max(ln for off, ln in starts if off <= match.start())
            snippet = " ".join(span.split())[:50]
            hits.append((line_no, f"{words}-word quote beside {cite.group(0)!r}: {snippet!r}..."))
    return hits


def _comment_blocks(source: str) -> list[list[tuple[int, str]]]:
    """Runs of comments on consecutive rows, comment markers stripped."""
    blocks: list[list[tuple[int, str]]] = []
    last_row = -2
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type != tokenize.COMMENT:
            continue
        row = tok.start[0]
        body = re.sub(r"^#[:!]?\s?", "", tok.string)
        if row != last_row + 1 or not blocks:
            blocks.append([])
        blocks[-1].append((row, body))
        last_row = row
    return blocks


def _docstrings(tree: ast.AST, skip: set[int]) -> list[tuple[int, str]]:
    """Every bare string statement: docstrings and attribute docstrings."""
    return [
        (node.lineno, node.value.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        and id(node) not in skip
    ]


def _string_bindings(tree: ast.AST) -> dict[str, str]:
    """Names bound to a plain string, so a row written as a name still reads."""
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if (
            isinstance(target, ast.Name)
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            bound[target.id] = value.value
    return bound


def _row_keys(node: ast.AST) -> list[int] | None:
    """The roll totals a table key names (``7``, ``"7"``, ``"40+"``, ``(3, 18)``)."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return None
        if isinstance(node.value, int):
            return [node.value]
        if isinstance(node.value, str):
            match = _ROW_KEY_STR.match(node.value)
            return [int(match.group(1))] if match else None
        return None
    if isinstance(node, (ast.Tuple, ast.List)) and node.elts:
        keys: list[int] = []
        for elt in node.elts:
            sub = _row_keys(elt)
            if sub is None:
                return None
            keys.extend(sub)
        return keys
    return None


def _cell_text(node: ast.AST, bound: dict[str, str]) -> str | None:
    """All the text a table cell carries: literals, and names bound to strings."""
    parts = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            parts.append(sub.value)
        elif isinstance(sub, ast.Name) and sub.id in bound:
            parts.append(bound[sub.id])
    return " ".join(parts) if parts else None


def _table_rows(node: ast.AST) -> list[tuple[list[int], ast.AST]] | None:
    """``(keys, cell)`` pairs if ``node`` is a dict, a sequence of ``(key, cell)``
    pairs, or a call whose positional arguments are such pairs."""
    if isinstance(node, ast.Dict):
        if not node.keys or any(k is None for k in node.keys):
            return None
        pairs = list(zip(node.keys, node.values))
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Call)):
        elts = node.args if isinstance(node, ast.Call) else node.elts
        if not elts or not all(
            isinstance(e, (ast.Tuple, ast.List)) and len(e.elts) == 2 for e in elts
        ):
            return None
        pairs = [(e.elts[0], e.elts[1]) for e in elts]
    else:
        return None
    rows = []
    for key, cell in pairs:
        keys = _row_keys(key)
        if keys is None:
            return None
        rows.append((keys, cell))
    return rows


def _table_detail(node: ast.AST, bound: dict[str, str]) -> str | None:
    """Why ``node`` is shaped like a full result table, or None."""
    texts: list[str] = []
    rows = _table_rows(node)
    if rows is not None:
        keys: set[int] = set()
        for row_keys, cell in rows:
            text = _cell_text(cell, bound)
            if text is None:
                return None
            for key in row_keys:
                keys.add(key)
                texts.append(text)
        if len(keys) < _TABLE_MIN_ROWS:
            return None
        lo, hi = min(keys), max(keys)
        if not any(lo >= a and hi <= b for a, b in _TABLE_KEY_RANGES):
            return None
        shape = f"{len(keys)} rows keyed {lo}-{hi}"
    elif isinstance(node, (ast.List, ast.Tuple)):
        cells = [e for e in node.elts if not (isinstance(e, ast.Constant) and e.value is None)]
        if len(cells) not in _TABLE_FULL_ROW_COUNTS:
            return None
        for cell in cells:
            is_str = isinstance(cell, ast.Constant) and isinstance(cell.value, str)
            if not (is_str or (isinstance(cell, ast.Name) and cell.id in bound)):
                return None
            texts.append(_cell_text(cell, bound) or "")
        shape = f"{len(cells)} unkeyed rows"
    else:
        return None
    average = sum(_word_count(t) for t in texts) / len(texts)
    if average <= _TABLE_MAX_AVG_WORDS:
        return None
    return f"result table, {shape}, {average:.1f} words per row"


def _planted_node_ids(tree: ast.AST) -> set[int]:
    """Node ids inside the ``_PLANTED_PY`` assignment."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == _PLANTED_NAME for t in targets):
            ids.update(id(sub) for sub in ast.walk(node))
    return ids


def _scan_python(source: str, rel: str) -> dict[str, list[str]]:
    """Layer-4 hits in one file's source, by sub-rule.

    ``error`` collects anything that stopped the file being read: a file the
    scan could not parse is a file it has not checked.
    """
    hits: dict[str, list[str]] = {rule: [] for rule in _LAYER4_RULES}
    try:
        tree = ast.parse(source, filename=rel)
        comments = _comment_blocks(source)
    except (SyntaxError, tokenize.TokenError, ValueError) as exc:
        hits["error"].append(f"{rel}   <-- could not parse: {exc}")
        return hits

    skip = _planted_node_ids(tree) if rel == _SELF_REL else set()

    # (a) a long quoted span beside a book cite, in a comment or docstring
    for block in comments:
        for line_no, detail in _cited_quote_hits(block):
            hits["quote"].append(f"{rel}:{line_no}   <-- comment: {detail}")
    for start, text in _docstrings(tree, skip):
        lines = [(start + i, t) for i, t in enumerate(text.split("\n"))]
        for line_no, detail in _cited_quote_hits(lines):
            hits["quote"].append(f"{rel}:{line_no}   <-- docstring: {detail}")

    # (b) a page cite introducing a quotation, in a comment or any string
    for block in comments:
        for line_no, text in block:
            if _CITE_COLON_QUOTE.search(text):
                hits["cite-quote"].append(f"{rel}:{line_no}   <-- comment: {text.strip()[:70]}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            for i, line in enumerate(node.value.split("\n")):
                if _CITE_COLON_QUOTE.search(line):
                    hits["cite-quote"].append(
                        f"{rel}:{node.lineno + i}   <-- string: {line.strip()[:70]}"
                    )

    # (c) a literal shaped like a full result table
    bound = _string_bindings(tree)
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        detail = _table_detail(node, bound)
        if detail:
            hits["table"].append(f"{rel}:{node.lineno}   <-- {detail}")
    return hits


@functools.lru_cache(maxsize=1)
def _python_scan() -> dict[str, list[str]]:
    """Layer 4 over every tracked Python file, exemptions applied. Cached: the
    tree does not change during a run, and four tests read the result."""
    merged: dict[str, list[str]] = {rule: [] for rule in _LAYER4_RULES}
    for rel in _tracked_python_files():
        try:
            source = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            merged["error"].append(f"{rel}   <-- could not read: {exc}")
            continue
        exempt_rules = _PY_EXEMPT.get(rel, (frozenset(), ""))[0]
        for rule, found in _scan_python(source, rel).items():
            if rule == "error" or rule not in exempt_rules:
                merged[rule].extend(found)
    return merged


# Row text for the planted tables: invented here, long enough to read as a
# result row, and a label short enough to read as a label.
_ROW_LONG = "Roll against the listed attribute, and lose your next full turn afterward."
_ROW_LABEL = "Lose a turn"
_FRIGHT_KEYS = [str(k) for k in range(4, 40)] + ["40+"]


def _dict_source(keys: list, cell: str, name: str = "TABLE") -> str:
    rows = "".join(f"    {key!r}: {cell},\n" for key in keys)
    return f"{name} = {{\n{rows}}}\n"


#: Planted sources, by case. Keys starting ``hit-`` must fire the named
#: sub-rule; ``clean-`` must fire nothing. Layer 4 skips this one assignment
#: when it scans this file, and ``test_the_self_exemption_is_exact`` proves the
#: skip covers nothing else.
_PLANTED_PY: dict[str, tuple[str, str, int]] = {
    # (a) long quotes beside a cite
    "hit-quote-comment": ("quote", (
        "X = 1\n"
        "# B123 settles it:\n"
        '# "the quick brown fox jumps over the lazy sleeping dog"\n'
    ), 3),
    "hit-quote-docstring-curly": ("quote", (
        'def f():\n'
        '    """LTC3 p. 14 says\n'
        '    “one two three four five six seven eight nine”.\n'
        '    """\n'
    ), 3),
    "hit-quote-across-lines": ("quote", (
        "# M45: the rule reads \"one two three four\n"
        "# five six seven eight\" and stops.\n"
    ), 1),
    "clean-quote-short": ("", '# B123: a "five words only right here" quote\n', 0),
    "clean-quote-uncited": ("", (
        '# "one two three four five six seven eight nine ten"\n'
    ), 0),
    "clean-quote-other-paragraph": ("", (
        'def f():\n'
        '    """See B123.\n'
        '\n'
        '    "one two three four five six seven eight nine ten"\n'
        '    """\n'
    ), 0),
    # (b) a page cite introducing a quote
    "hit-cite-quote-comment": ("cite-quote", 'X = 1\n# B360: "short"\n', 2),
    "hit-cite-quote-string-curly": ("cite-quote", 'NOTE = "per B556: “short”"\n', 1),
    "clean-cite-no-quote": ("", '# B360: short, and not quoted\n', 0),
    # (c) literals shaped like a full result table
    "hit-table-int-keys": ("table", _dict_source(list(range(3, 19)), repr(_ROW_LONG)), 1),
    "hit-table-str-keys-by-name": ("table", (
        f"_ROW = {_ROW_LONG!r}\n" + _dict_source(_FRIGHT_KEYS, "_ROW")
    ), 2),
    "hit-table-pairs-in-a-call": ("table", (
        "T = rows(\n"
        + "".join(f"    (({k}, {21 - k}), {_ROW_LONG!r}),\n" for k in range(3, 11))
        + ")\n"
    ), 1),
    "hit-table-unkeyed": ("table", "T = [\n" + f"    {_ROW_LONG!r},\n" * 16 + "]\n", 1),
    "clean-table-short-labels-by-str-key": ("", _dict_source(_FRIGHT_KEYS, repr(_ROW_LABEL)), 0),
    "clean-table-short-labels-in-a-call": ("", (
        "T = rows(\n"
        + "".join(f"    (({k}, {21 - k}), {_ROW_LABEL!r}),\n" for k in range(3, 11))
        + ")\n"
    ), 0),
    "clean-table-too-few-rows": ("", _dict_source(list(range(3, 12)), repr(_ROW_LONG)), 0),
    "clean-table-out-of-range": ("", _dict_source(list(range(1, 21)), repr(_ROW_LONG)), 0),
}


def _scan_planted(tmp_path: Path, case: str) -> dict[str, list[str]]:
    """Write one planted source to disk and scan it the way the tree is scanned."""
    _, source, _ = _PLANTED_PY[case]
    path = tmp_path / "planted.py"
    path.write_text(source, encoding="utf-8")
    return _scan_python(path.read_text(encoding="utf-8"), "planted.py")


class TestNoBookTextInPython:
    """No quoted book passages or copied result tables in Python source."""

    def test_the_scan_reaches_every_python_root(self):
        """FAIL CLOSED: a scan over nothing proves nothing."""
        files = _tracked_python_files()
        assert len(files) >= 150, f"layer 4 found only {len(files)} tracked .py files"
        for root in _PY_ROOTS:
            assert any(f.startswith(root) for f in files), f"no tracked .py under {root}"
        assert _SELF_REL in files, "layer 4 does not reach its own file"

    def test_every_python_file_is_read(self):
        """FAIL CLOSED: a file that did not parse is a file that was not checked."""
        errors = _python_scan()["error"]
        assert not errors, "layer 4 could not read:\n  " + "\n  ".join(errors)

    def test_an_unparseable_file_is_an_error_not_a_pass(self):
        assert _scan_python("def (:\n", "broken.py")["error"]

    @pytest.mark.parametrize("case", sorted(_PLANTED_PY))
    def test_detectors_on_planted_sources(self, tmp_path, case):
        rule, _, line = _PLANTED_PY[case]
        hits = _scan_planted(tmp_path, case)
        fired = {r: h for r, h in hits.items() if h}
        if case.startswith("clean-"):
            assert not fired, fired
            return
        assert set(fired) >= {rule}, fired
        assert f"planted.py:{line} " in fired[rule][0], fired[rule]

    def test_exemptions_are_named_and_scoped(self):
        tracked = set(_tracked_files())
        for rel, (rules, reason) in _PY_EXEMPT.items():
            assert rel in tracked, f"_PY_EXEMPT names an untracked file: {rel}"
            assert reason.strip(), f"_PY_EXEMPT[{rel!r}] has no reason"
            assert rules and rules <= set(_LAYER4_RULES) - {"error"}, rel

    def test_the_self_exemption_is_exact(self):
        """Scanned under another name, this file's hits all sit inside the
        planted assignment, so the skip hides the fixtures and nothing else."""
        source = (REPO_ROOT / _SELF_REL).read_text(encoding="utf-8")
        tree = ast.parse(source)
        spans = [
            (node.lineno, node.end_lineno)
            for node in tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(
                isinstance(t, ast.Name) and t.id == _PLANTED_NAME
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
            )
        ]
        assert len(spans) == 1, spans
        start, end = spans[0]
        unskipped = _scan_python(source, "not-this-file.py")
        lines = [
            int(hit.split("   <--")[0].rsplit(":", 1)[1])
            for rule, hits in unskipped.items()
            if rule != "error"
            for hit in hits
        ]
        assert lines, "the planted fixtures no longer fire when unskipped"
        assert all(start <= n <= end for n in lines), (start, end, lines)
        assert not any(_scan_python(source, _SELF_REL).values())

    def test_no_cited_quote_in_python(self):
        hits = _python_scan()["quote"]
        assert not hits, (
            f"{len(hits)} quoted span(s) of {_QUOTE_MIN_WORDS}+ words beside a book cite, "
            "in comments or docstrings:\n  "
            + "\n  ".join(hits)
            + "\n\nCite the page and state the rule in your own words."
        )

    def test_no_page_cite_introducing_a_quote_in_python(self):
        hits = _python_scan()["cite-quote"]
        assert not hits, (
            f"{len(hits)} page cite(s) introducing a quotation:\n  "
            + "\n  ".join(hits)
            + "\n\nCite the page and state the rule in your own words."
        )

    def test_no_result_table_in_python(self):
        hits = _python_scan()["table"]
        assert not hits, (
            f"{len(hits)} literal(s) shaped like a full result table:\n  "
            + "\n  ".join(hits)
            + f"\n\nRows averaging more than {_TABLE_MAX_AVG_WORDS:g} words across a "
            "3-18 or 4-40 range are a copied table. Keep the key, cite the page, "
            "and give each row a short original label at most."
        )
