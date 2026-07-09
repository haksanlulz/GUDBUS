"""Character management cog: /import and the /char group."""

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
    delete_character,
    get_active_character,
    get_character_by_name,
    get_user_character_names,
    get_user_characters,
    import_character,
    set_active_character,
)
from gurps_bot.ui import embeds
from gurps_bot.ui.formatters import (
    format_equipment_line,
    format_skill_line,
    format_spell_line,
    format_trait_line,
    paginate,
)
from gurps_bot.cogs._autocomplete import make_autocomplete
from gurps_bot.ui.views import ConfirmView, PaginatorView
from gurps_bot.utils._cache_instances import skill_cache as _skill_cache
from gurps_bot.utils.fuzzy import fuzzy_match

log = logging.getLogger(__name__)

MAX_IMPORT_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_CHARACTERS_PER_USER = 20


async def _fetch_char_names(
    session: AsyncSession, interaction: discord.Interaction,
) -> list[str]:
    return await get_user_character_names(session, interaction.user.id)


_char_name_autocomplete = make_autocomplete(_fetch_char_names)


async def _send_paginated(
    interaction: discord.Interaction,
    title: str,
    lines: list[str],
    char_name: str,
    per_page: int = 15,
    empty_msg: str = "No matching items found.",
) -> None:
    """Send a paginated embed list, with PaginatorView if multi-page."""
    if not lines:
        await interaction.followup.send(empty_msg, ephemeral=True)
        return

    page_embeds = []
    total_pages = max(1, (len(lines) + per_page - 1) // per_page)
    for p in range(total_pages):
        text, pg, tp = paginate(lines, p, per_page)
        page_embeds.append(embeds.paginated_list_embed(title, text, pg, tp, char_name))

    if len(page_embeds) == 1:
        await interaction.followup.send(embed=page_embeds[0])
    else:
        view = PaginatorView(page_embeds, interaction.user.id)
        msg = await interaction.followup.send(embed=page_embeds[0], view=view, wait=True)
        view.message = msg


class ImportCog(commands.Cog):
    "Import GCS Character Files."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.checks.cooldown(1, 10.0)
    @app_commands.command(name="import", description="Import a .gcs Character File")
    @app_commands.describe(file="A .gcs character sheet file")
    @app_commands.guild_only()
    async def import_char(self, interaction: discord.Interaction, file: discord.Attachment) -> None:
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
        guild_id = interaction.guild_id

        async with interaction.client.db() as session:
            # cap check; replacing an existing character is exempt
            existing_names = await get_user_character_names(session, user_id)
            if parsed.name not in existing_names and len(existing_names) >= MAX_CHARACTERS_PER_USER:
                await interaction.followup.send(
                    f"You have {len(existing_names)} characters (max {MAX_CHARACTERS_PER_USER}). "
                    "Delete one before importing a new one.",
                )
                return

            char, was_replacement = await import_character(
                session, user_id, parsed, file.filename, raw_data=data,
            )
            await set_active_character(session, user_id, guild_id, char.id)
            await session.commit()

            _skill_cache.invalidate_user(user_id)

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


@app_commands.guild_only()
class CharGroup(commands.GroupCog, group_name="char"):
    "Character Viewing and Management Commands."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.command(name="view", description="View Your Active Character Summary")
    async def view(self, interaction: discord.Interaction) -> None:
        async with CharacterContext(interaction) as ctx:
            if not ctx.ok:
                return
            attrs = await ctx.get_attrs()
            embed = embeds.char_summary_embed(
                ctx.char_name, ctx.char.total_points, attrs,
                ctx.char.calc_json, ctx.char.source_filename,
            )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="skills", description="List Your Character's Skills")
    @app_commands.describe(search="Filter skills by name")
    async def skills(self, interaction: discord.Interaction, search: str | None = None) -> None:
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

    @app_commands.command(name="spells", description="List Your Character's Spells")
    @app_commands.describe(search="Filter spells by name")
    async def spells(self, interaction: discord.Interaction, search: str | None = None) -> None:
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

    @app_commands.command(name="traits", description="List Your Character's Advantages and Disadvantages")
    @app_commands.describe(search="Filter traits by name")
    async def traits(self, interaction: discord.Interaction, search: str | None = None) -> None:
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

    @app_commands.command(name="equipment", description="View Your Character's Equipment")
    async def equipment(self, interaction: discord.Interaction) -> None:
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

    @app_commands.command(name="export", description="Export Your Active Character as .gcs")
    async def export(self, interaction: discord.Interaction) -> None:
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

    @app_commands.command(name="list", description="List All Your Imported Characters")
    async def list_chars(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        user_id = interaction.user.id
        guild_id = interaction.guild_id

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

    @app_commands.command(name="switch", description="Switch Your Active Character")
    @app_commands.describe(name="Character name to switch to")
    @app_commands.autocomplete(name=_char_name_autocomplete)
    async def switch(self, interaction: discord.Interaction, name: str) -> None:
        user_id = interaction.user.id
        guild_id = interaction.guild_id

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
    @app_commands.command(name="delete", description="Delete an Imported Character")
    @app_commands.describe(name="Character name to delete")
    @app_commands.autocomplete(name=_char_name_autocomplete)
    async def delete_char(self, interaction: discord.Interaction, name: str) -> None:
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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ImportCog(bot))
    await bot.add_cog(CharGroup(bot))
