"""Writing listed entries, regions and the blocklist into Postgres, for ``catalog-load`` (M5-40 plan §5.3).

Everything runs in the caller's transaction and is idempotent: a second run with the same files writes no row. Work
on many rows is one statement each (the blocklist, the tombstones, a change of regions), never row by row in Python,
so that a run stays short at 10⁶ entries.

* :func:`write_regions` keeps ``earthx_region`` equal to ``regions.json`` and, where an outline changed, derives the
  regions of every entry anew.
* :func:`write_hand_entries` writes the hand entries of ``listed/`` (adr/0033 F11). A blocked one is not written; one
  whose file left ``listed/`` becomes a tombstone with ``source_removed`` (plan A5).
* :func:`supersede` marks the row of a listed entry whose id a full entry took over (adr/0033 §11).
* :func:`apply_blocklist` turns every entry a line of ``blocked.yaml`` names into a tombstone (adr/0033 §9).
"""

from __future__ import annotations

import json
from collections.abc import Collection, Sequence

import psycopg
from psycopg import sql

from earthx.catalog.listed import (
    HAND_SOURCE,
    BlockRule,
    BlockScope,
    ListedEntry,
    Region,
    content_sha256,
    link_host,
    listed_keywords,
    sort_title,
    to_listed_collection,
)
from earthx.catalog.registry import ConfigError

__all__ = ["apply_blocklist", "is_blocked", "supersede", "write_hand_entries", "write_regions"]

#: The regions of a footprint: every outline it overlaps in more than a shared border. Asked of the small pieces of the
#: outlines; a footprint that only touches the cut between two pieces of one outline overlaps one of them inside.
REGIONS_OF = """
    COALESCE((SELECT array_agg(DISTINCT p.code ORDER BY p.code) FROM public.earthx_region_part p
              WHERE ST_Intersects(p.part, {footprint}) AND NOT ST_Touches(p.part, {footprint})), '{{}}')
"""
#: Points per piece of an outline (``ST_Subdivide``).
PART_POINTS = 128

#: Everything a tombstone drops (adr/0033 §9); the table's checks hold it to exactly this.
_TOMBSTONE = """
    state = 'tombstone', content = NULL, content_sha256 = NULL, sort_title = NULL, footprint = NULL,
    time_span = NULL, regions = NULL, keywords = NULL, data_kind = NULL, category = NULL, account = NULL, delivery = NULL, publisher = NULL,
    link_host = NULL, license_ref = NULL
"""


def write_regions(conn: psycopg.Connection, regions: Sequence[Region]) -> int:
    """Bring ``earthx_region`` in line with ``regions``; returns how many rows changed, gone ones included.

    Where any changed, the outlines are cut into pieces anew and the regions of every entry that keeps a footprint are
    derived anew, in one statement each.
    """
    changed = 0
    with conn.cursor() as cur:
        for region in regions:
            cur.execute(
                """
                INSERT INTO public.earthx_region AS stored (code, level, name, outline)
                VALUES (%s, %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
                ON CONFLICT (code) DO UPDATE SET level = EXCLUDED.level, name = EXCLUDED.name, outline = EXCLUDED.outline
                WHERE (stored.level, stored.name, ST_AsBinary(stored.outline))
                      IS DISTINCT FROM (EXCLUDED.level, EXCLUDED.name, ST_AsBinary(EXCLUDED.outline))
                """,
                (region.code, region.level, region.name, json.dumps(region.outline)),
            )
            changed += cur.rowcount
        cur.execute(
            "DELETE FROM public.earthx_region WHERE NOT (code = ANY(%s))", ([region.code for region in regions],)
        )
        changed += cur.rowcount
        cur.execute("SELECT NOT EXISTS (SELECT 1 FROM public.earthx_region_part)")
        if changed or (regions and cur.fetchone()[0]):
            cur.execute("DELETE FROM public.earthx_region_part")
            cur.execute(
                "INSERT INTO public.earthx_region_part (code, part) "
                "SELECT code, ST_Subdivide(outline, %s) FROM public.earthx_region",
                (PART_POINTS,),
            )
            # Only the rows whose regions differ are written.
            cur.execute(
                sql.SQL(
                    "UPDATE public.earthx_listed_entry e SET regions = d.regions FROM (SELECT dataset_id, {} AS regions "
                    "FROM public.earthx_listed_entry WHERE footprint IS NOT NULL) d "
                    "WHERE e.dataset_id = d.dataset_id AND e.regions IS DISTINCT FROM d.regions"
                ).format(sql.SQL(REGIONS_OF.format(footprint="footprint")))
            )
    return changed


