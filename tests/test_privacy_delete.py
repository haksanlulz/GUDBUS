"""`/privacy delete-my-data` must remove everything keyed to the user.

PRIVACY.md promises it, so the set of user-keyed tables is derived from the
model metadata rather than remembered: a new table with a `discord_user_id`
fails the first test until it is deleted here or recorded as anonymised.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy import func, select

from gurps_bot.db import crafting as _crafting  # noqa: F401
from gurps_bot.db import notes as _notes  # noqa: F401
from gurps_bot.db import study as _study  # noqa: F401
from gurps_bot.db import timers as _timers  # noqa: F401
from gurps_bot.db import wealth as _wealth  # noqa: F401
from gurps_bot.db.crafting import CraftingCharge
from gurps_bot.db.engine import dispose_engine, get_session_factory, init_db, init_engine
from gurps_bot.db.models import ActiveCharacter, Base, Character, Combatant, DiceMacro, Skill
from gurps_bot.db.notes import Note
from gurps_bot.db.study import StudyLog
from gurps_bot.db.wealth import Wealth
from gurps_bot.services.combat import add_pc_combatant, start_combat
from gurps_bot.services.crafting import record_attempt, start_project
from gurps_bot.services.privacy import (
    ANONYMISED_TABLES,
    DELETED_TABLES,
    delete_user_data,
)

USER = 42
OTHER = 43
GUILD = 777


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    init_engine(f"sqlite+aiosqlite:///{(tmp_path / 'privacy.db').as_posix()}")
    await init_db()
    yield get_session_factory()
    await dispose_engine()


def _user_keyed_tables() -> set[str]:
    return {
        t.name for t in Base.metadata.tables.values()
        if "discord_user_id" in t.columns.keys()
    }


def test_every_user_keyed_table_is_handled():
    found = _user_keyed_tables()
    handled = set(DELETED_TABLES) | set(ANONYMISED_TABLES)
    assert found == handled, (
        "the set of user-keyed tables changed.\n"
        f"  in metadata : {sorted(found)}\n"
        f"  handled     : {sorted(handled)}\n"
        "Delete the new table's rows in services/privacy.delete_user_data, or "
        "record why it is only anonymised. PRIVACY.md promises the user's data "
        "is removed."
    )


async def _seed(session_factory, user: int, guild: int) -> None:
    async with session_factory() as s:
        char = Character(discord_user_id=user, name=f"Hero{user}")
        s.add(char)
        await s.flush()
        s.add(Skill(character_id=char.id, name="Broadsword", difficulty="dx/a", level=14))
        s.add(ActiveCharacter(discord_user_id=user, guild_id=guild, character_id=char.id))
        s.add(DiceMacro(discord_user_id=user, name="sword", expression="2d+1"))
        s.add(Note(discord_user_id=user, guild_id=guild, channel_id=1, title="t", body="b"))
        s.add(StudyLog(
            discord_user_id=user, character_id=char.id, skill_name="Broadsword",
            method="self-study", real_hours=4.0, learning_hours=2.0,
        ))
        s.add(Wealth(discord_user_id=user, character_id=char.id, balance=100.0))
        project = await start_project(
            s, discord_user_id=user, guild_id=guild, name=f"engine{user}",
            complexity="average", skill=14,
        )
        await record_attempt(s, project, amount=100, outcome="failure")
        combat = await start_combat(s, guild, user, user)
        await add_pc_combatant(s, combat, char.id, char.name, user)
        await s.commit()


async def _count(session_factory, user: int) -> dict[str, int]:
    async with session_factory() as s:
        counts = {}
        for name in sorted(_user_keyed_tables()):
            table = Base.metadata.tables[name]
            counts[name] = await s.scalar(
                select(func.count()).select_from(table).where(table.c.discord_user_id == user)
            )
        return counts


async def test_removes_every_row_keyed_to_the_user(session_factory):
    await _seed(session_factory, USER, GUILD)
    before = await _count(session_factory, USER)
    assert all(v > 0 for v in before.values()), f"seed missed a table: {before}"

    async with session_factory() as s:
        result = await delete_user_data(s, USER)
        await s.commit()

    after = await _count(session_factory, USER)
    assert after == dict.fromkeys(after, 0), {k: v for k, v in after.items() if v}
    assert result["characters"] == 1
    assert result["combatants"] == 1


async def test_child_rows_go_with_their_parents(session_factory):
    """Skills hang off characters and charges off projects; neither carries a
    user id, so a delete that missed the cascade would leave them orphaned."""
    await _seed(session_factory, USER, GUILD)
    async with session_factory() as s:
        await delete_user_data(s, USER)
        await s.commit()
    async with session_factory() as s:
        assert await s.scalar(select(func.count(Skill.id))) == 0
        assert await s.scalar(select(func.count(CraftingCharge.id))) == 0


async def test_a_running_combat_keeps_an_unowned_row(session_factory):
    """Removing a combatant mid-fight would reorder someone else's game, so the
    row stays as an unowned tracker entry until that combat ends."""
    await _seed(session_factory, USER, GUILD)
    async with session_factory() as s:
        await delete_user_data(s, USER)
        await s.commit()
    async with session_factory() as s:
        rows = (await s.execute(select(Combatant))).scalars().all()
        assert len(rows) == 1
        assert rows[0].discord_user_id is None
        assert rows[0].character_id is None


async def test_another_users_data_is_untouched(session_factory):
    await _seed(session_factory, USER, GUILD)
    await _seed(session_factory, OTHER, GUILD + 1)
    async with session_factory() as s:
        await delete_user_data(s, USER)
        await s.commit()
    survivors = await _count(session_factory, OTHER)
    assert all(v > 0 for v in survivors.values()), survivors


async def test_a_user_with_nothing_stored_gets_zeros(session_factory):
    async with session_factory() as s:
        result = await delete_user_data(s, 999)
    assert set(result.values()) == {0}
