"""The index of the dataset search: written by ``catalog-load``, checked when `api` starts (M5-22 plan §3.4).

One row of ``public.earthx_dataset_search`` per registry entry (migration ``016``) and per published listed entry
(migration ``035``). :func:`write_search_index` writes a row only where the search text, the extent or the way the
items are held changed, and removes the rows of datasets the registry no longer has; prototype entries are only where
the registry of the instance holds them (adr/0024 R5). :func:`write_listed_search_index` does the same for the
listed entries: Postgres compares a hash of what each text is built from, so only the entries that changed are read
into Python, built and written.
:func:`check_search_index` stops a start where the index is not the one this code would write (plan A3): a new
search text cannot quietly run on an old index.

The vector arm (M5-23): a row written with a new text loses its vector; :func:`write_embeddings` gives every row without
one a vector after the main transaction of `catalog-load`, a batch per transaction, and :func:`check_embeddings` stops
a start of `api` where a full entry has none.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql

from earthx.catalog.embedding import Embedder, embedding_text, vector_literal
from earthx.catalog.registry import DatasetConfig, DatasetRegistry
from earthx.catalog.search_text import (
    ListedFields,
    SearchText,
    listed_search_text,
    listed_text_salt,
    region_names,
    search_text,
)

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
        west, south, east, north, time_start, time_end, has_time_axis, item_holding, entry
    ) VALUES (
        %(dataset_id)s, %(title)s, %(a)s, %(b)s, %(c)s, %(d)s, %(text_hash)s, {document}, %(trigram_text)s,
        %(west)s, %(south)s, %(east)s, %(north)s, %(time_start)s, %(time_end)s,
        %(has_time_axis)s, %(item_holding)s, %(entry)s
    )
    ON CONFLICT (dataset_id) DO UPDATE SET
        title = EXCLUDED.title, text_a = EXCLUDED.text_a, text_b = EXCLUDED.text_b, text_c = EXCLUDED.text_c,
        text_d = EXCLUDED.text_d, text_hash = EXCLUDED.text_hash, document = EXCLUDED.document,
        trigram_text = EXCLUDED.trigram_text, west = EXCLUDED.west, south = EXCLUDED.south, east = EXCLUDED.east,
        north = EXCLUDED.north, time_start = EXCLUDED.time_start,
        time_end = EXCLUDED.time_end, has_time_axis = EXCLUDED.has_time_axis, item_holding = EXCLUDED.item_holding,
        entry = EXCLUDED.entry,
        embedding = CASE WHEN stored.text_hash = EXCLUDED.text_hash THEN stored.embedding END,
        embedding_model = CASE WHEN stored.text_hash = EXCLUDED.text_hash THEN stored.embedding_model END
    WHERE stored.entry <> EXCLUDED.entry OR (stored.title, stored.text_hash, stored.trigram_text, stored.west, stored.south, stored.east, stored.north,
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
        "entry": "full",
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
            "DELETE FROM public.earthx_dataset_search WHERE entry = 'full' AND NOT (dataset_id = ANY(%s))"
            " RETURNING dataset_id",
            ([config.dataset_id for config in registry],),
        )
        removed = sorted(row[0] for row in cur.fetchall())
    return IndexOutcome(tuple(written), tuple(removed))


#: The published listed entries that no full entry took over and whose row is missing or was built from other inputs,
#: by id and hash of the inputs. The hash is computed here, in Postgres, so that an entry that did not change costs no
#: Python: the salt (text version, place names, category words), the document by its hash, the fields of the row the
#: text and the filters read, and the documents of the duplicates by their hashes. A listed row keeps it as its
#: ``text_hash``. One plain statement, no cursor and no subquery per entry, so that Postgres can run it in parallel
#: workers: 0.8 s on one core at 10⁵ entries, 0.2 s in parallel (M5-66).
_CHANGED_LISTED = """
    WITH duplicates AS (
        SELECT d.duplicate_of, string_agg(d.content_sha256, ',' ORDER BY d.dataset_id) AS hashes
        FROM public.earthx_listed_entry d WHERE d.state = 'duplicate' GROUP BY d.duplicate_of),
    entries AS (
        SELECT e.dataset_id, encode(sha256(convert_to(concat_ws('|', %(salt)s::text, e.content_sha256, e.regions::text,
                   e.keywords::text, e.category, coalesce(e.publisher, ''), e.account,
                   ST_XMin(e.footprint)::text, ST_YMin(e.footprint)::text, ST_XMax(e.footprint)::text,
                   ST_YMax(e.footprint)::text, coalesce(e.time_span::text, ''), coalesce(dup.hashes, '')), 'UTF8')),
                   'hex') AS input_hash
        FROM public.earthx_listed_entry e LEFT JOIN duplicates dup ON dup.duplicate_of = e.dataset_id
        WHERE e.state = 'published' AND NOT (e.dataset_id = ANY(%(full)s)))
    SELECT e.dataset_id, e.input_hash
    FROM entries e
    LEFT JOIN public.earthx_dataset_search s ON s.dataset_id = e.dataset_id AND s.entry = 'listed'
    WHERE s.text_hash IS DISTINCT FROM e.input_hash
