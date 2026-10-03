"""get_dashboard scoping (channel timers/combat, user study, note visibility) + limits."""

from __future__ import annotations

from gurps_bot.mechanics.study import METHOD_MULTIPLIERS
from gurps_bot.services.combat import start_combat
from gurps_bot.services.dashboard import get_dashboard
from gurps_bot.services.notes import add_note
from gurps_bot.services.study import log_study
from gurps_bot.services.timers import add_timer, tick_timers

USER = 111
OTHER = 222
GUILD = 900
CHANNEL = 901
_METHOD = next(iter(METHOD_MULTIPLIERS))  # any valid study method


class TestDashboard:
    async def test_aggregates_channel_and_user_state(self, db_session):
        await add_timer(db_session, GUILD, CHANNEL, "Haste", 3, "seconds")
        await log_study(db_session, USER, "Broadsword", _METHOD, 4.0)
        await log_study(db_session, USER, "Stealth", _METHOD, 2.0)
        await add_note(
            db_session, discord_user_id=USER, title="Plan", guild_id=GUILD, channel_id=CHANNEL
        )
        await start_combat(db_session, GUILD, CHANNEL, USER)
        await db_session.commit()

        dash = await get_dashboard(
            db_session, guild_id=GUILD, channel_id=CHANNEL, user_id=USER
        )
        assert [t.label for t in dash.timers] == ["Haste"]
        assert len(dash.recent_study) == 2
        assert [n.title for n in dash.recent_notes] == ["Plan"]
        assert dash.combat is not None

    async def test_live_timers_only(self, db_session):
        await add_timer(db_session, GUILD, CHANNEL, "Gone", 1, "seconds")
        await tick_timers(db_session, GUILD, CHANNEL, "seconds", 1)  # remaining -> 0
        await db_session.commit()
        dash = await get_dashboard(
            db_session, guild_id=GUILD, channel_id=CHANNEL, user_id=USER
        )
        assert dash.timers == []

    async def test_secret_notes_of_others_excluded(self, db_session):
        await add_note(
            db_session, discord_user_id=OTHER, title="Twist",
            guild_id=GUILD, channel_id=CHANNEL, gm_secret=True,
        )
        await add_note(
            db_session, discord_user_id=USER, title="Mine", guild_id=GUILD, channel_id=CHANNEL
        )
        await db_session.commit()
        dash = await get_dashboard(
            db_session, guild_id=GUILD, channel_id=CHANNEL, user_id=USER
        )
        titles = [n.title for n in dash.recent_notes]
        assert "Mine" in titles
        assert "Twist" not in titles

    async def test_no_guild_skips_channel_scoped(self, db_session):
        await log_study(db_session, USER, "Climbing", _METHOD, 1.0)
        await db_session.commit()
        dash = await get_dashboard(
            db_session, guild_id=None, channel_id=None, user_id=USER
        )
        assert dash.timers == []
        assert dash.combat is None
        assert len(dash.recent_study) == 1  # user-scoped state still shows

    async def test_study_limit(self, db_session):
        for i in range(7):
            await log_study(db_session, USER, f"Skill{i}", _METHOD, 1.0)
        await db_session.commit()
        dash = await get_dashboard(
            db_session, guild_id=GUILD, channel_id=CHANNEL, user_id=USER, study_limit=5
        )
        assert len(dash.recent_study) == 5
