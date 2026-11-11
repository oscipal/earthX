"""The state of the overview pyramids, as SQL on `earthx_overview` (M5-30b part 8b, adr/0032 §5.2, §8.2).

The build of a pyramid is a job of its own kind: no recipe, no user, not in the job list, not a row of `earthx_run`.
Its queue is two tables (migration 018): ``earthx_overview_request`` says "this dataset has this source version now"
(`materialize` writes it through `catalog`; :func:`request_missing` writes it for a version nobody asked for), and
``earthx_overview`` holds one row per dataset and version with the state of the build. `jobs` imports no `catalog`, so
both are touched with SQL here, like the queue's tables in `queue.py`. Every function takes a connection and does one
thing in one transaction.

**The rules these statements keep:**

* A build belongs to one attempt. Every change after :func:`claim` names the attempt it was claimed with and touches no
  row if another attempt owns it by now, like a run (a worker that woke up late cannot overwrite a newer one).
* Only the latest request of a dataset is built; an older version is never built any more.
* At most one build per host at a time (adr/0032 §8.2), counted from the rows under a lock taken in a statement of its
  own, like the cap of the queue (`queue.claim`). A build whose lease ran out is over: its row becomes ``failed`` with
  ``lease_lost`` before anything is picked.
* A failed build is tried again by the next claim only for a reason a second attempt can help (`queue.RETRYABLE`), at
  most :data:`MAX_ATTEMPTS` times in all, and not before :data:`RETRY_AFTER` has passed, except after a lost lease. Any
  other failure stays ``failed`` until a new source version is requested.
* A failure is a short name (:func:`finish_failed` refuses anything else): never an address, a path or a tile.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import psycopg
from psycopg.types.json import Jsonb

from earthx.jobs.queue import RETRYABLE

__all__ = [
    "MAX_ATTEMPTS",
    "OVERVIEW_LOCK_KEY",
    "RETRY_AFTER",
    "Build",
    "claim",
    "finish_failed",
    "finish_ready",
    "heartbeat",
    "request_missing",
    "write_progress",
]

# A third fixed key for `pg_advisory_xact_lock`, next to those of `queue.py`: 'jobs' in ASCII, plus 3.
OVERVIEW_LOCK_KEY = 0x6A6F6273_00000003

#: A build is tried this many times in all (the first included).
MAX_ATTEMPTS = 3
#: A failed build waits this long for its next attempt; a lost lease does not wait.
RETRY_AFTER = timedelta(hours=1)

_KIND = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_LEASE_LOST = "lease_lost"

# One statement for the builds whose worker is gone; they are over, and a later statement sees them as failed.
_EXPIRE_SQL = """
UPDATE public.earthx_overview
SET status = 'failed', failure_kind = %(kind)s, worker = NULL, lease_until = NULL, updated_at = clock_timestamp()
WHERE status = 'building' AND lease_until < clock_timestamp()
"""

# The latest request of each dataset that this worker can build, with what is known of its pyramid: nothing, or a failure
# that a second attempt can help.
_CANDIDATES_SQL = """
SELECT r.dataset_id, r.version, r.source_version
FROM (
    SELECT DISTINCT ON (dataset_id) dataset_id, version, source_version, requested_at
    FROM public.earthx_overview_request
    WHERE dataset_id = ANY(%(datasets)s)
    ORDER BY dataset_id, requested_at DESC
) r
LEFT JOIN public.earthx_overview o ON o.dataset_id = r.dataset_id AND o.version = r.version
WHERE o.version IS NULL
   OR (o.status = 'failed'
       AND o.failure_kind = ANY(%(retryable)s)
       AND o.attempts < %(max_attempts)s
       AND (o.failure_kind = %(lease_lost)s OR o.updated_at < clock_timestamp() - %(retry_after)s))
ORDER BY r.requested_at
"""

_START_SQL = """
INSERT INTO public.earthx_overview (dataset_id, version, status, hosts, worker, lease_until)
VALUES (%(dataset)s, %(version)s, 'building', %(hosts)s, %(worker)s, clock_timestamp() + make_interval(secs => %(lease)s))
ON CONFLICT (dataset_id, version) DO UPDATE
SET status = 'building', failure_kind = NULL, attempts = earthx_overview.attempts + 1, hosts = EXCLUDED.hosts,
    worker = EXCLUDED.worker, lease_until = EXCLUDED.lease_until, progress = 0, base_hashes = '{}',
    updated_at = clock_timestamp()
