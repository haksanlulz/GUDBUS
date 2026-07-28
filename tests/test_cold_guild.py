"""What a brand-new server experiences: every command, no data, nothing set up.

A stranger invites the bot into an empty guild and starts typing. Nothing has
been imported, no combat exists, no notes, no house rules. Every command they
reach in that state must *answer* — with a useful "you need to do X first" —
rather than raise and hand them the generic "Something went wrong", which reads
as a broken bot and is where a first impression dies.

This drives the real callbacks against a real empty database and asserts two
things per command: it did not raise, and it said something. It is deliberately
breadth-first rather than deep — the point is that no command is a trapdoor on
day one, not that each one is correct (the rest of the suite covers that).

Commands needing input this harness cannot synthesise are listed in
NEEDS_REAL_INPUT with the reason, so "not covered" stays visible instead of
quietly shrinking.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import pytest_asyncio
from discord import app_commands
from discord.ext import commands

from gurps_bot.bot import EXTENSIONS
from gurps_bot.db import notes as _n  # noqa: F401
from gurps_bot.db import study as _s  # noqa: F401
from gurps_bot.db import timers as _t  # noqa: F401
from gurps_bot.db import wealth as _w  # noqa: F401
from gurps_bot.db.models import Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

GUILD = 777_000
CHANNEL = 888_000
USER = 999_000

#: Commands this harness cannot drive, and why. Each is covered elsewhere.
#: Kept explicit so "not covered" stays visible rather than quietly shrinking —
#: a breadth test whose exemption list grows silently is worth very little.
NEEDS_REAL_INPUT = {
    "char import": "takes a discord.Attachment; covered by test_parser + import tests",
    "sync": "owner-gated; covered by test_command_sync",
    "status": "formats live gateway latency and uptime off the real client",
    "combat start": "stores the tracker message id from a real Discord message",
}


@pytest_asyncio.fixture
async def empty_db():
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    await eng.dispose()


@pytest_asyncio.fixture
async def tree():
    import sys

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    # Capture the module OBJECTS, not just the names. Bot.close() unloads every
    # extension and unload_extension pops them from sys.modules; re-importing
    # afterwards restores the names but builds NEW module objects, so anything
    # that already holds the old ones — a test that imported a class at
    # collection time, then patches "gurps_bot.cogs.x.log" by string — ends up
    # patching a different module than the code runs in. That is the knockdown
    # bug from earlier today, and this fixture reproduced it in nine
    # error-handler tests. Putting the same objects back avoids it entirely.
    preserved = {ext: sys.modules[ext] for ext in EXTENSIONS if ext in sys.modules}
    try:
        for ext in EXTENSIONS:
            await bot.load_extension(ext)
        # The real bot builds this in setup_hook and the reference cogs read it
        # as bot.reference. Building it here rather than mocking it keeps the
        # lookups exercising real catalog code on an empty guild.
        from gurps_bot.services.reference import get_reference_index

        bot.reference = get_reference_index()
        yield bot
    finally:
        await bot.close()
        sys.modules.update(preserved)


def _all_commands(bot) -> list[tuple[str, app_commands.Command]]:
    found = []
    for cmd in bot.tree.get_commands():
        if isinstance(cmd, app_commands.Group):
            for sub in cmd.commands:
                found.append((f"{cmd.name} {sub.name}", sub))
        else:
            found.append((cmd.name, cmd))
    return found


def _interaction(session_factory):
    it = MagicMock()
    it.guild_id = GUILD
    it.channel_id = CHANNEL
    it.user.id = USER
    it.user.display_name = "Newcomer"
    it.response.send_message = AsyncMock()
    it.response.defer = AsyncMock()
    it.response.is_done.return_value = False
    it.followup.send = AsyncMock()
    it.original_response = AsyncMock(return_value=MagicMock())
    it.client.db = session_factory
    it.client.is_owner = AsyncMock(return_value=True)
    return it


def _dummy_args(cmd) -> dict:
    """Plausible values so a command can actually be invoked.

    Choice-constrained parameters take a REAL declared choice rather than a
    made-up string — otherwise the command rejects the input and the test
    measures the harness's imagination instead of the cold-guild path.
    """
    declared = {p.name: p for p in cmd.parameters}
    args = {}
    sig = inspect.signature(cmd.callback)
    for name, param in list(sig.parameters.items())[2:]:  # skip self, interaction
        if param.default is not inspect.Parameter.empty:
            continue  # optional — the bare form is what a newcomer types first
        spec = declared.get(name)
        if spec is not None and spec.choices:
            args[name] = spec.choices[0].value
            continue
        text = str(param.annotation)
        if "int" in text and "Interaction" not in text:
            args[name] = 1
        elif "float" in text:
            args[name] = 1.0
        elif "bool" in text:
            args[name] = False
        else:
            args[name] = "test"
    return args


def _said_something(it) -> bool:
    return bool(
        it.response.send_message.await_args_list
        or it.followup.send.await_args_list
        or it.response.send_modal.await_args_list
    )


class TestNoCommandIsATrapdoorOnDayOne:
    async def test_every_command_answers_with_no_data(self, tree, empty_db):
        skipped, failures, silent, check_failed, driven = [], [], [], [], 0

        for name, cmd in _all_commands(tree):
            if name in NEEDS_REAL_INPUT:
                skipped.append(name)
                continue
            it = _interaction(empty_db)
            cog = cmd.binding
            try:
                await cmd.callback(cog, it, **_dummy_args(cmd))
            except app_commands.AppCommandError:
                # A check failing is a real, handled answer — the error handler
                # turns it into a message. Not a trapdoor. Counted, because a
                # branch that skips the assertions is how this test would go
                # quietly vacuous.
                check_failed.append(f"/{name}")
                continue
            except Exception as e:  # noqa: BLE001 — the whole point
                failures.append(f"/{name}: {type(e).__name__}: {e}")
                continue
            driven += 1
            if not _said_something(it):
                silent.append(f"/{name}")

        assert not failures, (
            f"{len(failures)} command(s) raised on an empty guild — a newcomer "
            f"sees 'Something went wrong':\n  " + "\n  ".join(failures)
        )
        assert not silent, (
            f"{len(silent)} command(s) returned without saying anything, which "
            f"Discord shows as a failed interaction:\n  " + "\n  ".join(silent)
        )
        # Floor, not an exact count: this passing while driving almost nothing
        # is the failure mode a green breadth test hides. If the harness stops
        # being able to invoke commands, that is a bug in the harness and this
        # says so instead of reporting success over an empty loop.
        assert driven >= 80, (
            f"only drove {driven} commands to completion "
            f"({len(check_failed)} stopped at a check, {len(skipped)} exempt) "
            "— the harness has stopped exercising the surface it claims to"
        )

    def test_the_uncovered_list_stays_honest(self, tree):
        """Every exemption names a real command, so the list cannot rot."""
        live = {name for name, _ in _all_commands(tree)}
        stale = set(NEEDS_REAL_INPUT) - live
        assert not stale, f"NEEDS_REAL_INPUT names dead commands: {sorted(stale)}"


class TestTheFirstThingsAStrangerTypes:
    """The specific paths a newcomer hits, asserted on content not just shape."""

    async def _run(self, tree, empty_db, name: str, **kwargs):
        cmd = dict(_all_commands(tree))[name]
        it = _interaction(empty_db)
        await cmd.callback(cmd.binding, it, **kwargs)
        parts = []
        for mock in (it.response.send_message, it.followup.send):
            for call in mock.await_args_list:
                parts += [str(a) for a in call.args]
                for k, v in call.kwargs.items():
                    if k == "embed" and v is not None:
                        parts += [str(v.title), str(v.description)]
                        parts += [f"{f.name} {f.value}" for f in v.fields]
        return "\n".join(parts)

    async def test_help_works_before_anything_else_does(self, tree, empty_db):
        text = await self._run(tree, empty_db, "help")
        assert "Quick start" in text
        assert "char import" in text, "the first step is not in the quick start"

    async def test_check_without_a_character_points_at_import(
        self, tree, empty_db
    ):
        text = await self._run(tree, empty_db, "check", target="Broadsword")
        assert "/char import" in text, (
            f"a newcomer's first /check must say what to do; got: {text!r}"
        )

    async def test_roll_works_with_no_setup_at_all(self, tree, empty_db):
        """The one command that should never need anything."""
        text = await self._run(tree, empty_db, "roll", dice="3d6")
        assert text.strip(), "/roll said nothing"

    async def test_combat_commands_say_there_is_no_combat(self, tree, empty_db):
        text = await self._run(tree, empty_db, "combat status", target="x", effect="Stunned")
        assert "No active combat" in text
