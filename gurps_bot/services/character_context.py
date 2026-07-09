from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from gurps_bot.db.models import Character, Skill, Spell, Trait
from gurps_bot.services.characters import (
    NoActiveCharacter,
    get_active_character,
    get_character_attrs,
    get_character_skills,
    get_character_spells,
    get_character_traits,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class CharacterContext:
    """Session + active-character acquisition for slash commands; check ctx.ok before use."""

    def __init__(
        self,
        interaction: discord.Interaction,
        *,
        defer: bool = True,
    ) -> None:
        self.interaction = interaction
        self._defer = defer
        self.session: AsyncSession = None  # type: ignore[assignment]
        self.char: Character = None  # type: ignore[assignment]
        self._session_ctx = None

    @property
    def char_name(self) -> str:
        return self.char.name

    @property
    def char_id(self) -> int:
        return self.char.id

    async def get_attrs(self) -> dict[str, float]:
        return await get_character_attrs(self.session, self.char.id)

    async def get_skills(self) -> list[Skill]:
        return await get_character_skills(self.session, self.char.id)

    async def get_spells(self) -> list[Spell]:
        return await get_character_spells(self.session, self.char.id)

    async def get_traits(self) -> list[Trait]:
        return await get_character_traits(self.session, self.char.id)

    @property
    def ok(self) -> bool:
        """True if an active character was found. Check before accessing char."""
        return self.char is not None  # type: ignore[comparison-overlap]

    async def __aenter__(self) -> CharacterContext:
        if self._defer and not self.interaction.response.is_done():
            await self.interaction.response.defer()

        self._session_ctx = self.interaction.client.db()
        self.session = await self._session_ctx.__aenter__()

        char = await get_active_character(
            self.session,
            self.interaction.user.id,
            self.interaction.guild_id,
        )
        if not char:
            # __aexit__ can't suppress an __aenter__ exception, so error goes out here
            await self.interaction.followup.send(
                "No active character. Use `/import` to add one.",
                ephemeral=True,
            )
        else:
            self.char = char
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._session_ctx is not None:
            await self._session_ctx.__aexit__(exc_type, exc_val, exc_tb)
        return False
