"""The index of the dataset search: written by ``catalog-load``, checked when `api` starts (M5-22 plan §3.4).

One row of ``public.earthx_dataset_search`` per registry entry (migration ``016``). :func:`write_search_index` writes
a row only where the search text, the extent or the way the items are held changed, and removes the rows of datasets
the registry no longer has; prototype entries are only where the registry of the instance holds them (adr/0024 R5).
:func:`check_search_index` stops a start where the index is not the one this code would write (plan A3): a new
search text cannot quietly run on an old index.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql

from earthx.catalog.registry import DatasetConfig, DatasetRegistry
from earthx.catalog.search_text import SearchText, search_text

#: The three configurations of the full text (adr/0026 §4.2): names and abbreviations, German, English.
CONFIGS = ("simple", "german", "english")
_PARTS = (("a", "A"), ("b", "B"), ("c", "C"), ("d", "D"))


def document_sql() -> sql.Composed:
    """``tsvector`` of the four parts with their weights, each in every configuration over ``unaccent``."""
    return sql.SQL(" || ").join(
        sql.SQL("setweight(to_tsvector({}::regconfig, unaccent({})), {})").format(
            sql.Literal(config), sql.Placeholder(part), sql.Literal(weight)
        )
        for part, weight in _PARTS
        for config in CONFIGS
    )


_UPSERT = sql.SQL(
    """
    INSERT INTO public.earthx_dataset_search AS stored (
        dataset_id, title, text_a, text_b, text_c, text_d, text_hash, document, trigram_text,
        west, south, east, north, time_start, time_end, has_time_axis, item_holding
    ) VALUES (
        %(dataset_id)s, %(title)s, %(a)s, %(b)s, %(c)s, %(d)s, %(text_hash)s, {document}, %(trigram_text)s,
        %(west)s, %(south)s, %(east)s, %(north)s, %(time_start)s, %(time_end)s,
        %(has_time_axis)s, %(item_holding)s
    )
    ON CONFLICT (dataset_id) DO UPDATE SET
        title = EXCLUDED.title, text_a = EXCLUDED.text_a, text_b = EXCLUDED.text_b, text_c = EXCLUDED.text_c,
        text_d = EXCLUDED.text_d, text_hash = EXCLUDED.text_hash, document = EXCLUDED.document,
        trigram_text = EXCLUDED.trigram_text, west = EXCLUDED.west, south = EXCLUDED.south, east = EXCLUDED.east,
        north = EXCLUDED.north, time_start = EXCLUDED.time_start,
        time_end = EXCLUDED.time_end, has_time_axis = EXCLUDED.has_time_axis, item_holding = EXCLUDED.item_holding
    WHERE (stored.title, stored.text_hash, stored.trigram_text, stored.west, stored.south, stored.east, stored.north,
           stored.time_start, stored.time_end, stored.has_time_axis, stored.item_holding)
       IS DISTINCT FROM (EXCLUDED.title, EXCLUDED.text_hash, EXCLUDED.trigram_text, EXCLUDED.west, EXCLUDED.south,
           EXCLUDED.east, EXCLUDED.north, EXCLUDED.time_start, EXCLUDED.time_end, EXCLUDED.has_time_axis,
           EXCLUDED.item_holding)
    RETURNING dataset_id
    """
)


@dataclass(frozen=True, slots=True)
class IndexOutcome:
    """What one run of :func:`write_search_index` changed: rows written (new or changed) and rows removed."""

    written: tuple[str, ...]
    removed: tuple[str, ...]


def _row(config: DatasetConfig, text: SearchText) -> dict[str, object]:
    west, south, east, north = config.spatial_extent.bbox
    return {
        "dataset_id": config.dataset_id,
        "title": config.title,
        "a": text.a,
        "b": text.b,
        "c": text.c,
        "d": text.d,
        "text_hash": text.text_hash,
        "trigram_text": text.trigram_text,
        "west": west,
        "south": south,
        "east": east,
        "north": north,
        "time_start": config.temporal_extent.start,
        "time_end": config.temporal_extent.end,
        "has_time_axis": config.capabilities.time_range,
        "item_holding": config.source.item_holding.value,
    }


def write_search_index(conn: psycopg.Connection, registry: DatasetRegistry) -> IndexOutcome:
    """Bring the index in line with ``registry``. Idempotent; the caller owns the transaction."""
    upsert = _UPSERT.format(document=document_sql())
    written = []
    with conn.cursor() as cur:
        for config in registry:
            cur.execute(upsert, _row(config, search_text(config)))
            if cur.fetchone() is not None:
                written.append(config.dataset_id)
        cur.execute(
            "DELETE FROM public.earthx_dataset_search WHERE NOT (dataset_id = ANY(%s)) RETURNING dataset_id",
            ([config.dataset_id for config in registry],),
        )
        removed = sorted(row[0] for row in cur.fetchall())
    return IndexOutcome(tuple(written), tuple(removed))


class SearchIndexMismatch(RuntimeError):
    """The index is not the one this code would write from the registry; names the datasets, nothing else."""


#: What the start check compares: the text by its hash, and every column the hard filters read.
_CHECKED = ("text_hash", "west", "south", "east", "north", "time_start", "time_end", "has_time_axis", "item_holding")


def compare_index(expected: Mapping[str, tuple], stored: Mapping[str, tuple]) -> list[str]:
    """What differs between the rows ``expected`` from the registry and those ``stored``, in words."""
    problems = []
    if missing := sorted(expected.keys() - stored.keys()):
        problems.append(f"no row for {', '.join(missing)}")
    if stale := sorted(i for i in expected.keys() & stored.keys() if expected[i] != stored[i]):
        problems.append(f"an old search text or extent for {', '.join(stale)}")
    if orphans := sorted(stored.keys() - expected.keys()):
        problems.append(f"rows without an entry for {', '.join(orphans)}")
    return problems


def expected_rows(configs: Iterable[DatasetConfig]) -> dict[str, tuple]:
    """Per entry the checked columns as :func:`write_search_index` writes them."""
    rows = {}
    for config in configs:
        row = _row(config, search_text(config))
        rows[config.dataset_id] = tuple(row[column] for column in _CHECKED)
    return rows


async def check_search_index(registry: DatasetRegistry, conn: Any) -> None:
    """Refuse to start where the index differs from the registry (plan §3.4, A3), like the check of item holdings.

    Every entry needs a row with the hash of the text this code builds and the extent, time axis and item holding the
    filters read; no row may be left without an entry.
    """
    async with conn.cursor() as cur:
        await cur.execute("SELECT to_regclass('public.earthx_dataset_search')")
        row = await cur.fetchone()
        if row is None or row[0] is None:
            raise SearchIndexMismatch("the search index does not exist; run `python -m earthx.catalog.load`")
        await cur.execute(
            sql.SQL("SELECT dataset_id, {} FROM public.earthx_dataset_search").format(
                sql.SQL(", ").join(map(sql.Identifier, _CHECKED))
            )
        )
        stored = {found[0]: tuple(found[1:]) for found in await cur.fetchall()}
    problems = compare_index(expected_rows(registry), stored)
    if problems:
        raise SearchIndexMismatch(
            f"the search index does not match the registry ({'; '.join(problems)}); run `python -m earthx.catalog.load`"
        )
