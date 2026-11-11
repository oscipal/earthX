"""The lexical arm of the dataset search with its hard filters (adr/0026 §4.2, §4.4; M5-22 plan §3.5, §3.6).

Two ranked lists over the index of ``search_index``, both after the same hard filters, fused by Reciprocal Rank Fusion
with k = 60:

* **Full text:** the query is cut into units by the glossary (:func:`~earthx.catalog.glossary.parse_query`); each
  unit is the OR of its terms as phrases in the configurations ``simple``, ``german`` and ``english`` over
  ``unaccent``. How the units are joined is :data:`JOINING` (F2, chosen on the evaluation set). A word that is a stop
  word in German or English ("bei", "in", "the") is no condition, as ``websearch_to_tsquery`` drops it. Ranked by
  ``ts_rank_cd`` with the weights of the search text.
* **Trigrams:** ``word_similarity`` of the normalized query with id, title and keywords, from
  :data:`TRIGRAM_THRESHOLD` on; it finds "Sentinal 2" and "Worldcovr".

Hard filters before both arms: the area meets the footprints of a materialized dataset that has items in pgstac,
otherwise the box of the collection (plan A4); the period overlaps the extent in time, an open end meaning now, and a
dataset without a time axis never drops out for a period but is named in ``ignored_filters``. Without text the
filtered list comes in the order of the ids, without a rank (plan A6).

Every text goes to SQL as a parameter, never into the statement.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from psycopg import sql

from earthx.catalog.glossary import Glossary, Unit, normalize, parse_query
from earthx.catalog.search_index import CONFIGS

MAX_QUERY_CHARS = 200
#: adr/0026 §3.1, §4.4.
RRF_K = 60
#: The least ``word_similarity`` the trigram arm counts, above the default 0.3 of pg_trgm (plan §3.5).
TRIGRAM_THRESHOLD = 0.5
#: The share of the units a dataset has to match under :attr:`Joining.SHARE`.
MIN_SHARE = 0.5
TIME_FILTER = "datetime"


class Joining(Enum):
    """How the units of a query are joined in the full text (F2)."""

    #: Every unit.
    ALL = "all"
    #: Every unit that some search text has; a unit no dataset knows ("Bewölkung") is dropped.
    KNOWN = "known"
    #: At least :data:`MIN_SHARE` of the units.
    SHARE = "share"


JOINING = Joining.KNOWN


class QueryTooLong(ValueError):
    """The query is longer than :data:`MAX_QUERY_CHARS`."""


@dataclass(frozen=True, slots=True)
class SearchResult:
    """The dataset ids in rank order, and the filters some of them were not filtered by."""

    ids: tuple[str, ...]
    ignored_filters: tuple[str, ...] = ()
    ignored_filters_by_collection: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


def box_area(west: float, south: float, east: float, north: float) -> dict[str, Any]:
    """A GeoJSON polygon of a box in degrees."""
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}


_FILTERED = """
    SELECT s.dataset_id, s.title, s.document, s.trigram_text, s.has_time_axis
    FROM public.earthx_dataset_search s
    WHERE (%(area)s::text IS NULL OR CASE
            WHEN s.item_holding = 'materialized'
                 AND EXISTS (SELECT 1 FROM pgstac.items i WHERE i.collection = s.dataset_id)
            THEN EXISTS (
                SELECT 1 FROM pgstac.items i
                WHERE i.collection = s.dataset_id
                  AND ST_Intersects(i.geometry, ST_SetSRID(ST_GeomFromGeoJSON(%(area)s::text), 4326)))
            ELSE ST_Intersects(
                ST_MakeEnvelope(s.west, s.south, s.east, s.north, 4326),
                ST_SetSRID(ST_GeomFromGeoJSON(%(area)s::text), 4326))
          END)
      AND (NOT %(timed)s OR NOT s.has_time_axis OR (
            (%(until)s::timestamptz IS NULL OR s.time_start IS NULL OR s.time_start <= %(until)s::timestamptz)
            AND (%(since)s::timestamptz IS NULL OR COALESCE(s.time_end, now()) >= %(since)s::timestamptz)))
