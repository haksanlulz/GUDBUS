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
