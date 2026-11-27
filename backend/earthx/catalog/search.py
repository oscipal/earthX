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

A number never drops out of a query that names a dataset (plan §11.7, A18): in the trigram arm every number of the
query, in the full text every number right after a name that carries a number itself ("Sentinel 3", "Copernicus DEM
90"), has to stand in the id, title or keywords of the dataset. A number on its own has to stand there as a word ("1"
is not the one of "c1"); the digits of a word with letters ("sentinel3", "l2a") as a run of digits anywhere. A number
with a unit ("10 m") or a year is no number of a name and drops out like any unknown word. Without such a
dataset the list is empty (adr/0026 K9); the full text cannot check this itself, as it splits "GLO-30" into "glo"
and "-30". Nor does a bare number carry a dataset in the full text on its own: "Landsat 9", with no Landsat in the
catalogue, finds nothing for its "9".

The index holds full and listed entries (migration ``035``); a listed row counts only while its entry is published (a
harvested entry whose link has not passed the check is ``link_hidden`` and no hit, M5-67), and the area is matched
against its footprint. Both arms go through the indexes of the table: the full text joins a row only to the units it
matches, the trigram arm asks ``<%`` with the threshold set for the transaction.

An area is applied before the text where that is cheaper (M5-65; :class:`Start`). Postgres cannot tell: it takes the
hits of any text for 0.5 % of the rows, and a few large footprints over a small area make its count of the footprints
that meet it a hundredth of the true one. So the search counts, up to a limit: where at most :data:`AREA_FIRST_MAX`
published listed entries have a footprint whose box meets the area and the text has more than :data:`TEXT_FIRST_MAX`
hits, it starts from the footprints (the GiST index of ``earthx_listed_entry``) and looks each entry up by its id;
otherwise from the text, as before. At 10⁵ entries that makes a text with many hits ("Götterbaum", 4·10⁴) over a city
6 to 9 times as fast, and costs a text with few ("Sentinel-2") about 10 ms for the two counts. A full row has the
envelope of its box in ``geometry`` (migration ``038``). The statements are sent without preparation: a plan prepared
for one area would serve the next.

Hard filters before both arms: the area meets the footprints of a materialized dataset that has items in pgstac,
otherwise the box of the collection (plan A4); the period overlaps the extent in time, an open end meaning now, and a
dataset without a time axis never drops out for a period but is named in ``ignored_filters``. Without text the
filtered full entries come in the order of the ids, without a rank (plan A6).

The rank of a hit is the sum of the ranks of the units it matches, added in the order of the units: a sum of ``real``
values depends on the order, which Postgres leaves to the plan, and equal ranks decide the fusion.

Broad words (M5-66, docs/plans/m5/m5-66-breite-suche.md): the filters of the Data catalogue (:class:`Kept`: kind of
entry, category, regions) stand in both arms, before any rank, so that a filter never drops hits after the depth. Each
arm hands its places up to :data:`DEPTH` to the fusion, a tie at the last place whole; every hit is still ranked in
SQL, since an exact rank needs each ``tsvector``. ``matched`` counts the hits of both arms together up to
:data:`COUNT_UP_TO` and is ``None`` above it (M5-40 F4).

Every text goes to SQL as a parameter, never into the statement.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping, Sequence
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
#: The places of each arm that go into the fusion (M5-42 F5 = 1, M5-66), a tie at the last one whole: every hit is
#: ranked in SQL, only these are fused. A hit beyond it in one arm adds nothing there to its fused score.
DEPTH = 1_000
#: Up to here the search counts its hits exactly (M5-40 F4); above it the number is left out.
COUNT_UP_TO = 10_000
#: The share of the units a dataset has to match under :attr:`Joining.SHARE`.
MIN_SHARE = 0.5
TIME_FILTER = "datetime"
_NUMBER = re.compile(r"[0-9]+")
_LETTER = re.compile(r"[^\W\d_]")
_YEAR = re.compile(r"(19|20)[0-9]{2}")
_UNITS = frozenset({"m", "km", "cm"})
_MEASURE = re.compile(r"[0-9]+(m|km|cm)")


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
    #: The ids of ``ids`` that are listed entries.
    listed: frozenset[str] = frozenset()
    #: How many datasets match, exact up to the ``count_up_to`` of the search; ``None`` above it.
    matched: int | None = None


