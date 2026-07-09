"""importing the service registers the Timer model on Base so create_all sees it"""

from __future__ import annotations

import pytest

from gurps_bot.services.timers import (
    add_timer,
    clear_timers,
    list_timers,
    remove_timer,
    tick_timers,
)

GUILD_ID = 999999999
CHANNEL_ID = 888888888
OTHER_CHANNEL = 777777777
OTHER_GUILD = 666666666


class TestAddTimer:
    async def test_add_basic(self, db_session):
        t = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "Haste", total=3, unit="turns")
        await db_session.commit()
        assert t.id is not None
        assert t.label == "Haste"
        assert t.total == 3
        assert t.remaining == 3  # defaults to total
        assert t.unit == "turns"
        assert t.target is None
        assert t.note == ""

    async def test_label_stripped(self, db_session):
        t = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "  Bleeding  ", total=2, unit="turns")
        await db_session.commit()
        assert t.label == "Bleeding"

    async def test_remaining_defaults_to_total(self, db_session):
        t = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "x", total=5, unit="turns")
        assert t.remaining == 5

    async def test_remaining_supplied(self, db_session):
        t = await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "x", total=5, unit="turns", remaining=2,
        )
        assert t.remaining == 2

    async def test_remaining_clamped_above_total(self, db_session):
        t = await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "x", total=3, unit="turns", remaining=10,
        )
        assert t.remaining == 3  # clamped down to total

    async def test_remaining_clamped_below_zero(self, db_session):
        t = await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "x", total=3, unit="turns", remaining=-5,
        )
        assert t.remaining == 0  # clamped up to 0

    async def test_target_and_note_stored(self, db_session):
        t = await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "Stunned", total=2, unit="turns",
            target="Goblin", note="from Daze",
        )
        await db_session.commit()
        assert t.target == "Goblin"
        assert t.note == "from Daze"

    async def test_target_stored_as_given(self, db_session):
        # stored as given (case preserved); matching is case-insensitive at tick
        t = await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "x", total=2, unit="turns", target="GoBLiN",
        )
        assert t.target == "GoBLiN"

    async def test_unknown_unit_raises(self, db_session):
        with pytest.raises(ValueError, match="Unknown unit"):
            await add_timer(db_session, GUILD_ID, CHANNEL_ID, "x", total=2, unit="rounds")

    async def test_total_zero_raises(self, db_session):
        with pytest.raises(ValueError, match="total must be >= 1"):
            await add_timer(db_session, GUILD_ID, CHANNEL_ID, "x", total=0, unit="turns")

    async def test_total_negative_raises(self, db_session):
        with pytest.raises(ValueError, match="total must be >= 1"):
            await add_timer(db_session, GUILD_ID, CHANNEL_ID, "x", total=-3, unit="turns")

    async def test_all_units_accepted(self, db_session):
        for unit in ("turns", "seconds", "minutes", "hours"):
            t = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "x", total=2, unit=unit)
            assert t.unit == unit
        await db_session.commit()


