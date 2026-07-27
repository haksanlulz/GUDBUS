"""Live rung (S5): upstream still serves the commit we vendor from.

OPT-IN. The rest of the suite is offline and finishes in ~18s; a network test in
the default run would trade that for flakiness against someone else's uptime.
Enable with::

    GUDBUS_LIVE_SYNC_SMOKE=1 uv run python -m pytest tests/test_sync_live.py -v

Run it before a deploy or an image build, and whenever the vendored tree is
about to be regenerated. Failure here means vendoring is broken everywhere at
once, which is how the 2026-07-21 escape presented.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_TOOLS_SCRIPT = (
    Path(__file__).resolve().parent.parent / "tools" / "sync_gcs_library.py"
)

pytestmark = pytest.mark.skipif(
    os.environ.get("GUDBUS_LIVE_SYNC_SMOKE") != "1",
    reason="live upstream smoke is opt-in; set GUDBUS_LIVE_SYNC_SMOKE=1",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("sync_gcs_library", _TOOLS_SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sync = _load_module()


def test_probe_goes_red_on_a_sha_upstream_cannot_have(monkeypatch):
    """Planted positive — run FIRST, and the rung below means nothing without it.

    A probe that cannot fail and a genuinely healthy upstream produce the same
    green. This plants a SHA upstream cannot possibly serve and requires the
    probe to reject it, so the passing case below is evidence rather than
    decoration.
    """
    monkeypatch.setattr(sync, "PINNED_REF", "deadbeef" * 5)
    assert sync._pinned_ref_is_fetchable() is False, (
        "the fetch probe accepted a SHA upstream cannot have — it is not "
        "measuring reachability, and the real-pin check below proves nothing"
    )


def test_pinned_commit_is_still_fetchable_upstream():
    """The rung itself: vendoring's source of truth is still served."""
    assert sync._pinned_ref_is_fetchable() is True, (
        f"upstream no longer serves {sync.PINNED_REF}. Every deploy and image "
        f"build that vendors the catalog is broken until PINNED_REF is bumped."
    )


def test_verify_upstream_command_exits_clean():
    """End to end through the CLI entry point deploy would call."""
    assert sync.main(["--verify-upstream"]) == 0


def test_provenance_branch_still_exists_upstream():
    """Drift check, not a gate.

    PROVENANCE.md prints BRANCH as the source branch. The fetch no longer
    depends on it, so a rename cannot break vendoring — but it does make that
    published line false, which is worth knowing before it is republished.
    """
    head = sync._remote_head_sha(sync.BRANCH)
    if head is None:
        pytest.fail(
            f"upstream has no head named {sync.BRANCH!r} — vendoring still "
            f"works (the pin carries it), but PROVENANCE.md's branch line is "
            f"now false and should be bumped with the next pin move"
        )
    assert len(head) == 40
