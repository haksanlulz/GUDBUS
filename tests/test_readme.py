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


# The worked session, which quotes bot output. Its prose names commands in
# backticks; a walkthrough naming a command the bot does not serve is worse
# than no walkthrough, and nothing else in the suite reads this section.
_SESSION_SECTION = re.compile(r"^## A session\n(.*?)(?=^## )", re.M | re.S)
_INLINE_COMMAND = re.compile(r"`(/[a-z][a-z0-9-]*(?: [a-z][a-z0-9-]*)?)`")


def _session_text() -> str:
    m = _SESSION_SECTION.search(README.read_text(encoding="utf-8"))
    assert m, "the README no longer carries a worked-session section"
    return m.group(1)


def _session_commands() -> set[str]:
    return set(_INLINE_COMMAND.findall(_session_text()))


async def test_the_worked_session_only_names_commands_that_exist(tree):
    live = {f"/{name}" for name in _tree_descriptions(tree)}
    named = _session_commands()
    assert named, "the session section names no commands at all"
    # Group parents (`/combat`) are real but are not themselves invocable, so
    # allow a name that is a prefix of a live subcommand.
    groups = {c.rsplit(" ", 1)[0] for c in live if " " in c}
    unknown = named - live - groups
    assert not unknown, f"the worked session names commands the tree does not serve: {sorted(unknown)}"


# The section's names and die faces are an example, but its message FORMATS
# claim to be the ones the bot emits. Command names alone were the only thing
# pinned, so a format-string edit anywhere below could leave the walkthrough
# quoting output the code no longer produces. These two renderings are the
# drift-prone ones: the tracker line and the shock line are both assembled
# from several moving pieces.


def test_the_worked_session_quotes_the_real_tracker_lines():
    from gurps_bot.ui.formatters import format_combatant_line

    text = _session_text()
    for name, speed, hp, hp_max, fp, fp_max, current in (
        ("Aldric", 5.75, 13, 13, 11, 11, True),
        ("Ogre", 4.5, 16, 25, 12, 12, False),
    ):
        line = format_combatant_line(
            name=name,
            basic_speed=speed,
            hp_current=hp,
            hp_max=hp_max,
            fp_current=fp,
            fp_max=fp_max,
            status_effects=[],
            maneuver=None,
            is_current=current,
            is_out=False,
        )
        assert line.strip() in text, line


def test_the_worked_session_quotes_the_real_shock_line():
    from gurps_bot.mechanics.injury import injury_effects

    # 9 injury on a 25-HP target: the -4 cap and the 2-HP-per-point scaling
    # that the prose beneath the quote explains.
    (shock,) = injury_effects(9, 25)
    assert shock in _session_text(), shock
