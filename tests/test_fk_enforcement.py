"""foreign_keys=ON is what makes the declared ON DELETE SET NULL actually fire."""

from __future__ import annotations

from sqlalchemy import select

from gurps_bot.db.study import StudyLog
from gurps_bot.db.wealth import Wealth
from gurps_bot.services.study import log_study
from gurps_bot.services.wealth import set_balance


# the service imports register their models on Base, so the db_session
# fixture's create_all builds these tables
class TestForeignKeyOnDeleteSetNull:
    async def test_deleting_character_nulls_dependents(self, db_session, make_character):
        char = await make_character(100, 555)
        await log_study(db_session, 555, "Stealth", "self_teaching", 5.0, character_id=100)
        await set_balance(db_session, 555, 50.0, character_id=100)
        await db_session.commit()

        await db_session.delete(char)
        await db_session.commit()

        # rows survive with character_id nulled — without the pragma they
        # dangle at the deleted character's id
        study_rows = (
            await db_session.execute(
                select(StudyLog).where(StudyLog.discord_user_id == 555)
            )
        ).scalars().all()
        assert len(study_rows) == 1
        assert study_rows[0].character_id is None

        wealth_rows = (
            await db_session.execute(
                select(Wealth).where(Wealth.discord_user_id == 555)
            )
        ).scalars().all()
        assert len(wealth_rows) == 1
        assert wealth_rows[0].character_id is None
        assert wealth_rows[0].balance == 50.0


class TestDeletingACharacterWithADefaultWalletAlready:
    """SET NULL re-parents the character's wallet onto the user-wide slot. If
    the user already had a default wallet, that made two default rows, and
    get_wealth returns the older one — so the user-wide balance silently
    became (or stopped being) the deleted character's. Reproduced: a 20
    default and a 500 character wallet read 500 after the delete."""

    async def test_the_money_is_kept_in_the_one_default_wallet(
        self, db_session, make_character
    ):
        from gurps_bot.services.characters import delete_character
        from gurps_bot.services.wealth import get_wealth

        await make_character(100, 555)
        await set_balance(db_session, 555, 500.0, character_id=100)
        await set_balance(db_session, 555, 20.0)
        await db_session.commit()

        assert await delete_character(db_session, 100)
        await db_session.commit()

        rows = (
            await db_session.execute(select(Wealth).where(Wealth.discord_user_id == 555))
        ).scalars().all()
        assert len(rows) == 1, "two default wallets: one of them is now unreachable"
        assert (await get_wealth(db_session, 555)).balance == 520.0

    async def test_the_default_wallets_status_is_kept(self, db_session, make_character):
        from gurps_bot.services.characters import delete_character
        from gurps_bot.services.wealth import get_wealth, set_status

        await make_character(100, 555)
        await set_balance(db_session, 555, 5.0, character_id=100)
        await set_status(db_session, 555, 3, character_id=100)
        await set_balance(db_session, 555, 1.0)
        await set_status(db_session, 555, 1)
        await db_session.commit()

        await delete_character(db_session, 100)
        await db_session.commit()
        assert (await get_wealth(db_session, 555)).status == 1
