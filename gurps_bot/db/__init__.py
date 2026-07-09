"""Eager-imports every model module so its tables land on Base.metadata before Alembic/create_all runs."""

from gurps_bot.db import study, notes, timers, wealth  # noqa: F401
