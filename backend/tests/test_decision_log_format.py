"""`docs/ENTSCHEIDUNGSLOG.md` stays append-only and well-formed.

The log is only appended to (`.gitattributes`: `merge=union`), so two branches that
both add a line merge without a conflict. Two things can still go wrong silently,
and only this test notices:

* a line appears twice (a union merge keeps both copies of a line added on both sides);
* a row has a different number of cells than the header, so the table renders wrongly.

A pipe inside a code span or written as ``\\|`` is not a cell separator here.

Rows from before this test existed that already break the second rule stay as they
are (the log is not rewritten); they are listed in `LEGACY_ROWS` by their start. A new
row must not be added there.
"""

from __future__ import annotations

import re
from pathlib import Path

LOG = Path(__file__).resolve().parents[2] / "docs" / "ENTSCHEIDUNGSLOG.md"

SEPARATOR = re.compile(r"`[^`]*`|\\\||\|")
ALIGNMENT_ROW = re.compile(r"^\|[\s:|-]+\|$")
PREFIX = 60

LEGACY_ROWS = frozenset(
    {
        "| 2026-10-15 | **M4-13c-1 umgesetzt** (PR #152, nur Frontend",
        "| 2026-10-26 | **UI-01c Nachtrag (Otto, zu PR #196): vier Er",
        "| 2026-10-28 | **UI-02b umgesetzt (Draft-PR): Overlays „Labe",
        "| 2026-10-28 | **UI-02b Auslegung (Vorschlag) und Frage an O",
        "| 2026-10-28 | **UI-02c umgesetzt (Draft-PR): Basemap und Pr",
        "| 2026-10-30 | **NM4-52 umgesetzt (Draft-PR [#238](https://g",
        "| 2026-10-30 | **NM4-09 umgesetzt (Draft-PR [#242](https://g",
        "| 2026-10-30 | **NM4-18 umgesetzt (Draft-PR [#242](https://g",
        "| 2026-10-31 | **DS-03b umgesetzt (Draft-PR [#265](https://g",
        "| 2026-11-02 | **UI-03a, Browsertest Otto zu [#277](https://",
    }
)


def cell_count(row: str) -> int:
    """Number of cells in a table row; pipes in code spans or escaped do not count."""
    return sum(m.group() == "|" for m in SEPARATOR.finditer(row.strip())) - 1


def duplicates(rows: list[str]) -> list[str]:
    seen: set[str] = set()
    twice: list[str] = []
    for row in rows:
        if row in seen:
            twice.append(row)
        seen.add(row)
    return twice


def wrong_width(rows: list[str], width: int) -> list[str]:
    return [r for r in rows if cell_count(r) != width and r[:PREFIX] not in LEGACY_ROWS]


def table_rows() -> list[str]:
    lines = LOG.read_text(encoding="utf-8").splitlines()
    return [ln for ln in lines if ln.startswith("|") and not ALIGNMENT_ROW.match(ln)]


def test_log_has_a_table_with_a_header():
    rows = table_rows()
    assert rows and cell_count(rows[0]) == 4


def test_no_row_appears_twice():
    twice = duplicates(table_rows())
    assert not twice, "Duplicate decision log rows:\n" + "\n".join(r[:100] for r in twice)


def test_every_row_has_the_header_width():
    rows = table_rows()
    bad = wrong_width(rows[1:], cell_count(rows[0]))
    assert not bad, "Rows with a different number of cells than the header:\n" + "\n".join(r[:100] for r in bad)


def test_legacy_rows_still_exist_and_still_break():
    """A legacy entry that no longer matches is dead weight and must be removed."""
    rows = table_rows()
    width = cell_count(rows[0])
    live = {r[:PREFIX] for r in rows if cell_count(r) != width}
    assert live == LEGACY_ROWS


def test_checker_catches_a_duplicate_and_a_short_row():
    row = "| 2026-11-06 | text | fest | doc |"
    assert duplicates([row, "| x | y | z | w |", row]) == [row]
    assert wrong_width(["| 2026-11-06 | text | fest |"], 4) != []
    assert wrong_width(["| 2026-11-06 | `a|b` | fest | doc \\| x |"], 4) == []
    assert wrong_width(["| a | b | c | d | e |"], 4) != []
