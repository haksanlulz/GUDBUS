from __future__ import annotations

import pytest

from gurps_bot.mechanics.wealth import (
    cost_of_living,
    starting_wealth,
    wealth_level_cost,
)
from gurps_bot.services.wealth import (  # noqa: F401 — import registers Wealth on Base
    adjust_balance,
    apply_cost_of_living,
    get_or_create_wealth,
    get_wealth,
    set_balance,
    set_status,
)

USER_ID = 123
OTHER_USER_ID = 7


class TestWalletRaceAndValidation:
    async def test_get_wealth_tolerates_duplicate_default_wallet_rows(self, db_session):
        from gurps_bot.db.wealth import Wealth
        # sqlite treats NULL character_id rows as distinct, so a first-touch race
        # can dup the default wallet; return one, not MultipleResultsFound
        db_session.add(Wealth(discord_user_id=USER_ID, character_id=None, balance=10.0, status=0))
        db_session.add(Wealth(discord_user_id=USER_ID, character_id=None, balance=20.0, status=0))
        await db_session.commit()
        w = await get_wealth(db_session, USER_ID)
        assert w is not None

    async def test_set_balance_rejects_non_finite(self, db_session):
        for bad in (float("inf"), float("-inf"), float("nan")):
            with pytest.raises(ValueError):
                await set_balance(db_session, USER_ID, bad)

    async def test_adjust_balance_rejects_non_finite(self, db_session):
        with pytest.raises(ValueError):
            await adjust_balance(db_session, USER_ID, float("inf"))

    async def test_adjust_balance_atomic_increment_is_correct(self, db_session):
        await set_balance(db_session, USER_ID, 100.0)
        await adjust_balance(db_session, USER_ID, 50.0)
        await adjust_balance(db_session, USER_ID, -30.0)
        await db_session.commit()
        w = await get_wealth(db_session, USER_ID)
        assert w.balance == 120.0


# pure mechanics
class TestCostOfLiving:
    def test_average_status_baseline(self):
        # B265: Status 0 upkeep is $600/mo
        assert cost_of_living(0) == 600

    def test_table_extremes(self):
        assert cost_of_living(-2) == 100
        assert cost_of_living(8) == 600000000

    def test_full_table_values(self):
        expected = {
            8: 600000000,
            7: 60000000,
            6: 6000000,
            5: 600000,
            4: 60000,
            3: 12000,
            2: 3000,
            1: 1200,
            0: 600,
            -1: 300,
            -2: 100,
        }
        for status, cost in expected.items():
            assert cost_of_living(status) == cost

    def test_above_range_raises(self):
        with pytest.raises(ValueError):
            cost_of_living(9)

    def test_below_range_raises(self):
        with pytest.raises(ValueError):
            cost_of_living(-3)


class TestStartingWealth:
    def test_tl3_average_canonical(self):
        # TL3 base 1000 x1.0
        assert starting_wealth(3, "average") == 1000

    def test_tl8_wealthy(self):
        # base 20000 x5
        assert starting_wealth(8, "wealthy") == 100000

    def test_dead_broke_is_exactly_zero(self):
        # x0 zeroes out at any TL
        assert starting_wealth(3, "dead_broke") == 0
        assert starting_wealth(12, "dead_broke") == 0

    def test_dead_broke_not_base(self):
        # not the base: the multiplier must actually apply
        assert starting_wealth(3, "dead_broke") != 1000

    def test_tl5_poor_fractional_multiplier(self):
        # base 5000 x0.2 = 1000.0, int via round()
        result = starting_wealth(5, "poor")
        assert result == 1000
        assert isinstance(result, int)

    def test_tl12_filthy_rich_max(self):
        # base 100000 x100
        assert starting_wealth(12, "filthy_rich") == 10000000

    def test_case_insensitive_normalization(self):
        assert starting_wealth(3, "Comfortable") == starting_wealth(3, "comfortable")
        assert starting_wealth(3, "Comfortable") == 2000

    def test_whitespace_normalization(self):
        assert starting_wealth(3, "  comfortable  ") == 2000

    def test_tl_out_of_range_high_raises(self):
        with pytest.raises(ValueError):
            starting_wealth(13, "average")

    def test_tl_out_of_range_low_raises(self):
        with pytest.raises(ValueError):
            starting_wealth(-1, "average")

    def test_unknown_wealth_level_raises_value_error(self):
        # ValueError naming the arg, not a raw KeyError
        with pytest.raises(ValueError):
            starting_wealth(3, "rich")

    def test_unknown_wealth_level_not_keyerror(self):
        with pytest.raises(ValueError):
            starting_wealth(3, "broke")
        try:
            starting_wealth(3, "broke")
        except KeyError:  # pragma: no cover
            pytest.fail("starting_wealth leaked a KeyError instead of ValueError")
        except ValueError:
            pass


