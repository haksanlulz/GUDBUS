"""`@<bot> admin ...`: owner-gated text commands that act on the TARGET user's rows.

Each subcommand is driven through its callback with a fake Context, the way
test_command_sync drives `@<bot> sync`. The gate is asserted on the commands' own check
list (``commands.is_owner``), and the assertions read the database, so a command that
silently acted on the caller instead of the target would fail here.
"""

from __future__ import annotations

import copy
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from discord.ext import commands
from sqlalchemy import select

from gurps_bot.cogs.admin_chars import AdminCharsCog
from gurps_bot.db.models import ActiveCharacter, Character

OWNER = 1
TARGET = 555
GUILD = 100
OTHER_GUILD = 777


@pytest_asyncio.fixture
async def session_factory(db_session):
    from gurps_bot.db.engine import get_session_factory

    return get_session_factory()


def _attachment(data: dict, filename: str = "hero.gcs"):
    raw = json.dumps(data).encode()
    file = MagicMock()
    file.filename = filename
    file.size = len(raw)
    file.read = AsyncMock(return_value=raw)
    return file


def _ctx(session_factory, *, owner: bool = True, attachments=()):
    ctx = MagicMock()
    ctx.author.id = OWNER
    ctx.guild.id = GUILD
    ctx.message.attachments = list(attachments)
    ctx.reply = AsyncMock(return_value=MagicMock())
    ctx.bot.is_owner = AsyncMock(return_value=owner)

    @asynccontextmanager
    async def db():
        async with session_factory() as s:
            yield s

    ctx.bot.db = db
    return ctx


def _user(uid: int = TARGET):
    user = MagicMock()
    user.id = uid
    user.mention = f"<@{uid}>"
    user.display_name = f"user-{uid}"
    return user


def _said(ctx) -> str:
    parts = []
    for call in ctx.reply.await_args_list:
        parts += [str(a) for a in call.args]
        embed = call.kwargs.get("embed")
        if embed is not None:
            parts.append(str(embed.title))
            parts.append(str(embed.description))
            parts += [str(f.value) for f in embed.fields]
    return "\n".join(parts)


def _sheet(sample, name: str, n: int = 1):
    d = copy.deepcopy(sample)
    d["id"] = f"id-{n}"
    d["profile"]["name"] = name
    return d


async def _rows(session_factory):
    async with session_factory() as s:
        chars = (await s.execute(select(Character))).scalars().all()
        active = (await s.execute(select(ActiveCharacter))).scalars().all()
    return [(c.discord_user_id, c.name) for c in chars], [(a.discord_user_id, a.guild_id, a.character_id) for a in active]


def _view(confirmed: bool | None):
    class View:
        def __init__(self, author_id: int, timeout: float = 30.0) -> None:
            self.author_id = author_id
            self.confirmed = confirmed
            self.message = None

        async def wait(self) -> None:
            return None

    return View


async def _import(session_factory, data, *, guild_id=None):
    cog = AdminCharsCog(MagicMock())
    ctx = _ctx(session_factory, attachments=[_attachment(data)])
    await AdminCharsCog.admin_import.callback(cog, ctx, _user(), guild_id)
    return ctx


class TestOwnerGate:
    """The gate is the framework check on every command, so a non-owner never reaches the
    callback; asserted on the check list itself, the way the framework runs it."""

    @pytest.mark.parametrize("cmd", [
        AdminCharsCog.admin, AdminCharsCog.admin_list, AdminCharsCog.admin_import,
        AdminCharsCog.admin_switch, AdminCharsCog.admin_delete,
    ])
    async def test_every_command_carries_the_owner_check(self, session_factory, cmd):
        assert cmd.checks, f"{cmd.qualified_name} has no checks at all"
        ctx = _ctx(session_factory, owner=False)
        with pytest.raises(commands.NotOwner):
            for check in cmd.checks:
                await check(ctx)
        ctx = _ctx(session_factory, owner=True)
        for check in cmd.checks:
            assert await check(ctx)

    def test_nothing_is_registered_as_a_slash_command(self):
        """The whole point: no entry in anyone's picker."""
        from discord import app_commands

        cog = AdminCharsCog(MagicMock())
        assert cog.get_app_commands() == []
        assert not isinstance(cog, commands.GroupCog)
        assert not any(isinstance(c, app_commands.Command) for c in vars(AdminCharsCog).values())


