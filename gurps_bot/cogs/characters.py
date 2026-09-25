"""Character management cog: the /char group, import included."""

from __future__ import annotations

import io
import json
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

from gurps_bot.gcs.parser import GCSParseError, parse_gcs
from gurps_bot.services.character_context import CharacterContext
from gurps_bot.services.characters import (
    CharacterNameTaken,
    delete_character,
    get_active_character,
    get_character_by_name,
    get_user_character_names,
    get_user_characters,
    import_character,
    set_active_character,
)
from gurps_bot.services.limits import StorageLimitExceeded
from gurps_bot.ui import embeds
from gurps_bot.ui.formatters import (
    format_equipment_line,
    format_skill_line,
    format_spell_line,
    format_trait_line,
    paginate,
)
from gurps_bot.cogs._autocomplete import make_autocomplete
from gurps_bot.ui.respond import respond
from gurps_bot.ui.views import ConfirmView, PaginatorView
from gurps_bot.utils.fuzzy import fuzzy_match
from gurps_bot.utils.scope import guild_id_of

log = logging.getLogger(__name__)

MAX_IMPORT_SIZE = 5 * 1024 * 1024  # 5 MB


async def _fetch_char_names(
    session: AsyncSession, interaction: discord.Interaction[GURPSBot],
) -> list[str]:
    return await get_user_character_names(session, interaction.user.id)


_char_name_autocomplete = make_autocomplete(_fetch_char_names)


