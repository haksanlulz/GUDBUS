"""Leaving a guild must take that guild's data with it.

PRIVACY.md tells users "kicking the bot from a server deletes that server's
data automatically", and that sentence is the kind a verification review reads
closely. It was not quite true: `campaign_settings` was added months after
`cleanup_guild_data` and never added to it, so a kick and re-invite silently
restored house rules the new occupants never chose. The bot has already been
kicked and re-invited once, during the 2026-07-25 rename.

The failure was not the missing call — it was that the set of guild-scoped
tables lived in a docstring and in whoever last edited the function. So the
first test here derives that set from the model metadata: adding a table with a
`guild_id` column fails it until the author either purges the table or records
why it survives.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy import func, select

# Imported for their side effect: each module registers its tables on the
# shared metadata, and a table that is not imported is not inspectable.
from gurps_bot.db import notes as _notes  # noqa: F401
from gurps_bot.db import study as _study  # noqa: F401
from gurps_bot.db import timers as _timers  # noqa: F401
from gurps_bot.db import wealth as _wealth  # noqa: F401
from gurps_bot.db.engine import (
    dispose_engine,
    get_session_factory,
    init_db,
    init_engine,
)
from gurps_bot.db.models import ActiveCharacter, Base, CampaignSettings, Character
from gurps_bot.db.notes import Note
from gurps_bot.db.timers import Timer
from gurps_bot.services.admin import cleanup_guild_data
from gurps_bot.services.combat import add_npc_combatant, start_combat

GUILD = 555_000
OTHER_GUILD = 555_001
USER = 42

#: Tables carrying a guild_id that `cleanup_guild_data` is expected to clear.
#: Deliberately a literal: the test below compares it against what the metadata
#: actually contains, so this list going stale is itself the failure.
EXPECTED_GUILD_SCOPED = {
    "active_characters",
    "campaign_settings",
    "combats",
    "notes",
    "timers",
}


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "teardown.db"
    init_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    await init_db()
    yield get_session_factory()
    await dispose_engine()


def _guild_scoped_tables() -> set[str]:
    return {
        t.name
        for t in Base.metadata.tables.values()
        if "guild_id" in t.columns.keys()
    }


class TestTheSetIsNotKeptInSomeonesHead:
    def test_no_unhandled_guild_scoped_table_exists(self):
        found = _guild_scoped_tables()
        assert found == EXPECTED_GUILD_SCOPED, (
            "the set of guild-scoped tables changed.\n"
            f"  in metadata : {sorted(found)}\n"
            f"  expected    : {sorted(EXPECTED_GUILD_SCOPED)}\n"
            "If you added a table with a guild_id, purge it in "
            "services/admin.cleanup_guild_data and add it here. If it is "
            "deliberately kept when the bot leaves, add it here with a comment "
            "saying why — PRIVACY.md promises the server's data is deleted."
        )


class TestLeavingAGuildClearsIt:
    async def _seed(self, session_factory, guild_id: int) -> None:
        async with session_factory() as s:
            char = Character(discord_user_id=USER, name=f"Hero{guild_id}")
            s.add(char)
            await s.flush()
            s.add(ActiveCharacter(
                discord_user_id=USER, guild_id=guild_id, character_id=char.id
            ))
            s.add(CampaignSettings(guild_id=guild_id, rule_of_14=False))
            s.add(Note(
                discord_user_id=USER, guild_id=guild_id, channel_id=1,
                title="t", body="b",
            ))
            s.add(Timer(
                guild_id=guild_id, channel_id=1, label="n",
                total=3, remaining=3, unit="rounds",
            ))
            combat = await start_combat(s, guild_id, 1, USER)
            await add_npc_combatant(
                s, combat, name="M", basic_speed=5.0, hp=10, fp=10, ht=10
            )
            await s.commit()

    async def _rows_for(self, session_factory, guild_id: int) -> dict[str, int]:
        counts = {}
        async with session_factory() as s:
            for name in sorted(EXPECTED_GUILD_SCOPED):
                table = Base.metadata.tables[name]
                counts[name] = await s.scalar(
                    select(func.count()).select_from(table).where(
                        table.c.guild_id == guild_id
                    )
                )
        return counts

    async def test_every_guild_scoped_table_is_emptied(self, session_factory):
        await self._seed(session_factory, GUILD)
        assert all(v > 0 for v in (await self._rows_for(session_factory, GUILD)).values())

        async with session_factory() as s:
            await cleanup_guild_data(s, GUILD)
            await s.commit()

        remaining = await self._rows_for(session_factory, GUILD)
        assert remaining == dict.fromkeys(EXPECTED_GUILD_SCOPED, 0), (
            f"rows survived the teardown: "
            f"{ {k: v for k, v in remaining.items() if v} }"
        )

    async def test_house_rules_do_not_survive_a_kick_and_reinvite(
        self, session_factory
    ):
        """The concrete bug: a re-invited bot must not restore old house rules."""
        from gurps_bot.services.campaign import get_campaign_rules

        await self._seed(session_factory, GUILD)  # rule_of_14 turned OFF
        async with session_factory() as s:
            assert (await get_campaign_rules(s, GUILD)).rule_of_14 is False

        async with session_factory() as s:
            await cleanup_guild_data(s, GUILD)
            await s.commit()

        async with session_factory() as s:
            # Back to the RAW default, not the departed guild's setting.
            assert (await get_campaign_rules(s, GUILD)).rule_of_14 is True

    async def test_it_does_not_touch_another_guild(self, session_factory):
        await self._seed(session_factory, GUILD)
        await self._seed(session_factory, OTHER_GUILD)

        async with session_factory() as s:
            await cleanup_guild_data(s, GUILD)
            await s.commit()

        survivors = await self._rows_for(session_factory, OTHER_GUILD)
        assert all(v > 0 for v in survivors.values()), (
            f"teardown reached another guild: {survivors}"
        )

    async def test_user_scoped_data_survives(self, session_factory):
        """Characters, macros, study logs and wealth are the user's, not the
        guild's — PRIVACY.md says the server's data goes, not the player's."""
        await self._seed(session_factory, GUILD)
        async with session_factory() as s:
            await cleanup_guild_data(s, GUILD)
            await s.commit()

        async with session_factory() as s:
            chars = await s.scalar(
                select(func.count(Character.id)).where(
                    Character.discord_user_id == USER
                )
            )
        assert chars > 0, "leaving a guild deleted the player's character"
