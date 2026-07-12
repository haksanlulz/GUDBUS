"""View button callbacks + AddNPCModal.on_submit.

test_views.py asserted constructor state only — the author-gate seam
(interaction.user.id != view.author_id) and the modal's submit-time GM
re-check had zero tests, and both are exactly the lines a refactor drops
silently. Buttons are invoked through their bound callbacks, mirroring how
cog tests call `command.callback`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from gurps_bot.db.models import Base, Combat, Combatant
from gurps_bot.ui.views import AddNPCModal, ConfirmView, PaginatorView

AUTHOR_ID = 42
STRANGER_ID = 777
GM_ID = 999


def _interaction(user_id: int):
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.guild_id = 100
    interaction.channel_id = 200
    interaction.response.send_message = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    return interaction


def _pages(n: int = 3) -> list[discord.Embed]:
    return [discord.Embed(title=f"Page {i}") for i in range(n)]


class TestPaginatorViewAuthorGate:
    async def test_stranger_press_rejected_ephemeral(self):
        view = PaginatorView(pages=_pages(), author_id=AUTHOR_ID)
        interaction = _interaction(STRANGER_ID)
        await view.next_btn.callback(interaction)

        call = interaction.response.send_message.await_args
        assert call.kwargs.get("ephemeral") is True
        interaction.response.edit_message.assert_not_awaited()
        assert view.current == 0  # page did not move

    async def test_author_press_pages(self):
        view = PaginatorView(pages=_pages(), author_id=AUTHOR_ID)
        interaction = _interaction(AUTHOR_ID)
        await view.next_btn.callback(interaction)

        assert view.current == 1
        interaction.response.edit_message.assert_awaited_once()

    async def test_prev_clamps_at_first_page(self):
        view = PaginatorView(pages=_pages(), author_id=AUTHOR_ID)
        interaction = _interaction(AUTHOR_ID)
        await view.prev_btn.callback(interaction)
        assert view.current == 0


class TestConfirmViewAuthorGate:
    async def test_stranger_cannot_confirm(self):
        view = ConfirmView(author_id=AUTHOR_ID)
        interaction = _interaction(STRANGER_ID)
        await view.confirm_btn.callback(interaction)

        assert view.confirmed is None
        assert interaction.response.send_message.await_args.kwargs.get(
            "ephemeral"
        ) is True

    async def test_author_confirm_and_cancel(self):
        for pressed, expected in (("confirm_btn", True), ("cancel_btn", False)):
            view = ConfirmView(author_id=AUTHOR_ID)
            interaction = _interaction(AUTHOR_ID)
            await getattr(view, pressed).callback(interaction)
            assert view.confirmed is expected


# ---------------------------------------------------------------------------
# AddNPCModal.on_submit — DB-backed, mirroring the combat-cog harness.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def session_factory():
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await eng.dispose()


async def _seed_combat(session_factory) -> int:
    async with session_factory() as s:
        combat = Combat(guild_id=100, channel_id=200, started_by=GM_ID)
        s.add(combat)
        await s.commit()
        return combat.id


def _modal_interaction(session_factory, user_id: int):
    interaction = _interaction(user_id)

    @asynccontextmanager
    async def fake_db():
        async with session_factory() as s:
            yield s

    interaction.client.db = fake_db
    return interaction


def _modal(*, name="Goblin", speed="5.25", hp="10", fp="10", dx="10") -> AddNPCModal:
    modal = AddNPCModal()
    modal.npc_name._value = name
    modal.speed._value = speed
    modal.hp._value = hp
    modal.fp._value = fp
    modal.dx_input._value = dx
    return modal


async def _count_combatants(session_factory) -> int:
    async with session_factory() as s:
        return len((await s.execute(select(Combatant))).scalars().all())


class TestAddNPCModalSubmit:
    async def test_submit_recheck_rejects_non_gm(self, session_factory):
        # Submit arrives as a new interaction, so the GM check has to run
        # again here — the modal-open check does not carry over.
        await _seed_combat(session_factory)
        interaction = _modal_interaction(session_factory, STRANGER_ID)
        with pytest_patch_tracker():
            await _modal().on_submit(interaction)

        msg = interaction.response.send_message.await_args.args[0]
        assert "GM" in msg
        assert await _count_combatants(session_factory) == 0

    async def test_gm_submit_adds_npc(self, session_factory):
        await _seed_combat(session_factory)
        interaction = _modal_interaction(session_factory, GM_ID)
        with pytest_patch_tracker():
            await _modal().on_submit(interaction)

        assert await _count_combatants(session_factory) == 1

    async def test_nan_speed_rejected_with_message(self, session_factory):
        await _seed_combat(session_factory)
        interaction = _modal_interaction(session_factory, GM_ID)
        with pytest_patch_tracker():
            await _modal(speed="nan").on_submit(interaction)

        msg = interaction.response.send_message.await_args.args[0]
        assert "finite" in msg
        assert await _count_combatants(session_factory) == 0


def pytest_patch_tracker():
    """Patch out the tracker HTTP refresh the modal performs after adding."""
    from unittest.mock import patch

    return patch(
        "gurps_bot.ui.tracker.TrackerManager.refresh",
        new_callable=AsyncMock,
        return_value=True,
    )