RETURNING attempts
"""

# What the latest materialize run of a dataset loaded or confirmed, where no pyramid of that version has a row.
_MISSING_SQL = """
INSERT INTO public.earthx_overview_request (dataset_id, source_version)
SELECT m.dataset_id, m.source_version
FROM (
    SELECT DISTINCT ON (dataset_id) dataset_id, source_version
    FROM public.earthx_materialize_runs
    WHERE dataset_id = ANY(%s)
    ORDER BY dataset_id, started_at DESC, id DESC
) m
WHERE NOT EXISTS (
    SELECT 1 FROM public.earthx_overview o
    WHERE o.dataset_id = m.dataset_id AND o.version = public.earthx_overview_version(m.source_version)
)
ON CONFLICT (dataset_id, source_version) DO UPDATE SET requested_at = now()
"""


@dataclass(frozen=True, slots=True)
class Build:
    """One pyramid to build, claimed by one attempt."""

    dataset_id: str
    #: The name of the source version in the object key (``earthx_overview_version``).
    version: str
    #: The source version as `materialize` recorded it; the child needs only what is in the registry and pgstac.
    source_version: str
    attempt: int
    hosts: tuple[str, ...]


def claim(
    conn: psycopg.Connection, *, worker: str, lease_seconds: float, hosts: Mapping[str, Sequence[str]]
) -> Build | None:
    """The next pyramid to build, now owned by ``worker``; ``None`` when nothing waits or its host is busy.

    ``hosts`` names the datasets this worker can build and the hosts each one reads from: a request for another dataset
    is left to a worker that knows it. The transaction runs in READ COMMITTED and takes its lock in a statement of its
    own (the same two steps as `queue.claim`: a count in the statement that waits for the lock would be a count from
    before the wait). The connection is in autocommit mode, so this transaction is the outermost one.
    """
    with conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (OVERVIEW_LOCK_KEY,))
        conn.execute(_EXPIRE_SQL, {"kind": _LEASE_LOST})
        candidates = conn.execute(
            _CANDIDATES_SQL,
            {
                "datasets": sorted(hosts),
                "retryable": sorted(RETRYABLE),
                "max_attempts": MAX_ATTEMPTS,
                "lease_lost": _LEASE_LOST,
                "retry_after": RETRY_AFTER,
            },
        ).fetchall()
        busy = {
            host
            for (building,) in conn.execute("SELECT hosts FROM public.earthx_overview WHERE status = 'building'")
            for host in building
        }
        for dataset_id, version, source_version in candidates:
            wanted = tuple(hosts[dataset_id])
            if busy.intersection(wanted):
                continue
            row = conn.execute(
                _START_SQL,
                {
                    "dataset": dataset_id,
                    "version": version,
                    "hosts": list(wanted),
                    "worker": worker,
                    "lease": lease_seconds,
                },
            ).fetchone()
            assert row is not None
            return Build(dataset_id, version, source_version, row[0], wanted)
        return None


def _own(conn: psycopg.Connection, build: Build, assignments: str, parameters: Mapping[str, object]) -> bool:
    """``UPDATE ... SET assignments`` of the row, only while ``build``'s attempt owns it."""
    row = conn.execute(
        f"""
        UPDATE public.earthx_overview SET {assignments}, updated_at = clock_timestamp()
        WHERE dataset_id = %(dataset)s AND version = %(version)s AND attempts = %(attempt)s AND status = 'building'
        RETURNING 1
        """,
        {"dataset": build.dataset_id, "version": build.version, "attempt": build.attempt, **parameters},
    ).fetchone()
    return row is not None


def heartbeat(conn: psycopg.Connection, build: Build, lease_seconds: float) -> bool:
    """Renew the lease; ``False`` if this attempt no longer owns the build."""
    return _own(
        conn, build, "lease_until = clock_timestamp() + make_interval(secs => %(lease)s)", {"lease": lease_seconds}
    )


def write_progress(conn: psycopg.Connection, build: Build, percent: int) -> bool:
    """Store the progress (0 to 99 while building); ``False`` if this attempt no longer owns the build."""
    return _own(conn, build, "progress = %(percent)s", {"percent": max(0, min(99, percent))})


def finish_ready(
    conn: psycopg.Connection, build: Build, *, checked_at: datetime, base_hashes: Mapping[str, str]
) -> bool:
    """Close the build as ready, only for the attempt that owns it; ``False`` if it no longer does.

    ``checked_at`` is the oldest time any object of the pyramid was read at the source (the term counts from it);
    ``base_hashes`` maps ``x/y`` of a base tile to the hash of the items it read, empty where the items allow none.
    """
    if checked_at.tzinfo is None:
        raise ValueError("checked_at must be timezone-aware")
    return _own(
        conn,
        build,
        "status = 'ready', failure_kind = NULL, worker = NULL, lease_until = NULL, progress = 100, "
        "checked_at = %(checked_at)s, base_hashes = %(hashes)s",
        {"checked_at": checked_at, "hashes": Jsonb(dict(base_hashes))},
    )


def finish_failed(conn: psycopg.Connection, build: Build, kind: str) -> bool:
    """Close the build as failed with a short name, only for the attempt that owns it; ``False`` if it no longer does."""
    if not _KIND.match(kind):
        raise ValueError("a failure kind is a short name of lowercase letters, digits and underscores")
    return _own(
        conn,
        build,
        "status = 'failed', failure_kind = %(kind)s, worker = NULL, lease_until = NULL",
        {"kind": kind},
    )


def request_missing(conn: psycopg.Connection, datasets: Collection[str]) -> int:
    """Ask for the pyramid of the latest materialized version of each dataset that has none; the number of rows written.

    The hourly round of the worker calls it for the datasets with ``viewer.overview: pyramid``: it catches a version
    `materialize` loaded before the request existed and a pyramid that was deleted. A pyramid in any state, a failed one
    included, is no gap here: a failure is retried by :func:`claim`, never by a second request.
    """
    if not datasets:
        return 0
    return conn.execute(_MISSING_SQL, (sorted(datasets),)).rowcount
