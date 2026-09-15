"""README claims that can rot are pinned to the artifacts they describe.

The headline said "94 slash commands" while the tree served 97 — nothing
coupled the number to the tree, so it aged silently every time a command
landed. The count definition is _tree_descriptions' (top-level commands plus
one level of group subcommands), the same enumeration /help audits itself
against.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest_asyncio

from gurps_bot.cogs.help import _tree_descriptions

README = Path(__file__).resolve().parent.parent / "README.md"


@pytest_asyncio.fixture
async def tree():
    # Bot.close() pops the cog modules out of sys.modules; loaded_bot() owns
    # putting the same objects back (see test_extensions_load for the story).
    from tests.test_extensions_load import loaded_bot

    async with loaded_bot() as bot:
        yield bot.tree


async def test_readme_command_count_matches_the_live_tree(tree):
    live = len(_tree_descriptions(tree))
    text = README.read_text(encoding="utf-8")
    m = re.search(r"(\d+) slash commands", text)
    assert m, "README no longer states the slash-command count"
    stated = int(m.group(1))
    assert stated == live, (
        f"README says {stated} slash commands, the tree serves {live} — "
        "update the README headline."
    )


# The Commands section's table. Anchored on the leading `| \`/` so it spans only
# rows naming a slash command: no other table in the README opens a cell with a
# backticked slash-path, and one that did (a config table, a file listing)
# would not match this shape.
_COMMAND_ROW = re.compile(r"^\| `(/[^`]+)`", re.M)


def _table_commands() -> list[str]:
    return _COMMAND_ROW.findall(README.read_text(encoding="utf-8"))


async def test_readme_command_table_matches_the_live_tree(tree):
    """The headline was pinned; the table under it was not, so it drifted.

    Three user-facing commands (`/campaign show`, `/campaign rule-of-14`,
    `/help`) were served, listed by `/help`, and absent from the table, while
    the count above it stayed green — the same rot this file exists to stop,
    one layer down.
    """
    live = {f"/{name}" for name in _tree_descriptions(tree)}
    rows = _table_commands()
    listed = set(rows)

    assert len(rows) == len(listed), (
        f"duplicate rows in the README command table: "
        f"{sorted({r for r in rows if rows.count(r) > 1})}"
    )
    assert listed == live, (
        f"README command table is out of date — missing {sorted(live - listed)}, "
        f"lists commands the tree does not serve {sorted(listed - live)}."
    )


async def test_the_table_and_the_headline_count_agree(tree):
    """Two claims about one number; if they can disagree, one of them is wrong."""
    text = README.read_text(encoding="utf-8")
    m = re.search(r"(\d+) slash commands", text)
    assert m, "README no longer states the slash-command count"
    assert int(m.group(1)) == len(_table_commands()), (
        "the README headline count and its own command table disagree"
    )
