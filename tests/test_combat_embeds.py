from gurps_bot.db.models import Combat, Combatant
from gurps_bot.mechanics.combat_constants import StatusEffect
from gurps_bot.ui.embeds import COMBAT_ORANGE, combat_tracker_embed, turn_announcement
from gurps_bot.ui.formatters import format_combatant_line


class TestFormatCombatantLine:
    def test_basic_line(self):
        line = format_combatant_line(
            name="Goblin",
            basic_speed=5.25,
            hp_current=8,
            hp_max=10,
            fp_current=10,
            fp_max=10,
            status_effects=[],
            maneuver="Attack",
            is_current=False,
            is_out=False,
        )
        assert "**Goblin**" in line
        assert "Spd 5.25" in line
        assert "8/10" in line
        assert "Attack" in line

    def test_current_turn_marker(self):
        line = format_combatant_line(
            "Hero", 6.0, 12, 12, 10, 10, [], None, is_current=True, is_out=False,
        )
        assert "\u25b6" in line  # right-pointing triangle

    def test_dead_strikethrough(self):
        line = format_combatant_line(
            "Dead Guy", 5.0, -5, 10, 10, 10,
            [StatusEffect.DEAD], None, is_current=False, is_out=True,
        )
        assert "~~Dead Guy~~" in line

    def test_status_icons_shown(self):
        line = format_combatant_line(
            "Stunned", 5.0, 10, 10, 10, 10,
            [StatusEffect.STUNNED], None, is_current=False, is_out=False,
        )
        assert "\u26a1" in line  # lightning bolt for Stunned


class TestCombatTrackerEmbed:
    def _make_combat(self, combatants=None):
        combat = Combat(
            guild_id=1, channel_id=1, started_by=1,
            round_number=1, current_index=0,
        )
        combat.combatants = combatants or []
        return combat

    def _make_combatant(self, name, speed, hp=10, slot=0, status=None):
        return Combatant(
            name=name, basic_speed=speed, dx=10, tiebreaker=slot,
            hp_current=hp, hp_max=10, fp_current=10, fp_max=10,
            status_effects=status or [], maneuver=None, slot=slot,
            combat_id=0, is_npc=True,
        )

    def test_empty_combat(self):
        combat = self._make_combat()
        embed = combat_tracker_embed(combat)
        assert embed.color == COMBAT_ORANGE
        assert "Round 1" in embed.title
        assert "No combatants" in embed.description

    def test_with_combatants(self):
        c1 = self._make_combatant("Fast", 6.0, slot=0)
        c2 = self._make_combatant("Slow", 5.0, slot=1)
        combat = self._make_combat([c1, c2])
        embed = combat_tracker_embed(combat)
        assert "Fast" in embed.description
        assert "Slow" in embed.description
        # higher speed sorts first
        fast_pos = embed.description.index("Fast")
        slow_pos = embed.description.index("Slow")
        assert fast_pos < slow_pos

    def test_dead_combatant_strikethrough(self):
        dead = self._make_combatant("Victim", 5.0, hp=-5, status=[StatusEffect.DEAD])
        combat = self._make_combat([dead])
        embed = combat_tracker_embed(combat)
        assert "~~Victim~~" in embed.description

    def test_current_turn_highlighted(self):
        c1 = self._make_combatant("Current", 6.0, slot=0)
        c2 = self._make_combatant("Other", 5.0, slot=1)
        combat = self._make_combat([c1, c2])
        combat.current_index = 0
        embed = combat_tracker_embed(combat)
        assert "\u25b6" in embed.description

    def test_highlight_follows_identity_anchor_not_index(self):
        # arrow tracks current_combatant_id, not the bare position; anchor the
        # turn on the slower combatant (sorted second)
        fast = self._make_combatant("Fast", 6.0, slot=0)
        slow = self._make_combatant("Slow", 5.0, slot=1)
        fast.id = 1
        slow.id = 2
        combat = self._make_combat([fast, slow])
        combat.current_index = 0  # stale on purpose; anchor wins
        combat.current_combatant_id = 2  # Slow's turn
        embed = combat_tracker_embed(combat)
        desc = embed.description
        arrow = desc.index("\u25b6")
        # arrow lands on Slow's line, not index 0
        assert arrow > desc.index("Fast")
        assert arrow < desc.index("Slow")

    def test_description_truncates_when_many_combatants(self):
        many = [
            self._make_combatant(f"Combatant Number {i}", 5.0 + i * 0.01, slot=i)
            for i in range(120)
        ]
        combat = self._make_combat(many)
        embed = combat_tracker_embed(combat)
        assert "truncated" in embed.description


class TestTurnAnnouncement:
    def _pc(self, name="Hero", uid=123):
        return Combatant(name=name, discord_user_id=uid, is_npc=False)

    def _npc(self, name="Goblin"):
        return Combatant(name=name, discord_user_id=None, is_npc=True)

    def test_none_combatant_no_note_is_none(self):
        assert turn_announcement(None, None) is None

    def test_pc_is_pinged(self):
        out = turn_announcement(self._pc(uid=555), None)
        assert "<@555>" in out
        assert "your turn" in out.lower()

    def test_npc_is_named_not_pinged(self):
        out = turn_announcement(self._npc("Goblin"), None)
        assert "Goblin" in out
        assert "<@" not in out

    def test_note_is_prepended_to_ping(self):
        out = turn_announcement(self._pc(uid=555), "Round 2 begins.")
        assert out.startswith("Round 2 begins.")
        assert "<@555>" in out

    def test_note_only_when_no_combatant(self):
        assert turn_announcement(None, "All combatants are down.") == "All combatants are down."
