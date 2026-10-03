"""/posture + /target: pure embed builders plus a cog-load collision check"""

from __future__ import annotations

import discord
from discord.ext import commands

from gurps_bot.cogs.body_ref import build_posture_embed, build_target_embed
from gurps_bot.mechanics.hit_location import deliberate_locations, hit_location
from gurps_bot.mechanics.posture import POSTURES


class TestPostureEmbed:
    def test_builds_for_every_posture_and_reflects_owner(self):
        for p in POSTURES:
            embed = build_posture_embed(p.name)
            assert isinstance(embed, discord.Embed)
            assert p.name in embed.title
            blob = "\n".join(f.value for f in embed.fields)
            assert f"{p.attack_penalty:+d}" in blob
            assert p.effect in blob
            for f in embed.fields:
                assert len(f.value) <= 1024

    def test_case_insensitive_lookup(self):
        assert build_posture_embed("standing").title == build_posture_embed("STANDING").title

    def test_unknown_posture_returns_friendly_embed(self):
        embed = build_posture_embed("levitating")
        assert isinstance(embed, discord.Embed)
        blob = (embed.description or "") + "".join(f.value for f in embed.fields)
        assert "Standing" in blob


class TestTargetEmbed:
    def test_builds_for_every_deliberate_location(self):
        for loc in deliberate_locations():
            embed = build_target_embed(loc.name)
            assert loc.name in embed.title
            blob = "\n".join(f.value for f in embed.fields)
            assert str(loc.penalty) in blob
            assert loc.effect in blob
            for f in embed.fields:
                assert len(f.value) <= 1024

    def test_target_penalty_sourced_from_owner(self):
        embed = build_target_embed("Eye")
        blob = "\n".join(f.value for f in embed.fields)
        assert str(hit_location("Eye").penalty) in blob  # -9

    def test_unknown_target_returns_friendly_embed(self):
        embed = build_target_embed("antenna")
        assert isinstance(embed, discord.Embed)
        blob = (embed.description or "") + "".join(f.value for f in embed.fields)
        assert "Eye" in blob or "Vitals" in blob


class TestCogLoads:
    async def test_cog_loads_without_collision(self):
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        try:
            await bot.load_extension("gurps_bot.cogs.body_ref")
            names = [c.name for c in bot.tree.get_commands()]
            assert "posture" in names
            assert "target" in names
            assert len(names) == len(set(names))
        finally:
            await bot.close()

    def test_registered_in_extensions(self):
        from gurps_bot.bot import EXTENSIONS

        assert "gurps_bot.cogs.body_ref" in EXTENSIONS
