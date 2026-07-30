"""tools/prose_inventory.py — the document a prose reviewer works from.

The tool is a generator, so its failure mode is not a crash: it is quietly
reporting less than it claims. The first version found 48 strings while the
codebase held roughly 900 user-facing string sites, and nothing in its output
made that visible. A reviewer would have read it as the whole surface.

So two properties are asserted here, and neither is "it runs":

  * **it does not invent text** — every string it attributes to a file is
    actually in that file
  * **it does not silently shrink** — a coverage floor, and the requirement
    that it keep reporting its own unresolved count

The floor is deliberately well under the current number. Its job is to catch a
collapse, not to be re-baselined on every edit.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "prose_inventory.py"

#: Well below the 723 measured 2026-07-29. A regression to the old literal-only
#: scan (48) or to an import failure has to fail; ordinary churn must not.
COVERAGE_FLOOR = 500

#: Command descriptions come from the live tree, so this is exact, not a floor.
MIN_COMMANDS = 90


def _run(*args: str) -> str:
    """The tool's stdout, decoded explicitly.

    `text=True` would use the locale encoding — cp1252 under PowerShell, UTF-8
    under a POSIX shell — and this output is full of em dashes and arrows, so an
    assertion on it would hold or fail by which terminal launched pytest.
    PYTHONIOENCODING covers the child's own side of the same problem.
    """
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True, encoding="utf-8", errors="replace",
        cwd=str(ROOT), env=env,
    )
    assert result.returncode == 0, f"tool failed:\n{result.stderr[-3000:]}"
    return result.stdout


@pytest.fixture(scope="module")
def report() -> str:
    return _run()


@pytest.fixture(scope="module")
def entries(report: str) -> list[tuple[str, int, str, str]]:
    """(file, line, kind, text) for every string in the § 3 listing."""
    rows: list[tuple[str, int, str, str]] = []
    current: str | None = None
    for line in report.splitlines():
        m = re.match(r"^### `(.+)`$", line)
        if m:
            current = m.group(1)
            continue
        m = re.match(r"^- `(\d+)` \*([\w.]+)\* (?:—|-) (.*)$", line)
        if m and current:
            rows.append((current, int(m.group(1)), m.group(2), m.group(3)))
    return rows


def _norm(text: str) -> str:
    """Words only — the comparison has to survive how Python spells a long string.

    Four seams sit between a joined string and the source it came from, and all
    four produced false alarms while this check was being written: a value
    resolved from a module constant is reported at its use site, implicit
    concatenation means the joined text appears nowhere literally, indentation
    lives inside those seams, and an `f` prefix ends up wedged between two words
    once the quotes are stripped.
    """
    text = re.sub(r"\b[fFrRbBuU]{1,2}(?=[\"'])", "", text)
    return re.sub(r"\s+", " ", text.replace('"', "").replace("'", ""))


class TestItDoesNotInventText:
    """A generator that fabricates is worse than one that omits — the reviewer
    would edit prose the bot never says, and the diff would look plausible."""

    def test_every_string_is_present_in_the_file_it_names(self, entries):
        assert entries, "parsed no entries; the report format changed"
        cache: dict[str, str] = {}
        bad = []
        checked = 0
        for rel, lineno, kind, text in entries:
            runs = re.findall(r"[A-Za-z][A-Za-z' ]{7,}", text)
            if not runs:
                continue  # too short to identify; nothing to verify against
            checked += 1
            if rel not in cache:
                cache[rel] = _norm((ROOT / rel).read_text(encoding="utf-8"))
            if _norm(max(runs, key=len).strip()) not in cache[rel]:
                bad.append(f"{rel}:{lineno} [{kind}] {text[:70]}")
        assert checked > 300, f"only verified {checked} entries; sample too thin"
        assert not bad, "attributed to a file that does not contain them:\n" + "\n".join(bad)

    def test_every_cited_file_exists(self, entries):
        missing = {rel for rel, *_ in entries if not (ROOT / rel).is_file()}
        assert not missing, f"cited files that do not exist: {sorted(missing)}"


class TestItDoesNotSilentlyShrink:
    def test_it_finds_the_bulk_of_the_prose(self, entries):
        assert len(entries) >= COVERAGE_FLOOR, (
            f"only {len(entries)} strings; the literal-only scan this replaced "
            f"found 48, so a number near that means the walk broke rather than "
            f"the prose shrinking"
        )

    def test_embeds_are_covered_not_just_reply_text(self, entries):
        """The specific gap that made the first version misleading: most of what
        a user reads is embed titles, field names and field values."""
        kinds = {kind for _, _, kind, _ in entries}
        assert {"embed.title", "embed.name", "embed.value"} <= kinds, (
            f"embed prose is missing; kinds present: {sorted(kinds)}"
        )
        embed = sum(1 for _, _, k, _ in entries if k.startswith("embed."))
        assert embed > len(entries) // 2, (
            f"only {embed} of {len(entries)} are embed prose; the embed walk is "
            "probably broken, since embeds carry most of this bot's output"
        )

    def test_the_command_tree_section_is_complete(self, report):
        listed = len(re.findall(r"^- \*\*`/", report, re.M))
        assert listed >= MIN_COMMANDS, f"only {listed} commands listed"


class TestItReportsItsOwnBlindSpot:
    """The honesty property. A floor presented as a total is the actual defect
    the rewrite was for — 48 strings with no way to tell that most were missing."""

    def test_it_publishes_a_coverage_figure(self, report):
        assert re.search(r"## 4\. Coverage — \d+ of \d+ sites \(\d+%\)", report), (
            "no coverage section; § 3 would read as a guarantee"
        )

    def test_it_names_where_the_unresolved_strings_live(self, report):
        tail = report.split("## 4.")[-1]
        assert "assembled at runtime" in tail
        assert re.search(r"^- `gurps_bot/.*` — \d+$", tail, re.M), (
            "unresolved count is stated but not attributed to files, so nobody "
            "can go look at them"
        )

    def test_stats_mode_agrees_with_the_document(self, entries):
        stats = _run("--stats")
        m = re.search(r"coverage\s+(\d+)/(\d+) sites", stats)
        assert m, f"no coverage line in --stats:\n{stats}"
        resolved = int(m.group(1))
        assert resolved == len(entries), (
            f"--stats says {resolved} resolved, the document lists "
            f"{len(entries)} — two counts of one thing, so one is wrong"
        )
