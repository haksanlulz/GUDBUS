"""Wire the golden characterization harnesses into pytest.

tests/golden/{parser_golden.json,magic_golden.txt} had no covering test —
parser_golden.py --check and the golden_magic diff were manual steps, so
drift was invisible to `uv run python -m pytest` and to the deploy smoke
gate. These tests make the goldens earn their keep.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "tests" / "golden"

# tools/ is not a package — import the harness modules by path.
sys.path.insert(0, str(REPO_ROOT / "tools"))

import golden_magic  # noqa: E402
import parser_golden  # noqa: E402


class TestParserGolden:
    def test_parser_output_matches_frozen_golden(self):
        golden = json.loads(
            (GOLDEN_DIR / "parser_golden.json").read_text(encoding="utf-8")
        )
        assert parser_golden.derive() == golden, (
            "parse_gcs output drifted from tests/golden/parser_golden.json — "
            "intentional behavior change? Re-capture via "
            "`uv run python tools/parser_golden.py --capture` and say so in "
            "the commit."
        )


class TestMagicGolden:
    def test_magic_behavior_matches_frozen_golden(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            golden_magic.main()
        actual = buf.getvalue().splitlines()
        expected = (
            (GOLDEN_DIR / "magic_golden.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        # line-wise compare (not byte-wise) so checkout newline translation
        # can't fake a drift; content must match exactly.
        assert actual == expected, (
            "mechanics/magic.py behavior drifted from "
            "tests/golden/magic_golden.txt — intentional change? Re-capture "
            "via `uv run python tools/golden_magic.py > "
            "tests/golden/magic_golden.txt` and say so in the commit."
        )
