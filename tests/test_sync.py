"""Tests for the GCS master-library vendoring script (``tools/sync_gcs_library.py``).

These assert the *contract* of the vendored snapshot — that the pin is a real
hex SHA, that PROVENANCE/LICENSE were written with the expected provenance, and
that the catalog data actually landed on disk. They never hit the network: the
vendoring (one ``git clone``) is performed by running the script directly; the
tests only inspect the resulting files and the module's constants.

If the snapshot has not been vendored yet, the on-disk checks skip gracefully
(``pytest.skip``) rather than fail, but the preferred / CI state is vendored.
"""

from __future__ import annotations

import importlib.util
import inspect
import re
import subprocess
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the script by file path (tools/ is not an importable package).
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# PINNED_REF is a non-empty hex SHA.
# ---------------------------------------------------------------------------
class TestPinnedRef:
    def test_script_file_exists(self):
        assert _TOOLS_SCRIPT.is_file()

    def test_pinned_ref_is_nonempty_hex_sha(self):
        ref = sync.PINNED_REF
        assert isinstance(ref, str)
        assert ref, "PINNED_REF must be non-empty"
        # Full 40-char SHA-1, all hex. (A short SHA would still be hex; we pin
        # the full one here so the assertion is exact.)
        assert re.fullmatch(r"[0-9a-f]{40}", ref), f"not a 40-char hex sha: {ref!r}"

    def test_branch_and_repo_constants(self):
        assert sync.BRANCH == "main"
        assert "richardwilkes/gcs_master_library" in sync.REPO_URL

    def test_fetch_is_keyed_on_the_sha_not_the_branch(self):
        # Upstream renamed master -> main and broke `clone --branch <BRANCH>`.
        # BRANCH is provenance metadata now; the fetch must use PINNED_REF, so a
        # future rename cannot break vendoring again.
        # Assert on the git invocations only. The docstring *describes* the old
        # `--branch` path, so matching raw source would hit the prose instead.
        src = inspect.getsource(sync._clone_pinned)
        git_calls = [ln for ln in src.splitlines() if "_run_git(" in ln]
        assert git_calls, "no git invocations found in _clone_pinned"
        joined = "\n".join(git_calls)
        assert "PINNED_REF" in joined
        assert "FETCH_HEAD" in joined
        assert "--branch" not in joined
        assert '"clone"' not in joined

    def test_category_extensions_cover_contract(self):
        # The four catalog categories named in the data contract.
        assert set(sync.CATEGORY_EXTENSIONS) == {
            "skills",
            "traits",
            "spells",
            "equipment",
        }
        assert sync.CATEGORY_EXTENSIONS["skills"] == ".skl"
        assert sync.CATEGORY_EXTENSIONS["traits"] == ".adq"
        assert sync.CATEGORY_EXTENSIONS["spells"] == ".spl"
        assert sync.CATEGORY_EXTENSIONS["equipment"] == ".eqp"


# ---------------------------------------------------------------------------
# PROVENANCE.md exists with source URL + sha.
# ---------------------------------------------------------------------------
class TestProvenance:
    def test_provenance_present_with_url_and_sha(self):
        prov = sync.VENDOR_PROVENANCE
        if not prov.is_file():
            pytest.skip("snapshot not vendored yet (run tools/sync_gcs_library.py)")
        text = prov.read_text(encoding="utf-8")
        assert "github.com/richardwilkes/gcs_master_library" in text
        assert sync.PINNED_REF in text, "PROVENANCE.md must record the pinned sha"
        assert sync.BRANCH in text
        # Attribution / licensing facts.
        assert "MPL-2.0" in text or "Mozilla Public License" in text
        assert "Steve Jackson Games" in text


# ---------------------------------------------------------------------------
# LICENSE exists (MPL-2.0).
# ---------------------------------------------------------------------------
class TestLicense:
    def test_license_present_and_mpl(self):
        lic = sync.VENDOR_LICENSE
        if not lic.is_file():
            pytest.skip("snapshot not vendored yet (run tools/sync_gcs_library.py)")
        text = lic.read_text(encoding="utf-8")
        assert "Mozilla Public License" in text