class TestTickTimers:
    async def test_basic_decrement_not_expired(self, db_session):
        await add_timer(db_session, GUILD_ID, CHANNEL_ID, "Haste", total=3, unit="turns")
        await db_session.commit()

        expired = await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", 1)
        await db_session.commit()
        assert expired == []  # 3 -> 2, not yet expired

        live = await list_timers(db_session, GUILD_ID, CHANNEL_ID)
        assert live[0].remaining == 2

    async def test_expiry_reported_on_crossing_tick(self, db_session):
        t = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "x", total=2, unit="turns")
        await db_session.commit()

        first = await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", 1)
        assert first == []  # 2 -> 1

        second = await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", 1)
        await db_session.commit()
        assert [x.id for x in second] == [t.id]  # 1 -> 0, expired now
        assert second[0].remaining == 0

    async def test_already_expired_not_reannounced(self, db_session):
        await add_timer(db_session, GUILD_ID, CHANNEL_ID, "x", total=1, unit="turns")
        await db_session.commit()

        first = await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", 1)
        assert len(first) == 1  # expires, returned once

        second = await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", 1)
        await db_session.commit()
        assert second == []  # not re-announced

        live = await list_timers(db_session, GUILD_ID, CHANNEL_ID)
        assert live[0].remaining == 0  # floored, not -1

    async def test_over_tick_clamps_to_zero(self, db_session):
        t = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "x", total=2, unit="turns")
        await db_session.commit()

        expired = await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", amount=5)
        await db_session.commit()
        assert [x.id for x in expired] == [t.id]
        assert expired[0].remaining == 0  # max(0, 2-5)

    async def test_units_independent(self, db_session):
        a = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "A", total=3, unit="turns")
        b = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "B", total=3, unit="seconds")
        await db_session.commit()

        expired = await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", 1)
        await db_session.commit()
        assert expired == []

        timers = {t.id: t for t in await list_timers(db_session, GUILD_ID, CHANNEL_ID)}
        assert timers[a.id].remaining == 2  # turns-timer decremented
        assert timers[b.id].remaining == 3  # seconds-timer untouched

    async def test_case_insensitive_per_target(self, db_session):
        gob = await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "x", total=2, unit="turns", target="Goblin",
        )
        orc = await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "x", total=2, unit="turns", target="Orc",
        )
        await db_session.commit()

        await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", 1, target="goblin")
        await db_session.commit()

        timers = {t.id: t for t in await list_timers(db_session, GUILD_ID, CHANNEL_ID)}
        assert timers[gob.id].remaining == 1  # decremented (case-insensitive match)
        assert timers[orc.id].remaining == 2  # untouched

    async def test_untargeted_tick_hits_all_including_targeted(self, db_session):
        scene = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "scene", total=3, unit="turns")
        gob = await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "g", total=3, unit="turns", target="Goblin",
        )
        await db_session.commit()

        await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", 1)  # target=None
        await db_session.commit()

        timers = {t.id: t for t in await list_timers(db_session, GUILD_ID, CHANNEL_ID)}
        assert timers[scene.id].remaining == 2
        assert timers[gob.id].remaining == 2  # targeted timer also decremented

    async def test_tick_empty_channel_returns_empty(self, db_session):
        expired = await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", 1)
        assert expired == []

    async def test_tick_unused_unit_decrements_nothing(self, db_session):
        a = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "A", total=3, unit="turns")
        await db_session.commit()

        expired = await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "minutes", 1)
        await db_session.commit()
        assert expired == []

        live = await list_timers(db_session, GUILD_ID, CHANNEL_ID)
        assert live[0].id == a.id
        assert live[0].remaining == 3  # untouched

    async def test_amount_zero_raises(self, db_session):
        with pytest.raises(ValueError):
            await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", 0)

    async def test_amount_negative_raises(self, db_session):
        with pytest.raises(ValueError):
            await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", -2)

    async def test_tick_unknown_unit_raises(self, db_session):
        with pytest.raises(ValueError, match="Unknown unit"):
            await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "rounds", 1)

    async def test_tick_returns_insertion_order(self, db_session):
        # two timers crossing on the same tick come back in id ASC order
        t1 = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "first", total=1, unit="turns")
        t2 = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "second", total=1, unit="turns")
        await db_session.commit()

        expired = await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", 1)
        await db_session.commit()
        assert [x.id for x in expired] == [t1.id, t2.id]

    async def test_tick_scoped_to_channel(self, db_session):
        here = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "here", total=2, unit="turns")
        there = await add_timer(db_session, GUILD_ID, OTHER_CHANNEL, "there", total=2, unit="turns")
        await db_session.commit()

        await tick_timers(db_session, GUILD_ID, CHANNEL_ID, "turns", 1)
        await db_session.commit()

        here_live = await list_timers(db_session, GUILD_ID, CHANNEL_ID)
        there_live = await list_timers(db_session, GUILD_ID, OTHER_CHANNEL)
        assert here_live[0].remaining == 1
        assert there_live[0].remaining == 2  # other channel untouched


