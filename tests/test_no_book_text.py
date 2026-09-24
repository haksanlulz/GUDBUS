"""Contract scan: no GURPS book text lives in this repo.

A standing invariant, deliberately wider than the draft it replaced: **not even
privately, not the Basic Set markdown.** The accepted consequence is that
book-checks can never run in CI, so CI green does not mean book-checked. That rung stays manual, local and dated.

The temptation this closes is specific and arrives with the crafting arc: five
domains, six books, and every one of them easier to implement with the chapter
sitting next to the module. `docs/GURPS-IP-COMPLIANCE.md` is the standing
statement of why facts ship and text does not — this file is the part that
still holds when nobody re-reads the doc.

Three layers, because each one is blind where the others see:

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

Layer 1 walks the working tree rather than the index on purpose: "privately"
means a gitignored `books/` directory would satisfy a tracked-only scan while
being exactly what the operator ruled out.

Every layer FAILS CLOSED and carries a planted positive, because an empty
result from a broken probe and an empty result from a clean tree render
identically.
"""

from __future__ import annotations

import re
import subprocess
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
#: listed — they are covered by their own suffix rules and by the shape tests.
_TRACKED_PROSE: dict[str, str] = {
    "README.md": "user-facing setup + command table",
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
