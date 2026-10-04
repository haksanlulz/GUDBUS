"""Logs carry IDs, not what users typed.

PRIVACY.md says routine logs record IDs and command names only. A log call
that formats a character name, a timer label or a note title breaks that, so
every logging call's arguments are scanned for the fields that hold user text.
Error logs go through the error handler's redaction instead and are not
scanned here.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "gurps_bot"

#: Names that hold text a user typed, as a variable or an attribute.
_USER_TEXT = frozenset({
    "name", "label", "title", "body", "note", "notes", "character_name",
    "expression", "tags", "query",
})

_LOG_METHODS = frozenset({"debug", "info", "warning", "error", "exception", "critical"})

#: Call sites allowed to log one of those names, and why.
_ALLOWED: dict[str, str] = {}


def _user_text_args(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in _LOG_METHODS:
            continue
        receiver = node.func.value
        if not (isinstance(receiver, ast.Name) and receiver.id in {"log", "logger"}):
            continue
        for arg in node.args[1:]:
            # `note.id` logs an id: a name that is only the object an attribute
            # is read from is not itself logged.
            bases = {
                id(sub.value) for sub in ast.walk(arg) if isinstance(sub, ast.Attribute)
            }
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Attribute):
                    ident = sub.attr
                elif isinstance(sub, ast.Name) and id(sub) not in bases:
                    ident = sub.id
                else:
                    continue
                if ident in _USER_TEXT:
                    hits.append(f"{path.name}:{node.lineno} logs {ident}")
    return hits


def test_the_scan_sees_the_package():
    assert len(list(PACKAGE_ROOT.rglob("*.py"))) >= 30


def test_the_scan_catches_a_planted_name(tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import logging\nlog = logging.getLogger(__name__)\n"
        "def f(char):\n    log.info('Importing %s', char.name)\n",
        encoding="utf-8",
    )
    assert _user_text_args(planted) == ["planted.py:4 logs name"]


def test_an_id_read_off_a_user_text_object_is_fine(tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import logging\nlog = logging.getLogger(__name__)\n"
        "def f(note, label):\n    log.info('note %d', note.id)\n"
        "    log.info('timer %s', label)\n",
        encoding="utf-8",
    )
    assert _user_text_args(planted) == ["planted.py:5 logs label"]


def test_no_log_call_formats_user_text():
    hits = [
        hit for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        for hit in _user_text_args(path)
        if hit.split(" logs ")[0] not in _ALLOWED
    ]
    assert not hits, (
        "log calls formatting user-typed text (PRIVACY.md promises IDs only):\n"
        + "\n".join(hits)
    )
