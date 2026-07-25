"""fright-check + critical table lookups

Verified against the printed Basic Set: Fright Check procedure + table
B360-361; Critical Hit / Critical Head Blow / Critical Miss B556; Unarmed
Critical Miss B556-557. Effect text in tables.py is original shorthand, so these
pin the MECHANICS (keys, numbers, attributes, escalation structure) rather than
wording — stable across paraphrase edits, failing on rules drift.
"""

from gurps_bot.mechanics.tables import (
    CRITICAL_HEAD_BLOW_TABLE,
    CRITICAL_HIT_TABLE,
    CRITICAL_MISS_TABLE,
    FRIGHT_CHECK_TABLE,
    FRIGHT_WILL_CAP,
    UNARMED_CRITICAL_MISS_TABLE,
    fright_table_effect,
)

_ALL_TABLES = (
    FRIGHT_CHECK_TABLE,
    CRITICAL_HIT_TABLE,
    CRITICAL_HEAD_BLOW_TABLE,
    CRITICAL_MISS_TABLE,
    UNARMED_CRITICAL_MISS_TABLE,
)


class TestRuleOf14:
    def test_cap_is_13(self):
        # B360: modified Will above 13 is reduced to 13 for the Fright Check,
        # so a roll of 14+ always fails. Fright Checks only.
        assert FRIGHT_WILL_CAP == 13


class TestFrightTableShape:
    def test_keys_are_4_through_40(self):
        # B360: roll 3d and add the margin of failure — the minimum possible
        # total is 3 (dice) + 1 (margin), and the printed table starts at 4;
        # the final row is 40+ (stored under key 40).
        assert set(FRIGHT_CHECK_TABLE) == set(range(4, 41))

    def test_all_effects_nonempty(self):
        for total, effect in FRIGHT_CHECK_TABLE.items():
            assert effect.strip(), f"empty fright effect for total {total}"


class TestFrightTableLookup:
    def test_every_tabled_total_returns_its_row(self):
        for total, effect in FRIGHT_CHECK_TABLE.items():
            assert fright_table_effect(total) == effect

    def test_past_40_uses_the_40_plus_row(self):
        assert fright_table_effect(41) == FRIGHT_CHECK_TABLE[40]
        assert fright_table_effect(999) == FRIGHT_CHECK_TABLE[40]

    def test_below_4_clamps_to_first_row(self):
        # Unreachable in play (3d min 3 + margin min 1) — defensive clamp.
        assert fright_table_effect(3) == FRIGHT_CHECK_TABLE[4]
        assert fright_table_effect(0) == FRIGHT_CHECK_TABLE[4]
        assert fright_table_effect(-5) == FRIGHT_CHECK_TABLE[4]


class TestFrightTableMechanics:
    """Attribute + escalation pins from B360-361."""

    def test_stun_recovery_is_will_not_ht(self):
        # 6-11: snap-out rolls are vs Will (unmodified / with-modifiers /
        # modified) — an HT recovery here is the drift flag.
        for total in range(6, 12):
            row = FRIGHT_CHECK_TABLE[total].lower()
            assert "will" in row, f"row {total} lost its Will recovery"
            assert "ht" not in row, f"row {total} recovers on HT (RAW: Will)"

    def test_paired_rows_share_one_effect(self):
        # The printed table groups these totals onto single rows.
        assert FRIGHT_CHECK_TABLE[4] == FRIGHT_CHECK_TABLE[5]
        assert FRIGHT_CHECK_TABLE[6] == FRIGHT_CHECK_TABLE[7]
        assert FRIGHT_CHECK_TABLE[8] == FRIGHT_CHECK_TABLE[9]
        assert FRIGHT_CHECK_TABLE[14] == FRIGHT_CHECK_TABLE[15]

    def test_physical_recovery_rows_use_ht(self):
        # Retching (12), fainting (17-19), comas (28-29) recover on HT rolls.
        for total in (12, 17, 18, 19, 28, 29):
            assert "ht" in FRIGHT_CHECK_TABLE[total].lower()

    def test_panic_rows_use_will(self):
        for total in (21, 33):
            assert "will" in FRIGHT_CHECK_TABLE[total].lower()

    def test_content_spot_checks(self):
        t = {k: v.lower() for k, v in FRIGHT_CHECK_TABLE.items()}
        assert "quirk" in t[13]
        assert "fp" in t[14]  # lose 1d FP + stun
        assert "faint" in t[17]
        assert "delusion" in t[22] and "-10" in t[22]
        assert "phobia" in t[23] and "-10" in t[23]
        assert "-15" in t[24]  # major physical effect, -15 pts
        assert "seizure" in t[31]
        assert "2d" in t[32]  # stricken: 2d injury
        assert "-20" in t[36]
        assert "-30" in t[37]
        assert "coma" in t[38] and "coma" in t[39]
        assert "iq" in t[40]  # 40+: permanent IQ loss