def box_area(west: float, south: float, east: float, north: float) -> dict[str, Any]:
    """A GeoJSON polygon of a box in degrees."""
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}


@dataclass(frozen=True, slots=True)
class Kept:
    """The filters of the Data catalogue a search keeps to in its statements, before any rank (M5-66).

    ``entry`` keeps it to ``full`` or ``listed`` rows. ``category`` keeps listed rows to that category; a full entry has
    its category in the registry, not in the index, so ``full_ids`` names the full entries that may be hits (``None``:
    all). ``regions`` (any of them) keeps listed rows by their regions and full rows by their box, which has to overlap
    one of the regions in more than a border: the rule that derives the regions of a listed entry.
    """

    entry: str | None = None
    category: str | None = None
    full_ids: Collection[str] | None = None
    regions: tuple[str, ...] = ()


#: No filter of the Data catalogue.
ALL_KEPT = Kept()

_AREA = "ST_SetSRID(ST_GeomFromGeoJSON(%(area)s::text), 4326)"
#: The period meets the extent in time, an open end meaning now; an entry without a time axis never drops out.
_TIME = """(NOT %(timed)s OR NOT f.has_time_axis OR (
            (%(until)s::timestamptz IS NULL OR f.time_start IS NULL OR f.time_start <= %(until)s::timestamptz)
            AND (%(since)s::timestamptz IS NULL OR COALESCE(f.time_end, now()) >= %(since)s::timestamptz)))"""
#: A full entry with items in pgstac is met by the footprints of its items, any other by its box (plan A4).
_FULL_AREA = f"""CASE
            WHEN f.item_holding = 'materialized'
                 AND EXISTS (SELECT 1 FROM pgstac.items i WHERE i.collection = f.dataset_id)
            THEN EXISTS (
                SELECT 1 FROM pgstac.items i
                WHERE i.collection = f.dataset_id AND ST_Intersects(i.geometry, {_AREA}))
            ELSE ST_Intersects(f.geometry, {_AREA})
          END"""


class Start(Enum):
    """Where a search starts (M5-65): the planner cannot know how many rows a text matches, so the search says."""

    #: No area: from the text.
    NO_AREA = "no_area"
    #: From the published listed entries whose footprint meets the area, each looked up in the index by its id.
    AREA = "area"
    #: From the text; the footprint is checked on its hits.
    TEXT = "text"


#: The most published listed entries whose footprint has a box meeting the area, up to which a search can start from the
#: area. Looking up one entry costs about as much as reading one hit of the text, 20 to 30 µs at 10⁵ entries.
AREA_FIRST_MAX = 5_000
#: The most hits of the full text, up to which a search starts from the text whatever the area keeps: reading 500
#: hits is 15 ms at most, and a text with so few ("Sentinel-2") is the common case.
TEXT_FIRST_MAX = 500

_CANDIDATES_SQL = f"""
    SELECT count(*) FROM (
        SELECT 1 FROM public.earthx_listed_entry e
        WHERE e.state = 'published' AND e.footprint && {_AREA} LIMIT %(limit)s) c
"""


def _kept_conditions(kept: Kept) -> tuple[str, str]:
    """The conditions of :class:`Kept` on a listed row (with its entry ``e``) and on a full row ``f``."""
    listed, full = "", ""
    if kept.category is not None:
        listed += " AND e.category = %(category)s"
    if kept.full_ids is not None:
        full += " AND f.dataset_id = ANY(%(full_ids)s)"
    if kept.regions:
        listed += " AND e.regions && %(regions)s::text[]"
        full += (
            " AND EXISTS (SELECT 1 FROM public.earthx_region_part p WHERE p.code = ANY(%(regions)s)"
            " AND ST_Intersects(p.part, f.geometry) AND NOT ST_Touches(p.part, f.geometry))"
        )
    return listed, full


