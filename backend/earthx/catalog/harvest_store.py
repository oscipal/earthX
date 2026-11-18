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
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

__all__ = [
    "LEASE_S",
    "MAX_RAW_BYTES",
    "HarvestBusy",
    "Pass",
    "ListValidators",
    "Previous",
    "RunCounts",
    "SourceState",
    "SourceSummary",
    "canonical",
    "finish_run",
    "begin_pass",
    "end_pass",
    "harvest_state",
    "rest",
    "save_pass",
    "list_validators",
    "mark_gone",
    "previous",
    "raw_records",
    "renew_run",
    "save_list_validators",
    "seen",
    "source_summary",
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
    """The numbers of a run's row. ``found_*`` and ``gone`` say what this run did; ``invalid`` and ``extent_unknown`` are
    the state of the source's finds after the run, whether this run evaluated them or found them unchanged."""

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
class Pass:
    """Where an open full pass of a CKAN source stands: the run that began it, when, the offset and first key of the
    next page, and what the check that the listing held still has gathered so far (migration 027)."""

    run_id: int
    started_at: datetime
    start: int
    last_key: str | None
    total: int | None
    read: int
    moved: bool
    #: The lower bound of ``metadata_modified`` of an incremental pass; ``None`` for a full pass.
    since: datetime | None = None

    @property
    def full(self) -> bool:
        return self.since is None


@dataclass(frozen=True, slots=True)
class SourceState:
    """What the next run of a source builds on, with the clock of the database now."""

    full_started_at: datetime | None
    changes_since: datetime | None
    open_pass: Pass | None
    #: No run of the source starts before this (it refused the harvest with 429; migration 028).
    rest_until: datetime | None
    now: datetime

    @property
    def resting(self) -> bool:
        return self.rest_until is not None and self.now < self.rest_until


@dataclass(frozen=True, slots=True)
class Previous:
    """What the last run kept of one find."""

    raw_sha256: str
    state: str
    reason: str | None
    extracted_sha256: str | None
    extractor_version: str | None


@dataclass(frozen=True, slots=True)
class SourceSummary:
    """The state of a source's finds: valid (``extracted``), invalid by reason, gone, and extracted without extent."""

    extracted: int
    invalid: Mapping[str, int]
    gone: int
    extent_unknown: int


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


def harvest_state(conn: psycopg.Connection, source_id: str) -> SourceState:
    row = conn.execute(
        "SELECT full_started_at, changes_since, pass_run_id, pass_started_at, pass_start, pass_last_key, pass_total,"
        " pass_read, pass_moved, pass_since, rest_until, clock_timestamp()"
        " FROM public.earthx_harvest_source WHERE source_id = %s",
        (source_id,),
    ).fetchone()
    if row is None:
        return SourceState(None, None, None, None, conn.execute("SELECT clock_timestamp()").fetchone()[0])
    full, since, run_id, *fields, rest_until, now = row
    return SourceState(full, since, None if run_id is None else Pass(run_id, *fields), rest_until, now)


_UPSERT = (
    "INSERT INTO public.earthx_harvest_source AS h (source_id) VALUES (%(source_id)s)"
    " ON CONFLICT (source_id) DO UPDATE SET updated_at = clock_timestamp()"
)


def begin_pass(conn: psycopg.Connection, source_id: str, run_id: int, since: datetime | None = None) -> Pass:
    """A new pass, begun by ``run_id`` at its start: a full one, or an incremental one from ``since``."""
    with conn.transaction():
        conn.execute(_UPSERT, {"source_id": source_id})
        row = conn.execute(
            "UPDATE public.earthx_harvest_source h SET pass_run_id = r.run_id, pass_started_at = r.started_at,"
            " pass_start = 0, pass_last_key = NULL, pass_total = NULL, pass_read = 0, pass_moved = false,"
            " pass_since = %s, updated_at = clock_timestamp() FROM public.earthx_harvest_run r"
            " WHERE h.source_id = %s AND r.run_id = %s RETURNING r.started_at",
            (since, source_id, run_id),
        ).fetchone()
    return Pass(run_id, row[0], 0, None, None, 0, False, since)


def save_pass(
    conn: psycopg.Connection, source_id: str, *, start: int, last_key: str | None, total: int | None, read: int, moved: bool
) -> None:
    """Where the open pass stands after a page whose finds are written."""
    conn.execute(
        "UPDATE public.earthx_harvest_source SET pass_start = %s, pass_last_key = %s, pass_total = %s, pass_read = %s,"
        " pass_moved = %s, updated_at = clock_timestamp() WHERE source_id = %s AND pass_run_id IS NOT NULL",
        (start, last_key, total, read, moved, source_id),
    )


def end_pass(conn: psycopg.Connection, source_id: str) -> None:
    """The open pass went through: every change up to its start is in, and a full one is the last full pass."""
    conn.execute(
        "UPDATE public.earthx_harvest_source SET changes_since = pass_started_at,"
        " full_started_at = CASE WHEN pass_since IS NULL THEN pass_started_at ELSE full_started_at END,"
        " pass_run_id = NULL, pass_started_at = NULL, pass_start = NULL, pass_last_key = NULL, pass_total = NULL,"
        " pass_read = NULL, pass_moved = NULL, pass_since = NULL, updated_at = clock_timestamp()"
        " WHERE source_id = %s AND pass_run_id IS NOT NULL",
        (source_id,),
    )


def rest(conn: psycopg.Connection, source_id: str, seconds: float | None) -> datetime:
    """Hold the source for ``seconds`` (its Retry-After), or without one until the next day begins (UTC): a source
    that refuses for hours keeps a quota, not a pace (Otto, 18.11.2026). Returns the end of the rest."""
    with conn.transaction():
        conn.execute(_UPSERT, {"source_id": source_id})
        return conn.execute(
            "UPDATE public.earthx_harvest_source SET rest_until = CASE WHEN %(seconds)s::float8 IS NULL"
            " THEN date_trunc('day', clock_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' + interval '1 day'"
            " ELSE clock_timestamp() + make_interval(secs => %(seconds)s::float8) END, updated_at = clock_timestamp()"
            " WHERE source_id = %(source_id)s RETURNING rest_until",
            {"seconds": seconds, "source_id": source_id},
        ).fetchone()[0]


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
        "SELECT r.source_key, r.raw_sha256, s.state, s.reason, s.extracted_sha256, s.extractor_version"
        " FROM public.earthx_raw_record r JOIN public.earthx_record_state s USING (source_id, source_key)"
        " WHERE r.source_id = %s AND r.source_key = ANY(%s)",
        (source_id, keys),
    ).fetchall()
    return {row[0]: Previous(*row[1:]) for row in rows}


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
    extractor_version: str,
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
        " (source_id, source_key, state, reason, extracted, extracted_sha256, extent_known, extractor_version,"
        " last_seen_run) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
        " ON CONFLICT (source_id, source_key) DO UPDATE SET state = EXCLUDED.state, reason = EXCLUDED.reason,"
        " extracted = EXCLUDED.extracted, extracted_sha256 = EXCLUDED.extracted_sha256,"
        " extent_known = EXCLUDED.extent_known, extractor_version = EXCLUDED.extractor_version,"
        " last_seen_run = EXCLUDED.last_seen_run, updated_at = clock_timestamp()",
        (
            source_id,
            key,
            state,
            reason,
            None if extracted is None else Jsonb(extracted),
            extracted_sha256,
            extent_known,
            extractor_version,
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


def mark_gone(conn: psycopg.Connection, *, run_id: int, source_id: str, seen_since_run: int | None = None) -> int:
    """Every find of the source that a complete listing did not name is ``gone`` (plan A3): no run from
    ``seen_since_run`` on (the run that began a full pass over several runs; this run where it is ``None``) saw it."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "UPDATE public.earthx_record_state s SET state = 'gone', reason = NULL, extracted = NULL,"
            " extracted_sha256 = NULL, extent_known = NULL, last_seen_run = %s, updated_at = clock_timestamp()"
            " FROM public.earthx_record_state old"
            " WHERE s.source_id = %s AND s.state <> 'gone' AND s.last_seen_run < %s"
            " AND old.source_id = s.source_id AND old.source_key = s.source_key"
            " RETURNING s.source_key, old.state",
            (run_id, source_id, run_id if seen_since_run is None else seen_since_run),
        )
        gone = cur.fetchall()
        for key, before in gone:
            _transition(cur, source_id, key, before, "gone", None, run_id)
    return len(gone)


def source_summary(conn: psycopg.Connection, source_id: str) -> SourceSummary:
    rows = conn.execute(
        "SELECT state, reason, count(*), count(*) FILTER (WHERE state = 'extracted' AND NOT extent_known)"
        " FROM public.earthx_record_state WHERE source_id = %s GROUP BY state, reason",
        (source_id,),
    ).fetchall()
    by_state = {state: 0 for state in ("extracted", "gone")}
    invalid: dict[str, int] = {}
    unknown = 0
    for state, reason, count, without_extent in rows:
        if state == "invalid":
            invalid[reason] = count
        else:
            by_state[state] += count
        unknown += without_extent
    return SourceSummary(by_state["extracted"], dict(sorted(invalid.items())), by_state["gone"], unknown)


def raw_records(
    conn: psycopg.Connection, source_id: str, *, outdated_for: str | None = None
) -> Iterator[tuple[str, bytes, str]]:
    """``(key, raw, state)`` of every kept raw answer of the source, for a re-extract without fetching (A4); with
    ``outdated_for`` only those whose state another extractor version derived."""
    # Held over the writes of the re-extract, which commit page by page on the same connection.
    with conn.cursor(name="earthx_raw_records", withhold=True) as cur:
        cur.execute(
            "SELECT r.source_key, r.raw_gzip, s.state FROM public.earthx_raw_record r"
            " JOIN public.earthx_record_state s USING (source_id, source_key)"
            " WHERE r.source_id = %s AND r.raw_gzip IS NOT NULL AND s.state <> 'gone'"
            " AND (%s::text IS NULL OR s.extractor_version IS DISTINCT FROM %s::text) ORDER BY r.source_key",
            (source_id, outdated_for, outdated_for),
        )
        for key, packed, state in cur:
            yield key, gzip.decompress(packed), state


def canonical(document: Any) -> bytes:
    """The bytes a hash is taken over: JSON with sorted keys, no spaces; ASCII, so a lone surrogate escape of a foreign
    answer is kept as written instead of failing the encoding."""
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("ascii")
