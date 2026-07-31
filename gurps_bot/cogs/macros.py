"""/macro — save, roll, list, delete named dice expressions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.mechanics.dice import roll
from gurps_bot.services.macros import (
    InvalidMacroName,
    delete_macro,
    get_macro,
    list_macros,
    normalize_macro_name,
    save_macro,
)
from gurps_bot.utils.fuzzy import fuzzy_match

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)


async def _macro_name_autocomplete(
    interaction: discord.Interaction, current: str,
) -> list[app_commands.Choice[str]]:
    """Suggest the caller's own saved macro names.

    Deliberately not guild-gated, unlike _autocomplete.make_autocomplete: macros
    are keyed on the user alone and /macro is not guild_only, so the commands
    work in DMs and their suggestions have to as well.
    """
    try:
        async with interaction.client.db() as session:
            names = [m.name for m in await list_macros(session, interaction.user.id)]
    except Exception:
        # Autocomplete has no error channel — a raise here just blanks the
        # suggestions with no diagnostic. Mirrors reference.py's _suggest.
        log.exception("macro autocomplete failed for user %s", interaction.user.id)
        return []

    if current:
        # Default WRatio, matching _autocomplete.make_autocomplete (the other
        # small per-user list). reference.py's prefix_optimized partial_ratio
        # keeps an ~11k-name catalog scan cheap and pays for it in precision —
        # on a handful of macro names it just returns everything.
        names = [m for m, _ in fuzzy_match(current, names, limit=25, score_cutoff=40)]
    else:
        names = names[:25]
    # Discord caps Choice name/value at 100 chars and rejects the WHOLE payload
    # on one over-long entry — the service caps names at 50, but a row written
    # before that cap must not silently kill every suggestion.
    return [app_commands.Choice(name=n[:100], value=n[:100]) for n in names]


class MacroCog(commands.GroupCog, group_name="macro"):
    "Save and roll named dice expressions."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.command(name="save", description="Save a named dice macro")
    @app_commands.describe(
        name="Macro name (e.g. greatsword)",
        expression="Dice notation (e.g. 2d+4, 3d6, 1d-1)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def save(
        self, interaction: discord.Interaction, name: str, expression: str,
    ) -> None:
        async with interaction.client.db() as session:
            try:
                macro = await save_macro(
                    session, interaction.user.id, name, expression
                )
            except InvalidMacroName as e:
                # Distinct from the expression branch: blaming the dice notation
                # for a bad name sends the user to fix the wrong argument.
                await interaction.response.send_message(
                    f"Invalid macro name: {e}", ephemeral=True
                )
                return
            except ValueError as e:
                await interaction.response.send_message(
                    f"Invalid dice expression: {e}", ephemeral=True
                )
                return
            # Read the persisted values BEFORE commit: the confirmation has to
            # quote what was stored (sanitized, lowercased, length-capped), not
            # what was typed, or the user can't find it again by name.
            stored_name, stored_expr = macro.name, macro.expression
            await session.commit()
        await interaction.response.send_message(
            f"Saved macro **{stored_name}** = `{stored_expr}`.", ephemeral=True
        )

    @app_commands.command(name="roll", description="Roll a saved macro")
    @app_commands.describe(name="Macro name")
    @app_commands.autocomplete(name=_macro_name_autocomplete)
    @app_commands.checks.cooldown(2, 5.0)
    async def roll_macro(self, interaction: discord.Interaction, name: str) -> None:
        # Normalize up front: get_macro raises InvalidMacroName for a name that
        # sanitizes to nothing, and an unhandled raise here reaches the user as
        # the generic "something went wrong" instead of a fixable message.
        try:
            key = normalize_macro_name(name)
        except InvalidMacroName as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        async with interaction.client.db() as session:
            macro = await get_macro(session, interaction.user.id, key)
        if macro is None:
            await interaction.response.send_message(
                f"No macro named **{key}**. Save one with `/macro save`.",
                ephemeral=True,
            )
            return
        try:
            result = roll(macro.expression)
        except ValueError as e:
            # save_macro validates on the way in, so this is a row that predates
            # the current parser bounds (or was written outside the service).
            log.warning(
                "Unrollable stored macro %r for user %s: %s",
                macro.name, interaction.user.id, e,
            )
            await interaction.response.send_message(
                f"Macro **{macro.name}** stores an expression that no longer "
                f"parses (`{macro.expression}`): {e}. Re-save it with "
                "`/macro save`.",
                ephemeral=True,
            )
            return
        dice = ", ".join(str(d) for d in result.dice)
        await interaction.response.send_message(
            f"**{macro.name}** (`{macro.expression}`): [{dice}] = **{result.total}**"
        )

    @app_commands.command(name="list", description="List your saved macros")
    @app_commands.checks.cooldown(2, 5.0)
    async def list_cmd(self, interaction: discord.Interaction) -> None:
        async with interaction.client.db() as session:
            macros = await list_macros(session, interaction.user.id)
        if not macros:
            await interaction.response.send_message(
                "You have no saved macros. Add one with `/macro save`.", ephemeral=True
            )
            return
        lines = "\n".join(f"**{m.name}** = `{m.expression}`" for m in macros)
        await interaction.response.send_message(lines, ephemeral=True)

    @app_commands.command(name="delete", description="Delete a saved macro")
    @app_commands.describe(name="Macro name")
    @app_commands.autocomplete(name=_macro_name_autocomplete)
    @app_commands.checks.cooldown(2, 5.0)
    async def delete_cmd(self, interaction: discord.Interaction, name: str) -> None:
        # Same guard as /macro roll — delete_macro reaches get_macro, which
        # raises InvalidMacroName on a name that sanitizes to nothing.
        try:
            key = normalize_macro_name(name)
        except InvalidMacroName as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        async with interaction.client.db() as session:
            removed = await delete_macro(session, interaction.user.id, key)
            await session.commit()
        if removed:
            await interaction.response.send_message(
                f"Deleted macro **{key}**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"No macro named **{key}**.", ephemeral=True
            )


async def setup(bot: GURPSBot) -> None:
    await bot.add_cog(MacroCog(bot))