"""
#: What the text of each of these entries is built from, read only for the entries that changed.
_LISTED_FIELDS = """
    SELECT e.dataset_id, coalesce(e.content ->> 'title', e.dataset_id), coalesce(e.content ->> 'description', ''),
           e.keywords, e.category, coalesce(e.publisher, ''), e.account, e.regions,
           ARRAY(SELECT d.content ->> 'title' FROM public.earthx_listed_entry d
                 WHERE d.duplicate_of = e.dataset_id AND d.state = 'duplicate' AND d.content ? 'title'
                 ORDER BY d.dataset_id),
           ST_XMin(e.footprint), ST_YMin(e.footprint), ST_XMax(e.footprint), ST_YMax(e.footprint),
           lower(e.time_span), upper(e.time_span), e.time_span IS NOT NULL
    FROM public.earthx_listed_entry e WHERE e.dataset_id = ANY(%s)
"""
_LISTED_GONE = """
    DELETE FROM public.earthx_dataset_search s WHERE s.entry = 'listed' AND (s.dataset_id = ANY(%(full)s) OR NOT EXISTS (
        SELECT 1 FROM public.earthx_listed_entry e WHERE e.dataset_id = s.dataset_id AND e.state = 'published'))
"""
#: Rows written per round trip.
_BATCH = 2_000


@dataclass(frozen=True, slots=True)
class ListedIndexOutcome:
    """How many rows of listed entries one run of :func:`write_listed_search_index` wrote and removed."""

    written: int
    removed: int


def write_listed_search_index(conn: psycopg.Connection, full_ids: Iterable[str]) -> ListedIndexOutcome:
    """Bring the rows of the listed entries in line with the published ones that no id of ``full_ids`` took over.

    Idempotent; the caller owns the transaction. Postgres picks the entries whose inputs changed (``_CHANGED_LISTED``,
    ids and hashes only); only their fields are read, their texts built and their ``tsvector`` computed, a batch at a
    time.
    """
    full = list(full_ids)
    upsert = _UPSERT.format(document=document_sql())
    names = region_names()
    written = 0
    with conn.cursor() as cur:
        cur.execute(_CHANGED_LISTED, {"full": full, "salt": listed_text_salt()})
        changed = dict(cur.fetchall())
        ids = sorted(changed)
        for start in range(0, len(ids), _BATCH):
            cur.execute(_LISTED_FIELDS, (ids[start : start + _BATCH],))
            batch = [(*row, changed[row[0]]) for row in cur.fetchall()]
            cur.executemany(upsert, [_listed_row(row, names) for row in batch])
            written += len(batch)
        cur.execute(_LISTED_GONE, {"full": full})
        removed = cur.rowcount
    return ListedIndexOutcome(written, removed)


def _listed_row(row: Sequence[Any], names: Mapping[str, tuple[str, ...]]) -> dict[str, object]:
    dataset_id, title, description, keywords, category, publisher, account, regions, duplicates = row[:9]
    west, south, east, north, start, end, timed, input_hash = row[9:]
    fields = ListedFields(
        dataset_id=dataset_id,
        title=title,
        description=description,
        keywords=tuple(keywords),
        category=category,
        publisher=publisher,
        account=account,
        region_names=tuple(name for code in regions for name in names.get(code, ())),
        duplicate_titles=tuple(duplicates),
    )
    text = listed_search_text(fields)
    return {
        "dataset_id": dataset_id,
        "title": title,
        "a": text.a,
        "b": text.b,
        "c": text.c,
        "d": text.d,
        "text_hash": input_hash,
        "trigram_text": text.trigram_text,
        "west": west,
        "south": south,
        "east": east,
        "north": north,
        "time_start": start,
        "time_end": end,
        "has_time_axis": timed,
        "item_holding": None,
        "entry": "listed",
    }


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
            sql.SQL("SELECT dataset_id, {} FROM public.earthx_dataset_search WHERE entry = 'full'").format(
                sql.SQL(", ").join(map(sql.Identifier, _CHECKED))
            )
        )
        stored = {found[0]: tuple(found[1:]) for found in await cur.fetchall()}
    problems = compare_index(expected_rows(registry), stored)
    if problems:
        raise SearchIndexMismatch(
            f"the search index does not match the registry ({'; '.join(problems)}); run `python -m earthx.catalog.load`"
        )


#: The rows without a vector of the model, after the last id of the previous batch (M5-23 plan §4.3).
_UNEMBEDDED = """
    SELECT dataset_id, text_hash, text_a, text_b FROM public.earthx_dataset_search
    WHERE embedding_model IS DISTINCT FROM %(model)s AND dataset_id > %(after)s ORDER BY dataset_id LIMIT %(batch)s