"""


def _unit_query(unit: Unit, number: int) -> sql.Composed:
    """The OR of every term of ``unit`` as a phrase in every configuration."""
    return sql.SQL(" || ").join(
        sql.SQL("phraseto_tsquery({}::regconfig, unaccent({}))").format(
            sql.Literal(config), sql.Placeholder(f"term_{number}_{index}")
        )
        for index, _ in enumerate(unit.terms)
        for config in CONFIGS
    )


def _stop_word(unit: Unit, number: int) -> sql.Composable:
    """True for a single word that German or English drops as a stop word; a glossary unit never is one."""
    if unit.from_glossary:
        return sql.SQL("false")
    return sql.SQL(" OR ").join(
        sql.SQL("numnode(phraseto_tsquery({}::regconfig, unaccent({}))) = 0").format(
            sql.Literal(config), sql.Placeholder(f"term_{number}_0")
        )
        for config in ("german", "english")
    )


_JOIN_CONDITION = {
    Joining.ALL: "h.matched = (SELECT count(*) FROM units)",
    Joining.KNOWN: "(SELECT count(*) FROM known) > 0 AND h.matched_known = (SELECT count(*) FROM known)",
    Joining.SHARE: "h.matched > 0 AND h.matched >= ceil(%(share)s * (SELECT count(*) FROM units))",
}


def _full_text_sql(units: Sequence[Unit], joining: Joining) -> sql.Composed:
    rows = sql.SQL(", ").join(
        sql.SQL("({}, {}, {})").format(sql.Literal(number), _unit_query(unit, number), _stop_word(unit, number))
        for number, unit in enumerate(units)
    )
    return sql.SQL(
        """
        WITH all_units(ord, query, stop) AS (VALUES {rows}),
        units AS (SELECT ord, query FROM all_units WHERE NOT stop),
        known AS (
            SELECT u.ord FROM units u
            WHERE EXISTS (SELECT 1 FROM public.earthx_dataset_search s WHERE s.document @@ u.query)),
        filtered AS ({filtered}),
        hits AS (
            SELECT f.dataset_id, f.title, f.has_time_axis,
                   count(*) FILTER (WHERE f.document @@ u.query) AS matched,
                   count(*) FILTER (WHERE f.document @@ u.query AND u.ord IN (SELECT ord FROM known)) AS matched_known,
                   sum(ts_rank_cd(f.document, u.query)) AS rank
            FROM filtered f CROSS JOIN units u
            GROUP BY f.dataset_id, f.title, f.has_time_axis)
        SELECT h.dataset_id, h.title, h.has_time_axis, h.rank FROM hits h
        WHERE {condition}
        ORDER BY h.rank DESC, h.title, h.dataset_id
        """
    ).format(rows=rows, filtered=sql.SQL(_FILTERED), condition=sql.SQL(_JOIN_CONDITION[joining]))


_TRIGRAM_SQL = sql.SQL(
    """
    WITH filtered AS ({filtered})
    SELECT f.dataset_id, f.title, f.has_time_axis, word_similarity(%(normal)s, f.trigram_text) FROM filtered f
    WHERE word_similarity(%(normal)s, f.trigram_text) >= %(threshold)s
    ORDER BY word_similarity(%(normal)s, f.trigram_text) DESC, f.title, f.dataset_id
    """
).format(filtered=sql.SQL(_FILTERED))

_UNRANKED_SQL = sql.SQL(
    "WITH filtered AS ({filtered}) SELECT f.dataset_id, f.title, f.has_time_axis, 0 FROM filtered f ORDER BY f.dataset_id"
).format(filtered=sql.SQL(_FILTERED))


def ranks(scored: Sequence[tuple[str, float]]) -> dict[str, int]:
    """The rank of each id by its score, highest first; equal scores share the better rank (1, 2, 2, 4).

    A tie must not be broken before the fusion: by title, "ESA WorldCover" would come before "Sentinel-2" in every arm
    where both score the same, and win the fusion for "Sentinel-2".
    """
    return {dataset_id: 1 + sum(other > score for _, other in scored) for dataset_id, score in scored}


def fuse(*ranked: Mapping[str, int], titles: Mapping[str, str], k: int = RRF_K) -> tuple[str, ...]:
    """Reciprocal Rank Fusion of the ranks per arm: ``Σ 1 / (k + rank)``; ties by title, then id."""
    scores: dict[str, float] = {}
    for arm in ranked:
        for dataset_id, rank in arm.items():
            scores[dataset_id] = scores.get(dataset_id, 0.0) + 1 / (k + rank)
    return tuple(sorted(scores, key=lambda i: (-scores[i], titles[i], i)))


def _filter_params(area: Mapping[str, Any] | None, period: tuple[datetime | None, datetime | None] | None) -> dict:
    since, until = period if period is not None else (None, None)
    return {
        "area": None if area is None else json.dumps(area),
        "timed": period is not None,
        "since": since,
        "until": until,
    }


async def search_datasets(
    conn: Any,
    text: str | None,
    *,
    area: Mapping[str, Any] | None = None,
    period: tuple[datetime | None, datetime | None] | None = None,
    joining: Joining = JOINING,
    threshold: float = TRIGRAM_THRESHOLD,
    glossary: Glossary | None = None,
) -> SearchResult:
    """The datasets for ``text`` within ``area`` (a GeoJSON polygon in WGS 84) and ``period`` (either end open), ranked.

    ``conn`` is the caller's async connection; the search runs in a transaction (a savepoint inside the caller's) and
    writes nothing. A ``text`` of only spaces is no text.
    """
    if text is not None and len(text) > MAX_QUERY_CHARS:
        raise QueryTooLong(f"the query is longer than {MAX_QUERY_CHARS} characters")
    params = _filter_params(area, period)
    rows: dict[str, tuple[str, bool]] = {}

    async def run(statement: sql.Composable, extra: Mapping[str, object]) -> list[tuple[str, float]]:
        async with conn.cursor() as cur:
            await cur.execute(statement, {**params, **extra})
            found = await cur.fetchall()
        for dataset_id, title, timed, _ in found:
            rows[dataset_id] = (title, timed)
        return [(row[0], float(row[3])) for row in found]

    # One snapshot for both arms; a stop word makes Postgres say so as a NOTICE, which is no news here.
    async with conn.transaction():
        await conn.execute("SET LOCAL client_min_messages = warning")
        if text is None or not text.strip():
            ids: tuple[str, ...] = tuple(dataset_id for dataset_id, _ in await run(_UNRANKED_SQL, {}))
        else:
            units = parse_query(text, glossary)
            normal = normalize(text)
            full_text = []
            if units:
                terms = {f"term_{n}_{i}": term for n, unit in enumerate(units) for i, term in enumerate(unit.terms)}
                full_text = await run(_full_text_sql(units, joining), {**terms, "share": MIN_SHARE})
            trigrams = await run(_TRIGRAM_SQL, {"normal": normal, "threshold": threshold}) if normal else []
            ids = fuse(ranks(full_text), ranks(trigrams), titles={i: title for i, (title, _) in rows.items()})
    if period is None:
        return SearchResult(ids)
    by_collection = {i: (TIME_FILTER,) for i in ids if not rows[i][1]}
    return SearchResult(ids, (TIME_FILTER,) if by_collection else (), by_collection)
