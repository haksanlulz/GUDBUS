"""Fright Check + critical-table lookups (B360-361, B556-557).

The books' result tables are not reproduced (SJG Online Policy: no copied
tables): this module holds no row text or per-row labels. A roll reports the
row it landed on and the page that row is printed on. See
docs/GURPS-IP-COMPLIANCE.md, condition 2.

/fright-check rolls the Fright Check Table; /attack rolls 3d for the Critical
Hit Table on a critical success and for the Critical Miss Table (Unarmed
Critical Miss for natural weapons) on a critical failure; /defend does the same
for a critically failed parry.

* Fright Check (B360-361): roll vs Will under the Rule of 14 — modified Will
  above 13 counts as 13, so 14+ always fails (Fright Checks only, not other Will
  rolls). On a failure, roll 3d, ADD the margin of failure, and read the table,
  which runs 4 through 40+. It is keyed by that TOTAL, not by the bare margin.
* Critical Hit / Critical Head Blow / Critical Miss (B556) and Unarmed Critical
  Miss (B556-557): 3d6 tables, keys 3-18. A critical hit to the face, skull or
  eye reads the Critical Head Blow Table instead of the Critical Hit Table.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Rule of 14 (B360): cap on modified Will for a Fright Check.
FRIGHT_WILL_CAP = 13

#: First and last Fright Check Table rows; the last row is "40+".
FRIGHT_TABLE_MIN = 4
FRIGHT_TABLE_MAX = 40

FRIGHT_TABLE_PAGES = "B360-361"


@dataclass(frozen=True)
class CriticalTable:
    """A 3d6 critical table, by name and page. Its rows stay in the book."""

    name: str
    page: str

    @property
    def cite(self) -> str:
        return f"{self.name} Table ({self.page})"

    def result(self, rolled: int) -> str:
        """The row a 3d roll landed on, and where that row is printed."""
        return f"Row **{rolled}** of the {self.cite}"


CRITICAL_HIT = CriticalTable("Critical Hit", "B556")
CRITICAL_HEAD_BLOW = CriticalTable("Critical Head Blow", "B556")
CRITICAL_MISS = CriticalTable("Critical Miss", "B556")
UNARMED_CRITICAL_MISS = CriticalTable("Unarmed Critical Miss", "B556-557")

#: Book order, for /screen's cites.
CRITICAL_TABLES: tuple[CriticalTable, ...] = (
    CRITICAL_HIT, CRITICAL_HEAD_BLOW, CRITICAL_MISS, UNARMED_CRITICAL_MISS,
)


def fright_table_row(total: int) -> str:
    """The Fright Check Table row to read for ``3d + margin of failure``.

    Totals past the table's end read the 40+ row; totals below 4 (impossible in
    play — 3d minimum 3 plus margin minimum 1) clamp to the first row.
    """
    if total >= FRIGHT_TABLE_MAX:
        return f"{FRIGHT_TABLE_MAX}+"
    return str(max(FRIGHT_TABLE_MIN, total))


def fright_table_result(total: int) -> str:
    """The row a total reads, and where that row is printed."""
    return f"Row **{fright_table_row(total)}** of the Fright Check Table ({FRIGHT_TABLE_PAGES})"
