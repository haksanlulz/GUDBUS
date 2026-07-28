"""One way to answer an interaction, whether or not it was deferred.

A command that defers must answer through ``interaction.followup``; one that
did not must answer through ``interaction.response``. Using the wrong one
raises, so any command that *might* defer needs the branch at every exit — and
`error_handler` and both service contexts had each grown their own copy of it.

`defer()` exists because Discord invalidates an un-deferred interaction token
after **3 seconds**, while SQLite will wait up to `busy_timeout` (5s here) for
a write lock. Measured across concurrent guild writes, the slowest combat write
goes from 0.37s at 24 to 1.58s at 120 before the connection pool queues — under
the deadline, but by under 2x at the top end, and with no margin for a slower
disk. Deferring moves the ceiling from 3 seconds to 15 minutes and retires the
whole class.
"""

from __future__ import annotations

import discord


async def respond(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
    ephemeral: bool = False,
    **kwargs,
) -> discord.Message | None:
    """Send the interaction's reply, routing on whether it is already answered.

    Deliberately does NOT fetch the sent message. The two callers that need one
    — attaching a view, and storing the tracker's message id — already call
    ``interaction.original_response()`` themselves, each inside a try/except
    that treats failure as non-fatal. Fetching it here as well would add a
    round trip to every reply in the cog to serve two of them.

    After a defer, ``@original`` is the placeholder that the first followup
    replaces, so those existing calls keep resolving to the real message.
    """
    payload = {k: v for k, v in kwargs.items() if v is not None}
    if content is not None:
        payload["content"] = content
    if embed is not None:
        payload["embed"] = embed
    if view is not None:
        payload["view"] = view

    if interaction.response.is_done():
        return await interaction.followup.send(ephemeral=ephemeral, **payload)

    return await interaction.response.send_message(ephemeral=ephemeral, **payload)