"""
_COUNT_UNEMBEDDED = "SELECT count(*) FROM public.earthx_dataset_search WHERE embedding_model IS DISTINCT FROM %s"
#: Only a row whose text is still the one embedded: a load that rewrote it since leaves it to the next run.
_SET_EMBEDDING = """
    UPDATE public.earthx_dataset_search SET embedding = %s::halfvec, embedding_model = %s
    WHERE dataset_id = %s AND text_hash = %s
"""
#: Rows per transaction (M5-42 F6 = 1): an interrupted run keeps every batch before.
EMBEDDING_BATCH = 256
#: How often the run says how far it is.
_PROGRESS_EVERY = 10_000


@dataclass(frozen=True, slots=True)
class EmbeddingOutcome:
    """How many rows one run of :func:`write_embeddings` gave a vector, of how many that lacked one."""

    written: int
    missing: int


def write_embeddings(
    conn: psycopg.Connection,
    embedder: Embedder,
    *,
    batch: int = EMBEDDING_BATCH,
    report: Callable[[str], None] = print,
) -> EmbeddingOutcome:
    """Give every row without a vector of ``embedder`` one, a batch per transaction (M5-42 §4, F6 = 1).

    Runs after the main transaction of `catalog-load`, on a connection that is not in autocommit; each batch commits.
    A row whose text changed between reading and writing is left to the next run. Says every
    :data:`_PROGRESS_EVERY` rows how far it is, nothing of the entries.
    """
    with conn.cursor() as cur:
        cur.execute(_COUNT_UNEMBEDDED, (embedder.name,))
        missing = cur.fetchone()[0]
        conn.commit()
        written, after, said = 0, "", 0
        while True:
            cur.execute(_UNEMBEDDED, {"model": embedder.name, "after": after, "batch": batch})
            rows = cur.fetchall()
            if not rows:
                conn.commit()
                break
            vectors = embedder.embed([embedding_text(a, b) for _, _, a, b in rows])
            cur.executemany(
                _SET_EMBEDDING,
                [
                    (vector_literal(vector), embedder.name, dataset_id, text_hash)
                    for (dataset_id, text_hash, _, _), vector in zip(rows, vectors, strict=True)
                ],
            )
            conn.commit()
            written += len(rows)
            after = rows[-1][0]
            if written // _PROGRESS_EVERY > said:
                said = written // _PROGRESS_EVERY
                report(f"embeddings written: {written} of {missing}")
    return EmbeddingOutcome(written, missing)


async def check_embeddings(conn: Any, model: str) -> None:
    """Refuse to start where a full entry has no vector of ``model`` (plan §4.4, A4); listed rows may still lack one
    (M5-42 F6): the next `catalog-load` gives it, the vector arm skips them until then."""
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT dataset_id FROM public.earthx_dataset_search"
            " WHERE entry = 'full' AND embedding_model IS DISTINCT FROM %s ORDER BY dataset_id",
            (model,),
        )
        lacking = [row[0] for row in await cur.fetchall()]
    if lacking:
        raise SearchIndexMismatch(
            f"no vector of the model {model} for {', '.join(lacking)}; run `python -m earthx.catalog.load`"
        )