def is_blocked(rule: BlockRule, *, source_id: str, source_key: str, publisher: str, host: str) -> bool:
    """Whether ``rule`` names an entry with these values (the same test :func:`apply_blocklist` makes in SQL)."""
    if rule.scope is BlockScope.ENTRY:
        return (rule.source_id, rule.source_key) == (source_id, source_key)
    if rule.scope is BlockScope.PUBLISHER:
        return (rule.source_id, rule.publisher) == (source_id, publisher)
    if rule.scope is BlockScope.HOST:
        return rule.host == host
    return rule.source_id == source_id


_UPSERT = sql.SQL(
    """
    INSERT INTO public.earthx_listed_entry AS stored (
        dataset_id, source_id, source_key, state, content, content_sha256, sort_title, footprint, time_span, regions,
        keywords,
        data_kind, category, account, delivery, publisher, link_host, approval_file, approval_sha256, approved_on,
        published_at,
        removed_reason, removed_on
    )
    SELECT %(id)s, %(source)s, %(id)s, 'published', %(content)s::jsonb, %(content_sha256)s, %(sort_title)s, f.geom,
           %(time_span)s::tstzrange, {regions}, %(keywords)s, %(data_kind)s, %(category)s, %(account)s, %(delivery)s, %(publisher)s,
           %(host)s, %(approval_file)s, %(approval_sha256)s, %(approved_on)s, now(), NULL, NULL
    FROM (SELECT ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326) AS geom) f
    ON CONFLICT (dataset_id) DO UPDATE SET
        state = EXCLUDED.state, content = EXCLUDED.content, content_sha256 = EXCLUDED.content_sha256,
        sort_title = EXCLUDED.sort_title, footprint = EXCLUDED.footprint, time_span = EXCLUDED.time_span,
        regions = EXCLUDED.regions, keywords = EXCLUDED.keywords, data_kind = EXCLUDED.data_kind, category = EXCLUDED.category,
        account = EXCLUDED.account,
        delivery = EXCLUDED.delivery, publisher = EXCLUDED.publisher, link_host = EXCLUDED.link_host,
        approval_file = EXCLUDED.approval_file, approval_sha256 = EXCLUDED.approval_sha256,
        approved_on = EXCLUDED.approved_on, published_at = EXCLUDED.published_at,
        removed_reason = NULL, removed_on = NULL
    WHERE stored.state IS DISTINCT FROM 'published'
       OR (stored.content_sha256, stored.approval_sha256, stored.sort_title)
          IS DISTINCT FROM (EXCLUDED.content_sha256, EXCLUDED.approval_sha256, EXCLUDED.sort_title)
    RETURNING dataset_id
    """
).format(regions=sql.SQL(REGIONS_OF.format(footprint="f.geom")))


def _time_span(entry: ListedEntry) -> str | None:
    """The period as a ``tstzrange`` literal, both ends included and open where the extent is; none without one."""
    start, end = entry.temporal_extent.start, entry.temporal_extent.end
    if start is None and end is None:
        return None
    return f"[{'' if start is None else start.isoformat()},{'' if end is None else end.isoformat()}]"


