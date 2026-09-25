"""Guild/channel ids for interactions that can only come from a server.

discord.py types ``guild_id`` and ``channel_id`` as optional because a DM has
neither. A ``guild_only`` command, or a button on a message posted in a server,
always has both — but nothing tells the type checker that. These helpers state
the guarantee once and make it loud if it is ever broken, instead of letting a
``None`` reach a query keyed on the id.
"""

from __future__ import annotations

import discord


class NotInGuild(RuntimeError):
    """A guild-scoped code path was reached from an interaction without a guild."""


def guild_id_of(interaction: discord.Interaction) -> int:
    if interaction.guild_id is None:
        raise NotInGuild(f"{interaction.command!r} reached a guild-scoped path from a DM")
    return interaction.guild_id


def channel_scope(interaction: discord.Interaction) -> tuple[int, int]:
    """``(guild_id, channel_id)`` — the key every channel-scoped row uses."""
    if interaction.channel_id is None:
        raise NotInGuild(f"{interaction.command!r} reached a channel-scoped path without a channel")
    return guild_id_of(interaction), interaction.channel_id
