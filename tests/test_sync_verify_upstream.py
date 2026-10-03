"""Offline tests for ``sync_gcs_library.py --verify-upstream`` (S5).

The 2026-07-21 escape: upstream deleted the ``master`` branch, so
``clone --branch master`` failed on every deploy and container build, and
nothing detected it until a deploy broke. The fetch was re-keyed onto a pinned
SHA, which makes a *rename* harmless — but leaves the pin itself unguarded. A
force-push upstream can orphan the pinned commit, and the failure would again
surface only at deploy time.

``--verify-upstream`` is the standing detector. These tests cover its logic
without touching the network; the live rung lives in ``test_sync_live.py`` and
is opt-in.
"""

from __future__ import annotations

import importlib.util
import inspect
import subprocess
from pathlib import Path

import pytest

_TOOLS_SCRIPT = (
    Path(__file__).resolve().parent.parent / "tools" / "sync_gcs_library.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("sync_gcs_library", _TOOLS_SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sync = _load_module()


def _completed(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestWiring:
    def test_verify_upstream_flag_routes_to_its_command(self, monkeypatch):
        called = {}

        def fake_verify() -> int:
            called["yes"] = True
            return 0

        monkeypatch.setattr(sync, "cmd_verify_upstream", fake_verify)
        assert sync.main(["--verify-upstream"]) == 0
        assert called.get("yes"), "--verify-upstream did not reach cmd_verify_upstream"

    def test_verify_upstream_does_not_run_the_vendor_sync(self, monkeypatch):
        """The smoke must never overwrite the vendored tree as a side effect."""
        monkeypatch.setattr(
            sync,
            "cmd_sync",
            lambda: pytest.fail("--verify-upstream must not run cmd_sync"),
        )
        monkeypatch.setattr(sync, "_remote_head_sha", lambda branch: "abc123")
        monkeypatch.setattr(sync, "_pinned_ref_is_fetchable", lambda: True)
        assert sync.main(["--verify-upstream"]) == 0

    def test_check_and_verify_are_separate_paths(self, monkeypatch):
        monkeypatch.setattr(
            sync,
            "cmd_verify_upstream",
            lambda: pytest.fail("--check must not hit the network path"),
        )
        # --check is the offline dry run; it must not touch upstream.
        sync.main(["--check"])


class TestProbeShape:
    def test_fetch_probe_is_blobless_and_keyed_on_the_pinned_sha(self):
        """Cheap by construction, and aimed at the pin rather than a branch.

        A full ``--depth 1`` fetch of this repo is ~201 MB; blob-filtered it is
        ~1 MB, which is what makes a standing rung affordable. Keying on the
        branch instead of PINNED_REF would re-create the 2026-07-21 escape.
        """
        src = inspect.getsource(sync._pinned_ref_is_fetchable)
        assert "--filter=blob:none" in src, "probe must not download blobs"
        assert "PINNED_REF" in src
        assert "--branch" not in src
        assert "BRANCH" not in src, "the pin probe must not depend on a branch name"


class TestVerdicts:
    def test_returns_zero_when_pin_is_fetchable_and_branch_present(self, monkeypatch):
        monkeypatch.setattr(sync, "_pinned_ref_is_fetchable", lambda: True)
        monkeypatch.setattr(sync, "_remote_head_sha", lambda branch: "cd5bb05")
        assert sync.cmd_verify_upstream() == 0

    def test_branch_rename_is_drift_not_failure(self, monkeypatch, capsys):
        """A rename cannot break the fetch any more — but PROVENANCE.md claims
        the branch, so the claim going stale must be said out loud."""
        monkeypatch.setattr(sync, "_pinned_ref_is_fetchable", lambda: True)
        monkeypatch.setattr(sync, "_remote_head_sha", lambda branch: None)
        rc = sync.cmd_verify_upstream()
        out = capsys.readouterr().out
        assert rc == 0, "a branch rename alone must not fail the rung"
        assert "DRIFT" in out.upper()
        assert sync.BRANCH in out

    def test_returns_one_when_pin_is_unreachable(self, monkeypatch):
        """The actionable failure: upstream no longer serves the pinned commit."""
        monkeypatch.setattr(sync, "_pinned_ref_is_fetchable", lambda: False)
        monkeypatch.setattr(sync, "_remote_head_sha", lambda branch: "cd5bb05")
        assert sync.cmd_verify_upstream() == 1

    def test_unreachable_pin_reported_even_if_branch_also_gone(self, monkeypatch):
        monkeypatch.setattr(sync, "_pinned_ref_is_fetchable", lambda: False)
        monkeypatch.setattr(sync, "_remote_head_sha", lambda branch: None)
        assert sync.cmd_verify_upstream() == 1


class TestGitPlumbing:
    def test_remote_head_sha_returns_none_on_missing_branch(self, monkeypatch):
        monkeypatch.setattr(sync, "_git", lambda args, cwd=None: _completed(2, ""))
        assert sync._remote_head_sha("nope") is None

    def test_remote_head_sha_parses_the_sha(self, monkeypatch):
        line = "cd5bb05e6eff5dece0a3dbac90cc295161ac8da7\trefs/heads/main\n"
        monkeypatch.setattr(sync, "_git", lambda args, cwd=None: _completed(0, line))
        assert sync._remote_head_sha("main") == (
            "cd5bb05e6eff5dece0a3dbac90cc295161ac8da7"
        )

    def test_remote_head_sha_returns_none_on_empty_success(self, monkeypatch):
        """``ls-remote`` exits 0 with no output when the ref simply is not there."""
        monkeypatch.setattr(sync, "_git", lambda args, cwd=None: _completed(0, "\n"))
        assert sync._remote_head_sha("main") is None

    def test_pin_probe_reports_false_on_fetch_failure(self, monkeypatch):
        monkeypatch.setattr(sync, "_git", lambda args, cwd=None: _completed(128, "", "no such object"))
        assert sync._pinned_ref_is_fetchable() is False
