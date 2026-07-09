"""Combat session wrapper — centralized permission enforcement and command context."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from gurps_bot.services.combat import current_combatant, get_combat
from gurps_bot.utils.fuzzy import fuzzy_match

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from gurps_bot.db.models import Combat, Combatant

log = logging.getLogger(__name__)


class CombatPermissionError(Exception):
    """Raised when a user lacks permission for a combat action."""


class CombatNotFound(Exception):
    """Raised when no active combat exists in the channel."""


class CombatTargetNotFound(Exception):
    """Raised when a combatant name doesn't match anyone."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"No combatant matching **{name}**.")


class CombatSession:
    """Permission + turn-state helpers over a Combat row."""

    def __init__(self, combat: Combat, user_id: int) -> None:
        self.combat = combat
        self.user_id = user_id

    @property
    def is_gm(self) -> bool:
        return self.combat.started_by == self.user_id

    @property
    def current_combatant(self) -> Combatant | None:
        # anchor-resolved, not positional — see services.combat.current_combatant
        return current_combatant(self.combat)

    @property
    def is_current_turn(self) -> bool:
        current = self.current_combatant
        return current is not None and current.discord_user_id == self.user_id

    def require_gm(self) -> None:
        if not self.is_gm:
            raise CombatPermissionError("Only the GM can do this.")

    def require_turn_or_gm(self) -> None:
        if not self.is_gm and not self.is_current_turn:
            raise CombatPermissionError(
                "Only the current-turn player or the GM can do this."
            )

    def find_own_combatant(self) -> Combatant | None:
        return next(
            (c for c in self.combat.combatants if c.discord_user_id == self.user_id),
            None,
        )

    def find_combatant(self, name: str) -> Combatant:
        names = [c.name for c in self.combat.combatants]
        matches = fuzzy_match(name, names, limit=1, score_cutoff=50)
        if not matches:
            raise CombatTargetNotFound(name)
        matched_name = matches[0][0]
        return next(c for c in self.combat.combatants if c.name == matched_name)


class CombatContext:
    """Session + combat acquisition for subcommands; check ctx.ok, combat errors go out ephemeral."""

    def __init__(self, interaction: discord.Interaction) -> None:
        self.interaction = interaction
        self.session: AsyncSession | None = None
        self.combat: Combat | None = None
        self.cs: CombatSession | None = None
        self._session_ctx = None

    @property
    def ok(self) -> bool:
        """True if an active combat was found."""
        return self.combat is not None

    async def __aenter__(self) -> CombatContext:
        self._session_ctx = self.interaction.client.db()
        self.session = await self._session_ctx.__aenter__()
        self.combat = await get_combat(
            self.session,
            self.interaction.guild_id,
            self.interaction.channel_id,
        )
        if not self.combat:
            await self._send_error("No active combat.")
        else:
            self.cs = CombatSession(self.combat, self.interaction.user.id)
        return self

    async def commit(self) -> None:
        """Commit the transaction. Call after mutations, before refresh_tracker."""
        await self.session.commit()

    async def respond_and_refresh(self, content: str) -> None:
        """Reply first, then refresh — the 3s interaction ACK window can't wait on the tracker edit."""
        await self.interaction.response.send_message(content)
        if not await self.refresh_tracker():
            await self.interaction.followup.send(
                "⚠️ Couldn't update the combat tracker — check my "
                "permissions in this channel.",
                ephemeral=True,
            )

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        suppress = False
        if exc_type in (CombatPermissionError, CombatTargetNotFound):
            msg = str(exc_val) if str(exc_val) else "Combat error."
            await self._send_error(msg)
            suppress = True
        if self._session_ctx is not None:
            await self._session_ctx.__aexit__(
                None if suppress else exc_type,
                None if suppress else exc_val,
                None if suppress else exc_tb,
            )
        return suppress

    async def _send_error(self, msg: str) -> None:
        if self.interaction.response.is_done():
            await self.interaction.followup.send(msg, ephemeral=True)
        else:
            await self.interaction.response.send_message(msg, ephemeral=True)

    async def refresh_tracker(self) -> bool:
        """Re-fetch combat + redraw the tracker; call after commit()."""
        from gurps_bot.ui.tracker import TrackerManager

        self.combat = await get_combat(
            self.session,
            self.interaction.guild_id,
            self.interaction.channel_id,
        )
        # a concurrent /combat end can land between commit and here — combat comes
        # back None, and dereferencing it would blow up after the reply went out
        if self.combat is None:
            return False
        tracker = TrackerManager(self.interaction.channel, self.combat.message_id)
        return await tracker.refresh(self.combat)
