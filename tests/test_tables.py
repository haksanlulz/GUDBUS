"""fright-check + critical table lookups

B360-361 (Fright Check), B556 (Critical Hit / Head Blow / Miss), B556-557
(Unarmed Critical Miss). The result rows are the book's text and are not
shipped (SJG Online Policy), so these pin the lookup mechanics — the Rule of 14
cap, which row a total reads, the page cites — and that no row text or per-row
label is carried at all.
"""

import pytest

from gurps_bot.mechanics import tables
from gurps_bot.mechanics.tables import (
    CriticalTable,
    CRITICAL_HEAD_BLOW,
    CRITICAL_HIT,
    CRITICAL_MISS,
    CRITICAL_TABLES,
    UNARMED_CRITICAL_MISS,
    FRIGHT_TABLE_MAX,
    FRIGHT_TABLE_MIN,
    FRIGHT_TABLE_PAGES,
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
    def test_fright_result_names_row_and_page(self):
        assert fright_table_result(27) == "Row **27** of the Fright Check Table (B360-361)"
        assert FRIGHT_TABLE_PAGES == "B360-361"
        assert "Row **40+**" in fright_table_result(43)

    def test_critical_tables_cite_their_pages(self):
        assert {t.name: t.page for t in CRITICAL_TABLES} == {
            "Critical Hit": "B556",
            "Critical Head Blow": "B556",
            "Critical Miss": "B556",
            "Unarmed Critical Miss": "B556-557",
        }

    @pytest.mark.parametrize(
        "table",
        [CRITICAL_HIT, CRITICAL_HEAD_BLOW, CRITICAL_MISS, UNARMED_CRITICAL_MISS],
        ids=lambda t: t.name,
    )
    def test_critical_result_names_row_table_and_page(self, table):
        assert table.result(5) == f"Row **5** of the {table.name} Table ({table.page})"


def _string_collections(module) -> set[str]:
    """Module-level dicts, lists and tuples that hold any string."""
    found = set()
    for name, value in vars(module).items():
        if name.startswith("__") or not isinstance(value, (dict, list, tuple)) or not value:
            continue
        items = value.values() if isinstance(value, dict) else value
        if any(isinstance(v, str) for v in items):
            found.add(name)
    return found


class TestNoRowTextShipped:
    def test_a_critical_table_is_a_name_and_a_page(self):
        # A field that could hold rows is how a book table would come back.
        assert set(CriticalTable.__dataclass_fields__) == {"name", "page"}

    def test_no_module_level_string_collections(self):
        # SJG Online Policy: no copied tables, and no per-row labels standing
        # in for them.
        assert _string_collections(tables) == set()

    def test_the_collection_check_can_fail(self, monkeypatch):
        monkeypatch.setattr(tables, "PLANTED", {"4": "planted"}, raising=False)
        assert _string_collections(tables) == {"PLANTED"}