# ---------------------------------------------------------------------------
# Vendored Library dir has >0 .skl files (prefer vendored; skip if absent).
# ---------------------------------------------------------------------------
class TestVendoredLibrary:
    def test_library_dir_has_skl_files(self):
        lib = sync.VENDOR_LIBRARY
        if not lib.is_dir():
            pytest.skip("snapshot not vendored yet (run tools/sync_gcs_library.py)")
        skl_files = [p for p in lib.rglob("*.skl") if p.is_file()]
        assert len(skl_files) > 0, "vendored Library/ must contain >0 .skl files"

    def test_all_catalog_categories_present(self):
        lib = sync.VENDOR_LIBRARY
        if not lib.is_dir():
            pytest.skip("snapshot not vendored yet (run tools/sync_gcs_library.py)")
        counts = sync._category_counts()
        # Every contract category should have landed at least one file.
        for cat in sync.CATEGORY_EXTENSIONS:
            assert counts.get(cat, 0) > 0, f"no vendored files for category {cat!r}"

    def test_contract_anchor_files_present(self):
        lib = sync.VENDOR_LIBRARY
        if not lib.is_dir():
            pytest.skip("snapshot not vendored yet (run tools/sync_gcs_library.py)")
        # Anchor files the data contract verified at the pinned SHA.
        anchors = [
            "Basic Set/Basic Set Skills.skl",
            "Basic Set/Basic Set Traits.adq",
            "Magic/Magic Spells.spl",
            "Basic Set/Basic Set Equipment.eqp",
            "Martial Arts/Martial Arts Skills.skl",
        ]
        for rel in anchors:
            assert (lib / rel).is_file(), f"missing contract anchor file: {rel}"

    def test_no_prose_or_sheet_files_leaked(self):
        """Copyright wall: only catalog extensions, never prose / character sheets."""
        lib = sync.VENDOR_LIBRARY
        if not lib.is_dir():
            pytest.skip("snapshot not vendored yet (run tools/sync_gcs_library.py)")
        allowed = sync.VENDOR_EXTENSIONS
        offenders = [
            str(p.relative_to(lib))
            for p in lib.rglob("*")
            if p.is_file() and p.suffix.lower() not in allowed
        ]
        assert not offenders, f"non-catalog files leaked into vendored tree: {offenders[:10]}"

    def test_check_command_returns_zero_when_vendored(self):
        if not sync.VENDOR_LIBRARY.is_dir():
            pytest.skip("snapshot not vendored yet (run tools/sync_gcs_library.py)")
        # --check is a network-free dry run; returns 0 when skills are present.
        assert sync.cmd_check() == 0


