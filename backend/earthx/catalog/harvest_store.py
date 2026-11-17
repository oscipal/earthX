"""The tables of the harvest (migration 024; M5-19 plan §3, adr/0025 §5.3).

``discovery`` runs the harvest and hands the rows here; the SQL lives with the migrations it belongs to. The connection
is in autocommit: the row of a run must be seen by every other run at once (its lease, A1), and the finds of a page are
written in one transaction of their own, so a run that stops halfway keeps what it has done.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, fields
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

__all__ = [
    "LEASE_S",
    "MAX_RAW_BYTES",
    "HarvestBusy",
    "ListValidators",
    "Previous",
    "RunCounts",
    "canonical",
    "count_finds",
    "finish_run",
    "list_validators",
    "mark_gone",
    "previous",
    "raw_records",
    "renew_run",
    "save_list_validators",
    "seen",
    "start_run",
    "write_find",
]

#: The term of a run's hold on its source; renewed after every page.
LEASE_S = 300.0
#: The largest raw answer kept per find (adr/0025 §5.3).
MAX_RAW_BYTES = 1024 * 1024


class HarvestBusy(RuntimeError):
    """Another run of the same source holds it."""


@dataclass(slots=True)
class RunCounts:
    requests: int = 0
    not_modified: int = 0
    bytes: int = 0
    found_new: int = 0
    found_changed: int = 0
    found_unchanged: int = 0
    invalid: int = 0
    gone: int = 0
    extent_unknown: int = 0


@dataclass(frozen=True, slots=True)
class ListValidators:
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True, slots=True)
class Previous:
    """What the last run kept of one find."""

    raw_sha256: str
    state: str
    reason: str | None
    extracted_sha256: str | None


def start_run(conn: psycopg.Connection, source_id: str, kind: str) -> int:
    """A new run of ``source_id``; a run whose term ran out is closed first. :class:`HarvestBusy` while one lives."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "UPDATE public.earthx_harvest_run SET status = 'interrupted', stop_reason = 'lease_expired',"
            " finished_at = clock_timestamp()"
            " WHERE source_id = %s AND status = 'running' AND lease_until <= clock_timestamp()",
            (source_id,),
        )
    try:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.earthx_harvest_run (source_id, kind, status, lease_until)"
                " VALUES (%s, %s, 'running', clock_timestamp() + make_interval(secs => %s)) RETURNING run_id",
                (source_id, kind, LEASE_S),
            )
            return cur.fetchone()[0]
    except psycopg.errors.UniqueViolation:
        raise HarvestBusy(f"another run of {source_id} is running") from None


def renew_run(conn: psycopg.Connection, run_id: int) -> bool:
    """The heartbeat of a run; ``False`` once its hold is gone (another run closed it after its term ran out)."""
    cur = conn.execute(
        "UPDATE public.earthx_harvest_run SET lease_until = clock_timestamp() + make_interval(secs => %s)"
        " WHERE run_id = %s AND status = 'running' AND lease_until > clock_timestamp()",
        (LEASE_S, run_id),
    )
    return cur.rowcount == 1


def finish_run(
    conn: psycopg.Connection, run_id: int, *, status: str, stop_reason: str | None, counts: RunCounts
) -> None:
    names = [field.name for field in fields(RunCounts)]
    assignments = ", ".join(f"{name} = %({name})s" for name in names)
    conn.execute(
        f"UPDATE public.earthx_harvest_run SET status = %(status)s, stop_reason = %(stop_reason)s,"
        f" finished_at = clock_timestamp(), {assignments} WHERE run_id = %(run_id)s AND status = 'running'",
        {"status": status, "stop_reason": stop_reason, "run_id": run_id, **{n: getattr(counts, n) for n in names}},
    )


def list_validators(conn: psycopg.Connection, source_id: str) -> ListValidators | None:
    row = conn.execute(
        "SELECT list_etag, list_last_modified FROM public.earthx_harvest_source WHERE source_id = %s", (source_id,)
    ).fetchone()
    return None if row is None else ListValidators(row[0], row[1])


def save_list_validators(conn: psycopg.Connection, source_id: str, validators: ListValidators) -> None:
    """The validators of a one-page listing; both ``None`` forgets them (the listing grew past one page)."""
    conn.execute(
        "INSERT INTO public.earthx_harvest_source (source_id, list_etag, list_last_modified) VALUES (%s, %s, %s)"
        " ON CONFLICT (source_id) DO UPDATE SET list_etag = EXCLUDED.list_etag,"
        " list_last_modified = EXCLUDED.list_last_modified, updated_at = clock_timestamp()",
        (source_id, validators.etag, validators.last_modified),
    )


def previous(conn: psycopg.Connection, source_id: str, keys: list[str]) -> dict[str, Previous]:
    """What the last runs kept of ``keys``, by key; a key never seen is missing."""
    rows = conn.execute(
        "SELECT r.source_key, r.raw_sha256, s.state, s.reason, s.extracted_sha256"
        " FROM public.earthx_raw_record r JOIN public.earthx_record_state s USING (source_id, source_key)"
        " WHERE r.source_id = %s AND r.source_key = ANY(%s)",
        (source_id, keys),
    ).fetchall()
    return {key: Previous(raw, state, reason, extracted) for key, raw, state, reason, extracted in rows}


