"""Fright Check + critical-table lookups (B360-361, B556-557). The books'
result rows are not reproduced (SJG Online Policy: no copied tables). A roll
gets an original label of three words or fewer for the one row it landed on,
plus the page for the full effect; no command lists the labels as a table. See
docs/GURPS-IP-COMPLIANCE.md, condition 2.

/fright-check rolls the Fright Check Table; /attack rolls Critical Hit on a
critical success and Critical Miss (Unarmed Critical Miss for natural weapons)
on a critical failure; /defend does the same for a critically failed parry.
Critical Head Blow is cited only: it depends on a hit location /attack does not
know.

* Fright Check (B360-361): roll vs Will under the Rule of 14 — modified Will
  above 13 counts as 13, so 14+ always fails (Fright Checks only, not other Will
  rolls). On a failure, roll 3d, ADD the margin of failure, and read the table,
  which runs 4 through 40+. It is keyed by that TOTAL, not by the bare margin.
* Critical Hit / Critical Head Blow / Critical Miss (B556) and Unarmed Critical
  Miss (B556-557): 3d6 tables, keys 3-18.
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
    """A 3d6 critical table: its page, and a label per row if the bot rolls it."""

    name: str
    page: str
    #: 3..18 -> original label, three words or fewer. None: cited, never rolled.
    labels: dict[int, str] | None = None

    def result(self, rolled: int) -> str:
        """The rolled row's label and where its full effect is printed."""
        if self.labels is None:
            raise ValueError(f"{self.name} is cited, not rolled")
        return f"**{self.labels[rolled]}** (roll {rolled}, {self.name}, {self.page})"


def _labels(*rows: tuple[tuple[int, ...], str]) -> dict[int, str]:
    return dict(sorted((key, label) for keys, label in rows for key in keys))


CRITICAL_HIT = CriticalTable("Critical Hit", "B556", _labels(
    ((3, 18), "Triple damage"),
    ((4, 17), "DR halved"),
    ((5, 16), "Double damage"),
    ((6, 15), "Maximum damage"),
    ((7, 13, 14), "Major wound"),
    ((8,), "Double shock, crippling"),
    ((9, 10, 11), "Normal damage"),
    ((12,), "Target drops item"),
))
CRITICAL_HEAD_BLOW = CriticalTable("Critical Head Blow", "B556")
CRITICAL_MISS = CriticalTable("Critical Miss", "B556", _labels(
    ((3, 4, 17, 18), "Weapon breaks"),
    ((5,), "Hits yourself"),
    ((6,), "Hits yourself, half"),
    ((7, 13), "Lose balance"),
    ((8, 12), "Weapon turns"),
    ((9, 10, 11), "Drop weapon"),
    ((14,), "Weapon flies"),
    ((15,), "Strained shoulder"),
    ((16,), "Fall down"),
))
UNARMED_CRITICAL_MISS = CriticalTable("Unarmed Critical Miss", "B556-557", _labels(
    ((3, 18), "Knock yourself out"),
    ((4, 17), "Strained limb"),
    ((5, 16), "Hit solid object"),
    ((6,), "Hit object, half"),
    ((7, 14), "Stumble"),
    ((8,), "Fall down"),
    ((9, 10, 11), "Lose balance"),
    ((12,), "Trip"),
    ((13,), "Guard dropped"),
    ((15,), "Torn muscle"),
))

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


#: Row -> original label, three words or fewer (B360-361 has the full effect).
#: Shown one row per roll only; never rendered as a list.
FRIGHT_RESULT_LABELS: dict[str, str] = {
    "4": "Stun, auto-recover",
    "5": "Stun, auto-recover",
    "6": "Stun, unmodified Will",
    "7": "Stun, unmodified Will",
    "8": "Stun, modified Will",
    "9": "Stun, modified Will",
    "10": "Stun 1d sec",
    "11": "Stun 2d sec",
    "12": "Retching",
    "13": "New quirk",
    "14": "FP loss, stun",
    "15": "FP loss, stun",
    "16": "Stun + quirk",
    "17": "Faint 1d min",
    "18": "Faint, 1 HP",
    "19": "Severe faint",
    "20": "Near-shock faint",
    "21": "Panic 1d min",
    "22": "-10 Delusion",
    "23": "-10 mental disadvantage",
    "24": "-15 physical disadvantages",
    "25": "Disadvantage worsens",
    "26": "Faint + Delusion",
    "27": "Faint + disadvantage",
    "28": "Light coma",
    "29": "Coma 1d hours",
    "30": "Catatonia 1d days",
    "31": "Seizure",
    "32": "Stricken, 2d injury",
    "33": "Total panic",
    "34": "-15 Delusion",
    "35": "-15 mental disadvantage",
    "36": "-20 physical disadvantages",
    "37": "-30 physical disadvantages",
    "38": "Coma + Delusion",
    "39": "Coma + disadvantage",
    "40+": "Coma, -1 IQ",
}


def fright_table_result(total: int) -> str:
    """The rolled row's label and where its full effect is printed."""
    row = fright_table_row(total)
    return f"**{FRIGHT_RESULT_LABELS[row]}** (row {row}, {FRIGHT_TABLE_PAGES})"
