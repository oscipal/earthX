"""Reading listed entries for ``api``: one page in the order of the catalogue, a count, one entry (M5-40 plan §5.5).

Every function reads one page or one row through the partial indexes of ``earthx_listed_entry`` (migration ``021``);
nothing here loads the whole list, and nothing is kept between requests, so any instance of ``api`` answers any page.
The order of the catalogue is :func:`~earthx.catalog.listed.sort_title`, then the id; a page goes on after the pair of
its last entry (keyset), never by an offset.

The full entries of the registry are few (10³ at most, M5-35 F3): :func:`full_entries` gives the ones of a filter in
the same order, so that ``api`` can lay them and the listed ones into one page.

Every value goes to SQL as a parameter. Nothing here logs an area, a region or a page key.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from psycopg import sql

from earthx.catalog.listed import sort_title

__all__ = [
    "Gone",
    "ListedFilter",
    "ListedRow",
    "count_listed",
    "full_entries",
    "listed_documents",
    "listed_entry",
    "listed_page",
    "matching_listed",
]


@dataclass(frozen=True, slots=True)
class ListedFilter:
    """The filters of one search: a category, an area as GeoJSON, a period with open ends as ``None``, region codes
    (any of)."""

    category: str | None = None
    area: Mapping[str, Any] | None = None
    period: tuple[datetime | None, datetime | None] | None = None
    regions: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ListedRow:
    """One listed entry of a page: its key in the order, its document, and whether a period was not applied to it."""

    sort_title: str
    dataset_id: str
    content: dict[str, Any]
    period_ignored: bool


@dataclass(frozen=True, slots=True)
class Gone:
    """A tombstone (adr/0033 §9): the entry was removed, for this reason."""

    reason: str


#: The places a dataset is also listed at (M5-20 plan §8, F4 = 1): the link and the files of every duplicate of the
#: entry, added when it is served, so that a change of a duplicate needs no rewrite of the main entry. Absent where
#: there is none.
_ALSO_AT = """
    CASE WHEN EXISTS (SELECT 1 FROM public.earthx_listed_entry d WHERE d.duplicate_of = e.dataset_id
                      AND d.state = 'duplicate')
    THEN jsonb_build_object('earthx:also_at', (
        SELECT jsonb_agg(jsonb_build_object(
                   'source_id', d.source_id,
                   'source_url', d.content -> 'earthx:listing' -> 'source_url',
                   'distributions', coalesce(d.content -> 'earthx:distributions', '[]'::jsonb))
               ORDER BY d.dataset_id)
        FROM public.earthx_listed_entry d WHERE d.duplicate_of = e.dataset_id AND d.state = 'duplicate'))
    ELSE jsonb_build_object() END
