"""Harvested rows of ``earthx_listed_entry``: writing what a report derived, dedupe and the stack (M5-20 plan §5, §8,
§12; migration ``032``).

``discovery`` derives a row per find and writes it here; nothing here derives anything. A row's own state follows
its verdict (``ok`` → ``in_review``, ``needs_rule``, ``not_geodata``); a published row stays published while only
describing fields change and goes back into review when its licence rule, publisher, account, delivery or the host of
its link change (adr/0033 §11, U1). Dedupe and the stack act on all rows at once, one statement each.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from earthx.catalog.listed import HAND_SOURCE
from earthx.catalog.listed_store import _TOMBSTONE, REGIONS_OF

__all__ = [
    "DedupeRow",
    "HarvestedRow",
    "Stack",
    "apply_duplicates",
    "dedupe_rows",
    "derivations",
    "form_stack",
    "mark_duplicates",
    "mark_listings",
    "settle_missing",
    "withdraw",
    "write_harvested",
]

#: What decides whether a published row may stay published when it changes (adr/0033 §11).
_DECISION = ("license_rule", "publisher", "account", "delivery", "link_host")


@dataclass(frozen=True, slots=True)
class HarvestedRow:
    """One derived row. ``footprint`` is GeoJSON (the source's geometry) or ``None``; ``footprint_codes`` the regions
    whose outlines are the footprint (a place text); ``regions`` ``None`` derives them from the footprint."""

    dataset_id: str
    source_id: str
    source_key: str
    verdict: str
    waiting_reason: str | None
    content: Mapping[str, Any]
    content_sha256: str
    sort_title: str
    footprint: Mapping[str, Any] | None
    footprint_codes: tuple[str, ...] | None
    regions: tuple[str, ...] | None
    time_span: str | None
    keywords: tuple[str, ...]
    data_kind: str
    category: str
    account: str | None
    delivery: str | None
    publisher: str | None
    link_host: str
    license_ref: str | None
    license_rule: str | None
    extent_basis: str
    dedupe_keys: tuple[str, ...]
    derived_sha256: str


_OWN_STATE = "CASE %(verdict)s WHEN 'ok' THEN 'in_review' ELSE %(verdict)s END"
_STAYS = sql.SQL(
    "stored.state = 'published' AND EXCLUDED.verdict = 'ok' AND ({stored}) IS NOT DISTINCT FROM ({excluded})"
    # A changed grade of the licence too: never a licence statement Otto has not seen with the entry (plan A18).
    " AND stored.content -> 'earthx:license_flags' IS NOT DISTINCT FROM EXCLUDED.content -> 'earthx:license_flags'"
).format(
    stored=sql.SQL(", ").join(sql.SQL("stored.{}").format(sql.Identifier(c)) for c in _DECISION),
    excluded=sql.SQL(", ").join(sql.SQL("EXCLUDED.{}").format(sql.Identifier(c)) for c in _DECISION),
)
_UPSERT = sql.SQL(
    """
    INSERT INTO public.earthx_listed_entry AS stored (
        dataset_id, source_id, source_key, state, verdict, waiting_reason, content, content_sha256, sort_title,
        footprint, time_span, regions, keywords, data_kind, category, account, delivery, publisher, link_host,
        license_ref, license_rule, extent_basis, dedupe_keys, derived_sha256, harvested_at
    )
    SELECT %(id)s, %(source)s, %(key)s, {own}, %(verdict)s, %(waiting)s, %(content)s, %(content_sha256)s,
           %(sort_title)s, f.geom, %(time_span)s::tstzrange,
           CASE WHEN %(regions)s::text[] IS NULL THEN {regions_of} ELSE %(regions)s::text[] END,
           %(keywords)s, %(data_kind)s, %(category)s, %(account)s, %(delivery)s, %(publisher)s, %(host)s,
           %(license_ref)s, %(license_rule)s, %(basis)s, %(dedupe_keys)s, %(derived)s, now()
    FROM (SELECT COALESCE(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)),
                          (SELECT ST_Union(p.outline) FROM (
                               SELECT r.outline FROM public.earthx_region r WHERE r.code = ANY(%(footprint_codes)s::text[])
                               UNION ALL
                               SELECT m.outline FROM public.earthx_municipality m
                               WHERE m.code = ANY(%(footprint_codes)s::text[])) p)) AS geom) f
    ON CONFLICT (dataset_id) DO UPDATE SET
        state = CASE WHEN {stays} THEN 'published' ELSE EXCLUDED.state END,
        content = CASE WHEN {stays}
                       THEN jsonb_set(EXCLUDED.content, '{{earthx:listing,approved_on}}', to_jsonb(stored.approved_on::text))
                       ELSE EXCLUDED.content END,
        approval_file = CASE WHEN {stays} THEN stored.approval_file END,
        approval_sha256 = CASE WHEN {stays} THEN stored.approval_sha256 END,
        approved_on = CASE WHEN {stays} THEN stored.approved_on END,
        published_at = CASE WHEN {stays} THEN stored.published_at END,
        verdict = EXCLUDED.verdict, waiting_reason = EXCLUDED.waiting_reason,
        content_sha256 = EXCLUDED.content_sha256, sort_title = EXCLUDED.sort_title, footprint = EXCLUDED.footprint,
        time_span = EXCLUDED.time_span, regions = EXCLUDED.regions, keywords = EXCLUDED.keywords,
        data_kind = EXCLUDED.data_kind, category = EXCLUDED.category, account = EXCLUDED.account,
        delivery = EXCLUDED.delivery, publisher = EXCLUDED.publisher, link_host = EXCLUDED.link_host,
        license_ref = EXCLUDED.license_ref, license_rule = EXCLUDED.license_rule,
        extent_basis = EXCLUDED.extent_basis, dedupe_keys = EXCLUDED.dedupe_keys,
        derived_sha256 = EXCLUDED.derived_sha256, harvested_at = EXCLUDED.harvested_at,
        duplicate_of = NULL, missing_since = NULL, removed_reason = NULL, removed_on = NULL
    WHERE stored.source_id = EXCLUDED.source_id AND stored.state <> 'superseded'
    """
).format(
    own=sql.SQL(_OWN_STATE),
    regions_of=sql.SQL(REGIONS_OF.format(footprint="f.geom")),
    stays=_STAYS,
)


def derivations(conn: psycopg.Connection, source_id: str) -> dict[str, str | None]:
    """Source key → the hash a row of the source was derived from (``None`` for a tombstone, which is rewritten)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_key, CASE WHEN state = 'tombstone' THEN NULL ELSE derived_sha256 END"
            " FROM public.earthx_listed_entry WHERE source_id = %s",
            (source_id,),
        )
        return dict(cur.fetchall())


