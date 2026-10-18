"""/admin at the command surface: owner-gated, acts on the TARGET user's rows.

Each command is driven through its callback with a fake interaction, the same way
test_char_import_cog drives /char import. The assertions read the database, so a
command that silently acted on the caller instead of the target would fail here.
"""

from __future__ import annotations

import copy
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from sqlalchemy import select

from gurps_bot.cogs.admin_chars import AdminGroup
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


def _interaction(session_factory, *, owner: bool = True):
    interaction = MagicMock()
    interaction.guild_id = GUILD
    interaction.user.id = OWNER
    interaction.client.is_owner = AsyncMock(return_value=owner)
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.original_response = AsyncMock()

    @asynccontextmanager
    async def db():
        async with session_factory() as s:
            yield s

    interaction.client.db = db
    return interaction


def _user(uid: int = TARGET):
    user = MagicMock()
    user.id = uid
    user.mention = f"<@{uid}>"
    user.display_name = f"user-{uid}"
    return user


def _said(interaction) -> str:
    parts = []
    for mock in (interaction.response.send_message, interaction.followup.send):
        for call in mock.await_args_list:
            parts += [str(a) for a in call.args]
            if call.kwargs.get("content"):
                parts.append(call.kwargs["content"])
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


async def _import(session_factory, data, *, owner=True, guild_id=None):
    cog = AdminGroup(MagicMock())
    interaction = _interaction(session_factory, owner=owner)
    await cog.import_char.callback(cog, interaction, _user(), _attachment(data), guild_id)
    return interaction


class TestOwnerGate:
    async def test_a_non_owner_is_refused_and_nothing_is_written(self, session_factory, sample_gcs_data):
        interaction = await _import(session_factory, _sheet(sample_gcs_data, "Hero"), owner=False)
        assert "Only the bot owner" in _said(interaction)
        chars, active = await _rows(session_factory)
        assert chars == [] and active == []

    async def test_every_subcommand_is_gated(self, session_factory):
        cog = AdminGroup(MagicMock())
        for call in (
            lambda i: cog.list_chars.callback(cog, i, _user(), None),
            lambda i: cog.switch.callback(cog, i, _user(), "Hero", None),
            lambda i: cog.delete_char.callback(cog, i, _user(), "Hero"),
        ):
            interaction = _interaction(session_factory, owner=False)
            await call(interaction)
            assert "Only the bot owner" in _said(interaction)


class TestImportForAnotherMember:
    async def test_the_sheet_lands_under_the_target_and_is_their_active_one(self, session_factory, sample_gcs_data):
        interaction = await _import(session_factory, _sheet(sample_gcs_data, "Hero"))
        assert "Hero" in _said(interaction) and f"<@{TARGET}>" in _said(interaction)
        chars, active = await _rows(session_factory)
        assert chars == [(TARGET, "Hero")]
        assert [(u, g) for u, g, _ in active] == [(TARGET, GUILD)]

    async def test_a_server_id_aims_the_active_mark_elsewhere(self, session_factory, sample_gcs_data):
        await _import(session_factory, _sheet(sample_gcs_data, "Hero"), guild_id=str(OTHER_GUILD))
        _, active = await _rows(session_factory)
        assert [(u, g) for u, g, _ in active] == [(TARGET, OTHER_GUILD)]

    async def test_a_malformed_server_id_is_refused_before_anything_runs(self, session_factory, sample_gcs_data):
        interaction = await _import(session_factory, _sheet(sample_gcs_data, "Hero"), guild_id="not-an-id")
        assert "server id" in _said(interaction)
        chars, _ = await _rows(session_factory)
        assert chars == []


class TestListSwitchDelete:
    async def _seed_two(self, session_factory, sample_gcs_data):
        await _import(session_factory, _sheet(sample_gcs_data, "Hero", 1))
        await _import(session_factory, _sheet(sample_gcs_data, "Villain", 2))

    async def test_list_names_the_targets_characters(self, session_factory, sample_gcs_data):
        await self._seed_two(session_factory, sample_gcs_data)
        cog = AdminGroup(MagicMock())
        interaction = _interaction(session_factory)
        await cog.list_chars.callback(cog, interaction, _user(), None)
        said = _said(interaction)
        assert "Hero" in said and "Villain" in said and f"user-{TARGET}" in said

    async def test_switch_moves_the_targets_active_mark(self, session_factory, sample_gcs_data):
        await self._seed_two(session_factory, sample_gcs_data)   # Villain is active after the second import
        cog = AdminGroup(MagicMock())
        interaction = _interaction(session_factory)
        await cog.switch.callback(cog, interaction, _user(), "Hero", None)
        assert "Switched" in _said(interaction)
        _, active = await _rows(session_factory)
        async with session_factory() as s:
            hero_id = await s.scalar(select(Character.id).where(Character.name == "Hero"))
        assert active == [(TARGET, GUILD, hero_id)]

    async def test_switch_to_an_unknown_name_says_so(self, session_factory, sample_gcs_data):
        await self._seed_two(session_factory, sample_gcs_data)
        cog = AdminGroup(MagicMock())
        interaction = _interaction(session_factory)
        await cog.switch.callback(cog, interaction, _user(), "Nobody", None)
        assert "no character named" in _said(interaction)

    async def test_delete_confirmed_removes_the_targets_row_only(self, session_factory, sample_gcs_data):
        await self._seed_two(session_factory, sample_gcs_data)
        cog = AdminGroup(MagicMock())
        interaction = _interaction(session_factory)
        with patch("gurps_bot.cogs.admin_chars.ConfirmView", _view(True)):
            await cog.delete_char.callback(cog, interaction, _user(), "Hero")
        assert "Deleted" in _said(interaction)
        chars, _ = await _rows(session_factory)
        assert chars == [(TARGET, "Villain")]

    async def test_delete_cancelled_keeps_the_row(self, session_factory, sample_gcs_data):
        await self._seed_two(session_factory, sample_gcs_data)
        cog = AdminGroup(MagicMock())
        interaction = _interaction(session_factory)
        with patch("gurps_bot.cogs.admin_chars.ConfirmView", _view(False)):
            await cog.delete_char.callback(cog, interaction, _user(), "Hero")
        chars, _ = await _rows(session_factory)
        assert sorted(n for _, n in chars) == ["Hero", "Villain"]