class TestListTimers:
    async def test_empty_returns_empty(self, db_session):
        assert await list_timers(db_session, GUILD_ID, CHANNEL_ID) == []

    async def test_ordered_by_remaining_asc(self, db_session):
        await add_timer(db_session, GUILD_ID, CHANNEL_ID, "five", total=5, unit="turns")
        await add_timer(db_session, GUILD_ID, CHANNEL_ID, "one", total=1, unit="turns")
        await add_timer(db_session, GUILD_ID, CHANNEL_ID, "three", total=3, unit="turns")
        await db_session.commit()

        timers = await list_timers(db_session, GUILD_ID, CHANNEL_ID)
        assert [t.remaining for t in timers] == [1, 3, 5]  # soonest-to-expire first

    async def test_filter_by_target_case_insensitive(self, db_session):
        await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "g", total=2, unit="turns", target="Goblin",
        )
        await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "o", total=2, unit="turns", target="Orc",
        )
        await db_session.commit()

        timers = await list_timers(db_session, GUILD_ID, CHANNEL_ID, target="goblin")
        assert len(timers) == 1
        assert timers[0].target == "Goblin"

    async def test_include_expired_false_filters(self, db_session):
        await add_timer(db_session, GUILD_ID, CHANNEL_ID, "live", total=3, unit="turns")
        await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "done", total=2, unit="turns", remaining=0,
        )
        await db_session.commit()

        all_t = await list_timers(db_session, GUILD_ID, CHANNEL_ID, include_expired=True)
        live = await list_timers(db_session, GUILD_ID, CHANNEL_ID, include_expired=False)
        assert len(all_t) == 2
        assert len(live) == 1
        assert live[0].label == "live"


class TestRemoveTimer:
    async def test_remove_existing(self, db_session):
        t = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "x", total=2, unit="turns")
        await db_session.commit()

        ok = await remove_timer(db_session, GUILD_ID, CHANNEL_ID, t.id)
        await db_session.commit()
        assert ok is True
        assert await list_timers(db_session, GUILD_ID, CHANNEL_ID) == []

    async def test_remove_nonexistent(self, db_session):
        ok = await remove_timer(db_session, GUILD_ID, CHANNEL_ID, 99999)
        assert ok is False

    async def test_remove_cross_channel_scope_guard(self, db_session):
        t = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "x", total=2, unit="turns")
        await db_session.commit()

        ok = await remove_timer(db_session, GUILD_ID, OTHER_CHANNEL, t.id)
        await db_session.commit()
        assert ok is False  # scope guard: not in that channel

        still = await list_timers(db_session, GUILD_ID, CHANNEL_ID)
        assert len(still) == 1  # original still present

    async def test_remove_cross_guild_scope_guard(self, db_session):
        t = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "x", total=2, unit="turns")
        await db_session.commit()

        ok = await remove_timer(db_session, OTHER_GUILD, CHANNEL_ID, t.id)
        await db_session.commit()
        assert ok is False
        assert len(await list_timers(db_session, GUILD_ID, CHANNEL_ID)) == 1


