"""deploy/backup-db.sh — the fallback ladder must never degrade to cp.

The original script fell back to `cp` when sqlite3 was missing and printed
success — not WAL-safe on a live database, and the Docker image ships no
sqlite3 CLI, so every containerized run took exactly that branch. The ladder
is now sqlite3 -> python3 (same online-backup API) -> refuse with exit 1.

Tools are named through SQLITE3_BIN / PYTHON3_BIN rather than stubbed on
PATH: Git Bash on Windows prepends its own bin dir ahead of the caller's,
so a PATH stub is silently ignored there (the lesson test_nas_update.py
learned with curl).
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "backup-db.sh"
# sh first: on Windows shutil.which("bash") finds WSL's system32 bash, which
# cannot take Windows paths; Git Bash's sh.exe can (same order as
# test_nas_update.py).
SHELL = shutil.which("sh") or shutil.which("bash")

pytestmark = pytest.mark.skipif(
    SHELL is None, reason="no POSIX shell available to run the backup script"
)


def _make_db(root: Path) -> Path:
    db = root / "data" / "gurps_bot.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE marker (v TEXT)")
    conn.execute("INSERT INTO marker VALUES ('survives-backup')")
    conn.commit()
    conn.close()
    return db


def _run(cwd: Path, **env_overrides: str) -> subprocess.CompletedProcess:
    # The script cd's to its parent's parent, so give it a fake project root
    # with deploy/backup-db.sh inside.
    deploy = cwd / "deploy"
    deploy.mkdir(exist_ok=True)
    script = deploy / "backup-db.sh"
    script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    import os

    env = dict(os.environ)
    env.update(env_overrides)
    return subprocess.run(
        [SHELL, str(script)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_python3_branch_produces_a_real_openable_backup(tmp_path):
    """No sqlite3 -> python3 branch; the backup must reopen with data intact."""
    _make_db(tmp_path)
    result = _run(
        tmp_path,
        SQLITE3_BIN="definitely-not-a-real-tool",
        PYTHON3_BIN=sys.executable,
    )
    assert result.returncode == 0, result.stderr
    backups = list((tmp_path / "backups").glob("gurps_bot-*.db"))
    assert len(backups) == 1
    conn = sqlite3.connect(backups[0])
    rows = conn.execute("SELECT v FROM marker").fetchall()
    conn.close()
    assert rows == [("survives-backup",)]


def test_no_tool_at_all_refuses_instead_of_cp(tmp_path):
    """Neither tool -> exit 1, no backup file, and it says why."""
    _make_db(tmp_path)
    result = _run(
        tmp_path,
        SQLITE3_BIN="definitely-not-a-real-tool",
        PYTHON3_BIN="also-not-a-real-tool",
    )
    assert result.returncode == 1
    assert "refusing" in result.stderr
    backups = list((tmp_path / "backups").glob("gurps_bot-*.db"))
    assert backups == [], "refusal must not leave a half-made backup behind"


def test_sqlite3_branch_is_preferred_and_gets_backup_argv(tmp_path):
    """sqlite3 present -> it is used, with the .backup command, not a copy."""
    _make_db(tmp_path)
    log = tmp_path / "sqlite3.log"
    stub = tmp_path / "sqlite3-stub"
    # Faithful stub: real sqlite3 .backup writes the output file, and the
    # prune step's glob relies on that — a write-nothing stub trips pipefail
    # on `ls` and fails the script for a reason the real tool can't produce.
    stub.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$SQLITE3_LOG"\n'
        "mkdir -p backups && touch backups/gurps_bot-stub.db\n"
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    result = _run(
        tmp_path,
        SQLITE3_BIN=str(stub),
        PYTHON3_BIN="also-not-a-real-tool",
        SQLITE3_LOG=str(log),
    )
    assert result.returncode == 0, result.stderr
    logged = log.read_text(encoding="utf-8")
    assert ".backup" in logged, "sqlite3 must be invoked with .backup"


def test_missing_db_is_a_clean_noop(tmp_path):
    """No database yet -> exit 0 and say so (cron runs before first boot)."""
    result = _run(tmp_path)
    assert result.returncode == 0
    assert "nothing to back up" in result.stdout
