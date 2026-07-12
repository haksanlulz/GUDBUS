"""/study /notes /timer /wealth — slash wiring only; cogs own the commit, services never do."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from gurps_bot.mechanics.study import METHOD_MULTIPLIERS, POINT_HOURS
from gurps_bot.mechanics.wealth import (
    COST_OF_LIVING,
    WEALTH_MULTIPLIER,
    cost_of_living,
    starting_wealth,
)
from gurps_bot.services.characters import get_active_character
from gurps_bot.services.notes import (
    NoteNotFound,
    add_note,
    delete_note,
    edit_note,
    list_notes,
    search_notes,
)
from gurps_bot.services.study import (
    get_skill_progress,
    list_study,
    log_study,
    reset_skill,
)
from gurps_bot.services.timers import (
    add_timer,
    clear_timers,
    list_timers,
    remove_timer,
    tick_timers,
)
from gurps_bot.services.wealth import (
    adjust_balance,
    apply_cost_of_living,
    get_wealth,
    set_balance,
    set_status,
)

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

log = logging.getLogger(__name__)

# embeds.py palette, redefined so we don't import its private state
BLUE = discord.Color.blue()
GREEN = discord.Color.green()
GOLD = discord.Color.gold()
GREY = discord.Color.greyple()
ORANGE = discord.Color.dark_orange()

# keep bodies/lists under discord's embed caps
EMBED_FIELD_LIMIT = 1024
EMBED_DESC_LIMIT = 4096
EMBED_TITLE_LIMIT = 256
_LIST_PAGE = 10


def _cap_title(text: str) -> str:
    """Fit user text into an embed title (256) — slash options allow 6000.

    Display-only: storage keeps the full text. Overflow used to 400 the reply
    after the DB commit, which read as a bot crash and caused retry-duplicates.
    """
    if len(text) <= EMBED_TITLE_LIMIT:
        return text
    return text[: EMBED_TITLE_LIMIT - 1] + "…"


def _cap_desc(text: str) -> str:
    """Fit user text into an embed description (4096). Display-only."""
    if len(text) <= EMBED_DESC_LIMIT:
        return text
    return text[: EMBED_DESC_LIMIT - 40] + "\n*…truncated*"

# no 'adventuring' choice — it's GM-set per session and needs a multiplier arg
STUDY_METHOD_CHOICES = [
    app_commands.Choice(name=key.replace("_", " ").title(), value=key)
    for key in METHOD_MULTIPLIERS
]

TIMER_UNIT_CHOICES = [
    app_commands.Choice(name=u.title(), value=u)
    for u in ("turns", "seconds", "minutes", "hours")
]

# ordered poorest→richest by multiplier
WEALTH_LEVEL_CHOICES = [
    app_commands.Choice(name=key.replace("_", " ").title(), value=key)
    for key, _ in sorted(WEALTH_MULTIPLIER.items(), key=lambda kv: kv[1][0])
]

# richest→poorest — high status first reads best in the picker
STATUS_CHOICES = [
    app_commands.Choice(name=f"Status {tier} (${cost:,}/mo)", value=tier)
    for tier, cost in sorted(COST_OF_LIVING.items(), reverse=True)
][:25]


def _fmt_money(amount: float) -> str:
    if float(amount).is_integer():
        return f"${int(amount):,}"
    return f"${amount:,.2f}"


def _fmt_hours(hours: float) -> str:
    if float(hours).is_integer():
        return str(int(hours))
    return f"{hours:g}"


async def _active_character_id(
    interaction: discord.Interaction,
) -> tuple[int | None, str | None]:
    """Active character as (id, name); (None, None) in DMs or with none set. Opens its own session."""
    if not interaction.guild_id:
        return None, None
    async with interaction.client.db() as session:
        char = await get_active_character(
            session, interaction.user.id, interaction.guild_id
        )
        if char is None:
            return None, None
        return char.id, char.name


def _scope_suffix(char_name: str | None) -> str:
    return f"{char_name}" if char_name else "your log (no active character)"


class StudyCog(commands.Cog):
    "Training-Time Tracker: Convert Real Hours to Learning-Hours (B292-294)."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    study_group = app_commands.Group(
        name="study", description="Log Training Time and Track Skill Learning-Hours"
    )

    @study_group.command(name="log", description="Log a Study Session Toward a Skill")
    @app_commands.describe(
        skill="Skill being studied (free text — need not be on your sheet)",
        method="Study method (sets the real→learning-hour rate)",
        hours="Real/work hours spent this session",
        character_scoped="Track under your active character (default) or your user bucket",
    )
    @app_commands.choices(method=STUDY_METHOD_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def study_log(
        self,
        interaction: discord.Interaction,
        skill: str,
        method: str,
        hours: float,
        character_scoped: bool = True,
    ) -> None:
        char_id, char_name = (
            await _active_character_id(interaction)
            if character_scoped
            else (None, None)
        )
        try:
            async with interaction.client.db() as session:
                row = await log_study(
                    session,
                    interaction.user.id,
                    skill,
                    method,
                    hours,
                    character_id=char_id,
                )
                progress = await get_skill_progress(
                    session,
                    interaction.user.id,
                    skill,
                    character_id=char_id,
                )
                await session.commit()
        except ValueError as e:
            await interaction.response.send_message(
                f"Could not log study: {e}", ephemeral=True
            )
            return

        method_label = row.method.replace("_", " ").title()
        embed = discord.Embed(title=_cap_title(f"Studied {skill}"), color=GREEN)
        embed.add_field(name="Method", value=method_label, inline=True)
        embed.add_field(
            name="Real Hours", value=_fmt_hours(row.real_hours), inline=True
        )
        embed.add_field(
            name="Learning Hours +",
            value=_fmt_hours(row.learning_hours),
            inline=True,
        )
        embed.add_field(
            name="Total Learning Hours",
            value=_fmt_hours(progress.total_learning_hours),
            inline=True,
        )
        embed.add_field(
            name="Points Earned", value=str(progress.points_earned), inline=True
        )
        embed.add_field(
            name="To Next Point",
            value=f"{_fmt_hours(progress.hours_to_next)} hrs "
            f"({_fmt_hours(progress.remainder)}/{int(POINT_HOURS)} banked)",
            inline=True,
        )
        embed.set_footer(text=f"Scope: {_scope_suffix(char_name)}")
        await interaction.response.send_message(embed=embed)

    @study_group.command(
        name="progress", description="Show Learning-Hour Progress for a Skill"
    )
    @app_commands.describe(
        skill="Skill to report on",
        character_scoped="Read your active character's bucket (default) or user bucket",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def study_progress_cmd(
        self,
        interaction: discord.Interaction,
        skill: str,
        character_scoped: bool = True,
    ) -> None:
        char_id, char_name = (
            await _active_character_id(interaction)
            if character_scoped
            else (None, None)
        )
        async with interaction.client.db() as session:
            progress = await get_skill_progress(
                session, interaction.user.id, skill, character_id=char_id
            )

        embed = discord.Embed(
            title=_cap_title(f"{skill} — Study Progress"), color=BLUE
        )
        embed.add_field(
            name="Total Learning Hours",
            value=_fmt_hours(progress.total_learning_hours),
            inline=True,
        )
        embed.add_field(
            name="Points Earned", value=str(progress.points_earned), inline=True
        )
        embed.add_field(
            name="Banked",
            value=f"{_fmt_hours(progress.remainder)}/{int(POINT_HOURS)} hrs",
            inline=True,
        )
        embed.add_field(
            name="To Next Point",
            value=f"{_fmt_hours(progress.hours_to_next)} hrs",
            inline=True,
        )
        embed.set_footer(text=f"Scope: {_scope_suffix(char_name)}")
        await interaction.response.send_message(embed=embed)

    @study_group.command(
        name="list", description="List Your Recent Study Sessions"
    )
    @app_commands.describe(
        skill="Optional: only sessions for this skill",
        character_scoped="Limit to your active character (default) or show all",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def study_list(
        self,
        interaction: discord.Interaction,
        skill: str | None = None,
        character_scoped: bool = True,
    ) -> None:
        char_id, char_name = (
            await _active_character_id(interaction)
            if character_scoped
            else (None, None)
        )
        async with interaction.client.db() as session:
            rows = await list_study(
                session,
                interaction.user.id,
                character_id=char_id,
                skill_name=skill,
            )

        embed = discord.Embed(title="Study Log", color=BLUE)
        if not rows:
            embed.description = "*No study sessions logged yet. Use `/study log`.*"
        else:
            lines = []
            for r in rows[:_LIST_PAGE]:
                method_label = r.method.replace("_", " ").title()
                lines.append(
                    f"- **{r.skill_name}** — {method_label}: "
                    f"{_fmt_hours(r.real_hours)} real → "
                    f"{_fmt_hours(r.learning_hours)} learning hrs"
                )
            if len(rows) > _LIST_PAGE:
                lines.append(f"*…and {len(rows) - _LIST_PAGE} more.*")
            description = "\n".join(lines)
            if len(description) > EMBED_DESC_LIMIT:
                description = description[: EMBED_DESC_LIMIT - 40] + "\n*…truncated*"
            embed.description = description
        embed.set_footer(text=f"Scope: {_scope_suffix(char_name)}")
        await interaction.response.send_message(embed=embed)

    @study_group.command(
        name="reset", description="Delete All Study Sessions for One Skill"
    )
    @app_commands.describe(
        skill="Skill whose study log to wipe",
        character_scoped="Reset your active character's bucket (default) or user bucket",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def study_reset(
        self,
        interaction: discord.Interaction,
        skill: str,
        character_scoped: bool = True,
    ) -> None:
        char_id, char_name = (
            await _active_character_id(interaction)
            if character_scoped
            else (None, None)
        )
        async with interaction.client.db() as session:
            deleted = await reset_skill(
                session, interaction.user.id, skill, character_id=char_id
            )
            await session.commit()

        embed = discord.Embed(
            title=_cap_title(f"Reset {skill}"),
            description=(
                f"Deleted **{deleted}** study session(s)."
                if deleted
                else "*No matching sessions — nothing to delete.*"
            ),
            color=GREY if not deleted else GREEN,
        )
        embed.set_footer(text=f"Scope: {_scope_suffix(char_name)}")
        await interaction.response.send_message(embed=embed)


class NotesCog(commands.Cog):
    "Campaign / Session / GM Notes With Author-Only Secret Visibility."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    notes_group = app_commands.Group(
        name="notes", description="Campaign, Session, and GM Notes",
        # guild_only: a DM has guild_id None, which would disable the scope
        # filter and leak every user's non-secret notes across guilds
        guild_only=True,
    )

    @notes_group.command(name="add", description="Add a Note")
    @app_commands.describe(
        title="Short note title",
        body="Note body text",
        tags="Comma-separated tags (optional)",
        secret="GM secret — visible only to you",
        character_scoped="Attach to your active character (default) or leave unattached",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def notes_add(
        self,
        interaction: discord.Interaction,
        title: str,
        body: str = "",
        tags: str | None = None,
        secret: bool = False,
        character_scoped: bool = True,
    ) -> None:
        char_id, _ = (
            await _active_character_id(interaction)
            if character_scoped
            else (None, None)
        )
        tag_list = (
            [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        )
        try:
            async with interaction.client.db() as session:
                note = await add_note(
                    session,
                    discord_user_id=interaction.user.id,
                    title=title,
                    body=body,
                    guild_id=interaction.guild_id,
                    channel_id=(
                        interaction.channel_id if interaction.channel_id else None
                    ),
                    character_id=char_id,
                    tags=tag_list,
                    gm_secret=secret,
                )
                await session.commit()
                note_id = note.id
                note_title = note.title
                note_tags = list(note.tags_json or [])
        except ValueError as e:
            await interaction.response.send_message(
                f"Could not add note: {e}", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=_cap_title(f"Note #{note_id}: {note_title}"),
            description=_cap_desc(body) if body else "*No body.*",
            color=GOLD if secret else GREEN,
        )
        if note_tags:
            embed.add_field(
                name="Tags", value=", ".join(f"`{t}`" for t in note_tags), inline=False
            )
        if secret:
            embed.add_field(name="Visibility", value="GM secret (only you)", inline=True)
        embed.set_footer(text="Use /notes list or /notes search to find it again.")
        await interaction.response.send_message(embed=embed, ephemeral=secret)

    @notes_group.command(name="list", description="List Notes Visible to You")
    @app_commands.describe(
        tag="Optional: only notes carrying this tag",
        this_channel="Limit to notes filed in this channel",
        character_scoped="Limit to your active character's notes",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def notes_list(
        self,
        interaction: discord.Interaction,
        tag: str | None = None,
        this_channel: bool = False,
        character_scoped: bool = False,
    ) -> None:
        char_id: int | None = None
        if character_scoped:
            char_id, _ = await _active_character_id(interaction)
        channel_id = (
            interaction.channel_id if this_channel and interaction.channel_id else None
        )
        async with interaction.client.db() as session:
            notes = await list_notes(
                session,
                requesting_user_id=interaction.user.id,
                guild_id=interaction.guild_id,
                channel_id=channel_id,
                character_id=char_id,
                tag=tag,
            )

        embed = self._notes_list_embed("Notes", notes, tag=tag)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @notes_group.command(
        name="search", description="Search Your Visible Notes (Title/Body/Tags)"
    )
    @app_commands.describe(query="Substring to search for")
    @app_commands.checks.cooldown(2, 5.0)
    async def notes_search(
        self, interaction: discord.Interaction, query: str
    ) -> None:
        try:
            async with interaction.client.db() as session:
                notes = await search_notes(
                    session,
                    requesting_user_id=interaction.user.id,
                    query=query,
                    guild_id=interaction.guild_id,
                )
        except ValueError as e:
            await interaction.response.send_message(
                f"Could not search: {e}", ephemeral=True
            )
            return

        embed = self._notes_list_embed(f'Search: "{query}"', notes)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @notes_group.command(name="edit", description="Edit One of Your Notes")
    @app_commands.describe(
        note_id="ID of the note to edit (shown in /notes list)",
        title="New title (optional)",
        body="New body (optional)",
        tags="New comma-separated tags — replaces existing (optional)",
        secret="Toggle GM-secret visibility (optional)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def notes_edit(
        self,
        interaction: discord.Interaction,
        note_id: int,
        title: str | None = None,
        body: str | None = None,
        tags: str | None = None,
        secret: bool | None = None,
    ) -> None:
        tag_list = (
            [t.strip() for t in tags.split(",") if t.strip()] if tags is not None else None
        )
        try:
            async with interaction.client.db() as session:
                note = await edit_note(
                    session,
                    note_id=note_id,
                    requesting_user_id=interaction.user.id,
                    title=title,
                    body=body,
                    tags=tag_list,
                    gm_secret=secret,
                )
                await session.commit()
                note_title = note.title
                note_body = note.body
                note_tags = list(note.tags_json or [])
                note_secret = note.gm_secret
        except (NoteNotFound, ValueError) as e:
            await interaction.response.send_message(
                f"Could not edit note: {e}", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=_cap_title(f"Note #{note_id}: {note_title}"),
            description=_cap_desc(note_body) if note_body else "*No body.*",
            color=GOLD if note_secret else GREEN,
        )
        if note_tags:
            embed.add_field(
                name="Tags", value=", ".join(f"`{t}`" for t in note_tags), inline=False
            )
        embed.set_footer(text="Note updated.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @notes_group.command(name="delete", description="Delete One of Your Notes")
    @app_commands.describe(note_id="ID of the note to delete")
    @app_commands.checks.cooldown(2, 5.0)
    async def notes_delete(
        self, interaction: discord.Interaction, note_id: int
    ) -> None:
        async with interaction.client.db() as session:
            deleted = await delete_note(
                session,
                note_id=note_id,
                requesting_user_id=interaction.user.id,
            )
            await session.commit()

        if not deleted:
            await interaction.response.send_message(
                f"No note #{note_id} found.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"Deleted Note #{note_id}",
            color=GREY,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _notes_list_embed(
        self, title: str, notes: list, *, tag: str | None = None
    ) -> discord.Embed:
        embed = discord.Embed(title=title, color=BLUE)
        if not notes:
            suffix = f" tagged `{tag}`" if tag else ""
            embed.description = f"*No notes found{suffix}.*"
            return embed
        lines = []
        for n in notes[:_LIST_PAGE]:
            marker = " 🔒" if n.gm_secret else ""
            tag_str = (
                f" [{', '.join(n.tags_json)}]" if n.tags_json else ""
            )
            lines.append(f"- **#{n.id}** {n.title}{marker}{tag_str}")
        if len(notes) > _LIST_PAGE:
            lines.append(f"*…and {len(notes) - _LIST_PAGE} more.*")
        description = "\n".join(lines)
        if len(description) > EMBED_DESC_LIMIT:
            description = description[: EMBED_DESC_LIMIT - 40] + "\n*…truncated*"
        embed.description = description
        embed.set_footer(text="🔒 = GM secret (only you can see it)")
        return embed


class TimersCog(commands.Cog):
    "Channel-Scoped Countdowns for Spell Durations, Afflictions, Conditions."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    timer_group = app_commands.Group(
        name="timer", description="Countdown Timers for Durations and Conditions",
        guild_only=True,  # timers are guild/channel-scoped; never usable in a DM
    )

    def _require_channel(
        self, interaction: discord.Interaction
    ) -> tuple[int, int] | None:
        if interaction.guild_id is None or interaction.channel_id is None:
            return None
        return interaction.guild_id, interaction.channel_id

    @timer_group.command(name="add", description="Start a Countdown Timer")
    @app_commands.describe(
        label="What the timer counts (e.g. Haste, Bleeding, Stunned)",
        duration="How many units the timer lasts",
        unit="Time unit (turns/seconds/minutes/hours)",
        target="Combatant/character it applies to (optional)",
        note="Optional note (source spell, save condition, etc.)",
    )
    @app_commands.choices(unit=TIMER_UNIT_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def timer_add(
        self,
        interaction: discord.Interaction,
        label: str,
        duration: int,
        unit: str = "turns",
        target: str | None = None,
        note: str = "",
    ) -> None:
        scope = self._require_channel(interaction)
        if scope is None:
            await interaction.response.send_message(
                "Timers are channel-scoped — use this in a server channel.",
                ephemeral=True,
            )
            return
        guild_id, channel_id = scope
        try:
            async with interaction.client.db() as session:
                timer = await add_timer(
                    session,
                    guild_id,
                    channel_id,
                    label,
                    duration,
                    unit,
                    target=target,
                    note=note,
                )
                await session.commit()
                timer_id = timer.id
                timer_label = timer.label
                timer_remaining = timer.remaining
                timer_total = timer.total
        except ValueError as e:
            await interaction.response.send_message(
                f"Could not add timer: {e}", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=_cap_title(f"Timer Started: {timer_label}"), color=ORANGE
        )
        embed.add_field(
            name="Remaining",
            value=f"{timer_remaining}/{timer_total} {unit}",
            inline=True,
        )
        if target:
            embed.add_field(name="Target", value=target, inline=True)
        if note:
            embed.add_field(name="Note", value=note, inline=False)
        embed.set_footer(text=f"#{timer_id} • /timer tick to advance")
        await interaction.response.send_message(embed=embed)

    @timer_group.command(
        name="tick", description="Advance This Channel's Timers and Report Expirations"
    )
    @app_commands.describe(
        unit="Which unit to advance (only timers of this unit tick)",
        amount="How many units to advance (default 1)",
        target="Only advance timers on this target (optional)",
    )
    @app_commands.choices(unit=TIMER_UNIT_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def timer_tick(
        self,
        interaction: discord.Interaction,
        unit: str = "turns",
        amount: int = 1,
        target: str | None = None,
    ) -> None:
        scope = self._require_channel(interaction)
        if scope is None:
            await interaction.response.send_message(
                "Timers are channel-scoped — use this in a server channel.",
                ephemeral=True,
            )
            return
        guild_id, channel_id = scope
        try:
            async with interaction.client.db() as session:
                expired = await tick_timers(
                    session, guild_id, channel_id, unit, amount, target=target
                )
                # list after ticking so the embed shows post-tick state
                remaining = await list_timers(
                    session, guild_id, channel_id, include_expired=False
                )
                await session.commit()
                expired_lines = [
                    f"- **{t.label}**" + (f" on {t.target}" if t.target else "")
                    for t in expired
                ]
                live_lines = [
                    f"- **{t.label}**"
                    + (f" on {t.target}" if t.target else "")
                    + f" — {t.remaining}/{t.total} {t.unit}"
                    for t in remaining[:_LIST_PAGE]
                ]
                live_overflow = max(0, len(remaining) - _LIST_PAGE)
        except ValueError as e:
            await interaction.response.send_message(
                f"Could not tick timers: {e}", ephemeral=True
            )
            return

        # units are stored plural; singularize only when amount == 1
        unit_label = unit[:-1] if amount == 1 and unit.endswith("s") else unit
        embed = discord.Embed(
            title=f"Advanced {amount} {unit_label}",
            color=ORANGE,
        )
        embed.description = f"Ticked **{amount}** {unit_label}."
        if expired_lines:
            value = "\n".join(expired_lines)
            embed.add_field(
                name=f"Expired ({len(expired_lines)})",
                value=value[:EMBED_FIELD_LIMIT],
                inline=False,
            )
        else:
            embed.add_field(name="Expired", value="*None.*", inline=False)
        if live_lines:
            if live_overflow:
                live_lines.append(f"*…and {live_overflow} more.*")
            embed.add_field(
                name="Still Running",
                value="\n".join(live_lines)[:EMBED_FIELD_LIMIT],
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @timer_group.command(name="list", description="List This Channel's Timers")
    @app_commands.describe(
        target="Optional: only timers on this target",
        include_expired="Include already-expired timers (default true)",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def timer_list(
        self,
        interaction: discord.Interaction,
        target: str | None = None,
        include_expired: bool = True,
    ) -> None:
        scope = self._require_channel(interaction)
        if scope is None:
            await interaction.response.send_message(
                "Timers are channel-scoped — use this in a server channel.",
                ephemeral=True,
            )
            return
        guild_id, channel_id = scope
        async with interaction.client.db() as session:
            timers = await list_timers(
                session,
                guild_id,
                channel_id,
                target=target,
                include_expired=include_expired,
            )

        embed = discord.Embed(title="Timers", color=ORANGE)
        if not timers:
            embed.description = "*No timers in this channel. Use `/timer add`.*"
        else:
            lines = []
            for t in timers[:_LIST_PAGE]:
                tag = " ⏳" if t.remaining <= 0 else ""
                tgt = f" on {t.target}" if t.target else ""
                lines.append(
                    f"- **#{t.id} {t.label}**{tgt} — "
                    f"{t.remaining}/{t.total} {t.unit}{tag}"
                )
            if len(timers) > _LIST_PAGE:
                lines.append(f"*…and {len(timers) - _LIST_PAGE} more.*")
            description = "\n".join(lines)
            if len(description) > EMBED_DESC_LIMIT:
                description = description[: EMBED_DESC_LIMIT - 40] + "\n*…truncated*"
            embed.description = description
            embed.set_footer(text="⏳ = expired")
        await interaction.response.send_message(embed=embed)

    @timer_group.command(
        name="remove", description="Remove One Timer (or Clear All) in This Channel"
    )
    @app_commands.describe(
        timer_id="ID of the timer to remove (omit to clear — see clear_all)",
        clear_all="Remove ALL timers in this channel instead of one",
        expired_only="With clear_all: remove only expired timers",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def timer_remove(
        self,
        interaction: discord.Interaction,
        timer_id: int | None = None,
        clear_all: bool = False,
        expired_only: bool = False,
    ) -> None:
        scope = self._require_channel(interaction)
        if scope is None:
            await interaction.response.send_message(
                "Timers are channel-scoped — use this in a server channel.",
                ephemeral=True,
            )
            return
        guild_id, channel_id = scope

        if clear_all:
            async with interaction.client.db() as session:
                count = await clear_timers(
                    session, guild_id, channel_id, expired_only=expired_only
                )
                await session.commit()
            scope_word = "expired " if expired_only else ""
            embed = discord.Embed(
                title="Cleared Timers",
                description=f"Removed **{count}** {scope_word}timer(s).",
                color=GREY,
            )
            await interaction.response.send_message(embed=embed)
            return

        if timer_id is None:
            await interaction.response.send_message(
                "Give a `timer_id` to remove, or set `clear_all: True`.",
                ephemeral=True,
            )
            return

        async with interaction.client.db() as session:
            removed = await remove_timer(session, guild_id, channel_id, timer_id)
            await session.commit()

        if not removed:
            await interaction.response.send_message(
                f"No timer #{timer_id} in this channel.", ephemeral=True
            )
            return
        embed = discord.Embed(
            title=f"Removed Timer #{timer_id}", color=GREY
        )
        await interaction.response.send_message(embed=embed)


class WealthCog(commands.Cog):
    "Per-Character Wallet + Status Cost-of-Living Tracker (B265, B25-27)."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    wealth_group = app_commands.Group(
        name="wealth", description="Track Cash Balance and Status Cost-of-Living"
    )

    @wealth_group.command(name="show", description="Show Your Current Wallet")
    @app_commands.describe(
        character_scoped="Show your active character's wallet (default) or user wallet"
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def wealth_show(
        self, interaction: discord.Interaction, character_scoped: bool = True
    ) -> None:
        char_id, char_name = (
            await _active_character_id(interaction)
            if character_scoped
            else (None, None)
        )
        async with interaction.client.db() as session:
            wallet = await get_wealth(session, interaction.user.id, char_id)

        if wallet is None:
            embed = discord.Embed(
                title="Wallet",
                description="*No wallet yet. Use `/wealth adjust` or `/wealth set` to start one.*",
                color=GREY,
            )
            embed.set_footer(text=f"Scope: {_scope_suffix(char_name)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        upkeep = cost_of_living(wallet.status)
        embed = discord.Embed(title="Wallet", color=GREEN)
        embed.add_field(name="Balance", value=_fmt_money(wallet.balance), inline=True)
        embed.add_field(name="Status", value=str(wallet.status), inline=True)
        embed.add_field(
            name="Monthly Cost of Living",
            value=f"{_fmt_money(upkeep)}/mo",
            inline=True,
        )
        embed.set_footer(text=f"Scope: {_scope_suffix(char_name)}")
        await interaction.response.send_message(embed=embed)

    @wealth_group.command(
        name="adjust", description="Add Income (+) or Record a Spend (-)"
    )
    @app_commands.describe(
        amount="Signed $ amount — positive = income, negative = spend",
        reason="Optional note shown in the receipt",
        character_scoped="Apply to your active character's wallet (default) or user wallet",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def wealth_adjust(
        self,
        interaction: discord.Interaction,
        amount: float,
        reason: str | None = None,
        character_scoped: bool = True,
    ) -> None:
        char_id, char_name = (
            await _active_character_id(interaction)
            if character_scoped
            else (None, None)
        )
        async with interaction.client.db() as session:
            wallet = await adjust_balance(
                session, interaction.user.id, amount, char_id
            )
            await session.commit()
            new_balance = wallet.balance

        sign = "+" if amount >= 0 else "-"
        verb = "Income" if amount >= 0 else "Spend"
        embed = discord.Embed(
            title=verb,
            color=GREEN if amount >= 0 else ORANGE,
        )
        embed.add_field(
            name="Change", value=f"{sign}{_fmt_money(abs(amount))}", inline=True
        )
        embed.add_field(
            name="New Balance", value=_fmt_money(new_balance), inline=True
        )
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"Scope: {_scope_suffix(char_name)}")
        await interaction.response.send_message(embed=embed)

    @wealth_group.command(
        name="set", description="Set Your Balance to an Exact Amount (GM Correction)"
    )
    @app_commands.describe(
        balance="Exact $ balance to set",
        character_scoped="Apply to your active character's wallet (default) or user wallet",
    )
    @app_commands.checks.cooldown(2, 5.0)
    async def wealth_set(
        self,
        interaction: discord.Interaction,
        balance: float,
        character_scoped: bool = True,
    ) -> None:
        char_id, char_name = (
            await _active_character_id(interaction)
            if character_scoped
            else (None, None)
        )
        async with interaction.client.db() as session:
            wallet = await set_balance(
                session, interaction.user.id, balance, char_id
            )
            await session.commit()
            new_balance = wallet.balance

        embed = discord.Embed(title="Balance Set", color=BLUE)
        embed.add_field(
            name="New Balance", value=_fmt_money(new_balance), inline=True
        )
        embed.set_footer(text=f"Scope: {_scope_suffix(char_name)}")
        await interaction.response.send_message(embed=embed)

    @wealth_group.command(
        name="status", description="Set Your Status Tier (Drives Cost of Living)"
    )
    @app_commands.describe(
        status="GURPS Status tier (-2..8)",
        character_scoped="Apply to your active character's wallet (default) or user wallet",
    )
    @app_commands.choices(status=STATUS_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def wealth_status(
        self,
        interaction: discord.Interaction,
        status: int,
        character_scoped: bool = True,
    ) -> None:
        char_id, char_name = (
            await _active_character_id(interaction)
            if character_scoped
            else (None, None)
        )
        try:
            async with interaction.client.db() as session:
                wallet = await set_status(
                    session, interaction.user.id, status, char_id
                )
                await session.commit()
                new_status = wallet.status
        except ValueError as e:
            await interaction.response.send_message(
                f"Could not set Status: {e}", ephemeral=True
            )
            return

        upkeep = cost_of_living(new_status)
        embed = discord.Embed(title="Status Set", color=BLUE)
        embed.add_field(name="Status", value=str(new_status), inline=True)
        embed.add_field(
            name="Monthly Cost of Living",
            value=f"{_fmt_money(upkeep)}/mo",
            inline=True,
        )
        embed.set_footer(text=f"Scope: {_scope_suffix(char_name)}")
        await interaction.response.send_message(embed=embed)

    @wealth_group.command(
        name="upkeep", description="Deduct One Month's Cost of Living From Your Wallet"
    )
    @app_commands.describe(
        living_status="Status you're living at this month (B265: may be above/below your own; defaults to your set Status)",
        character_scoped="Apply to your active character's wallet (default) or user wallet",
    )
    @app_commands.choices(living_status=STATUS_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def wealth_upkeep(
        self,
        interaction: discord.Interaction,
        living_status: int | None = None,
        character_scoped: bool = True,
    ) -> None:
        char_id, char_name = (
            await _active_character_id(interaction)
            if character_scoped
            else (None, None)
        )
        try:
            async with interaction.client.db() as session:
                wallet = await apply_cost_of_living(
                    session, interaction.user.id, char_id, living_status=living_status
                )
                await session.commit()
                new_balance = wallet.balance
                nominal_status = wallet.status
        except ValueError as e:
            await interaction.response.send_message(
                f"Could not apply cost of living: {e}", ephemeral=True
            )
            return

        # override if given, else stored status — mirrors apply_cost_of_living
        effective_status = (
            living_status if living_status is not None else nominal_status
        )
        upkeep = cost_of_living(effective_status)
        embed = discord.Embed(title="Cost of Living Deducted", color=ORANGE)
        embed.add_field(
            name="Deducted", value=f"-{_fmt_money(upkeep)}", inline=True
        )
        embed.add_field(
            name="New Balance", value=_fmt_money(new_balance), inline=True
        )
        if living_status is not None and living_status != nominal_status:
            # B265: living above/below your own status this month
            embed.add_field(
                name="Living At",
                value=f"Status {effective_status} (your Status {nominal_status})",
                inline=True,
            )
        else:
            embed.add_field(name="Status", value=str(effective_status), inline=True)
        if new_balance < 0:
            embed.add_field(
                name="In Debt",
                value="Balance is negative — the GM decides consequences.",
                inline=False,
            )
        embed.set_footer(text=f"Scope: {_scope_suffix(char_name)}")
        await interaction.response.send_message(embed=embed)

    @wealth_group.command(
        name="starting", description="Look up Starting Cash for a TL + Wealth Level"
    )
    @app_commands.describe(
        tl="Tech level (0..12)",
        wealth_level="Wealth advantage/disadvantage level",
    )
    @app_commands.choices(wealth_level=WEALTH_LEVEL_CHOICES)
    @app_commands.checks.cooldown(2, 5.0)
    async def wealth_starting(
        self,
        interaction: discord.Interaction,
        tl: int,
        wealth_level: str,
    ) -> None:
        try:
            cash = starting_wealth(tl, wealth_level)
        except ValueError as e:
            await interaction.response.send_message(
                f"Could not compute starting wealth: {e}", ephemeral=True
            )
            return

        level_label = wealth_level.replace("_", " ").title()
        embed = discord.Embed(title="Starting Wealth", color=BLUE)
        embed.add_field(name="Tech Level", value=f"TL{tl}", inline=True)
        embed.add_field(name="Wealth Level", value=level_label, inline=True)
        embed.add_field(name="Starting Cash", value=_fmt_money(cash), inline=True)
        embed.set_footer(text="GURPS Basic Set B25-27, B265")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StudyCog(bot))
    await bot.add_cog(NotesCog(bot))
    await bot.add_cog(TimersCog(bot))
    await bot.add_cog(WealthCog(bot))