def write_harvested(cur: psycopg.Cursor, rows: Iterable[HarvestedRow]) -> tuple[int, list[str]]:
    """Write the derived rows; returns how many and the keys of those Postgres refused (a geometry PostGIS cannot read).
    A row of another source under the same id, or one a full entry took over, is left alone. Each row in a savepoint
    of its own: one foreign value must not stop the rest."""
    count = 0
    refused: list[str] = []
    for row in rows:
        try:
            with cur.connection.transaction():
                count += _write(cur, row)
        except (psycopg.errors.DataException, psycopg.errors.InternalError_):
            refused.append(row.source_key)
    return count, refused


def _write(cur: psycopg.Cursor, row: HarvestedRow) -> int:
    cur.execute(
            _UPSERT,
            {
                "id": row.dataset_id,
                "source": row.source_id,
                "key": row.source_key,
                "verdict": row.verdict,
                "waiting": row.waiting_reason,
                "content": Jsonb(row.content),
                "content_sha256": row.content_sha256,
                "sort_title": row.sort_title,
                "geojson": None if row.footprint is None else json.dumps(row.footprint),
                "footprint_codes": None if row.footprint_codes is None else list(row.footprint_codes),
                "regions": None if row.regions is None else list(row.regions),
                "time_span": row.time_span,
                "keywords": list(row.keywords),
                "data_kind": row.data_kind,
                "category": row.category,
                "account": row.account,
                "delivery": row.delivery,
                "publisher": row.publisher,
                "host": row.link_host,
                "license_ref": row.license_ref,
                "license_rule": row.license_rule,
                "basis": row.extent_basis,
                "dedupe_keys": list(row.dedupe_keys),
                "derived": row.derived_sha256,
            },
        )
    return cur.rowcount


@dataclass(frozen=True, slots=True)
class Missing:
    deleted: int
    marked: int
    tombstones: int