def _sources(start: Start, kept: Kept = ALL_KEPT) -> tuple[tuple[str, str], ...]:
    """What both arms read, as the ``FROM`` and ``WHERE`` of each of the two kinds of row, in the alias ``f``.

    The published listed entries and the full entries are two flat queries, not one query over a union: with a union
    Postgres cannot push the join with the text into its branches. A listed row of an entry the harvest took back, or
    whose link has not passed the check (``link_hidden``, M5-67), is no row of the first source, whatever the start.

    :attr:`Start.AREA`: the entries the area keeps come from the GiST index of ``earthx_listed_entry`` (partial on
    ``published``), and each is looked up here by its id, one lookup per entry. The two ``OFFSET 0`` keep Postgres
    from turning that into a join it orders by its own guess. :attr:`Start.TEXT`: ``NOT ST_Disjoint`` is the same test
    as ``ST_Intersects`` without its use of the index. Without an area, no condition on a geometry is in the statement.

    The filters of ``kept`` stand in both sources, before any rank; ``kept.entry`` leaves the other kind of row out.
    """
    spatial = start is not Start.NO_AREA
    listed_kept, full_kept = _kept_conditions(kept)
    full_area = f" AND {_FULL_AREA}" if spatial else ""
    if start is Start.AREA:
        listed = (
            f"""(SELECT e.dataset_id FROM public.earthx_listed_entry e
                 WHERE e.state = 'published' AND ST_Intersects(e.footprint, {_AREA}){listed_kept} OFFSET 0) a
            CROSS JOIN LATERAL (
                SELECT s.ctid, s.dataset_id, s.title, s.document, s.trigram_text, s.has_time_axis, s.time_start,
                       s.time_end, s.entry
                FROM public.earthx_dataset_search s WHERE s.dataset_id = a.dataset_id AND s.entry = 'listed'
                OFFSET 0) f""",
            _TIME,
        )
    else:
        listed_area = f" AND NOT ST_Disjoint(e.footprint, {_AREA})" if start is Start.TEXT else ""
        listed = (
            "public.earthx_dataset_search f JOIN public.earthx_listed_entry e ON e.dataset_id = f.dataset_id",
            f"f.entry = 'listed' AND e.state = 'published'{listed_area}{listed_kept} AND {_TIME}",
        )
    full = ("public.earthx_dataset_search f", f"f.entry = 'full'{full_area}{full_kept} AND {_TIME}")
    return tuple(source for kind, source in (("listed", listed), ("full", full)) if kept.entry in (None, kind))


_WORDS_OF_DIGITS = "ARRAY(SELECT w FROM unnest(string_to_array(f.trigram_text, ' ')) w WHERE w ~ '^[0-9]+$')"
_RUNS_OF_DIGITS = "ARRAY(SELECT (regexp_matches(f.trigram_text, '[0-9]+', 'g'))[1])"


def _carries(words: str | None = None, runs: str | None = None) -> str:
    """True where id, title or keywords of the row ``f`` have every number of the parameter ``words`` as a word and
    every one of ``runs`` as a run of digits. A parameter that is ``None`` has nothing to carry: its condition is left
    out, because Postgres would evaluate it for every row and find it true."""
    conditions = []
    if words is not None:
        conditions.append(f"%({words})s::text[] <@ {_WORDS_OF_DIGITS}")
    if runs is not None:
        conditions.append(f"%({runs})s::text[] <@ {_RUNS_OF_DIGITS}")
    return " AND ".join(conditions) or "true"


def _name_numbers(words: Sequence[str]) -> list[int]:
    """The positions of the words that can be the number of a name: digits only, no year, no unit after them."""
    return [
        position
        for position, word in enumerate(words)
        if _NUMBER.fullmatch(word)
        and not _YEAR.fullmatch(word)
        and (position + 1 == len(words) or words[position + 1] not in _UNITS)
    ]