class TestCriticalHitTable:
    def test_keys_cover_3_to_18(self):
        assert set(CRITICAL_HIT_TABLE) == set(range(3, 19))

    def test_symmetric_rows_match(self):
        # B556 pairs the table's ends: 3/18 triple, 4/17 half-DR (round down),
        # 5/16 double, 6/15 maximum, and 7/13/14 share the major-wound row.
        assert CRITICAL_HIT_TABLE[3] == CRITICAL_HIT_TABLE[18]
        assert CRITICAL_HIT_TABLE[4] == CRITICAL_HIT_TABLE[17]
        assert CRITICAL_HIT_TABLE[5] == CRITICAL_HIT_TABLE[16]
        assert CRITICAL_HIT_TABLE[6] == CRITICAL_HIT_TABLE[15]
        assert CRITICAL_HIT_TABLE[7] == CRITICAL_HIT_TABLE[13]
        assert CRITICAL_HIT_TABLE[7] == CRITICAL_HIT_TABLE[14]
        assert (
            CRITICAL_HIT_TABLE[9] == CRITICAL_HIT_TABLE[10] == CRITICAL_HIT_TABLE[11]
        )

    def test_row_effects(self):
        t = {k: v.lower() for k, v in CRITICAL_HIT_TABLE.items()}
        assert "triple" in t[3]
        assert "half" in t[4] and "down" in t[4]
        assert "double" in t[5]
        assert "maximum" in t[6]
        assert "major wound" in t[7]
        # 8: double shock capped -8; limb/extremity funny-bone crippling.
        assert "shock" in t[8] and "-8" in t[8] and "crippl" in t[8]
        assert "normal" in t[9]
        assert "drop" in t[12]

    def test_old_fabricated_rows_are_gone(self):
        # "HT or stunned" at 4/5/17 and weapon drops at 6/15/16 are not on the
        # printed table.
        joined = " ".join(CRITICAL_HIT_TABLE.values()).lower()
        assert "stunned" not in joined
        assert "drops weapon" not in joined


class TestCriticalHeadBlowTable:
    def test_keys_cover_3_to_18(self):
        assert set(CRITICAL_HEAD_BLOW_TABLE) == set(range(3, 19))

    def test_paired_rows(self):
        assert CRITICAL_HEAD_BLOW_TABLE[4] == CRITICAL_HEAD_BLOW_TABLE[5]
        assert CRITICAL_HEAD_BLOW_TABLE[6] == CRITICAL_HEAD_BLOW_TABLE[7]
        assert CRITICAL_HEAD_BLOW_TABLE[12] == CRITICAL_HEAD_BLOW_TABLE[13]
        assert (
            CRITICAL_HEAD_BLOW_TABLE[9]
            == CRITICAL_HEAD_BLOW_TABLE[10]
            == CRITICAL_HEAD_BLOW_TABLE[11]
        )

    def test_row_effects(self):
        t = {k: v.lower() for k, v in CRITICAL_HEAD_BLOW_TABLE.items()}
        assert "maximum" in t[3] and "ignor" in t[3]  # max damage, ignores DR
        assert "major wound" in t[4]
        assert "eye" in t[6]  # face/skull redirected to an eye hit
        assert "do nothing" in t[8]
        assert "deafen" in t[12]
        assert "drop" in t[14]
        assert "maximum" in t[15]
        assert "double" in t[16]
        assert "triple" in t[18]

    def test_head_blow_rounds_up_where_main_rounds_down(self):
        # The two tables disagree on the half-DR rounding direction on purpose:
        # main Critical Hit rounds down (4/17), Head Blow rounds up (4-5/17).
        # The book's two-column page scrambles these rows in text extraction —
        # this pin keeps the reassembly honest.
        assert "down" in CRITICAL_HIT_TABLE[4].lower()
        assert "up" in CRITICAL_HEAD_BLOW_TABLE[4].lower()
        assert "up" in CRITICAL_HEAD_BLOW_TABLE[17].lower()