"""


def _conditions(where: ListedFilter) -> tuple[sql.Composable, dict[str, Any]]:
    parts = [sql.SQL("state = 'published'")]
    params: dict[str, Any] = {}
    if where.category is not None:
        parts.append(sql.SQL("category = %(category)s"))
        params["category"] = where.category
    if where.area is not None:
        parts.append(
            sql.SQL(
                "footprint && ST_SetSRID(ST_GeomFromGeoJSON(%(area)s), 4326) "
                "AND ST_Intersects(footprint, ST_SetSRID(ST_GeomFromGeoJSON(%(area)s), 4326))"
            )
        )
        params["area"] = json.dumps(where.area)
    if where.period is not None:
        # An entry without a period stays and is named as one the filter did not apply to (plan F10).
        parts.append(sql.SQL("(time_span IS NULL OR time_span && tstzrange(%(since)s, %(until)s, '[]'))"))
        params["since"], params["until"] = where.period
    if where.regions:
        parts.append(sql.SQL("regions && %(regions)s::text[]"))
        params["regions"] = list(where.regions)
    return sql.SQL(" AND ").join(parts), params


async def listed_page(conn: Any, where: ListedFilter, *, after: tuple[str, str] | None, limit: int) -> list[ListedRow]:
    """At most ``limit`` published entries of ``where`` after the key ``after``, in the order of the catalogue."""
    condition, params = _conditions(where)
    if after is not None:
        condition = sql.SQL("{} AND (sort_title, dataset_id) > (%(after_title)s, %(after_id)s)").format(condition)
        params["after_title"], params["after_id"] = after
    # The keys of the page first, through the indexes; the documents only for them. Built for every match before the
    # sort, the documents of a city's 22 000 matches cost a third of a second (plan §8).
    statement = sql.SQL(
        "SELECT e.sort_title, e.dataset_id, e.content || jsonb_build_object('earthx:regions', to_jsonb(e.regions)) || "
        + _ALSO_AT
        + ", "
        "e.time_span IS NULL FROM (SELECT dataset_id FROM public.earthx_listed_entry WHERE {} "
        "ORDER BY sort_title, dataset_id LIMIT %(limit)s) AS page "
        "JOIN public.earthx_listed_entry e USING (dataset_id) ORDER BY e.sort_title, e.dataset_id"
    ).format(condition)
    async with conn.cursor() as cur:
        await cur.execute(statement, {**params, "limit": limit})
        rows = await cur.fetchall()
    timed = where.period is not None
    return [ListedRow(row[0], row[1], row[2], timed and row[3]) for row in rows]


async def count_listed(conn: Any, where: ListedFilter, *, cap: int) -> int:
    """How many published entries ``where`` matches, counted up to ``cap`` at most (plan F4)."""
    condition, params = _conditions(where)
    statement = sql.SQL(
        "SELECT count(*) FROM (SELECT 1 FROM public.earthx_listed_entry WHERE {} LIMIT %(cap)s) AS hits"
    ).format(condition)
    async with conn.cursor() as cur:
        await cur.execute(statement, {**params, "cap": cap})
        row = await cur.fetchone()
    return int(row[0])


async def full_entries(conn: Any, ids: Sequence[str], regions: Sequence[str]) -> list[tuple[str, str]]:
    """The key in the order of the catalogue of each of the full entries ``ids``, sorted; with ``regions``, only those
    whose box overlaps one of them in more than a border (the same rule that derives the regions of a listed entry)."""
    if not ids:
        return []
    statement = (
        "SELECT s.dataset_id, s.title FROM public.earthx_dataset_search s WHERE s.dataset_id = ANY(%(ids)s)"
        if not regions
        else "SELECT s.dataset_id, s.title FROM public.earthx_dataset_search s, "
        "LATERAL (SELECT ST_MakeEnvelope(s.west, s.south, s.east, s.north, 4326) AS box) b "
        "WHERE s.dataset_id = ANY(%(ids)s) AND EXISTS (SELECT 1 FROM public.earthx_region_part p "
        "WHERE p.code = ANY(%(regions)s) AND ST_Intersects(p.part, b.box) AND NOT ST_Touches(p.part, b.box))"
    )
    async with conn.cursor() as cur:
        await cur.execute(statement, {"ids": list(ids), "regions": list(regions)})
        rows = await cur.fetchall()
    return sorted((sort_title(title), dataset_id) for dataset_id, title in rows)


async def matching_listed(conn: Any, ids: Sequence[str], where: ListedFilter) -> frozenset[str]:
    """The published entries of ``ids`` that ``where`` matches."""
    if not ids:
        return frozenset()
    condition, params = _conditions(where)
    statement = sql.SQL("SELECT dataset_id FROM public.earthx_listed_entry WHERE dataset_id = ANY(%(ids)s) AND {}").format(
        condition
    )
    async with conn.cursor() as cur:
        await cur.execute(statement, {**params, "ids": list(ids)})
        return frozenset(row[0] for row in await cur.fetchall())


async def listed_documents(conn: Any, ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """The documents of the published entries of ``ids``, as :func:`listed_entry` gives one."""
    if not ids:
        return {}
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT dataset_id, content || jsonb_build_object('earthx:regions', to_jsonb(regions)) || "
            + _ALSO_AT
            + " FROM public.earthx_listed_entry e WHERE dataset_id = ANY(%s) AND state = 'published'",
            (list(ids),),
        )
        return {row[0]: row[1] for row in await cur.fetchall()}


async def listed_entry(conn: Any, dataset_id: str) -> dict[str, Any] | Gone | None:
    """The document of a published listed entry, :class:`Gone` for a tombstone, ``None`` for anything else."""
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT state, content || jsonb_build_object('earthx:regions', to_jsonb(regions)) || "
            + _ALSO_AT
            + ", removed_reason FROM public.earthx_listed_entry e WHERE dataset_id = %s"
            " AND state IN ('published', 'tombstone')",
            (dataset_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return Gone(row[2]) if row[0] == "tombstone" else row[1]
