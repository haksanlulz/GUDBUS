"""`/privacy delete-my-data`: confirm deletes, cancel deletes nothing, and every
reply stays private."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from sqlalchemy import func, select

from gurps_bot.db.engine import dispose_engine, get_session_factory, init_db, init_engine
from gurps_bot.db.models import Character, DiceMacro

USER = 42


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    init_engine(f"sqlite+aiosqlite:///{(tmp_path / 'privacy_cog.db').as_posix()}")
    await init_db()
    factory = get_session_factory()
    async with factory() as s:
        s.add(Character(discord_user_id=USER, name="Hero"))
        s.add(DiceMacro(discord_user_id=USER, name="sword", expression="2d+1"))
        await s.commit()
    yield factory
    await dispose_engine()


def _interaction(session_factory):
    interaction = MagicMock()
    interaction.user.id = USER
    interaction.guild_id = 100
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done.return_value = False
    interaction.original_response = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.client.db = session_factory
    return interaction


def _view(confirmed: bool | None):
    class _Stub:
        def __init__(self, author_id: int, timeout: float = 30.0) -> None:
            self.author_id = author_id
            self.confirmed = None
            self.message = None

        async def wait(self) -> None:
            self.confirmed = confirmed

    return _Stub


async def _run(session_factory, confirmed: bool | None):
    from gurps_bot.cogs.privacy import PrivacyGroup

    interaction = _interaction(session_factory)
    group = PrivacyGroup(MagicMock())
    with patch("gurps_bot.cogs.privacy.ConfirmView", _view(confirmed)):
        await group.delete_my_data.callback(group, interaction)
    return interaction


async def _stored(session_factory) -> int:
    async with session_factory() as s:
        chars = await s.scalar(select(func.count(Character.id)))
        macros = await s.scalar(select(func.count(DiceMacro.id)))
    return chars + macros


async def test_confirm_deletes_everything(session_factory):
    interaction = await _run(session_factory, confirmed=True)
    assert await _stored(session_factory) == 0
    sent = interaction.followup.send.await_args
    assert sent.kwargs.get("ephemeral") is True
    assert "1 character" in sent.args[0]


async def test_cancel_deletes_nothing(session_factory):
    interaction = await _run(session_factory, confirmed=False)
    assert await _stored(session_factory) == 2
    interaction.followup.send.assert_not_awaited()


async def test_timeout_deletes_nothing(session_factory):
    await _run(session_factory, confirmed=None)
    assert await _stored(session_factory) == 2


async def test_the_prompt_is_private_and_says_what_goes(session_factory):
    interaction = await _run(session_factory, confirmed=False)
    kwargs = interaction.response.send_message.await_args.kwargs
    assert kwargs.get("ephemeral") is True
    prompt = interaction.response.send_message.await_args.args[0]
    assert "cannot be undone" in prompt
    assert "1 character, 1 macro" in prompt


async def test_nothing_stored_answers_without_a_prompt(session_factory):
    from gurps_bot.cogs.privacy import PrivacyGroup

    interaction = _interaction(session_factory)
    interaction.user.id = 999
    group = PrivacyGroup(MagicMock())
    with patch("gurps_bot.cogs.privacy.ConfirmView") as view:
        await group.delete_my_data.callback(group, interaction)
    view.assert_not_called()
    args, kwargs = interaction.response.send_message.await_args
    assert "nothing" in args[0] and kwargs.get("ephemeral") is True