class TestClearTimers:
    async def test_clear_all_in_channel(self, db_session):
        await add_timer(db_session, GUILD_ID, CHANNEL_ID, "a", total=2, unit="turns")
        await add_timer(db_session, GUILD_ID, CHANNEL_ID, "b", total=2, unit="turns")
        await db_session.commit()

        n = await clear_timers(db_session, GUILD_ID, CHANNEL_ID)
        await db_session.commit()
        assert n == 2
        assert await list_timers(db_session, GUILD_ID, CHANNEL_ID) == []

    async def test_clear_expired_only(self, db_session):
        await add_timer(db_session, GUILD_ID, CHANNEL_ID, "live1", total=3, unit="turns")
        await add_timer(db_session, GUILD_ID, CHANNEL_ID, "live2", total=2, unit="turns")
        await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "dead", total=2, unit="turns", remaining=0,
        )
        await db_session.commit()

        n = await clear_timers(db_session, GUILD_ID, CHANNEL_ID, expired_only=True)
        await db_session.commit()
        assert n == 1

        remaining = await list_timers(db_session, GUILD_ID, CHANNEL_ID)
        assert len(remaining) == 2
        assert {t.label for t in remaining} == {"live1", "live2"}

    async def test_clear_expired_only_when_none_expired(self, db_session):
        await add_timer(db_session, GUILD_ID, CHANNEL_ID, "live", total=3, unit="turns")
        await db_session.commit()

        n = await clear_timers(db_session, GUILD_ID, CHANNEL_ID, expired_only=True)
        await db_session.commit()
        assert n == 0
        assert len(await list_timers(db_session, GUILD_ID, CHANNEL_ID)) == 1

    async def test_clear_by_target(self, db_session):
        await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "g", total=2, unit="turns", target="Goblin",
        )
        await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "o", total=2, unit="turns", target="Orc",
        )
        await db_session.commit()

        n = await clear_timers(db_session, GUILD_ID, CHANNEL_ID, target="goblin")
        await db_session.commit()
        assert n == 1

        remaining = await list_timers(db_session, GUILD_ID, CHANNEL_ID)
        assert len(remaining) == 1
        assert remaining[0].target == "Orc"

    async def test_clear_scoped_to_channel(self, db_session):
        await add_timer(db_session, GUILD_ID, CHANNEL_ID, "here", total=2, unit="turns")
        await add_timer(db_session, GUILD_ID, OTHER_CHANNEL, "there", total=2, unit="turns")
        await db_session.commit()

        n = await clear_timers(db_session, GUILD_ID, CHANNEL_ID)
        await db_session.commit()
        assert n == 1  # only the in-scope channel's timer

        there = await list_timers(db_session, GUILD_ID, OTHER_CHANNEL)
        assert len(there) == 1


class TestProgressFraction:
    async def test_progress_fraction(self, db_session):
        t = await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, "x", total=4, unit="turns", remaining=1,
        )
        assert t.progress == pytest.approx(0.25)

    async def test_progress_fraction_full(self, db_session):
        t = await add_timer(db_session, GUILD_ID, CHANNEL_ID, "x", total=4, unit="turns")
        assert t.progress == pytest.approx(1.0)


class TestTimerTargetWhitespace:
    """regression: a target with stray whitespace must still match the trimmed form"""

    async def test_tick_matches_trailing_whitespace_target(self, db_session):
        await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, label="Bleeding",
            total=3, unit="turns", target="Goblin ",
        )
        await db_session.commit()

        expired = await tick_timers(
            db_session, GUILD_ID, CHANNEL_ID, unit="turns", amount=1, target="Goblin",
        )
        # ticked but not expired (3 -> 2), so confirm via re-list, not the expired return
        rows = await list_timers(db_session, GUILD_ID, CHANNEL_ID, target="Goblin")
        assert len(rows) == 1
        assert rows[0].remaining == 2


class TestTimerTargetUnicode:
    """regression: sqlite's built-in lower() is ascii-only — the engine overrides it for non-ascii targets"""

    async def test_tick_matches_non_ascii_target_case_insensitive(self, db_session):
        await add_timer(
            db_session, GUILD_ID, CHANNEL_ID, label="Bleed",
            total=3, unit="turns", target="GÁNOR",
        )
        await db_session.commit()

        await tick_timers(
            db_session, GUILD_ID, CHANNEL_ID, unit="turns", amount=1, target="gánor",
        )
        rows = await list_timers(db_session, GUILD_ID, CHANNEL_ID, target="gánor")
        assert len(rows) == 1
        assert rows[0].remaining == 2