# ---------------------------------------------------------------------------
# Every git call is bounded.
# ---------------------------------------------------------------------------
class TestGitCallsAreBounded:
    """A stalled fetch must fail with a message, not hang the deploy.

    ``subprocess.run`` blocks indefinitely on a stalled TCP connection (as
    opposed to a refused one), and this script shells out to git over the
    network. deploy.sh runs it at deploy time, which is where an unbounded hang
    is worst — the deploy simply looks like it is still working.
    """

    def test_git_passes_an_explicit_timeout(self, monkeypatch):
        seen = {}

        def fake_run(argv, **kwargs):
            seen.update(kwargs)
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(sync.subprocess, "run", fake_run)
        sync._git(["ls-remote", "--heads", sync.REPO_URL, "main"])
        assert seen.get("timeout") == sync.GIT_TIMEOUT_SECONDS
        assert isinstance(sync.GIT_TIMEOUT_SECONDS, (int, float))
        assert sync.GIT_TIMEOUT_SECONDS > 0

    def test_a_timeout_becomes_a_runtime_error_naming_the_upstream(self, monkeypatch):
        def fake_run(argv, **kwargs):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs["timeout"])

        monkeypatch.setattr(sync.subprocess, "run", fake_run)
        with pytest.raises(RuntimeError) as exc:
            sync._git(["fetch", "--depth", "1", "origin", sync.PINNED_REF])
        message = str(exc.value)
        assert sync.REPO_URL in message, message
        assert str(sync.GIT_TIMEOUT_SECONDS) in message, message

    def test_the_cli_turns_it_into_a_nonzero_exit_rather_than_a_traceback(
        self, monkeypatch, capsys
    ):
        """main() already funnels exceptions into exit 2 — pin that it still does."""

        def fake_run(argv, **kwargs):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs["timeout"])

        monkeypatch.setattr(sync.subprocess, "run", fake_run)
        assert sync.main(["--verify-upstream"]) == 2
        assert sync.REPO_URL in capsys.readouterr().err

    def test_there_is_no_retry(self, monkeypatch):
        """A deploy-time tool fails with a message; it does not quietly try again.

        Asserted by counting attempts rather than by grepping _git's source
        for loop keywords: a recursive re-call, a second subprocess.run in the
        except block, and `return _git(args) if proc.returncode else proc`
        all carry neither `for ` nor `while `, and a future docstring
        containing either word would have failed a passing implementation.
        """
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv)
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs["timeout"])

        monkeypatch.setattr(sync.subprocess, "run", fake_run)
        with pytest.raises(RuntimeError):
            sync._git(["fetch", "--depth", "1", "origin", sync.PINNED_REF])
        assert len(calls) == 1, calls

    def test_the_ceiling_is_overridable_without_editing_the_file(self, monkeypatch):
        """The ceiling fires inside `docker build` and deploy/deploy.sh, where
        raising the constant in the source means rebuilding the thing that is
        timing out. A slow-but-working link that used to finish is the one
        regression direction a ceiling has, so the escape hatch has to reach
        the place the failure happens.
        """
        monkeypatch.setenv("GCS_GIT_TIMEOUT", "1800")
        assert _load_module().GIT_TIMEOUT_SECONDS == 1800

        monkeypatch.delenv("GCS_GIT_TIMEOUT")
        assert _load_module().GIT_TIMEOUT_SECONDS == 600

    def test_a_garbage_override_is_refused_rather_than_silently_ignored(
        self, monkeypatch
    ):
        """Falling back to the default would hand back the hang the ceiling
        exists to bound, with the operator believing they had raised it.
        """
        monkeypatch.setenv("GCS_GIT_TIMEOUT", "ten minutes")
        with pytest.raises(ValueError) as exc:
            _load_module()
        assert "GCS_GIT_TIMEOUT" in str(exc.value)

    def test_docker_build_can_actually_deliver_the_override(self):
        """The test above proves the module READS the variable. It cannot see
        whether the caller the escape hatch names can SEND it, and for a while
        the primary one could not: `docker build` does not inherit the host
        environment, so with no `ARG GCS_GIT_TIMEOUT` declared, both
        `GCS_GIT_TIMEOUT=1800 docker build .` and `--build-arg
        GCS_GIT_TIMEOUT=1800` changed nothing — on the one path that does the
        cold-cache ~201 MB fetch.

        Ordering matters as much as presence: an ARG only reaches RUN
        instructions after it in the same build stage.
        """
        dockerfile = (_TOOLS_SCRIPT.parent.parent / "Dockerfile").read_text(
            encoding="utf-8"
        )
        lines = dockerfile.splitlines()

        arg_at = [
            i
            for i, line in enumerate(lines)
            if line.strip().startswith("ARG GCS_GIT_TIMEOUT")
        ]
        assert arg_at, "Dockerfile declares no ARG GCS_GIT_TIMEOUT"

        run_at = [
            i
            for i, line in enumerate(lines)
            if "sync_gcs_library.py" in line and line.lstrip().startswith("RUN")
        ]
        assert run_at, "no RUN invokes sync_gcs_library.py"

        for run_line in run_at:
            earlier = [i for i in arg_at if i < run_line]
            assert earlier, f"ARG declared after the RUN on line {run_line + 1}"
            # ...and in the same stage: a FROM between them resets the ARG.
            assert not any(
                lines[i].startswith("FROM ") for i in range(max(earlier) + 1, run_line)
            ), "a FROM sits between the ARG and the RUN, which resets it"

        default = lines[arg_at[0]].split("=", 1)[1].strip()
        assert default == str(sync._GIT_TIMEOUT_DEFAULT), (
            f"Dockerfile default {default} != _GIT_TIMEOUT_DEFAULT "
            f"{sync._GIT_TIMEOUT_DEFAULT}"
        )