def settle_missing(conn: psycopg.Connection, source_id: str, blocked_keys: Sequence[str] = ()) -> Missing:
    """Rows of finds that are gone, invalid or blocked (plan A4).

    A row never published goes; a published one whose find is gone is marked the first time and becomes a tombstone
    ``source_removed`` once a later full pass of the source ends without it (adr/0033 §9). A published row whose find
    became invalid stays as it is. ``blocked_keys`` are finds the blocklist names: their unpublished rows go too
    (published ones become tombstones through ``apply_blocklist``).
    """
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM public.earthx_listed_entry e WHERE e.source_id = %(source)s"
            " AND e.state NOT IN ('published', 'tombstone', 'superseded')"
            " AND (e.source_key = ANY(%(blocked)s) OR NOT EXISTS (SELECT 1 FROM public.earthx_record_state s"
            "      WHERE s.source_id = e.source_id AND s.source_key = e.source_key AND s.state = 'extracted'))",
            {"source": source_id, "blocked": list(blocked_keys)},
        )
        deleted = cur.rowcount
        cur.execute(
            "UPDATE public.earthx_listed_entry e SET missing_since = NULL WHERE e.source_id = %s"
            " AND e.missing_since IS NOT NULL AND EXISTS (SELECT 1 FROM public.earthx_record_state s"
            " WHERE s.source_id = e.source_id AND s.source_key = e.source_key AND s.state = 'extracted')",
            (source_id,),
        )
        cur.execute(
            "UPDATE public.earthx_listed_entry e SET missing_since = now() WHERE e.source_id = %s"
            " AND e.state = 'published' AND e.missing_since IS NULL AND EXISTS (SELECT 1"
            " FROM public.earthx_record_state s WHERE s.source_id = e.source_id AND s.source_key = e.source_key"
            " AND s.state = 'gone')",
            (source_id,),
        )
        marked = cur.rowcount
        cur.execute(
            sql.SQL(
                """
            UPDATE public.earthx_listed_entry e SET {tombstone}, removed_reason = 'source_removed',
                removed_on = current_date
            WHERE e.source_id = %(source)s AND e.state = 'published' AND e.missing_since IS NOT NULL
              AND EXISTS (SELECT 1 FROM public.earthx_record_state s WHERE s.source_id = e.source_id
                          AND s.source_key = e.source_key AND s.state = 'gone')
              AND EXISTS (SELECT 1 FROM public.earthx_harvest_run r WHERE r.source_id = e.source_id
                          AND r.kind = 'full' AND r.status = 'done' AND r.started_at > e.missing_since)
            """
            ).format(tombstone=sql.SQL(_TOMBSTONE)),
            {"source": source_id},
        )
        return Missing(deleted, marked, cur.rowcount)