class TestCriticalMissTable:
    def test_keys_cover_3_to_18(self):
        assert set(CRITICAL_MISS_TABLE) == set(range(3, 19))

    def test_shared_rows(self):
        # 3/4 and 17/18 are the broken-weapon row; 8/12 weapon-turns;
        # 7/13 lose-balance; 9/10/11 drop.
        assert CRITICAL_MISS_TABLE[3] == CRITICAL_MISS_TABLE[4]
        assert CRITICAL_MISS_TABLE[3] == CRITICAL_MISS_TABLE[17]
        assert CRITICAL_MISS_TABLE[3] == CRITICAL_MISS_TABLE[18]
        assert CRITICAL_MISS_TABLE[8] == CRITICAL_MISS_TABLE[12]
        assert CRITICAL_MISS_TABLE[7] == CRITICAL_MISS_TABLE[13]
        assert (
            CRITICAL_MISS_TABLE[9] == CRITICAL_MISS_TABLE[10] == CRITICAL_MISS_TABLE[11]
        )

    def test_row_effects(self):
        t = {k: v.lower() for k, v in CRITICAL_MISS_TABLE.items()}
        assert "break" in t[3]
        # 5/6: you hit YOURSELF (full then half damage); "weapon flung" belongs
        # at 14.
        assert ("yourself" in t[5]) or ("own" in t[5])
        assert "half" in t[6]
        assert "balance" in t[7] and "-2" in t[7]
        assert "ready" in t[8]  # weapon turns in hand — extra Ready
        assert "drop" in t[9]
        assert "1d yards" in t[14]
        assert "30 min" in t[15]  # strained shoulder: arm out 30 minutes
        assert "fall" in t[16]

    def test_old_fabricated_rows_are_gone(self):
        # There is no "hit nearby ally" result on the printed table, and the
        # self-hit rows are at 5-6, not 10-13.
        joined = " ".join(CRITICAL_MISS_TABLE.values()).lower()
        assert "ally" not in joined


class TestUnarmedCriticalMissTable:
    def test_keys_cover_3_to_18(self):
        assert set(UNARMED_CRITICAL_MISS_TABLE) == set(range(3, 19))

    def test_shared_rows(self):
        # 3/18 knockout, 5/16 solid object, 7/14 stumble, 9/10/11 balance.
        assert UNARMED_CRITICAL_MISS_TABLE[3] == UNARMED_CRITICAL_MISS_TABLE[18]
        assert UNARMED_CRITICAL_MISS_TABLE[5] == UNARMED_CRITICAL_MISS_TABLE[16]
        assert UNARMED_CRITICAL_MISS_TABLE[7] == UNARMED_CRITICAL_MISS_TABLE[14]
        assert (
            UNARMED_CRITICAL_MISS_TABLE[9]
            == UNARMED_CRITICAL_MISS_TABLE[10]
            == UNARMED_CRITICAL_MISS_TABLE[11]
        )

    def test_row_effects(self):
        t = {k: v.lower() for k, v in UNARMED_CRITICAL_MISS_TABLE.items()}
        assert "knock yourself out" in t[3] and "ht" in t[3]
        assert "strain" in t[4]
        assert "solid object" in t[5]
        assert "half" in t[6]
        assert "stumble" in t[7]
        assert "fall" in t[8]
        assert "balance" in t[9]
        assert "dx" in t[12]  # trip: DX roll to avoid falling
        assert "guard" in t[13]
        assert "1d-3" in t[15]  # torn muscle
        assert "animal" in t[17]  # IQ 3-5 animals lose their nerve


class TestAllTablesNonempty:
    def test_no_empty_effects_anywhere(self):
        for table in _ALL_TABLES:
            for key, effect in table.items():
                assert effect.strip(), f"empty effect at {key}"
