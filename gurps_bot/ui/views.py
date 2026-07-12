from __future__ import annotations

import math

import discord

from gurps_bot.services.combat_session import CombatPermissionError, CombatSession


class PaginatorView(discord.ui.View):
    def __init__(
        self,
        pages: list[discord.Embed],
        author_id: int,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.pages = pages
        self.author_id = author_id
        self.current = 0
        self.message: discord.Message | None = None
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current >= len(self.pages) - 1

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[union-attr]
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your character list.", ephemeral=True)
            return
        self.current = max(0, self.current - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your character list.", ephemeral=True)
            return
        self.current = min(len(self.pages) - 1, self.current + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)


class ConfirmView(discord.ui.View):
    def __init__(self, author_id: int, timeout: float = 30.0) -> None:
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.confirmed: bool | None = None
        self.message: discord.Message | None = None

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[union-attr]
        if self.message:
            try:
                await self.message.edit(content="Timed out.", view=self)
            except discord.NotFound:
                pass

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your action.", ephemeral=True)
            return
        self.confirmed = True
        self.stop()
        await interaction.response.edit_message(content="Confirmed.", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your action.", ephemeral=True)
            return
        self.confirmed = False
        self.stop()
        await interaction.response.edit_message(content="Cancelled.", view=None)


class RollDamageView(discord.ui.View):
    def __init__(self, damage_str: str, timeout: float = 120.0, *, hidden: bool = False) -> None:
        super().__init__(timeout=timeout)
        self.damage_str = damage_str
        self.hidden = hidden
        self.message: discord.Message | None = None

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[union-attr]
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

    @discord.ui.button(label="Roll Damage", style=discord.ButtonStyle.danger, emoji="\U0001f3b2")
    async def roll_damage_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button,
    ) -> None:
        from gurps_bot.mechanics.damage import parse_gcs_damage, roll_damage
        from gurps_bot.ui.embeds import damage_embed

        dice_expr, damage_type = parse_gcs_damage(self.damage_str)
        try:
            result = roll_damage(dice_expr, damage_type)
        except ValueError:
            await interaction.response.send_message(
                f"Could not parse damage: {self.damage_str}", ephemeral=True
            )
            return

        embed = damage_embed(result)
        await interaction.response.send_message(embed=embed, ephemeral=self.hidden)


# no CombatContext here — button success path needs edit_message, not send_message
class CombatTrackerView(discord.ui.View):
    """persistent (custom_id, timeout=None) — survives restarts; each press re-fetches combat"""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Next Turn", style=discord.ButtonStyle.primary,
        custom_id="combat_next_turn", row=0,
    )
    async def next_turn_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button,
    ) -> None:
        from gurps_bot.services.combat import advance_turn, current_combatant, get_combat
        from gurps_bot.ui.embeds import combat_tracker_embed, turn_announcement

        async with interaction.client.db() as session:
            combat = await get_combat(session, interaction.guild_id, interaction.channel_id)
            if not combat:
                await interaction.response.send_message("No active combat.", ephemeral=True)
                return
            if not combat.combatants:
                await interaction.response.send_message("No combatants yet.", ephemeral=True)
                return

            cs = CombatSession(combat, interaction.user.id)
            try:
                cs.require_turn_or_gm()
            except CombatPermissionError as e:
                await interaction.response.send_message(str(e), ephemeral=True)
                return

            msg = advance_turn(combat)
            current = current_combatant(combat)
            await session.commit()
            embed = combat_tracker_embed(combat)
            announcement = turn_announcement(current, msg)

        await interaction.response.edit_message(embed=embed, view=self)
        if announcement:
            # embed mentions don't ping — send in content with users allowed
            await interaction.followup.send(
                announcement,
                ephemeral=False,
                allowed_mentions=discord.AllowedMentions(users=True),
            )

    @discord.ui.button(
        label="Prev Turn", style=discord.ButtonStyle.secondary,
        custom_id="combat_prev_turn", row=0,
    )
    async def prev_turn_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button,
    ) -> None:
        from gurps_bot.services.combat import get_combat, previous_turn
        from gurps_bot.ui.embeds import combat_tracker_embed

        async with interaction.client.db() as session:
            combat = await get_combat(session, interaction.guild_id, interaction.channel_id)
            if not combat:
                await interaction.response.send_message("No active combat.", ephemeral=True)
                return

            try:
                CombatSession(combat, interaction.user.id).require_gm()
            except CombatPermissionError as e:
                await interaction.response.send_message(str(e), ephemeral=True)
                return

            previous_turn(combat)
            await session.commit()
            embed = combat_tracker_embed(combat)

        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="Add NPC", style=discord.ButtonStyle.secondary,
        custom_id="combat_add_npc", row=0,
    )
    async def add_npc_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button,
    ) -> None:
        from gurps_bot.services.combat import get_combat

        async with interaction.client.db() as session:
            combat = await get_combat(session, interaction.guild_id, interaction.channel_id)

        if not combat:
            await interaction.response.send_message("No active combat.", ephemeral=True)
            return

        try:
            CombatSession(combat, interaction.user.id).require_gm()
        except CombatPermissionError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        await interaction.response.send_modal(AddNPCModal())

    @discord.ui.button(
        label="End Combat", style=discord.ButtonStyle.danger,
        custom_id="combat_end", row=0,
    )
    async def end_combat_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button,
    ) -> None:
        from gurps_bot.services.combat import end_combat, get_combat

        async with interaction.client.db() as session:
            combat = await get_combat(session, interaction.guild_id, interaction.channel_id)
            if not combat:
                await interaction.response.send_message("No active combat.", ephemeral=True)
                return

            try:
                CombatSession(combat, interaction.user.id).require_gm()
            except CombatPermissionError as e:
                await interaction.response.send_message(str(e), ephemeral=True)
                return

            await end_combat(session, interaction.guild_id, interaction.channel_id)
            await session.commit()

        await interaction.response.edit_message(
            content="Combat ended.", embed=None, view=None,
        )