def write_hand_entries(
    conn: psycopg.Connection,
    entries: Sequence[tuple[ListedEntry, str]],
    blocklist: Sequence[BlockRule],
    *,
    full_ids: Collection[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Write the hand entries, each with the SHA-256 of its file; returns the ids written and the ids left out as blocked.

    An id that is a full entry or a retired one (``full_ids``), or that a harvested row already holds, is an error: two
    files in Git cannot both own it, and a hand entry never takes a harvested row over.
    """
    ids = [entry.dataset_id for entry, _ in entries]
    if clash := sorted(set(ids) & set(full_ids)):
        raise ConfigError(f"listed/: a full or retired entry has the same id: {', '.join(clash)}")
    written: list[str] = []
    blocked: list[str] = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT dataset_id FROM public.earthx_listed_entry WHERE dataset_id = ANY(%s) AND source_id <> %s "
            "ORDER BY dataset_id",
            (ids, HAND_SOURCE),
        )
        if taken := [row[0] for row in cur.fetchall()]:
            raise ConfigError(f"listed/: a harvested entry holds the same id: {', '.join(taken)}")
        for entry, file_hash in entries:
            host = link_host(entry.source_url)
            values = {"source_id": HAND_SOURCE, "source_key": entry.dataset_id, "publisher": entry.publisher}
            if any(is_blocked(rule, host=host, **values) for rule in blocklist):
                blocked.append(entry.dataset_id)
                continue
            collection = to_listed_collection(entry)
            west, south, east, north = entry.spatial_extent.bbox
            cur.execute(
                _UPSERT,
                {
                    "id": entry.dataset_id,
                    "source": HAND_SOURCE,
                    "content": json.dumps(collection),
                    "content_sha256": content_sha256(collection),
                    "sort_title": sort_title(entry.title),
                    "west": west,
                    "south": south,
                    "east": east,
                    "north": north,
                    "time_span": _time_span(entry),
                    "data_kind": entry.data_kind.value,
                    "category": entry.category,
                    "keywords": list(listed_keywords(entry.keywords, entry.category)),
                    "account": entry.access.account.value,
                    "delivery": entry.access.delivery.value,
                    "publisher": entry.publisher,
                    "host": host,
                    "approval_file": f"listed/{entry.dataset_id}.yaml",
                    "approval_sha256": file_hash,
                    "approved_on": entry.approved_on,
                },
            )
            if cur.fetchone() is not None:
                written.append(entry.dataset_id)
        # A hand entry whose file is gone: a tombstone, so a link to it ends in 410 (plan A5). A superseded row stays.
        cur.execute(
            sql.SQL(
                "UPDATE public.earthx_listed_entry SET {tombstone}, removed_reason = 'source_removed', "
                "removed_on = current_date WHERE source_id = %s AND state NOT IN ('tombstone', 'superseded') "
                "AND NOT (dataset_id = ANY(%s))"
            ).format(tombstone=sql.SQL(_TOMBSTONE)),
            (HAND_SOURCE, ids),
        )
    return tuple(written), tuple(blocked)


def supersede(conn: psycopg.Connection, full_ids: Collection[str]) -> tuple[str, ...]:
    """Mark the listed rows whose id a full entry now has (adr/0033 §11); returns their ids."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE public.earthx_listed_entry SET state = 'superseded' "
            "WHERE dataset_id = ANY(%s) AND state NOT IN ('tombstone', 'superseded') RETURNING dataset_id",
            (list(full_ids),),
        )
        return tuple(sorted(row[0] for row in cur.fetchall()))


_CONDITION = {
    BlockScope.ENTRY: ("source_id = %s AND source_key = %s", ("source_id", "source_key")),
    BlockScope.PUBLISHER: ("source_id = %s AND publisher = %s", ("source_id", "publisher")),
    BlockScope.HOST: ("link_host = %s", ("host",)),
    BlockScope.SOURCE: ("source_id = %s", ("source_id",)),
}


def apply_blocklist(conn: psycopg.Connection, blocklist: Sequence[BlockRule]) -> int:
    """Turn every entry a line names into a tombstone with the line's reason and day; returns how many.

    A superseded row is left alone: its id belongs to a full entry, which leaves by ``retired.yaml`` (adr/0017).
    """
    count = 0
    with conn.cursor() as cur:
        for rule in blocklist:
            condition, fields = _CONDITION[rule.scope]
            cur.execute(
                sql.SQL(
                    "UPDATE public.earthx_listed_entry SET {tombstone}, removed_reason = %s, removed_on = %s "
                    "WHERE state NOT IN ('tombstone', 'superseded') AND {condition}"
                ).format(tombstone=sql.SQL(_TOMBSTONE), condition=sql.SQL(condition)),
                (rule.reason.value, rule.blocked_on, *(getattr(rule, name) for name in fields)),
            )
            count += cur.rowcount
    return count
