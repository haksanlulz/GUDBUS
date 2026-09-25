"""deploy/deploy.sh — what it does when `git pull` fails.

It ran `git pull --ff-only 2>/dev/null || echo "(no git remote or nothing to
pull — skipping)"` under `set -e`. "Nothing to pull" exits 0, so the `||`
branch only ever caught REAL failures — a diverged branch, local edits in the
way, a network or auth error — and then went on to migrate, run the tests
(which pass, on the old code), restart the service and print Done.

Runs the real script in throwaway git repos with `uv` stubbed on PATH, so
nothing past the pull step can touch this machine.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "deploy.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(
    BASH is None or shutil.which("git") is None or sys.platform == "win32",
    reason="needs bash and git; Git Bash on Windows ignores a PATH-prepended stub",
)


def _git(cwd, *args):
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )


def _checkout(tmp_path: Path, *, remote: bool) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    (work / "deploy").mkdir()
    shutil.copy(SCRIPT, work / "deploy" / "deploy.sh")
    _git(work, "init", "-q", "-b", "main")
    _git(work, "add", ".")
    _git(work, "commit", "-q", "-m", "base")
    if remote:
        origin = tmp_path / "origin.git"
        _git(tmp_path, "clone", "-q", "--bare", str(work), str(origin))
        _git(work, "remote", "add", "origin", str(origin))
        _git(work, "fetch", "-q", "origin")
        _git(work, "branch", "-q", "--set-upstream-to=origin/main", "main")
    return work


def _run(work: Path, tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "uv.log"
    # every later step goes through uv: stub it to record and fail loudly, so
    # a run that reaches it is visible and stops right there
    (bin_dir / "uv").write_text(f'#!/bin/sh\necho "$*" >> "{log}"\nexit 97\n')
    (bin_dir / "uv").chmod(0o755)
    proc = subprocess.run(
        [BASH, str(work / "deploy" / "deploy.sh")],
        cwd=work, capture_output=True, text=True,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
    )
    return proc, (log.read_text() if log.exists() else "")


class TestAFailedPullStopsTheDeploy:
    def test_a_diverged_branch_aborts_before_anything_else_runs(self, tmp_path):
        work = _checkout(tmp_path, remote=True)
        # origin moves on…
        other = tmp_path / "other"
        _git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(other))
        (other / "remote.txt").write_text("r")
        _git(other, "add", ".")
        _git(other, "commit", "-q", "-m", "remote")
        _git(other, "push", "-q", "origin", "main")
        # …and so does the deploy checkout: ff-only is now impossible
        (work / "local.txt").write_text("l")
        _git(work, "add", ".")
        _git(work, "commit", "-q", "-m", "local")

        proc, uv_calls = _run(work, tmp_path)
        assert proc.returncode != 0
        assert uv_calls == "", "the deploy carried on past a failed pull"

    def test_no_remote_is_still_a_skip(self, tmp_path):
        """The rsync'd-tree setup DEPLOY.md documents has no remote at all."""
        work = _checkout(tmp_path, remote=False)
        proc, uv_calls = _run(work, tmp_path)
        assert "skipping" in proc.stdout
        assert uv_calls.startswith("sync"), "a remote-less checkout must still deploy"

    def test_up_to_date_proceeds(self, tmp_path):
        work = _checkout(tmp_path, remote=True)
        _, uv_calls = _run(work, tmp_path)
        assert uv_calls.startswith("sync")


class TestTheClosingInstructionIsCurrent:
    def test_it_does_not_name_the_removed_sync_option(self):
        """/sync has no `clear` option since the 2026-07-25 escape; commands
        re-register at startup, and `@bot sync` is the rescue."""
        assert "clear:true" not in SCRIPT.read_text(encoding="utf-8")