def numbers_of(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The numbers of names in ``text`` (normalized), and the runs of digits in its words with letters.

    A number with a unit after it ("10 m", "10m") and a year ("2021") are never part of a name (Otto, 11.11.2026).
    """
    words = normalize(text).split()
    numbers = tuple(words[position] for position in _name_numbers(words))
    codes = tuple(
        run
        for word in words
        if not _NUMBER.fullmatch(word) and not _MEASURE.fullmatch(word)
        for run in _NUMBER.findall(word)
    )
    return numbers, codes


def numbers_after_names(text: str, names: frozenset[str]) -> tuple[str, ...]:
    """The numbers of names in ``text`` right after a word of ``names``: "3" in "Sentinel 3"."""
    words = normalize(text).split()
    return tuple(words[position] for position in _name_numbers(words) if position and words[position - 1] in names)


def names_before_numbers(text: str) -> list[str]:
    """``LIKE`` patterns of the words of ``text`` right before a number of a name: the rows :data:`_NAMES_SQL` reads."""
    words = normalize(text).split()
    escaped = (re.sub(r"([\\%_])", r"\\\1", words[position - 1]) for position in _name_numbers(words) if position)
    return [f"%{word}%" for word in dict.fromkeys(escaped)]


def numbered_names(rows: Sequence[str]) -> frozenset[str]:
    """The words of the ids and titles in ``rows`` that come before a number of a name in the same row.

    Only names that carry a number themselves ("Sentinel-2", "Copernicus DEM GLO-30") hold a number of the query to
    account; "ESA WorldCover 2020" carries a year and none of its words does.
    """
    names: set[str] = set()
    for row in rows:
        words = normalize(row).split()
        numbered = _name_numbers(words)
        if numbered:
            names.update(word for word in words[: numbered[-1]] if _LETTER.search(word))
    return frozenset(names)


#: Only the rows whose id, title or keywords hold a word that comes right before a number of the query, through the
#: trigram index: the rest cannot make that word a name with a number.
_NAMES_SQL = "SELECT dataset_id || ' ' || title FROM public.earthx_dataset_search WHERE trigram_text LIKE ANY(%s)"


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


def _bare_number(unit: Unit) -> bool:
    """A unit of digits only ("9", "2020"); it never carries a dataset on its own."""
    return not unit.from_glossary and all(_NUMBER.fullmatch(word) for word in unit.terms[0].split("-"))


def _unit_rows(units: Sequence[Unit]) -> sql.Composed:
    return sql.SQL(", ").join(
        sql.SQL("({}, {}, {}, {})").format(
            sql.Literal(number), _unit_query(unit, number), _stop_word(unit, number), sql.Literal(_bare_number(unit))
        )
        for number, unit in enumerate(units)
    )


def _text_hits_sql(units: Sequence[Unit]) -> sql.Composed:
    """At most ``limit`` rows (one per unit a row matches) of the full text, to be counted."""
    return sql.SQL(
        """
        WITH all_units(ord, query, stop, bare) AS (VALUES {rows}),
        units AS (SELECT ord, query, bare FROM all_units WHERE NOT stop)
        SELECT count(*) FROM (
            SELECT 1 FROM units u JOIN public.earthx_dataset_search s ON s.document @@ u.query LIMIT %(limit)s) h
        """
    ).format(rows=_unit_rows(units))


def _full_text_sql(
    units: Sequence[Unit], joining: Joining, *, start: Start, named_numbers: bool, kept: Kept = ALL_KEPT
) -> sql.Composed:
    """The hits of the full text by rank, cut by :func:`_cut`.

    A row is ranked for each unit it matches, the ranks added in the order of the units. With one unit, every match is
    a hit and is ranked where it is read. With more, which units a row matches comes from the index alone, without
    reading its ``tsvector``; only the rows the joining keeps are then read again by their row id and ranked (M5-66):
    three broad words matched 9·10⁴ pairs of row and unit at 10⁵ entries, of which 750 rows had all three. Either way
    the grouping carries no ``tsvector``; with one it spilled to disk.
    """
    two_steps = len(units) > 1
    rank = "NULL::real" if two_steps else "ts_rank_cd(f.document, u.query)"
    matches = sql.SQL(" UNION ALL ").join(
        sql.SQL(
            """
            SELECT f.ctid AS row_id, f.dataset_id, f.title, f.has_time_axis, f.entry, u.ord, u.bare, {rank} AS rank
            FROM {source}, units u
            WHERE {condition} AND f.document @@ u.query AND {carries}"""
        ).format(
            rank=sql.SQL(rank),
            source=sql.SQL(source),
            condition=sql.SQL(condition),
            carries=sql.SQL(_carries("named_numbers" if named_numbers else None)),
        )
        for source, condition in _sources(start, kept)
    )
    # With one unit a row matches at most once: nothing to group.
    hits = (
        """SELECT m.row_id, any_value(m.dataset_id) AS dataset_id, any_value(m.title) AS title,
                  any_value(m.has_time_axis) AS has_time_axis, any_value(m.entry) AS entry, array_agg(m.ord) AS ords,
                  count(*) AS matched, count(*) FILTER (WHERE NOT m.bare) AS matched_words,
                  count(*) FILTER (WHERE m.ord IN (SELECT ord FROM known)) AS matched_known
           FROM ({matches}) m GROUP BY m.row_id"""
        if two_steps
        else """SELECT m.dataset_id, m.title, m.has_time_axis, m.entry, m.rank, 1 AS matched,
                  (NOT m.bare)::int AS matched_words, (m.ord IN (SELECT ord FROM known))::int AS matched_known
           FROM ({matches}) m"""
    )
    ranked = (
        """(SELECT sum(ts_rank_cd(s.document, u.query) ORDER BY u.ord)
            FROM public.earthx_dataset_search s, units u WHERE s.ctid = h.row_id AND u.ord = ANY(h.ords))"""
        if two_steps
        else "h.rank"
    )
    return sql.SQL(
        """
        WITH all_units(ord, query, stop, bare) AS (VALUES {rows}),
        units AS (SELECT ord, query, bare FROM all_units WHERE NOT stop),
        known AS (
            SELECT u.ord FROM units u
            WHERE EXISTS (SELECT 1 FROM public.earthx_dataset_search s WHERE s.document @@ u.query)),
        hits AS ({hits})
        {cut}
        """
    ).format(
        rows=_unit_rows(units),
        hits=sql.SQL(hits).format(matches=matches),
        cut=_cut(
            sql.SQL(
                "SELECT h.dataset_id, h.title, h.has_time_axis, h.entry, {ranked} AS score FROM hits h"
                " WHERE h.matched_words > 0 AND {condition}"
            ).format(ranked=sql.SQL(ranked), condition=sql.SQL(_JOIN_CONDITION[joining]))
        ),
    )


def _trigram_sql(*, start: Start, numbers: bool, codes: bool, kept: Kept = ALL_KEPT) -> sql.Composed:
    """The hits of the trigrams by similarity, cut by :func:`_cut`."""
    arms = sql.SQL(" UNION ALL ").join(
        sql.SQL(
            """
            SELECT f.dataset_id, f.title, f.has_time_axis, f.entry, word_similarity(%(normal)s, f.trigram_text) AS score
            FROM {source}
            WHERE {condition} AND %(normal)s <%% f.trigram_text AND {carries}"""
        ).format(
            source=sql.SQL(source),
            condition=sql.SQL(condition),
            carries=sql.SQL(_carries("numbers" if numbers else None, "codes" if codes else None)),
        )
        for source, condition in _sources(start, kept)
    )
    return _cut(arms)


def _cut(hits: sql.Composable) -> sql.Composed:
    """The rows of ``hits`` (``dataset_id``, ``title``, ``has_time_axis``, ``entry``, ``score``) by score, each with
    its place (1, 2, 2, 4) and the number of all hits: those up to the place ``depth``, a tie at it whole, and all of
    them where there are no more than ``count_up_to``, so that the hits beyond the depth can be counted.

    A tie is never cut: in the trigram arm one similarity is shared by thousands of hits of a broad word ("map" in
    13 144 rows at 10⁵ entries), and a cut by title would take an arbitrary part of them into the fusion and leave out
    the hits the full text ranks first (M5-66).
    """
    return sql.SQL(
        """
        SELECT r.dataset_id, r.title, r.has_time_axis, r.entry, r.score, r.place, r.total FROM (
            SELECT t.*, rank() OVER (ORDER BY t.score DESC) AS place, count(*) OVER () AS total FROM ({hits}) t) r
        WHERE r.place <= %(depth)s OR r.total <= %(count_up_to)s
        ORDER BY r.score DESC, r.title, r.dataset_id"""
    ).format(hits=hits)


def _unranked_sql(*, start: Start) -> sql.Composed:
    source, condition = _sources(start)[1]
    return sql.SQL(
        "SELECT f.dataset_id, f.title, f.has_time_axis, f.entry, 0 FROM {source} WHERE {condition}"
        " ORDER BY f.dataset_id"
    ).format(source=sql.SQL(source), condition=sql.SQL(condition))


def ranks(scored: Sequence[tuple[str, float]]) -> dict[str, int]:
    """The rank of each id by its score, highest first; equal scores share the better rank (1, 2, 2, 4).

    A tie must not be broken before the fusion: by title, "ESA WorldCover" would come before "Sentinel-2" in every arm
    where both score the same, and win the fusion for "Sentinel-2".
    """
    first: dict[float, int] = {}
    for position, score in enumerate(sorted((score for _, score in scored), reverse=True), start=1):
        first.setdefault(score, position)
    return {dataset_id: first[score] for dataset_id, score in scored}


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


async def _start(
    conn: Any,
    params: Mapping[str, Any],
    units: Sequence[Unit],
    terms: Mapping[str, str],
    area_first_max: int,
    text_first_max: int,
) -> Start:
    """Where a search with the text ``units`` and the area of ``params`` starts, by counting up to a limit.

    From the area where at most ``area_first_max`` published listed entries have a footprint whose box meets it and the
    text has more than ``text_first_max`` hits; otherwise from the text. Postgres could not decide this: it takes the
    hits of a text for 0.5 % of the rows whatever the words, and the footprints of an area for as many rows as its
    statistics say, which for a few large footprints over a small area is one row instead of thousands.
    """
    if params["area"] is None:
        return Start.NO_AREA
    async with conn.cursor() as cur:
        await cur.execute(_CANDIDATES_SQL, {"area": params["area"], "limit": area_first_max + 1}, prepare=False)
        candidates = (await cur.fetchone())[0]
        if candidates > area_first_max or not units:
            return Start.TEXT
        await cur.execute(_text_hits_sql(units), {**terms, "limit": text_first_max + 1}, prepare=False)
        hits = (await cur.fetchone())[0]
    return Start.TEXT if hits <= text_first_max else Start.AREA


async def search_datasets(
    conn: Any,
    text: str | None,
    *,
    area: Mapping[str, Any] | None = None,
    period: tuple[datetime | None, datetime | None] | None = None,
    joining: Joining = JOINING,
    threshold: float = TRIGRAM_THRESHOLD,
    glossary: Glossary | None = None,
    area_first_max: int = AREA_FIRST_MAX,
    text_first_max: int = TEXT_FIRST_MAX,
    kept: Kept = ALL_KEPT,
    depth: int = DEPTH,
    count_up_to: int = COUNT_UP_TO,
) -> SearchResult:
    """The datasets for ``text`` within ``area`` (a GeoJSON polygon in WGS 84) and ``period`` (either end open), ranked.

    ``conn`` is the caller's async connection; the search runs in a transaction (a savepoint inside the caller's) and
    writes nothing. Inside a transaction of the caller, ``client_min_messages`` stays at ``warning`` until it ends. A ``text`` of only spaces is no text.

    With text, the filters of ``kept`` stand in both arms; each arm hands its first ``depth`` hits to the fusion, so
    ``ids`` holds at most twice as many. ``matched`` is the number of all hits up to ``count_up_to``, ``None`` above it.
    Without text, ``kept`` is not applied and ``matched`` is the number of ``ids``.
    """
    if text is not None and len(text) > MAX_QUERY_CHARS:
        raise QueryTooLong(f"the query is longer than {MAX_QUERY_CHARS} characters")
    params = _filter_params(area, period)
    rows: dict[str, tuple[str, bool, str]] = {}

    async def run(statement: sql.Composable, extra: Mapping[str, object]) -> list[tuple[str, float, int, int]]:
        """The rows of ``statement`` as (id, score, place, number of all hits); without the last two, 0."""
        async with conn.cursor() as cur:
            await cur.execute(statement, {**params, **extra}, prepare=False)
            found = await cur.fetchall()
        for dataset_id, title, timed, entry, *_ in found:
            rows[dataset_id] = (title, timed, entry)
        return [(row[0], float(row[4]), *(row[5:7] if len(row) > 5 else (0, 0))) for row in found]

    # One snapshot for both arms; a stop word makes Postgres say so as a NOTICE, which is no news here.
    async with conn.transaction():
        await conn.execute("SET LOCAL client_min_messages = warning")
        if text is None or not text.strip():
            start = Start.NO_AREA if area is None else Start.TEXT
            ids: tuple[str, ...] = tuple(row[0] for row in await run(_unranked_sql(start=start), {}))
            matched: int | None = len(ids)
        else:
            units = parse_query(text, glossary)
            terms = {f"term_{n}_{i}": term for n, unit in enumerate(units) for i, term in enumerate(unit.terms)}
            start = await _start(conn, params, units, terms, area_first_max, text_first_max)
            extra = {**_kept_params(kept), "depth": depth, "count_up_to": count_up_to}
            normal = normalize(text)
            numbers, codes = numbers_of(text)
            full_text = []
            if units:
                named_numbers: tuple[str, ...] = ()
                if numbers:
                    async with conn.cursor() as cur:
                        await cur.execute(_NAMES_SQL, (names_before_numbers(text),))
                        names = numbered_names([row[0] for row in await cur.fetchall()])
                    named_numbers = numbers_after_names(text, names)
                full_text = await run(
                    _full_text_sql(units, joining, start=start, named_numbers=bool(named_numbers), kept=kept),
                    {**extra, **terms, "share": MIN_SHARE, "named_numbers": list(named_numbers)},
                )
            # A similarity is at most 1: above it, the arm finds nothing and pg_trgm would refuse the threshold.
            trigrams = []
            if normal and threshold <= 1:
                await conn.execute(
                    "SELECT set_config('pg_trgm.word_similarity_threshold', %s, true)", (str(threshold),)
                )
                trigrams = await run(
                    _trigram_sql(start=start, numbers=bool(numbers), codes=bool(codes), kept=kept),
                    {**extra, "normal": normal, "numbers": list(numbers), "codes": list(codes)},
                )
            ids = fuse(
                *(ranks([(row[0], row[1]) for row in arm if row[2] <= depth]) for arm in (full_text, trigrams)),
                titles={i: row[0] for i, row in rows.items()},
            )
            matched = _count(full_text, trigrams, up_to=count_up_to)
    listed = frozenset(i for i in ids if rows[i][2] == "listed")
    if period is None:
        return SearchResult(ids, listed=listed, matched=matched)
    by_collection = {i: (TIME_FILTER,) for i in ids if not rows[i][1]}
    return SearchResult(ids, (TIME_FILTER,) if by_collection else (), by_collection, listed, matched)


def _kept_params(kept: Kept) -> dict[str, object]:
    return {
        "category": kept.category,
        "full_ids": None if kept.full_ids is None else list(kept.full_ids),
        "regions": list(kept.regions),
    }


def _count(*arms: Sequence[tuple[str, float, int, int]], up_to: int) -> int | None:
    """The number of datasets in any of ``arms``, or ``None`` where it is above ``up_to``. An arm with no more than
    ``up_to`` hits holds them all (:func:`_cut`)."""
    if any(arm and arm[0][3] > up_to for arm in arms):
        return None
    found = len({row[0] for arm in arms for row in arm})
    return found if found <= up_to else None
