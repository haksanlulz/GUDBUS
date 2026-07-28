"""`/help` must describe the bot that exists, not the one it was written for.

Help text rots in one direction: commands change, the page does not, and it
goes on confidently describing something that no longer works that way. That is
worse than no help, because a newcomer trusts it.

Two properties keep it honest. The page never restates a command's description
— it reads them from the live tree — so the only thing that can drift is which
topic a command belongs to. And every command must be claimed by exactly one
topic or listed in UNTOPICED with a reason, so adding a command fails this
until someone decides where it goes.
"""

from __future__ import annotations

import discord
import pytest
import pytest_asyncio
from discord.ext import commands

from gurps_bot.bot import EXTENSIONS
from gurps_bot.cogs.help import TOPICS, UNTOPICED, HelpCog, _tree_descriptions


@pytest_asyncio.fixture
async def tree():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    try:
        for ext in EXTENSIONS:
            await bot.load_extension(ext)
        yield bot.tree
    finally:
        await bot.close()
        # Bot.close() unloads every extension, which pops the cog modules out
        # of sys.modules. Restore the same OBJECTS rather than re-importing —
        # re-importing restores the names but builds new modules, which is how
        # a patch and a call end up in two different ones (see
        # test_extensions_load._restore_extension_modules for the full story).
        from tests.test_extensions_load import _restore_extension_modules

        _restore_extension_modules()


def _topiced() -> set[str]:
    return {name for _, _, names in TOPICS.values() for name in names}


class TestEveryCommandIsAccountedFor:
    async def test_no_command_is_undocumented(self, tree):
        live = set(_tree_descriptions(tree))
        missing = live - _topiced() - set(UNTOPICED)
        assert not missing, (
            f"{len(missing)} command(s) belong to no /help topic: "
            f"{sorted(missing)}.\n"
            "Add each to a topic in cogs/help.py, or to UNTOPICED with the "
            "reason it is deliberately not shown."
        )

    async def test_help_mentions_no_command_that_does_not_exist(self, tree):
        live = set(_tree_descriptions(tree))
        phantom = _topiced() - live
        assert not phantom, (
            f"/help lists command(s) that do not exist: {sorted(phantom)}. "
            "A renamed or removed command has to be updated here too."
        )

    async def test_untopiced_entries_are_real_commands(self, tree):
        live = set(_tree_descriptions(tree))
        stale = set(UNTOPICED) - live
        assert not stale, (
            f"UNTOPICED names commands that no longer exist: {sorted(stale)}"
        )

    def test_every_topic_has_a_reason_and_commands(self):
        for key, (title, framing, names) in TOPICS.items():
            assert title and framing, f"topic {key} is missing its framing"
            assert names, f"topic {key} lists no commands"

    def test_cross_topic_duplicates_are_deliberate(self):
        """`start` is a curated overlap by design — it re-lists the four
        commands a newcomer needs, which necessarily live in other topics too.
        Any OTHER command in two topics is a filing mistake unless named here.
        """
        DELIBERATE = {"screen"}  # a GM tool that is also a reference lookup

        seen: dict[str, list[str]] = {}
        for key, (_, _, names) in TOPICS.items():
            for name in names:
                seen.setdefault(name, []).append(key)

        unexpected = {
            name: keys
            for name, keys in seen.items()
            if len(keys) > 1 and "start" not in keys and name not in DELIBERATE
        }
        assert not unexpected, (
            f"command(s) filed under two topics without a reason: {unexpected}. "
            "Pick one, or add it to DELIBERATE with why both apply."
        )


class TestTheLandingPageMatchesThePicker:
    """The overview must name topics the way Discord's dropdown does.

    Discord shows a choice's NAME; the embed used to list its VALUE, so the page
    said "/help start" while the picker offered "Getting started" — two
    vocabularies for one thing, and the one the embed taught never appeared on
    screen. Operator caught it on the deployed bot.
    """

    async def test_the_choice_names_are_the_topic_titles(self, tree):
        cmd = next(c for c in tree.get_commands() if c.name == "help")
        param = next(p for p in cmd.parameters if p.name == "topic")
        offered = {c.name for c in param.choices}
        titles = {title for title, _, _ in TOPICS.values()}
        assert offered == titles, (
            f"the picker offers {sorted(offered)} but the topics are "
            f"{sorted(titles)} — the two must agree or the overview cannot"
        )

    async def test_the_overview_lists_what_the_picker_shows(self):
        """Render the landing page and check it names titles, not raw keys."""
        from unittest.mock import AsyncMock, MagicMock

        from gurps_bot.cogs.help import HelpCog

        bot = MagicMock()
        bot.tree.get_commands.return_value = []
        interaction = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()

        await HelpCog(bot).help_cmd.callback(HelpCog(bot), interaction, None)
        embed = interaction.response.send_message.await_args.kwargs["embed"]
        topics_field = next(f for f in embed.fields if f.name == "Topics")

        for title, _, _ in TOPICS.values():
            assert title in topics_field.value, f"{title!r} missing from overview"
        for key in TOPICS:
            assert f"/help {key}" not in topics_field.value, (
                f"overview still cites the raw key {key!r}, which the picker "
                "never shows"
            )


class TestTheEntryPointReads:
    async def test_import_is_reachable_as_char_import(self, tree):
        """It moved out of the top level; the whole point was discoverability."""
        live = _tree_descriptions(tree)
        assert "char import" in live
        assert "import" not in live, "the old top-level /import still exists"

    async def test_quick_start_only_names_real_commands(self, tree):
        import re

        from gurps_bot.cogs.help import QUICK_START

        live = set(_tree_descriptions(tree))
        cited = set(re.findall(r"`/([a-z ]+?)`", QUICK_START))
        assert cited <= live, f"quick start cites missing: {sorted(cited - live)}"


class TestRendering:
    @pytest.mark.parametrize("topic", sorted(TOPICS))
    async def test_no_topic_field_exceeds_discords_limit(self, tree, topic):
        """A field over 1024 chars is dropped by Discord, silently."""
        descriptions = _tree_descriptions(tree)
        _, _, names = TOPICS[topic]
        lines = [f"`/{n}` — {descriptions[n]}" for n in names if n in descriptions]

        chunks, chunk, size = [], [], 0
        for line in lines:
            if size + len(line) + 1 > 1000 and chunk:
                chunks.append("\n".join(chunk))
                chunk, size = [], 0
            chunk.append(line)
            size += len(line) + 1
        if chunk:
            chunks.append("\n".join(chunk))

        for c in chunks:
            assert len(c) <= 1024, f"{topic}: a rendered field is {len(c)} chars"
