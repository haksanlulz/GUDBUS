"""fright-check + critical hit/miss table lookups"""

from gurps_bot.mechanics.tables import (
    CRITICAL_HIT_TABLE,
    CRITICAL_MISS_TABLE,
    FRIGHT_CHECK_TABLE,
    fright_check_effect,
)


class TestFrightCheckEffect:
    def test_negative_margin_no_effect(self):
        assert fright_check_effect(-1) == "No fright effect."
        assert fright_check_effect(-100) == "No fright effect."

    def test_zero_margin_lookup(self):
        assert fright_check_effect(0) == FRIGHT_CHECK_TABLE[0]

    def test_every_tabled_margin_returns_its_row(self):
        for margin, effect in FRIGHT_CHECK_TABLE.items():
            assert fright_check_effect(margin) == effect

    def test_max_tabled_margin(self):
        assert fright_check_effect(19) == FRIGHT_CHECK_TABLE[19]

    def test_over_table_falls_to_catch_all(self):
        # 20+ is past the last tabled row → the shared max effect (coma).
        over = fright_check_effect(20)
        assert over == fright_check_effect(999)
        assert "Coma" in over
        assert over not in FRIGHT_CHECK_TABLE.values()


class TestFrightCheckTableShape:
    def test_keys_contiguous_0_through_19(self):
        assert set(FRIGHT_CHECK_TABLE) == set(range(0, 20))

    def test_all_effects_nonempty(self):
        for margin, effect in FRIGHT_CHECK_TABLE.items():
            assert effect.strip(), f"empty fright effect for margin {margin}"


class TestCriticalTables:
    """3d6 crit tables must cover the full 3-18 roll span with no gaps"""

    def test_hit_table_covers_3_to_18(self):
        assert set(CRITICAL_HIT_TABLE) == set(range(3, 19))

    def test_miss_table_covers_3_to_18(self):
        assert set(CRITICAL_MISS_TABLE) == set(range(3, 19))

    def test_all_crit_effects_nonempty(self):
        for table in (CRITICAL_HIT_TABLE, CRITICAL_MISS_TABLE):
            for roll_value, effect in table.items():
                assert effect.strip(), f"empty crit effect for {roll_value}"