class TestImportForAnotherMember:
    async def test_the_sheet_lands_under_the_target_and_is_their_active_one(self, session_factory, sample_gcs_data):
        ctx = await _import(session_factory, _sheet(sample_gcs_data, "Hero"))
        assert "Hero" in _said(ctx) and f"<@{TARGET}>" in _said(ctx)
        chars, active = await _rows(session_factory)
        assert chars == [(TARGET, "Hero")]
        assert [(u, g) for u, g, _ in active] == [(TARGET, GUILD)]

    async def test_a_server_id_aims_the_active_mark_elsewhere(self, session_factory, sample_gcs_data):
        await _import(session_factory, _sheet(sample_gcs_data, "Hero"), guild_id=OTHER_GUILD)
        _, active = await _rows(session_factory)
        assert [(u, g) for u, g, _ in active] == [(TARGET, OTHER_GUILD)]

    async def test_no_attachment_is_told_what_to_attach(self, session_factory):
        cog = AdminCharsCog(MagicMock())
        ctx = _ctx(session_factory)
        await AdminCharsCog.admin_import.callback(cog, ctx, _user(), None)
        assert "Attach" in _said(ctx)
        chars, _ = await _rows(session_factory)
        assert chars == []

    async def test_the_upload_prechecks_apply(self, session_factory, sample_gcs_data):
        cog = AdminCharsCog(MagicMock())
        ctx = _ctx(session_factory, attachments=[_attachment(_sheet(sample_gcs_data, "Hero"), "hero.txt")])
        await AdminCharsCog.admin_import.callback(cog, ctx, _user(), None)
        assert ".gcs" in _said(ctx)
        chars, _ = await _rows(session_factory)
        assert chars == []


class TestListSwitchDelete:
    async def _seed_two(self, session_factory, sample_gcs_data):
        await _import(session_factory, _sheet(sample_gcs_data, "Hero", 1))
        await _import(session_factory, _sheet(sample_gcs_data, "Villain", 2))

    async def test_list_names_the_targets_characters(self, session_factory, sample_gcs_data):
        await self._seed_two(session_factory, sample_gcs_data)
        cog = AdminCharsCog(MagicMock())
        ctx = _ctx(session_factory)
        await AdminCharsCog.admin_list.callback(cog, ctx, _user(), None)
        said = _said(ctx)
        assert "Hero" in said and "Villain" in said and f"user-{TARGET}" in said

    async def test_switch_moves_the_targets_active_mark(self, session_factory, sample_gcs_data):
        await self._seed_two(session_factory, sample_gcs_data)   # Villain is active after the second import
        cog = AdminCharsCog(MagicMock())
        ctx = _ctx(session_factory)
        await AdminCharsCog.admin_switch.callback(cog, ctx, _user(), None, name="Hero")
        assert "Switched" in _said(ctx)
        _, active = await _rows(session_factory)
        async with session_factory() as s:
            hero_id = await s.scalar(select(Character.id).where(Character.name == "Hero"))
        assert active == [(TARGET, GUILD, hero_id)]

    async def test_switch_to_an_unknown_name_says_so(self, session_factory, sample_gcs_data):
        await self._seed_two(session_factory, sample_gcs_data)
        cog = AdminCharsCog(MagicMock())
        ctx = _ctx(session_factory)
        await AdminCharsCog.admin_switch.callback(cog, ctx, _user(), None, name="Nobody")
        assert "no character named" in _said(ctx)

    async def test_delete_confirmed_removes_the_targets_row_only(self, session_factory, sample_gcs_data):
        await self._seed_two(session_factory, sample_gcs_data)
        cog = AdminCharsCog(MagicMock())
        ctx = _ctx(session_factory)
        with patch("gurps_bot.cogs.admin_chars.ConfirmView", _view(True)):
            await AdminCharsCog.admin_delete.callback(cog, ctx, _user(), name="Hero")
        assert "Deleted" in _said(ctx)
        chars, _ = await _rows(session_factory)
        assert chars == [(TARGET, "Villain")]

    async def test_delete_cancelled_keeps_the_row(self, session_factory, sample_gcs_data):
        await self._seed_two(session_factory, sample_gcs_data)
        cog = AdminCharsCog(MagicMock())
        ctx = _ctx(session_factory)
        with patch("gurps_bot.cogs.admin_chars.ConfirmView", _view(False)):
            await AdminCharsCog.admin_delete.callback(cog, ctx, _user(), name="Hero")
        chars, _ = await _rows(session_factory)
        assert sorted(n for _, n in chars) == ["Hero", "Villain"]
