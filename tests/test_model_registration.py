"""Every model module must be eager-imported, or its table silently never exists.

Found 2026-08-09 while adding the crafting tables. `gurps_bot/db/__init__.py`
eager-imports the model modules so their tables reach `Base.metadata` before
`create_all` runs, and the new module was not on that line. The result on a
brand-new database:

* `create_all` built the 14 tables it could see;
* the fresh DB was then STAMPED at Alembic head, which asserts that every
  migration — including the one creating the missing tables — has run;
* the startup gate compares revision to head, matches, and boots clean;
* `alembic upgrade head` has nothing left to do, ever;
* the only symptom is `no such table` when a command finally touches it.

A crash-loop is a better failure than this. The 2026-07-27 incident at least
stopped the container. This boots, serves every other command, and is
unrecoverable by the documented repair path.

⚠️ **These run in a SUBPROCESS, and that is the whole design.** `Base.metadata`
is process-global and `sys.modules` is a cache: once any other test in the
session has imported `gurps_bot.db.crafting`, its table is registered forever
and an in-process check passes whether or not `db/__init__.py` mentions it.
The first draft of this file did exactly that and was green with the import
line broken — a Rule 22 fail-open, in the guard written to close a fail-open.
A clean interpreter is the only instrument that can read this.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Model modules live directly under `gurps_bot/db/`. These declare no tables,
#: so their absence from the eager-import line is correct.
_NOT_MODEL_MODULES = {"__init__", "bootstrap", "engine", "models", "migrations"}

#: Run in a fresh interpreter: import ONLY the package, the way the deploy path
#: and the startup gate do, then report what metadata ended up holding versus
#: what the modules on disk actually declare.
_PROBE = """
import importlib, json, pkgutil, sys

import gurps_bot.db                      # the ONLY import under test
from gurps_bot.db.models import Base

registered = sorted(Base.metadata.tables)

# Now — and only now, after the reading is taken — import everything on disk to
# find out what SHOULD have been there.
declared = {}
for info in pkgutil.iter_modules(gurps_bot.db.__path__):
    if info.name in %(skip)r:
        continue
    module = importlib.import_module("gurps_bot.db." + info.name)
    tables = [
        obj.__tablename__
        for obj in vars(module).values()
        if isinstance(obj, type)
        and issubclass(obj, Base)
        and obj is not Base
        and getattr(obj, "__tablename__", None)
    ]
    if tables:
        declared[info.name] = sorted(set(tables))

print(json.dumps({"registered": registered, "declared": declared}))
"""


def _probe(extra: str = "") -> dict:
    source = _PROBE % {"skip": _NOT_MODEL_MODULES}
    result = subprocess.run(
        [sys.executable, "-c", extra + source],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"probe failed:\n{result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_the_probe_sees_a_real_schema():
    """FAIL CLOSED: a probe returning nothing would pass everything below."""
    data = _probe()
    assert len(data["registered"]) >= 14, data["registered"]
    assert len(data["declared"]) >= 4, data["declared"]


def test_the_probe_can_detect_a_missing_module():
    """Verify the instrument before trusting its clean reading.

    Simulates the defect by hiding one model module from the import machinery,
    so a green result below means the import line is right rather than that the
    probe cannot see wrong.
    """
    # `find_spec`, not the `find_module`/`load_module` pair — that protocol was
    # removed in Python 3.12, so the legacy form is silently ignored and the
    # block never happens. Which would make this instrument-check itself the
    # fail-open it exists to rule out.
    hide = (
        "import sys\n"
        "class _Block:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'gurps_bot.db.crafting':\n"
        "            raise ImportError('blocked for the test')\n"
        "        return None\n"
        "sys.meta_path.insert(0, _Block())\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", hide + "import gurps_bot.db"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0, (
        "blocking a model module did not break the package import — the eager "
        "import line is not actually importing it, so this probe proves nothing"
    )


def test_importing_the_package_registers_every_declared_table():
    """The property that matters, read from a clean interpreter."""
    data = _probe()
    registered = set(data["registered"])

    missing: dict[str, list[str]] = {}
    for module, tables in data["declared"].items():
        absent = [t for t in tables if t not in registered]
        if absent:
            missing[module] = absent

    assert not missing, (
        f"table(s) not on Base.metadata after importing gurps_bot.db: {missing}.\n"
        "Add the module to the eager-import line in gurps_bot/db/__init__.py.\n"
        "Until then a fresh database is built WITHOUT those tables and then "
        "stamped at Alembic head — the schema claims to be current while the "
        "table does not exist, and no upgrade will ever fix it."
    )
