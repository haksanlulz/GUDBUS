"""Combat rolls (/attack, /defend, /hit-location) and the /combat tracker group."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

if TYPE_CHECKING:
    from gurps_bot.bot import GURPSBot

from gurps_bot.db.models import Trait
from gurps_bot.mechanics.checks import Outcome, check
from gurps_bot.mechanics.combat_constants import Maneuver, StatusEffect
from gurps_bot.mechanics.damage import roll_hit_location
from gurps_bot.mechanics.defense import defense_penalty
from gurps_bot.mechanics.injury import (
    injury_effects,
    is_major_wound,
    knockdown_label,
    knockdown_modifier,
    knockdown_statuses,
    resolve_knockdown,
)
from gurps_bot.services.characters import (
    NoActiveCharacter,
    get_active_character,
    get_character_traits,
    require_active_character,
)
from gurps_bot.services.combat import (
    add_npc_combatant,
    add_pc_combatant,
    add_status,
    cleanup_stale_combats,
    end_combat,
    get_combat,
    modify_fp,
    modify_hp,
    record_defense,
    remove_combatant,
    remove_status,
    set_maneuver,
    start_combat,
)
from gurps_bot.services.combat_session import CombatContext, CombatPermissionError, CombatSession
from gurps_bot.ui import embeds
from gurps_bot.ui.formatters import _md_escape, format_modifier_suffix
from gurps_bot.ui.tracker import TrackerManager, get_tracker_view
from gurps_bot.ui.views import RollDamageView
from gurps_bot.cogs._autocomplete import make_autocomplete
from gurps_bot.utils.fuzzy import fuzzy_match
from gurps_bot.utils.sanitize import sanitize_name

log = logging.getLogger(__name__)


def _weapon_display_name(w: dict) -> str:
    """One formatter for weapon names; autocomplete and lookup must agree."""
    usage = w.get("usage") or "Attack"
    return f"{w.get('source', 'Unknown')} ({usage})"


def _resolve_defense_value(defense_str: str, weapon_level: int) -> int:
    """Parse defense value from GCS string, or calculate from weapon level."""
    if defense_str and str(defense_str).isdigit():
        return int(defense_str)
    return math.floor(weapon_level / 2) + 3


def _collect_weapons(equipment_json: list, char_traits: list[Trait]) -> list[dict]:
    weapons: list[dict] = []

    for item in equipment_json:
        if not item.get("equipped"):
            continue
        for w in item.get("weapons", []):
            w_copy = dict(w)
            w_copy["source"] = item.get("description", "Equipment")
            weapons.append(w_copy)

    for t in char_traits:
        if not t.has_weapon:
            continue
        for w in t.weapon_json:
            w_copy = dict(w)
            w_copy["source"] = t.name
            weapons.append(w_copy)

    return weapons


async def _fetch_weapon_names(session, interaction):
    char = await get_active_character(session, interaction.user.id, interaction.guild_id)
    if not char:
        return []
    traits = await get_character_traits(session, char.id)
    weapons = _collect_weapons(char.equipment_json, traits)
    return [_weapon_display_name(w) for w in weapons]


_weapon_autocomplete = make_autocomplete(_fetch_weapon_names)


async def _fetch_combatant_names(session, interaction):
    combat = await get_combat(session, interaction.guild_id, interaction.channel_id)
    if not combat:
        return []
    return [c.name for c in combat.combatants]


_combatant_name_autocomplete = make_autocomplete(_fetch_combatant_names)


# --------------------------------------------------------------------------- #
# Stateless combat roll commands
# --------------------------------------------------------------------------- #

@app_commands.guild_only()
class CombatCog(commands.Cog):
    "Stateless Combat Roll Commands — Attack, Defend, Hit Location."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    @app_commands.checks.cooldown(2, 5.0)
    @app_commands.command(name="attack", description="Roll an Attack With a Weapon")
    @app_commands.describe(
        weapon="Weapon name (autocomplete from your character)",
        modifier="Bonus or penalty to the attack roll",
        hidden="Roll in secret (GM blind roll): only you see the result",
    )
    @app_commands.autocomplete(weapon=_weapon_autocomplete)
    async def attack(
        self,
        interaction: discord.Interaction,
        weapon: str,
        modifier: int = 0,
        hidden: bool = False,
    ) -> None:
        async with interaction.client.db() as session:
            try:
                char = await require_active_character(session, interaction.user.id, interaction.guild_id)
            except NoActiveCharacter:
                await interaction.response.send_message("No active character.", ephemeral=True)
                return

            traits = await get_character_traits(session, char.id)
            weapons = _collect_weapons(char.equipment_json, traits)
            char_name = char.name

        weapon_names = [_weapon_display_name(w) for w in weapons]
        matches = fuzzy_match(weapon, weapon_names, limit=1, score_cutoff=40)
        if not matches:
            await interaction.response.send_message(
                f"No weapon matching **{weapon}**.", ephemeral=True
            )
            return

        idx = weapon_names.index(matches[0][0])
        w = weapons[idx]
        skill_level = w.get("level", 10)
        damage_str = w.get("damage", "?")

        label = f"{char_name} — Attack: {_weapon_display_name(w)}{format_modifier_suffix(modifier)}"

        result = check(skill_level, modifier)
        embed = embeds.check_embed(result, label)
        # escape for display (sheet strings can carry masked-link markdown); keep raw for the roll
        if damage_str and damage_str != "?":
            embed.add_field(name="Damage", value=_md_escape(damage_str), inline=True)
        if w.get("reach"):
            embed.add_field(name="Reach", value=_md_escape(w["reach"]), inline=True)

        view = RollDamageView(damage_str, hidden=hidden) if damage_str and damage_str != "?" else None
        await interaction.response.send_message(embed=embed, view=view, ephemeral=hidden)
        if view:
            try:
                view.message = await interaction.original_response()
            except discord.HTTPException:
                # roll already posted; view just won't auto-disable on timeout
                log.warning("Could not fetch original_response for RollDamageView")

    @app_commands.checks.cooldown(2, 5.0)
    @app_commands.command(name="defend", description="Roll a Defense (Dodge, Parry, or Block)")
    @app_commands.describe(
        defense_type="Type of defense",
        modifier="Bonus or penalty",
        weapon="Weapon/shield for parry/block (optional)",
    )
    @app_commands.choices(defense_type=[
        app_commands.Choice(name="Dodge", value="dodge"),
        app_commands.Choice(name="Parry", value="parry"),
        app_commands.Choice(name="Block", value="block"),
    ])
    async def defend(
        self,
        interaction: discord.Interaction,
        defense_type: str,
        modifier: int = 0,
        weapon: str | None = None,
    ) -> None:
        async with interaction.client.db() as session:
            try:
                char = await require_active_character(session, interaction.user.id, interaction.guild_id)
            except NoActiveCharacter:
                await interaction.response.send_message("No active character.", ephemeral=True)
                return

            calc = char.calc_json
            traits = await get_character_traits(session, char.id)
            equipment = char.equipment_json
            char_name = char.name

        target = 0
        label = ""

        if defense_type == "dodge":
            dodge_arr = calc.get("dodge", [])
            target = dodge_arr[0] if dodge_arr else 8
            label = f"{char_name} — Dodge"

        elif defense_type == "parry":
            weapons = _collect_weapons(equipment, traits)
            if weapon:
                weapon_names = [_weapon_display_name(w) for w in weapons]
                matches = fuzzy_match(weapon, weapon_names, limit=1, score_cutoff=40)
                if matches:
                    idx = weapon_names.index(matches[0][0])
                    w = weapons[idx]
                    target = _resolve_defense_value(w.get("parry", ""), w.get("level", 10))
                    label = f"{char_name} — Parry ({w.get('source', 'Unknown')})"
                else:
                    await interaction.response.send_message(
                        f"No weapon matching **{weapon}**.", ephemeral=True
                    )
                    return
            else:
                melee = [w for w in weapons if w.get("parry")]
                if melee:
                    w = melee[0]
                    target = _resolve_defense_value(w.get("parry", ""), w.get("level", 10))
                    label = f"{char_name} — Parry ({w.get('source', 'Unknown')})"
                else:
                    target = 8
                    label = f"{char_name} — Parry (unarmed)"

        elif defense_type == "block":
            weapons = _collect_weapons(equipment, traits)
            shields = [w for w in weapons if w.get("block")]
            if shields:
                w = shields[0]
                target = _resolve_defense_value(w.get("block", ""), w.get("level", 10))
                label = f"{char_name} — Block ({w.get('source', 'Unknown')})"
            else:
                await interaction.response.send_message(
                    "No shield found for blocking.", ephemeral=True
                )
                return

        label += format_modifier_suffix(modifier)

        result = check(target, modifier)
        embed = embeds.check_embed(result, label)
        await interaction.response.send_message(embed=embed)

    @app_commands.checks.cooldown(2, 5.0)
    @app_commands.command(name="hit-location", description="Roll a Random Hit Location (3d6)")
    async def hit_location(self, interaction: discord.Interaction) -> None:
        result = roll_hit_location()
        embed = embeds.hit_location_embed(result)
        await interaction.response.send_message(embed=embed)


# --------------------------------------------------------------------------- #
# Combat Tracker group
# --------------------------------------------------------------------------- #

@app_commands.guild_only()
@app_commands.default_permissions(send_messages=True)
class CombatTrackerGroup(commands.GroupCog, group_name="combat"):
    "Combat Tracker Commands."

    def __init__(self, bot: GURPSBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self._cleanup_task.start()

    async def cog_unload(self) -> None:
        self._cleanup_task.cancel()

    @tasks.loop(hours=1)
    async def _cleanup_task(self) -> None:
        try:
            async with self.bot.db() as session:
                count = await cleanup_stale_combats(session)
                if count:
                    await session.commit()
                    log.info("Cleaned up %d stale combats", count)
        except Exception:
            log.exception("Stale combat cleanup failed")

    @_cleanup_task.before_loop
    async def _before_cleanup(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.checks.cooldown(1, 5.0)
    @app_commands.command(name="start", description="Start a New Combat in This Channel")
    async def start(self, interaction: discord.Interaction) -> None:
        async with interaction.client.db() as session:
            try:
                combat = await start_combat(
                    session, interaction.guild_id, interaction.channel_id, interaction.user.id,
                )
            except ValueError as e:
                await interaction.response.send_message(str(e), ephemeral=True)
                return

            embed = embeds.combat_tracker_embed(combat)
            view = get_tracker_view()
            await interaction.response.send_message(embed=embed, view=view)

            # commit even if the message-id fetch fails; losing message_id only
            # costs tracker auto-refresh, rolling back would lose the combat
            try:
                msg = await interaction.original_response()
                combat.message_id = msg.id
            except discord.HTTPException:
                log.warning("Could not fetch tracker message id at combat start")
            await session.commit()

    @app_commands.command(name="join", description="Join the Current Combat With Your Active Character")
    async def join(self, interaction: discord.Interaction) -> None:
        async with CombatContext(interaction) as ctx:
            if not ctx.ok:
                return

            try:
                char = await require_active_character(ctx.session, interaction.user.id, interaction.guild_id)
            except NoActiveCharacter:
                await interaction.response.send_message("No active character. Use `/import` first.", ephemeral=True)
                return

            try:
                pc = await add_pc_combatant(ctx.session, ctx.combat, char.id, char.name, interaction.user.id)
            except ValueError as e:
                await interaction.response.send_message(str(e), ephemeral=True)
                return

            await ctx.commit()
            await ctx.respond_and_refresh(
                f"**{pc.name}** joined combat (Speed {pc.basic_speed})."
            )

    @app_commands.command(name="add-npc", description="Add an NPC to Combat (GM Only)")
    @app_commands.describe(
        name="NPC name",
        speed="Basic Speed",
        hp="Hit Points",
        fp="Fatigue Points",
        dx="DX (for tie-breaking)",
        ht="HT (for consciousness rolls)",
    )
    async def add_npc(
        self,
        interaction: discord.Interaction,
        name: str,
        speed: float,
        hp: int,
        fp: int = 10,
        dx: int = 10,
        ht: int = 10,
    ) -> None:
        name = sanitize_name(name)
        if not name:
            await interaction.response.send_message(
                "NPC name is empty after removing special characters.", ephemeral=True,
            )
            return

        async with CombatContext(interaction) as ctx:
            if not ctx.ok:
                return
            ctx.cs.require_gm()
            npc = await add_npc_combatant(ctx.session, ctx.combat, name, speed, hp, fp, dx=dx, ht=ht)
            await ctx.commit()
            await ctx.respond_and_refresh(
                f"Added **{npc.name}** (Speed {npc.basic_speed}, HP {npc.hp_max})."
            )

    @app_commands.command(name="leave", description="Leave the Current Combat")
    async def leave(self, interaction: discord.Interaction) -> None:
        async with CombatContext(interaction) as ctx:
            if not ctx.ok:
                return
            my_combatant = ctx.cs.find_own_combatant()
            if not my_combatant:
                await interaction.response.send_message("You're not in this combat.", ephemeral=True)
                return

            combatant_name = my_combatant.name
            await remove_combatant(ctx.session, ctx.combat, my_combatant.id)
            await ctx.commit()
            await ctx.respond_and_refresh(f"**{combatant_name}** left combat.")

    @app_commands.command(name="remove", description="Remove a Combatant (GM Only)")
    @app_commands.describe(target="Combatant name")
    @app_commands.autocomplete(target=_combatant_name_autocomplete)
    async def remove(self, interaction: discord.Interaction, target: str) -> None:
        async with CombatContext(interaction) as ctx:
            if not ctx.ok:
                return
            ctx.cs.require_gm()
            c = ctx.cs.find_combatant(target)
            combatant_name = c.name
            await remove_combatant(ctx.session, ctx.combat, c.id)
            await ctx.commit()
            await ctx.respond_and_refresh(f"Removed **{combatant_name}** from combat.")

    @app_commands.command(name="hp", description="Modify a Combatant's HP")
    @app_commands.describe(
        target="Combatant name",
        amount="HP change (negative = damage, positive = heal)",
        location="Hit location — only affects a major-wound knockdown roll (B420)",
    )
    @app_commands.choices(location=[
        app_commands.Choice(name="Face (-5)", value="face"),
        app_commands.Choice(name="Skull (-10)", value="skull"),
        app_commands.Choice(name="Eye (-10)", value="eye"),
        app_commands.Choice(name="Groin (-10)", value="groin"),
        app_commands.Choice(name="Vitals (-10, crushing)", value="vitals"),
    ])
    @app_commands.autocomplete(target=_combatant_name_autocomplete)
    async def hp_cmd(
        self,
        interaction: discord.Interaction,
        target: str,
        amount: int,
        location: str | None = None,
    ) -> None:
        async with CombatContext(interaction) as ctx:
            if not ctx.ok:
                return
            c = ctx.cs.find_combatant(target)
            ctx.cs.require_gm_or_owner(c)
            combatant, warning = await modify_hp(ctx.session, c.id, amount)

            # B420: major wound triggers a knockdown/stun roll unless already down
            # (dead/unconscious don't roll); resolve before commit so hp + status
            # persist together
            knockdown_line = ""
            injury = -amount if amount < 0 else 0
            already_down = {
                StatusEffect.DEAD.value, StatusEffect.UNCONSCIOUS.value,
            } & set(combatant.status_effects or [])
            if is_major_wound(injury, combatant.hp_max) and not already_down:
                # B420: roll vs higher of HT/Will, minus location penalty
                base_target = max(combatant.ht, combatant.will)
                mod = knockdown_modifier(location)
                roll = check(base_target, mod)
                outcome = resolve_knockdown(
                    succeeded=roll.outcome.succeeded,
                    margin=roll.margin,
                    critical_failure=roll.outcome is Outcome.CRITICAL_FAILURE,
                )
                applied = knockdown_statuses(outcome)
                for status in applied:
                    await add_status(ctx.session, c.id, status)
                loc_note = f", {location} {mod}" if mod else ""
                knockdown_line = (
                    f"\nKnockdown & stunning (HT/Will {base_target}{loc_note}): rolled "
                    f"{roll.rolled} vs {roll.target} \u2014 {knockdown_label(outcome)}"
                    + (f" ({', '.join(applied)} applied)." if applied else ".")
                )

            await ctx.commit()

            sign = "+" if amount > 0 else ""
            msg = f"**{combatant.name}** HP {sign}{amount} \u2192 {combatant.hp_current}/{combatant.hp_max}"
            if warning:
                msg += f"\n{warning}"
            # B419/B420 shock + major-wound advisories; no-op on heals
            for line in injury_effects(-amount, combatant.hp_max):
                msg += f"\n{line}"
            msg += knockdown_line
            await ctx.respond_and_refresh(msg)

    @app_commands.command(name="fp", description="Modify a Combatant's FP")
    @app_commands.describe(target="Combatant name", amount="FP change (negative = spend, positive = recover)")
    @app_commands.autocomplete(target=_combatant_name_autocomplete)
    async def fp_cmd(
        self,
        interaction: discord.Interaction,
        target: str,
        amount: int,
    ) -> None:
        async with CombatContext(interaction) as ctx:
            if not ctx.ok:
                return
            c = ctx.cs.find_combatant(target)
            ctx.cs.require_gm_or_owner(c)
            combatant = await modify_fp(ctx.session, c.id, amount)
            await ctx.commit()

            sign = "+" if amount > 0 else ""
            await ctx.respond_and_refresh(
                f"**{combatant.name}** FP {sign}{amount} \u2192 {combatant.fp_current}/{combatant.fp_max}"
            )

    @app_commands.command(name="status", description="Add or Remove a Status Effect")
    @app_commands.describe(target="Combatant name", effect="Status effect", action="Add or remove")
    @app_commands.autocomplete(target=_combatant_name_autocomplete)
    @app_commands.choices(
        effect=[app_commands.Choice(name=e.value, value=e.value) for e in StatusEffect],
        action=[
            app_commands.Choice(name="Add", value="add"),
            app_commands.Choice(name="Remove", value="remove"),
        ],
    )
    async def status_cmd(
        self,
        interaction: discord.Interaction,
        target: str,
        effect: str,
        action: str = "add",
    ) -> None:
        async with CombatContext(interaction) as ctx:
            if not ctx.ok:
                return
            c = ctx.cs.find_combatant(target)
            ctx.cs.require_gm_or_owner(c)

            try:
                if action == "add":
                    await add_status(ctx.session, c.id, effect)
                    verb = "added to"
                else:
                    await remove_status(ctx.session, c.id, effect)
                    verb = "removed from"
            except ValueError as e:
                await interaction.response.send_message(str(e), ephemeral=True)
                return

            await ctx.commit()
            await ctx.respond_and_refresh(f"**{effect}** {verb} **{c.name}**.")

    @app_commands.command(name="maneuver", description="Set Your Maneuver for This Turn")
    @app_commands.describe(maneuver="GURPS maneuver")
    @app_commands.choices(
        maneuver=[app_commands.Choice(name=m.value, value=m.value) for m in Maneuver],
    )
    async def maneuver_cmd(
        self,
        interaction: discord.Interaction,
        maneuver: str,
    ) -> None:
        async with CombatContext(interaction) as ctx:
            if not ctx.ok:
                return
            ctx.cs.require_turn_or_gm()

            current = ctx.cs.current_combatant
            if not current:
                await interaction.response.send_message("No combatants.", ephemeral=True)
                return

            effects = set(current.status_effects or [])
            if StatusEffect.STUNNED in effects and maneuver != Maneuver.DO_NOTHING.value:
                await interaction.response.send_message(
                    f"**{current.name}** is Stunned and must Do Nothing.", ephemeral=True
                )
                return

            await set_maneuver(ctx.session, current.id, maneuver)
            await ctx.commit()
            await ctx.respond_and_refresh(f"**{current.name}** chooses **{maneuver}**.")

    @app_commands.command(name="defend", description="Roll an Active Defense (auto-tracks cumulative Parry penalties)")
    @app_commands.describe(
        defense_type="Dodge, Parry, or Block",
        value="Your defense score (the Dodge/Parry/Block target number)",
        modifier="Extra modifier — e.g. +3 for a retreat",
        target="Combatant defending (GM only; defaults to your own)",
        hidden="Roll in secret (GM blind roll): only you see the result",
    )
    @app_commands.choices(defense_type=[
        app_commands.Choice(name="Dodge", value="dodge"),
        app_commands.Choice(name="Parry", value="parry"),
        app_commands.Choice(name="Block", value="block"),
    ])
    @app_commands.autocomplete(target=_combatant_name_autocomplete)
    async def defend_tracked(
        self,
        interaction: discord.Interaction,
        defense_type: str,
        value: int,
        modifier: int = 0,
        target: str | None = None,
        hidden: bool = False,
    ) -> None:
        async with CombatContext(interaction) as ctx:
            if not ctx.ok:
                return

            if target:
                ctx.cs.require_gm()
                combatant = ctx.cs.find_combatant(target)
            else:
                combatant = ctx.cs.find_own_combatant()
                if combatant is None:
                    await interaction.response.send_message(
                        "You're not in this combat. (GMs: pass a `target`.)", ephemeral=True,
                    )
                    return

            combatant_name = combatant.name
            combatant_id = combatant.id
            penalty, note = defense_penalty(
                defense_type, combatant.parries_this_turn, combatant.blocks_this_turn,
            )
            result = check(value, penalty + modifier)

            # dodge is unlimited; parry/block accrue and reset via advance_turn
            if defense_type in ("parry", "block"):
                await record_defense(ctx.session, combatant_id, defense_type)
                await ctx.commit()

            label = (
                f"{combatant_name} — {defense_type.capitalize()}"
                f"{format_modifier_suffix(penalty + modifier)}"
            )
            embed = embeds.check_embed(result, label)
            if note:
                embed.add_field(name="Note", value=note, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=hidden)

    @app_commands.checks.cooldown(1, 5.0)
    @app_commands.command(name="end", description="End the Current Combat (GM Only)")
    async def end(self, interaction: discord.Interaction) -> None:
        async with CombatContext(interaction) as ctx:
            if not ctx.ok:
                return
            ctx.cs.require_gm()
            tracker = TrackerManager(interaction.channel, ctx.combat.message_id)
            await end_combat(ctx.session, interaction.guild_id, interaction.channel_id)
            await ctx.commit()
            # ack before the tracker-clear edit so the interaction doesn't expire
            await interaction.response.send_message("Combat ended.")
            await tracker.end()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CombatCog(bot))
    await bot.add_cog(CombatTrackerGroup(bot))