class TestWealthLevelCost:
    def test_known_point_costs(self):
        assert wealth_level_cost("dead_broke") == -25
        assert wealth_level_cost("poor") == -15
        assert wealth_level_cost("struggling") == -10
        assert wealth_level_cost("average") == 0
        assert wealth_level_cost("comfortable") == 10
        assert wealth_level_cost("wealthy") == 20
        assert wealth_level_cost("very_wealthy") == 30
        assert wealth_level_cost("filthy_rich") == 50

    def test_case_insensitive(self):
        assert wealth_level_cost("Comfortable") == 10
        assert wealth_level_cost("  POOR ") == -15

    def test_unknown_raises_value_error(self):
        with pytest.raises(ValueError):
            wealth_level_cost("rich")


# service layer
class TestGetWealth:
    async def test_get_returns_none_when_absent(self, db_session):
        result = await get_wealth(db_session, USER_ID, None)
        assert result is None

    async def test_get_or_create_makes_default_row(self, db_session):
        w = await get_or_create_wealth(db_session, USER_ID, None)
        await db_session.commit()
        assert w.discord_user_id == USER_ID
        assert w.character_id is None
        assert w.balance == 0.0
        assert w.status == 0
        assert w.id is not None

    async def test_get_or_create_returns_existing(self, db_session):
        first = await get_or_create_wealth(db_session, USER_ID, None)
        await db_session.commit()
        second = await get_or_create_wealth(db_session, USER_ID, None)
        assert first.id == second.id


class TestBalanceMutators:
    async def test_adjust_first_touch_creates_and_credits(self, db_session):
        await adjust_balance(db_session, USER_ID, 500.0)
        await db_session.commit()
        w = await get_wealth(db_session, USER_ID, None)
        assert w is not None
        assert w.balance == 500.0

    async def test_set_then_adjust_compose(self, db_session):
        await set_balance(db_session, USER_ID, 1000.0)
        await adjust_balance(db_session, USER_ID, -250.0)
        await db_session.commit()
        w = await get_wealth(db_session, USER_ID, None)
        assert w.balance == 750.0

    async def test_adjust_allows_negative_debt(self, db_session):
        await adjust_balance(db_session, USER_ID, -2000.0)
        await db_session.commit()
        w = await get_wealth(db_session, USER_ID, None)
        assert w.balance == -2000.0

    async def test_set_balance_is_absolute(self, db_session):
        await set_balance(db_session, USER_ID, 1000.0)
        await set_balance(db_session, USER_ID, 42.0)
        await db_session.commit()
        w = await get_wealth(db_session, USER_ID, None)
        assert w.balance == 42.0

    async def test_no_commit_in_service(self, db_session):
        # if the service committed, rollback would not discard the row
        await set_balance(db_session, USER_ID, 999.0)
        await db_session.rollback()
        w = await get_wealth(db_session, USER_ID, None)
        assert w is None


class TestSetStatus:
    async def test_set_status_persists(self, db_session):
        await set_status(db_session, USER_ID, 3)
        await db_session.commit()
        w = await get_wealth(db_session, USER_ID, None)
        assert w.status == 3

    async def test_set_invalid_status_raises_and_does_not_persist(self, db_session):
        await set_status(db_session, USER_ID, 2)
        await db_session.commit()
        with pytest.raises(ValueError):
            await set_status(db_session, USER_ID, 9)
        # stored status survives the failed set
        await db_session.rollback()
        w = await get_wealth(db_session, USER_ID, None)
        assert w.status == 2

    async def test_set_invalid_status_on_new_user_creates_nothing_bad(self, db_session):
        with pytest.raises(ValueError):
            await set_status(db_session, OTHER_USER_ID, -3)