def withdraw(conn: psycopg.Connection, granted: Callable[[str, str | None, tuple[str, ...]], bool]) -> int:
    """Hide at once every harvested row whose licence rule Otto took back (adr/0033 §9): ``granted`` says whether the
    licences of a publisher of a source still are; returns how many rows went back to the waiting list. The next
    report derives them anew."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT source_id, publisher, license_ref FROM public.earthx_listed_entry"
            " WHERE source_id <> %s AND state IN ('published', 'in_review') AND license_ref IS NOT NULL",
            (HAND_SOURCE,),
        )
        gone = [row for row in cur.fetchall() if not granted(row[0], row[1], tuple(row[2].split("+")))]
        count = 0
        for source_id, publisher, refs in gone:
            cur.execute(
                "UPDATE public.earthx_listed_entry SET state = 'needs_rule', verdict = 'needs_rule',"
                " waiting_reason = 'not_granted', approval_file = NULL, approval_sha256 = NULL, approved_on = NULL,"
                " published_at = NULL, derived_sha256 = NULL WHERE source_id = %s AND publisher IS NOT DISTINCT FROM %s"
                " AND license_ref = %s AND state IN ('published', 'in_review')",
                (source_id, publisher, refs),
            )
            count += cur.rowcount
        return count


@dataclass(frozen=True, slots=True)
class DedupeRow:
    dataset_id: str
    source_id: str
    keys: tuple[str, ...]
    source_rank: int
    footprint: bool


def dedupe_rows(conn: psycopg.Connection) -> list[DedupeRow]:
    """Every row with keys that can be the main entry of a group: harvested and not hidden as no geodata, plus the
    hand entries by their DOI."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT dataset_id, source_id,
                   CASE WHEN source_id = %(hand)s THEN ARRAY['doi:' || lower(content->>'sci:doi')] ELSE dedupe_keys END,
                   coalesce((content->'earthx:listing'->>'source_rank')::int, 0), footprint IS NOT NULL
            FROM public.earthx_listed_entry
            WHERE state NOT IN ('tombstone', 'superseded', 'not_geodata')
              AND ((source_id <> %(hand)s AND cardinality(dedupe_keys) > 0)
                   OR (source_id = %(hand)s AND content->>'sci:doi' IS NOT NULL))
            """,
            {"hand": HAND_SOURCE},
        )
        return [DedupeRow(row[0], row[1], tuple(row[2]), row[3], row[4]) for row in cur.fetchall()]


_MARK_DUPLICATES = (
    "UPDATE public.earthx_listed_entry e SET state = 'duplicate', duplicate_of = d.main"
    " FROM unnest(%s::text[], %s::text[]) AS d(id, main)"
    " WHERE e.dataset_id = d.id AND e.source_id <> %s AND e.state NOT IN ('tombstone', 'superseded')"
    " AND (e.state, e.duplicate_of) IS DISTINCT FROM ('duplicate', d.main)"
)


def mark_duplicates(conn: psycopg.Connection, duplicates: Mapping[str, str]) -> int:
    """Mark the harvested rows of ``duplicates`` (id → main id); returns how many rows changed."""
    with conn.cursor() as cur:
        cur.execute(_MARK_DUPLICATES, (list(duplicates), [duplicates[i] for i in duplicates], HAND_SOURCE))
        return cur.rowcount


def mark_listings(conn: psycopg.Connection, listings: Mapping[str, str]) -> tuple[str, ...]:
    """Mark the rows that are the listing of a full entry (``also_listed_as``, ``<source id>:<identifier>`` → dataset id)
    as its duplicates, by the ``id:`` key they hold; returns their ids. Only marks: the report restores a row whose
    listing is no longer named."""
    if not listings:
        return ()
    sources, identifiers, mains = [], [], []
    for key, main in sorted(listings.items()):
        source_id, identifier = key.split(":", 1)
        sources.append(source_id)
        identifiers.append(identifier)
        mains.append(main)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE public.earthx_listed_entry e SET state = 'duplicate', duplicate_of = d.main"
            " FROM unnest(%s::text[], %s::text[], %s::text[]) AS d(source_id, identifier, main)"
            " WHERE e.source_id = d.source_id AND 'id:' || d.identifier = ANY(e.dedupe_keys)"
            " AND e.source_id <> %s AND e.state NOT IN ('tombstone', 'superseded')"
            " AND (e.state, e.duplicate_of) IS DISTINCT FROM ('duplicate', d.main) RETURNING e.dataset_id",
            (sources, identifiers, mains, HAND_SOURCE),
        )
        return tuple(sorted(row[0] for row in cur.fetchall()))


def apply_duplicates(conn: psycopg.Connection, duplicates: Mapping[str, str]) -> tuple[int, int]:
    """Mark the harvested rows of ``duplicates`` (id → main id) and restore the ones that are no longer one; returns
    (marked, restored). A restored row goes back to its own state; one that was published goes back into review."""
    marked = mark_duplicates(conn, duplicates)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE public.earthx_listed_entry SET duplicate_of = NULL, approval_file = NULL, approval_sha256 = NULL,"
            " approved_on = NULL, published_at = NULL,"
            " state = CASE verdict WHEN 'ok' THEN 'in_review' ELSE verdict END"
            " WHERE state = 'duplicate' AND NOT (dataset_id = ANY(%s))",
            (list(duplicates),),
        )
        return marked, cur.rowcount


@dataclass(frozen=True, slots=True)
class Stack:
    """The stack of one report: ``created`` is false where the open stack already held exactly these entries."""

    batch_id: int
    fingerprint: str
    entries: tuple[tuple[str, str, str], ...]
    created: bool


def fingerprint_of(entries: Sequence[tuple[str, str, str]]) -> str:
    """The SHA-256 of the manifest: one line ``id content_sha256 license_rule`` per entry, sorted (adr/0033 §8.1)."""
    return hashlib.sha256("".join(f"{a} {b} {c}\n" for a, b, c in sorted(entries)).encode("utf-8")).hexdigest()


def form_stack(conn: psycopg.Connection, source_id: str) -> Stack | None:
    """The stack of the rows of ``source_id`` in review; ``None`` where there are none. A later stack takes over an
    open one, which expires (adr/0033 §8.3); the same entries again keep the open stack."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT dataset_id, content_sha256, license_rule FROM public.earthx_listed_entry"
            " WHERE source_id = %s AND state = 'in_review' ORDER BY dataset_id",
            (source_id,),
        )
        entries = tuple((row[0], row[1], row[2]) for row in cur.fetchall())
        cur.execute(
            "SELECT batch_id, fingerprint FROM public.earthx_listing_batch WHERE source_id = %s AND state = 'open'",
            (source_id,),
        )
        open_stack = cur.fetchone()
        fingerprint = fingerprint_of(entries) if entries else None
        if open_stack is not None and open_stack[1] == fingerprint:
            return Stack(open_stack[0], fingerprint, entries, created=False)
        if open_stack is not None:
            cur.execute("UPDATE public.earthx_listing_batch SET state = 'expired' WHERE batch_id = %s", (open_stack[0],))
        if not entries:
            return None
        cur.execute(
            "INSERT INTO public.earthx_listing_batch (source_id, fingerprint, entries, state)"
            " VALUES (%s, %s, %s, 'open') RETURNING batch_id",
            (source_id, fingerprint, len(entries)),
        )
        batch_id = cur.fetchone()[0]
        cur.executemany(
            "INSERT INTO public.earthx_listing_batch_entry (batch_id, dataset_id, content_sha256, license_rule)"
            " VALUES (%s, %s, %s, %s)",
            [(batch_id, *entry) for entry in entries],
        )
        assert fingerprint is not None
        return Stack(batch_id, fingerprint, entries, created=True)
