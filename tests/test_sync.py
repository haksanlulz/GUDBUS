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