class AddNPCModal(discord.ui.Modal, title="Add NPC"):
    npc_name = discord.ui.TextInput(
        label="Name", placeholder="Goblin Warrior", max_length=200,
    )
    speed = discord.ui.TextInput(
        label="Basic Speed", placeholder="5.25",
    )
    hp = discord.ui.TextInput(
        label="HP", placeholder="10",
    )
    fp = discord.ui.TextInput(
        label="FP", placeholder="10", required=False, default="10",
    )
    dx_input = discord.ui.TextInput(
        label="DX (for Tie-Breaking)", placeholder="10", required=False, default="10",
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from gurps_bot.services.combat import add_npc_combatant, get_combat
        from gurps_bot.ui.tracker import TrackerManager
        from gurps_bot.utils.sanitize import sanitize_name

        try:
            speed_val = float(self.speed.value)
            if not math.isfinite(speed_val):
                # float() happily parses "nan"/"inf"; a NaN speed silently
                # poisons the initiative sort. The service guards too.
                raise ValueError
            hp_val = int(self.hp.value)
            fp_val = int(self.fp.value or "10")
            dx_val = int(self.dx_input.value or "10")
        except ValueError:
            await interaction.response.send_message(
                "Invalid numbers. Speed must be a finite decimal, HP/FP/DX must be integers.",
                ephemeral=True,
            )
            return

        npc_name = sanitize_name(self.npc_name.value)
        if not npc_name:
            await interaction.response.send_message(
                "NPC name is empty after removing special characters.", ephemeral=True,
            )
            return

        async with interaction.client.db() as session:
            combat = await get_combat(session, interaction.guild_id, interaction.channel_id)
            if not combat:
                await interaction.response.send_message("No active combat.", ephemeral=True)
                return

            # modal open was gm-gated but submit is a new interaction — re-check
            try:
                CombatSession(combat, interaction.user.id).require_gm()
            except CombatPermissionError as e:
                await interaction.response.send_message(str(e), ephemeral=True)
                return

            await add_npc_combatant(
                session, combat, npc_name, speed_val, hp_val, fp_val, dx=dx_val,
            )
            await session.commit()

        # ack within the modal's 3s window before the tracker edit — a rate-limited
        # edit would blow the deadline with the NPC already committed
        await interaction.response.send_message(
            f"Added **{npc_name}** (Speed {speed_val}, HP {hp_val}).",
            ephemeral=True,
        )
        tracker = TrackerManager(interaction.channel, combat.message_id)
        await tracker.refresh(combat)
