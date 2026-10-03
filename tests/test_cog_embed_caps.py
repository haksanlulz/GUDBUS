"""Embed fields built from user input must stay under Discord's 1024-char cap or the command dies silently."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gurps_bot.cogs.calc_combat import _parse_distances
from gurps_bot.cogs.gmscreen import _dashboard_embed


class TestDashboardFieldCap:
    def test_live_timers_field_capped(self):
        t = MagicMock()
        t.label = "L" * 200
        t.target = "T" * 200
        t.remaining = 1
        t.total = 9
        t.unit = "turns"
        dash = MagicMock()
        dash.timers = [t for _ in range(10)]
        dash.combat = None
        dash.recent_study = []
        dash.recent_notes = []

        embed = _dashboard_embed(dash)
        field = next(f for f in embed.fields if f.name == "Live Timers")
        assert len(field.value) <= 1024


class TestExplosionDistanceCap:
    def test_too_many_distances_raises(self):
        with pytest.raises(ValueError, match="[Tt]oo many"):
            _parse_distances(" ".join(str(i) for i in range(1, 30)))

    def test_normal_count_ok(self):
        assert _parse_distances("0 2 5 10") == [0, 2, 5, 10]