def _transition(
    cur: psycopg.Cursor, source_id: str, key: str, before: str | None, after: str, reason: str | None, run_id: int
) -> None:
    cur.execute(
        "INSERT INTO public.earthx_state_transition (source_id, source_key, from_state, to_state, reason, run_id)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        (source_id, key, before, after, reason, run_id),
    )


def write_find(
    cur: psycopg.Cursor,
    *,
    run_id: int,
    source_id: str,
    key: str,
    raw: bytes | None,
    raw_sha256: str,
    state: str,
    reason: str | None,
    extracted: Mapping[str, Any] | None,
    extracted_sha256: str | None,
    extent_known: bool | None,
    before: tuple[str, str | None] | None,
) -> None:
    """The raw answer and the state of one find; a change of state or reason goes into the transitions.

    ``raw`` ``None`` keeps the stored raw answer (a re-extract). A raw answer over :data:`MAX_RAW_BYTES` is not kept,
    only its hash (plan §3).
    """
    packed = None if raw is None or len(raw) > MAX_RAW_BYTES else gzip.compress(raw, mtime=0)
    cur.execute(
        "INSERT INTO public.earthx_raw_record (source_id, source_key, raw_gzip, raw_sha256, run_id)"
        " VALUES (%s, %s, %s, %s, %s)"
        " ON CONFLICT (source_id, source_key) DO UPDATE SET"
        " raw_gzip = coalesce(EXCLUDED.raw_gzip, CASE WHEN EXCLUDED.raw_sha256 = earthx_raw_record.raw_sha256"
        " THEN earthx_raw_record.raw_gzip END),"
        " raw_sha256 = EXCLUDED.raw_sha256, fetched_at = clock_timestamp(), run_id = EXCLUDED.run_id",
        (source_id, key, packed, raw_sha256, run_id),
    )
    cur.execute(
        "INSERT INTO public.earthx_record_state"
        " (source_id, source_key, state, reason, extracted, extracted_sha256, extent_known, last_seen_run)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        " ON CONFLICT (source_id, source_key) DO UPDATE SET state = EXCLUDED.state, reason = EXCLUDED.reason,"
        " extracted = EXCLUDED.extracted, extracted_sha256 = EXCLUDED.extracted_sha256,"
        " extent_known = EXCLUDED.extent_known, last_seen_run = EXCLUDED.last_seen_run, updated_at = clock_timestamp()",
        (
            source_id,
            key,
            state,
            reason,
            None if extracted is None else Jsonb(extracted),
            extracted_sha256,
            extent_known,
            run_id,
        ),
    )
    if before != (state, reason):
        _transition(cur, source_id, key, None if before is None else before[0], state, reason, run_id)


def seen(cur: psycopg.Cursor, *, run_id: int, source_id: str, key: str) -> None:
    """An unchanged find: only the run that last saw it moves on."""
    cur.execute(
        "UPDATE public.earthx_record_state SET last_seen_run = %s WHERE source_id = %s AND source_key = %s",
        (run_id, source_id, key),
    )


def mark_gone(conn: psycopg.Connection, *, run_id: int, source_id: str) -> int:
    """Every find of the source that a complete listing of this run did not name is ``gone`` (plan A3)."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "UPDATE public.earthx_record_state s SET state = 'gone', reason = NULL, extracted = NULL,"
            " extracted_sha256 = NULL, extent_known = NULL, last_seen_run = %s, updated_at = clock_timestamp()"
            " FROM public.earthx_record_state old"
            " WHERE s.source_id = %s AND s.state <> 'gone' AND s.last_seen_run <> %s"
            " AND old.source_id = s.source_id AND old.source_key = s.source_key"
            " RETURNING s.source_key, old.state",
            (run_id, source_id, run_id),
        )
        gone = cur.fetchall()
        for key, before in gone:
            _transition(cur, source_id, key, before, "gone", None, run_id)
    return len(gone)


def count_finds(conn: psycopg.Connection, source_id: str) -> tuple[int, int]:
    """``(live, extent_unknown)``: finds of the source that are not ``gone``, and the extracted ones without extent."""
    row = conn.execute(
        "SELECT count(*) FILTER (WHERE state <> 'gone'),"
        " count(*) FILTER (WHERE state = 'extracted' AND NOT extent_known)"
        " FROM public.earthx_record_state WHERE source_id = %s",
        (source_id,),
    ).fetchone()
    return row[0], row[1]


def raw_records(conn: psycopg.Connection, source_id: str) -> Iterator[tuple[str, bytes, str]]:
    """``(key, raw, state)`` of every kept raw answer of the source, for a re-extract without fetching (A4)."""
    # Held over the writes of the re-extract, which commit page by page on the same connection.
    with conn.cursor(name="earthx_raw_records", withhold=True) as cur:
        cur.execute(
            "SELECT r.source_key, r.raw_gzip, s.state FROM public.earthx_raw_record r"
            " JOIN public.earthx_record_state s USING (source_id, source_key)"
            " WHERE r.source_id = %s AND r.raw_gzip IS NOT NULL AND s.state <> 'gone' ORDER BY r.source_key",
            (source_id,),
        )
        for key, packed, state in cur:
            yield key, gzip.decompress(packed), state


def canonical(document: Any) -> bytes:
    """The bytes a hash is taken over: JSON with sorted keys, no spaces; ASCII, so a lone surrogate escape of a foreign
    answer is kept as written instead of failing the encoding."""
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii")