class TestApplyCostOfLiving:
    async def test_deducts_status_5_upkeep_can_go_negative(self, db_session):
        # Status 5 = $600k/mo; from 0.0 that goes negative
        await set_status(db_session, USER_ID, 5)
        await apply_cost_of_living(db_session, USER_ID)
        await db_session.commit()
        w = await get_wealth(db_session, USER_ID, None)
        assert w.balance == -600000.0

    async def test_uses_stored_status_average_default(self, db_session):
        # fresh row defaults to Status 0 -> $600/mo
        await apply_cost_of_living(db_session, USER_ID)
        await db_session.commit()
        w = await get_wealth(db_session, USER_ID, None)
        assert w.balance == -600.0

    async def test_returns_row_with_new_balance(self, db_session):
        await set_balance(db_session, USER_ID, 5000.0)
        await set_status(db_session, USER_ID, 0)
        w = await apply_cost_of_living(db_session, USER_ID)
        await db_session.commit()
        assert w.balance == 4400.0

    # B265: you can pay upkeep at a Status above or below your own, within [-2, 8]

    async def test_living_status_below_saves_money(self, db_session):
        # stored Status 2 ($3k), slumming at 0 ($600)
        await set_status(db_session, USER_ID, 2)
        await apply_cost_of_living(db_session, USER_ID, living_status=0)
        await db_session.commit()
        w = await get_wealth(db_session, USER_ID, None)
        assert w.balance == -600.0

    async def test_living_status_above_costs_more(self, db_session):
        # stored Status 0 ($600), living at 2 ($3k)
        await set_status(db_session, USER_ID, 0)
        await apply_cost_of_living(db_session, USER_ID, living_status=2)
        await db_session.commit()
        w = await get_wealth(db_session, USER_ID, None)
        assert w.balance == -3000.0

    async def test_living_status_none_uses_stored(self, db_session):
        # no override: charge stored Status 3 -> $12k
        await set_status(db_session, USER_ID, 3)
        await apply_cost_of_living(db_session, USER_ID, living_status=None)
        await db_session.commit()
        w = await get_wealth(db_session, USER_ID, None)
        assert w.balance == -12000.0

    async def test_living_status_does_not_mutate_stored_status(self, db_session):
        await set_status(db_session, USER_ID, 2)
        w = await apply_cost_of_living(db_session, USER_ID, living_status=-2)
        await db_session.commit()
        assert w.status == 2          # nominal Status unchanged
        assert w.balance == -100.0    # charged the -2 tier ($100)

    async def test_living_status_out_of_range_raises(self, db_session):
        await set_status(db_session, USER_ID, 0)
        with pytest.raises(ValueError):
            await apply_cost_of_living(db_session, USER_ID, living_status=9)


class TestWalletIsolation:
    async def test_default_and_character_wallets_are_distinct(self, db_session, make_character):
        await make_character(4, OTHER_USER_ID)
        await set_balance(db_session, OTHER_USER_ID, 10.0, character_id=None)
        await set_balance(db_session, OTHER_USER_ID, 99.0, character_id=4)
        await db_session.commit()

        default_wallet = await get_wealth(db_session, OTHER_USER_ID, None)
        char_wallet = await get_wealth(db_session, OTHER_USER_ID, 4)

        assert default_wallet is not None
        assert char_wallet is not None
        assert default_wallet.id != char_wallet.id
        assert default_wallet.balance == 10.0
        assert char_wallet.balance == 99.0

    async def test_mutating_character_wallet_does_not_touch_default(self, db_session, make_character):
        await make_character(4, OTHER_USER_ID)
        await set_balance(db_session, OTHER_USER_ID, 10.0, character_id=None)
        await set_balance(db_session, OTHER_USER_ID, 99.0, character_id=4)
        await db_session.commit()

        await adjust_balance(db_session, OTHER_USER_ID, -50.0, character_id=4)
        await db_session.commit()

        default_wallet = await get_wealth(db_session, OTHER_USER_ID, None)
        char_wallet = await get_wealth(db_session, OTHER_USER_ID, 4)
        assert default_wallet.balance == 10.0
        assert char_wallet.balance == 49.0


class TestWealthOverflowGuard:
    """a finite delta summing to inf must be rejected; a persisted $inf wallet renders forever"""

    async def test_adjust_overflow_to_inf_is_rejected(self, db_session):
        import math

        await set_balance(db_session, USER_ID, 1.6e308)
        await db_session.commit()

        with pytest.raises(ValueError, match="overflow"):
            await adjust_balance(db_session, USER_ID, 1.6e308)
        await db_session.rollback()

        w = await get_wealth(db_session, USER_ID)
        assert math.isfinite(w.balance)


class TestWealthSchemaParity:
    """uq_wealth_owner stays on the model; create_all and migration d7b3f0a1c2e4 depend on it"""

    def test_wealth_table_declares_owner_unique_constraint(self):
        from gurps_bot.db.wealth import Wealth

        names = {c.name for c in Wealth.__table__.constraints}
        assert "uq_wealth_owner" in names
