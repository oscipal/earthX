"""The groups of the Data catalogue in the frontend are the categories of ``backend/catalog/categories.yaml`` (M5-40).

The frontend keeps a copy of ids and titles in ``frontend/src/catalogue.ts`` (``CATEGORIES`` and ``OTHER_CATEGORY``)
while the plan's question H4 is open; this test holds the copy equal to the file, in order, so that the file stays the
one place a category is decided.
"""

from __future__ import annotations

import re
from pathlib import Path

from earthx.catalog.categories import load_categories

CATALOGUE_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "catalogue.ts"
_ENTRY = re.compile(r"\{ id: '([a-z_]+)', title: '([^']+)' \}")


def _copy() -> list[tuple[str, str]]:
    text = CATALOGUE_TS.read_text(encoding="utf-8")
    block = text[text.index("export const CATEGORIES = [") : text.index("export const CATALOGUE_GROUPS")]
    return _ENTRY.findall(block)


def test_the_frontend_lists_the_categories_of_the_file_in_its_order() -> None:
    categories = load_categories()
    assert _copy() == [(category, categories.titles[category]) for category in categories.ids]


def test_the_pattern_reads_every_entry_of_the_copy() -> None:
    text = CATALOGUE_TS.read_text(encoding="utf-8")
    block = text[text.index("export const CATEGORIES = [") : text.index("export const CATALOGUE_GROUPS")]
    assert len(_copy()) == block.count("{ id:")
