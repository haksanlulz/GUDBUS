"""Eager-imports every model module so its tables land on Base.metadata before Alembic/create_all runs.

⚠️ A module missing from this line fails OPEN and permanently. `create_all`
builds whatever metadata it can see and the fresh database is then STAMPED at
Alembic head — so the missing table is absent while the schema claims to be
current. The startup gate compares revision to head, matches, and boots clean;
`alembic upgrade head` has nothing to do; the failure surfaces only when a
command touches the table, and no upgrade will ever fix it. That is strictly
worse than the 2026-07-27 crash-loop, which at least crashed.

`tests/test_model_registration.py` asserts this list covers every model module
on disk, because a one-line import is exactly the kind of thing a new table
forgets.
"""

from gurps_bot.db import crafting, notes, study, timers, wealth  # noqa: F401
