"""fright-check + critical table lookups

B360-361 (Fright Check), B556 (Critical Hit / Head Blow / Miss), B556-557
(Unarmed Critical Miss). The result rows are the book's text and are not
shipped (SJG Online Policy), so these pin the lookup mechanics — the Rule of 14
cap, which row a total reads, the page cites — and that each row's label stays
a label (three words or fewer), not a paraphrase of the book's effect.
"""

import pytest

from gurps_bot.mechanics import tables
from gurps_bot.mechanics.tables import (
    CRITICAL_HEAD_BLOW,
    CRITICAL_HIT,
    CRITICAL_MISS,
    CRITICAL_TABLES,
    UNARMED_CRITICAL_MISS,
    FRIGHT_TABLE_MAX,
    FRIGHT_TABLE_MIN,
    FRIGHT_TABLE_PAGES,
    FRIGHT_RESULT_LABELS,
    FRIGHT_WILL_CAP,
    fright_table_result,
    fright_table_row,
)


class TestRuleOf14:
    def test_cap_is_13(self):
        # B360: modified Will above 13 is reduced to 13 for the Fright Check,
        # so a roll of 14+ always fails. Fright Checks only.
        assert FRIGHT_WILL_CAP == 13


class TestFrightTableRow:
    def test_table_runs_4_to_40_plus(self):
        # B360: 3d + margin of failure — minimum 3 (dice) + 1 (margin) = 4;
        # the final row is 40+.
        assert (FRIGHT_TABLE_MIN, FRIGHT_TABLE_MAX) == (4, 40)

    @pytest.mark.parametrize("total", range(4, 40))
    def test_every_tabled_total_reads_its_own_row(self, total):
        assert fright_table_row(total) == str(total)

    @pytest.mark.parametrize("total", [40, 41, 999])
    def test_40_and_past_read_the_40_plus_row(self, total):
        assert fright_table_row(total) == "40+"

    @pytest.mark.parametrize("total", [3, 0, -5])
    def test_below_4_clamps_to_first_row(self, total):
        assert fright_table_row(total) == "4"


class TestCites:
    def test_fright_result_names_label_row_and_page(self):
        result = fright_table_result(27)
        assert FRIGHT_RESULT_LABELS["27"] in result
        assert "row 27" in result
        assert FRIGHT_TABLE_PAGES in result
        assert FRIGHT_TABLE_PAGES == "B360-361"
        assert "row 40+" in fright_table_result(43)

    def test_critical_tables_cite_their_pages(self):
        assert {t.name: t.page for t in CRITICAL_TABLES} == {
            "Critical Hit": "B556",
            "Critical Head Blow": "B556",
            "Critical Miss": "B556",
            "Unarmed Critical Miss": "B556-557",
        }


class TestNoRowTextShipped:
    def test_every_row_has_a_label(self):
        rows = [str(t) for t in range(FRIGHT_TABLE_MIN, FRIGHT_TABLE_MAX)] + ["40+"]
        assert list(FRIGHT_RESULT_LABELS) == rows

    @pytest.mark.parametrize(
        "table", [CRITICAL_HIT, CRITICAL_MISS, UNARMED_CRITICAL_MISS], ids=lambda t: t.name,
    )
    def test_rolled_critical_tables_label_every_3d_total(self, table):
        assert list(table.labels) == list(range(3, 19))

    def test_head_blow_is_cited_not_rolled(self):
        # it depends on the hit location, which /attack does not know
        assert CRITICAL_HEAD_BLOW.labels is None
        with pytest.raises(ValueError):
            CRITICAL_HEAD_BLOW.result(10)

    def test_critical_result_names_label_roll_table_and_page(self):
        assert CRITICAL_HIT.result(5) == "**Double damage** (roll 5, Critical Hit, B556)"

    @pytest.mark.parametrize("table,row,label", [
        *(("Fright", row, label) for row, label in FRIGHT_RESULT_LABELS.items()),
        *(
            (t.name, row, label)
            for t in CRITICAL_TABLES if t.labels
            for row, label in t.labels.items()
        ),
    ])
    def test_labels_are_three_words_or_fewer(self, table, row, label):
        # The Online Policy forbids copied tables; a label that grows into a
        # sentence is no longer a label.
        assert len(label.split()) <= 3, (table, row, label)

    def test_no_row_text_outside_the_label_maps(self):
        # Module-level str-valued dicts are the label maps and nothing else;
        # a new one is how a book table would come back.
        maps = {
            name for name, value in vars(tables).items()
            if not name.startswith("__")
            and isinstance(value, dict) and value and all(isinstance(v, str) for v in value.values())
        }
        assert maps == {"FRIGHT_RESULT_LABELS"}