async def _send_paginated(
    interaction: discord.Interaction[GURPSBot],
    title: str,
    lines: list[str],
    char_name: str,
    per_page: int = 15,
    empty_msg: str = "No matching items found.",
) -> None:
    """Send a paginated embed list, with PaginatorView if multi-page."""
    if not lines:
        await respond(interaction, empty_msg, ephemeral=True)
        return

    page_embeds = []
    total_pages = max(1, (len(lines) + per_page - 1) // per_page)
    for p in range(total_pages):
        text, pg, tp = paginate(lines, p, per_page)
        page_embeds.append(embeds.paginated_list_embed(title, text, pg, tp, char_name))

    # through respond(): a public reply here must consume CharacterContext's
    # placeholder, or a later private reply would delete this list
    if len(page_embeds) == 1:
        await respond(interaction, embed=page_embeds[0])
    else:
        view = PaginatorView(page_embeds, interaction.user.id)
        await respond(interaction, embed=page_embeds[0], view=view)
        try:
            view.message = await interaction.original_response()
        except discord.HTTPException:
            pass  # paging still works; only the timeout cleanup needs it




@app_commands.guild_only()
class CharGroup(commands.GroupCog, group_name="char"):
    "Import, view, and manage your characters."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.checks.cooldown(1, 10.0)
    @app_commands.command(name="import", description="Import a .gcs character file")
    @app_commands.describe(file="A .gcs character sheet file")
    async def import_char(self, interaction: discord.Interaction[GURPSBot], file: discord.Attachment) -> None:
        # extension check is just ux; the json parse below is the real validation
        if not file.filename.endswith(".gcs"):
            await interaction.response.send_message(
                "Please upload a `.gcs` file.", ephemeral=True
            )
            return

        if file.size and file.size > MAX_IMPORT_SIZE:
            await interaction.response.send_message(
                f"File too large ({file.size // 1024} KB). Maximum is 5 MB.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)

        try:
            raw = await file.read()
        except discord.HTTPException:
            await interaction.followup.send("Failed to download file.")
            return

        if len(raw) > MAX_IMPORT_SIZE:
            await interaction.followup.send(
                f"File too large ({len(raw) // 1024} KB). Maximum is 5 MB.",
            )
            return

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            await interaction.followup.send(f"Failed to read file: {e}")
            return

        try:
            parsed = parse_gcs(data)
        except GCSParseError as e:
            await interaction.followup.send(f"GCS parse error: {e}")
            return
        except (RecursionError, ValueError, TypeError, AttributeError, KeyError):
            # parse_gcs only raises GCSParseError for known-bad shapes; a novel
            # malformed sheet gets a clean message here instead of the generic error
            log.exception(
                "Unexpected error parsing GCS import for user %s", interaction.user.id
            )
            await interaction.followup.send(
                "That doesn't look like a valid GCS v5 character file."
            )
            return

        user_id = interaction.user.id
        guild_id = guild_id_of(interaction)

        async with interaction.client.db() as session:
            # the service owns the cap: only it knows whether this is a new row
            try:
                char, was_replacement = await import_character(
                    session, user_id, parsed, file.filename, raw_data=data,
                )
            except (StorageLimitExceeded, CharacterNameTaken) as e:
                await interaction.followup.send(str(e))
                return
            await set_active_character(session, user_id, guild_id, char.id)
            await session.commit()
            # Cache invalidation is owned by services/characters.py
            # (import_character + set_active_character), so /char switch and
            # /char delete get it too — they never had it here.

            attrs = {a.attr_id: a.value for a in parsed.attributes}
            for a in parsed.attributes:
                if a.current is not None:
                    attrs[f"{a.attr_id}_current"] = a.current

        embed = embeds.char_summary_embed(
            parsed.name, parsed.total_points, attrs, parsed.calc, file.filename
        )
        replaced = " (replaced existing)" if was_replacement else ""
        await interaction.followup.send(
            f"Imported **{parsed.name}**{replaced} and set as active.",
            embed=embed,
        )

    @app_commands.command(name="view", description="View your active character summary")
    async def view(self, interaction: discord.Interaction[GURPSBot]) -> None:
        async with CharacterContext(interaction) as ctx:
            if not ctx.ok:
                return
            attrs = await ctx.get_attrs()
            embed = embeds.char_summary_embed(
                ctx.char_name, ctx.char.total_points, attrs,
                ctx.char.calc_json, ctx.char.source_filename,
            )
        await respond(interaction, embed=embed)

    @app_commands.command(name="skills", description="List your character's skills")
    @app_commands.describe(search="Filter skills by name")
    async def skills(self, interaction: discord.Interaction[GURPSBot], search: str | None = None) -> None:
        async with CharacterContext(interaction) as ctx:
            if not ctx.ok:
                return
            all_skills = await ctx.get_skills()
            char_name = ctx.char_name

        if search:
            names = [s.display_name for s in all_skills]
            matches = fuzzy_match(search, names, limit=25, score_cutoff=40)
            matched_names = {m for m, _ in matches}
            all_skills = [s for s in all_skills if s.display_name in matched_names]

        lines = [
            format_skill_line(s.name, s.specialization, s.level, s.relative_level, s.points)
            for s in all_skills
        ]
        await _send_paginated(interaction, "Skills", lines, char_name)

    @app_commands.command(name="spells", description="List your character's spells")
    @app_commands.describe(search="Filter spells by name")
    async def spells(self, interaction: discord.Interaction[GURPSBot], search: str | None = None) -> None:
        async with CharacterContext(interaction) as ctx:
            if not ctx.ok:
                return
            all_spells = await ctx.get_spells()
            char_name = ctx.char_name

        if search:
            names = [s.name for s in all_spells]
            matches = fuzzy_match(search, names, limit=25, score_cutoff=40)
            matched_names = {m for m, _ in matches}
            all_spells = [s for s in all_spells if s.name in matched_names]

        lines = [
            format_spell_line(s.name, s.level, s.college, s.casting_cost)
            for s in all_spells
        ]
        await _send_paginated(interaction, "Spells", lines, char_name)

    @app_commands.command(name="traits", description="List your character's advantages and disadvantages")
    @app_commands.describe(search="Filter traits by name")
    async def traits(self, interaction: discord.Interaction[GURPSBot], search: str | None = None) -> None:
        async with CharacterContext(interaction) as ctx:
            if not ctx.ok:
                return
            all_traits = await ctx.get_traits()
            char_name = ctx.char_name

        if search:
            names = [t.name for t in all_traits]
            matches = fuzzy_match(search, names, limit=25, score_cutoff=40)
            matched_names = {m for m, _ in matches}
            all_traits = [t for t in all_traits if t.name in matched_names]

        lines = [
            format_trait_line(t.name, t.points, t.level)
            for t in all_traits
        ]
        await _send_paginated(interaction, "Traits", lines, char_name)

    @app_commands.command(name="equipment", description="View your character's equipment")
    async def equipment(self, interaction: discord.Interaction[GURPSBot]) -> None:
        async with CharacterContext(interaction) as ctx:
            if not ctx.ok:
                return
            equip = ctx.char.equipment_json
            char_name = ctx.char_name

        lines = [
            format_equipment_line(
                e["description"], e.get("quantity", 1),
                e.get("weight", "?"), e.get("equipped", False),
            )
            for e in equip
            if e.get("description")
        ]
        await _send_paginated(
            interaction, "Equipment", lines, char_name,
            per_page=20, empty_msg="No equipment.",
        )

    @app_commands.command(name="export", description="Export your active character as .gcs")
    async def export(self, interaction: discord.Interaction[GURPSBot]) -> None:
        await interaction.response.defer(ephemeral=True)
        async with CharacterContext(interaction, defer=False) as ctx:
            if not ctx.ok:
                return
            raw = ctx.char.raw_gcs_json
            char_name = ctx.char_name
            filename = ctx.char.source_filename or f"{char_name}.gcs"

        if not raw:
            await interaction.followup.send(
                "No raw GCS data stored for this character "
                "(imported before export support was added).",
                ephemeral=True,
            )
            return

        raw_bytes = json.dumps(raw, indent=2).encode("utf-8")
        file = discord.File(io.BytesIO(raw_bytes), filename=filename)
        await interaction.followup.send(
            f"Exported **{char_name}**.", file=file, ephemeral=True,
        )

    @app_commands.command(name="list", description="List all your imported characters")
    async def list_chars(self, interaction: discord.Interaction[GURPSBot]) -> None:
        await interaction.response.defer()
        user_id = interaction.user.id
        guild_id = guild_id_of(interaction)

        async with interaction.client.db() as session:
            chars = await get_user_characters(session, user_id)
            active = await get_active_character(session, user_id, guild_id)
            active_id = active.id if active else None

        char_list = [
            (c.name, c.total_points, c.id == active_id)
            for c in chars
        ]
        embed = embeds.char_list_embed(char_list)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="switch", description="Switch your active character")
    @app_commands.describe(name="Character name to switch to")
    @app_commands.autocomplete(name=_char_name_autocomplete)
    async def switch(self, interaction: discord.Interaction[GURPSBot], name: str) -> None:
        user_id = interaction.user.id
        guild_id = guild_id_of(interaction)

        async with interaction.client.db() as session:
            char = await get_character_by_name(session, user_id, name)
            if not char:
                await interaction.response.send_message(
                    f"No character named **{name}**.", ephemeral=True
                )
                return

            await set_active_character(session, user_id, guild_id, char.id)
            await session.commit()

        await interaction.response.send_message(f"Switched to **{name}**.")

    @app_commands.checks.cooldown(1, 10.0)
    @app_commands.command(name="delete", description="Delete an imported character")
    @app_commands.describe(name="Character name to delete")
    @app_commands.autocomplete(name=_char_name_autocomplete)
    async def delete_char(self, interaction: discord.Interaction[GURPSBot], name: str) -> None:
        user_id = interaction.user.id

        async with interaction.client.db() as session:
            char = await get_character_by_name(session, user_id, name)

        if not char:
            await interaction.response.send_message(
                f"No character named **{name}**.", ephemeral=True
            )
            return

        view = ConfirmView(author_id=user_id)
        await interaction.response.send_message(
            f"Delete **{name}** ({char.total_points} pts)? This cannot be undone.",
            view=view,
        )
        view.message = await interaction.original_response()
        await view.wait()

        if view.confirmed:
            async with interaction.client.db() as session:
                deleted = await delete_character(session, char.id)
                if deleted:
                    await session.commit()
                    await interaction.followup.send(f"Deleted **{name}**.")
                else:
                    await interaction.followup.send(
                        f"**{name}** was already deleted.", ephemeral=True
                    )


async def setup(bot: GURPSBot) -> None:
    await bot.add_cog(CharGroup(bot))
