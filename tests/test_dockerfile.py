"""Dockerfile layer order: the reference-data clone must not follow `COPY . .`.

Vendoring ran after the whole source tree was copied in, so any source edit
invalidated its layer and every build re-cloned the pinned upstream library.
Its output depends only on tools/sync_gcs_library.py (stdlib-only; it holds
the pin), so it belongs in a layer fed by that one file.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def _builder_instructions() -> list[str]:
    stage = DOCKERFILE.split("AS runtime")[0]
    joined = re.sub(r"\\\n\s*", " ", stage)  # fold line continuations
    return [
        line.strip() for line in joined.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _index(pred) -> int:
    lines = _builder_instructions()
    hits = [i for i, line in enumerate(lines) if pred(line)]
    assert hits, "instruction not found in the builder stage"
    return hits[0]


def test_vendoring_runs_before_the_full_source_copy():
    vendor = _index(lambda s: s.startswith("RUN") and "sync_gcs_library.py" in s)
    full_copy = _index(lambda s: s.split() == ["COPY", ".", "."])
    assert vendor < full_copy


def test_the_vendoring_layer_is_fed_only_the_script():
    vendor = _index(lambda s: s.startswith("RUN") and "sync_gcs_library.py" in s)
    copies = [
        s for s in _builder_instructions()[:vendor]
        if s.startswith("COPY") and "--from" not in s
    ]
    assert copies[-1].split()[1] == "tools/sync_gcs_library.py"


def test_the_script_really_is_stdlib_only():
    """The layer runs it with the base image's python, before any project
    dependency or package is installed."""
    src = (ROOT / "tools" / "sync_gcs_library.py").read_text(encoding="utf-8")
    imports = {
        a or b
        for a, b in re.findall(r"^(?:from (\w+)[\w.]* import |import (\w+))", src, flags=re.M)
    }
    assert "gurps_bot" not in imports
    assert imports <= {
        "__future__", "argparse", "datetime", "re", "shutil", "subprocess",
        "sys", "tempfile", "pathlib", "json", "os", "hashlib",
    }, imports


def test_the_local_vendored_copy_stays_out_of_the_context():
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "gurps_bot/data/gcs_library/" in ignore
