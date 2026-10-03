"""/char import at the command surface — it had no test above the service.

Drives the real command with a fake attachment, so the cap, the rename-onto-
a-taken-name refusal and the size guard are checked where users meet them.
"""

from __future__ import annotations

import copy
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio

from gurps_bot.cogs.characters import MAX_IMPORT_SIZE, CharGroup

USER = 555


@pytest_asyncio.fixture
async def session_factory(db_session):
    # db_session initialises the shared in-memory engine; hand out its factory
    from gurps_bot.db.engine import get_session_factory

    return get_session_factory()


def _attachment(data: dict, filename: str = "hero.gcs"):
    raw = json.dumps(data).encode()
    file = MagicMock()
    file.filename = filename
    file.size = len(raw)
    file.read = AsyncMock(return_value=raw)
    return file


def _interaction(session_factory):
    interaction = MagicMock()
    interaction.guild_id = 100
    interaction.user.id = USER
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    @asynccontextmanager
    async def db():
        async with session_factory() as s:
            yield s

    interaction.client.db = db
    return interaction


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
    return "\n".join(parts)


def _sheet(sample, n, name=None):
    d = copy.deepcopy(sample)
    d["id"] = f"id-{n}"
    d["profile"]["name"] = name or f"Hero {n}"
    return d


async def _import(session_factory, data):
    cog = CharGroup(MagicMock())
    interaction = _interaction(session_factory)
    await cog.import_char.callback(cog, interaction, _attachment(data))
    return _said(interaction)


class TestImportAtTheCommand:
    async def test_a_fresh_import_is_confirmed(self, session_factory, sample_gcs_data):
        said = await _import(session_factory, _sheet(sample_gcs_data, 1))
        assert "Hero 1" in said

    async def test_a_renamed_reimport_at_the_cap_goes_through(
        self, session_factory, sample_gcs_data, monkeypatch
    ):
        from gurps_bot.services import characters as svc

        monkeypatch.setattr(svc, "MAX_CHARACTERS_PER_USER", 2)
        for n in range(2):
            await _import(session_factory, _sheet(sample_gcs_data, n))
        said = await _import(session_factory, _sheet(sample_gcs_data, 0, "Hero Zero II"))
        assert "Hero Zero II" in said
        assert "Delete" not in said

    async def test_a_new_character_at_the_cap_is_told_why(
        self, session_factory, sample_gcs_data, monkeypatch
    ):
        from gurps_bot.services import characters as svc

        monkeypatch.setattr(svc, "MAX_CHARACTERS_PER_USER", 2)
        for n in range(2):
            await _import(session_factory, _sheet(sample_gcs_data, n))
        said = await _import(session_factory, _sheet(sample_gcs_data, 9))
        assert "maximum 2" in said

    async def test_renaming_onto_a_taken_name_is_explained(
        self, session_factory, sample_gcs_data
    ):
        for n in range(2):
            await _import(session_factory, _sheet(sample_gcs_data, n))
        said = await _import(session_factory, _sheet(sample_gcs_data, 0, "Hero 1"))
        assert "already have a character named" in said

    async def test_an_oversized_file_is_refused_before_download(self, session_factory):
        cog = CharGroup(MagicMock())
        interaction = _interaction(session_factory)
        file = _attachment({"version": 5})
        file.size = MAX_IMPORT_SIZE + 1
        await cog.import_char.callback(cog, interaction, file)
        file.read.assert_not_awaited()
        assert "too large" in _said(interaction)
