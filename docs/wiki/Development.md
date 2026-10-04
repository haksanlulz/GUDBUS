# Development

**Database migrations:**
```bash
# new migration after model changes
uv run python -m alembic revision --autogenerate -m "describe change"

# apply pending migrations
uv run python -m alembic upgrade head
```

Deploys run `uv run python -m gurps_bot.db.bootstrap` instead. It creates and
stamps a fresh database at head, upgrades a stamped one, and refuses with
instructions on an unstamped legacy one. Startup `create_all` builds a new
database at the current schema and stamps it automatically; `upgrade head`
only works on stamped databases (the initial migration assumes a pre-existing
schema).

**Dependencies:** Python 3.10+, discord.py 2.3+, SQLAlchemy 2.0+ (async), aiosqlite, rapidfuzz, Alembic.

## Testing

Layers and the test style each gets:

- `mechanics/`: pure functions, so every rule is a plain unit test with literal inputs and expected outputs.
- `services/` and integration tests: a real SQLite database through the async engine. No mocked sessions.
- `cogs/`: driven discord.py components (real cog callbacks, views, and modals over a faked interaction). The cog itself is never mocked.
- `db/`: bootstrap and migration paths run real Alembic against a file database.
- `ui/`: embed and formatter output asserted as payloads.

Run everything (about 80 s on a workstation):
```bash
uv run python -m pytest
```
Fast tier, which skips the `slow`, `integration`, and `load` markers:
```bash
uv run python -m pytest -m "not slow and not integration and not load"
```
Markers are declared in `pyproject.toml` under `[tool.pytest.ini_options]` with strict markers on, so a misspelled mark on a test fails collection instead of warning.

Counts, to the nearest thousand lines, pinned to the tree by `tests/test_readme.py`:
- application code: 24K lines (`find gurps_bot -name '*.py' | xargs cat | wc -l`)
- tests: 33K lines (`find tests -name '*.py' | xargs cat | wc -l`)

Rounded and pinned instead of exact and dated. The previous figures carried a
date, printed a tenth of a thousand, and were both wrong within days of being
written, sitting beside the commands that disprove them.

The collected-test total is deliberately left out. It moved on the very next
commit after it was written, and a stale number beside the command that
disproves it is worse than no number:

```bash
uv run python -m pytest --collect-only -q | tail -1
```

**Why so many tests.** The mechanics layer is pure: no I/O, no Discord, no database, so every GURPS rule the bot implements is checkable with a two-line test, and there are a lot of rules. The pins hold: mutating the natural-17 branch in `gurps_bot/mechanics/checks.py` turns exactly two tests red (`tests/test_checks.py::TestDetermineOutcome::test_crit_failure_on_17_when_target_15_or_less` and `::test_17_always_fails_even_at_high_skill`) and nothing else; removing the minimum-injury floor in `gurps_bot/mechanics/damage.py` turns exactly three red (`tests/test_damage.py::TestMinimumInjuryFloor::test_one_point_small_piercing_floors_to_1`, `::test_penetrating_after_dr_floors_to_1`, and `tests/test_injury_tolerance.py::TestInteractionWithLocationAndFloor::test_minimum_one_injury_floor_survives`).

Call-only wiring assertions (`assert_awaited()` with nothing said about the payload) were audited and pruned on 2026-09-11. Policy going forward: tests pin rules and regressions. Assert behavior and payloads, never bare invocation.
