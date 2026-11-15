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
* The upkeep of the pyramids (extend, sweep) runs on one worker at a time: a worker takes a turn of the task
  (:func:`take_turn`, migration 019) or skips the round. A turn is a lease like a build's, renewed while the work goes on
  and taken over when it ran out; like a build, every change after it names the turn and touches nothing if a newer one
  exists.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import psycopg
from psycopg.types.json import Jsonb

from earthx.jobs.queue import RETRYABLE
from earthx.objectstore.overviews import (
    EXTEND_WINDOW,
    OVERVIEW_TTL,
    PROTOTYPE_PREFIX,
    PROTOTYPE_TTL,
    term_of,
)

__all__ = [
    "EXPIRED",
    "EXTEND_WINDOW",
    "MAX_ATTEMPTS",
    "OVERVIEW_LOCK_KEY",
    "RETRY_AFTER",
    "REUSE_MARGIN",
    "UPKEEP_TASKS",
    "Build",
    "Previous",
    "Turn",
    "claim",
    "expired",
    "end_turn",
    "finish_failed",
    "finish_ready",
    "heartbeat",
    "mark_expired",
    "mark_extended",
    "previous_ready",
    "protected_versions",
    "release",
    "renew_turn",
    "request_missing",
    "take_turn",
    "to_extend",
    "write_progress",
]

# A third fixed key for `pg_advisory_xact_lock`, next to those of `queue.py`: 'jobs' in ASCII, plus 3.
OVERVIEW_LOCK_KEY = 0x6A6F6273_00000003

#: The failure kind of a pyramid whose term ran out; it is not in `RETRYABLE`, so :func:`claim` does not retry it; a successful `materialize` run of the same version
#: makes it buildable again (`catalog.pgstac.rearm_overview`, adr/0032 §5: the next successful run builds anew).
EXPIRED = "expired"

#: A build is tried this many times in all (the first included).
MAX_ATTEMPTS = 3
#: A tile or a pyramid of an older version is a source for reuse only while at least this much of its term is left: a new
#: pyramid takes the oldest time of what it reuses, so a tile near its end would shorten the whole pyramid to that.
REUSE_MARGIN = timedelta(days=7)
#: A failed build waits this long for its next attempt; a lost lease does not wait.
RETRY_AFTER = timedelta(hours=1)
#: The tasks of the upkeep that take turns (the rows of `earthx_overview_upkeep`).
UPKEEP_TASKS = frozenset({"extend", "sweep"})

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


@dataclass(frozen=True, slots=True)
class Previous:
    """A ready pyramid of an older version of the same dataset: what a new build may copy tiles from."""

    version: str
    #: The oldest time any of its objects was confirmed at the source.
    checked_at: datetime
    #: ``x/y`` of a base tile to the hash of the items it read, for the tiles that were stored and have a hash.
    base_hashes: dict[str, str]


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


def previous_ready(conn: psycopg.Connection, dataset_id: str, version: str) -> Previous | None:
    """The newest ready pyramid of ``dataset_id`` other than ``version`` with at least :data:`REUSE_MARGIN` of its term left, or ``None``.

    "Newest" is by ``checked_at``. Its tiles are the ones a build of ``version`` may reuse when their hash is the same; one
    whose term ends within the margin (or has ended) is no source, so a new pyramid is never cut short by an old one.
    """
    row = conn.execute(
        """
        SELECT version, checked_at, base_hashes FROM public.earthx_overview
        WHERE dataset_id = %s AND version <> %s AND status = 'ready' AND checked_at + %s - %s > clock_timestamp()
        ORDER BY checked_at DESC LIMIT 1
        """,
        (dataset_id, version, term_of(dataset_id), REUSE_MARGIN),
    ).fetchone()
    return None if row is None else Previous(row[0], row[1], dict(row[2]))


def release(conn: psycopg.Connection, build: Build) -> bool:
    """Give a build back at a shutdown, without it counting as an attempt; ``False`` if this attempt no longer owns it.

    The first attempt leaves no row at all (the request is a candidate again); a later one goes back to ``failed`` with
    ``lease_lost`` and its earlier number, which :func:`claim` takes up at once.
    """
    with conn.transaction():
        if build.attempt == 1:
            row = conn.execute(
                """
                DELETE FROM public.earthx_overview
                WHERE dataset_id = %s AND version = %s AND attempts = 1 AND status = 'building' RETURNING 1
                """,
                (build.dataset_id, build.version),
            ).fetchone()
        else:
            row = conn.execute(
                """
                UPDATE public.earthx_overview
                SET status = 'failed', failure_kind = %s, worker = NULL, lease_until = NULL, attempts = attempts - 1,
                    updated_at = clock_timestamp()
                WHERE dataset_id = %s AND version = %s AND attempts = %s AND status = 'building' RETURNING 1
                """,
                (_LEASE_LOST, build.dataset_id, build.version, build.attempt),
            ).fetchone()
    return row is not None


@dataclass(frozen=True, slots=True)
class Turn:
    """One worker's turn at a task of the upkeep."""

    task: str
    #: The number of the turn; a renewal or an end names it, so a worker that woke up late changes nothing.
    number: int


# The row of the task is made by the first turn. A turn is free when no lease holds it (or the lease ran out) and its
# time has come; a second worker that inserts at the same moment waits for the first and then finds the turn taken.
_TAKE_TURN_SQL = """
INSERT INTO public.earthx_overview_upkeep AS u (task, worker, lease_until, next_at)
VALUES (%(task)s, %(worker)s, clock_timestamp() + make_interval(secs => %(lease)s),
        clock_timestamp() + make_interval(secs => %(gap)s))
ON CONFLICT (task) DO UPDATE
SET turn = u.turn + 1, worker = EXCLUDED.worker, lease_until = EXCLUDED.lease_until, next_at = EXCLUDED.next_at
WHERE (u.lease_until IS NULL OR u.lease_until < clock_timestamp()) AND u.next_at <= clock_timestamp()
RETURNING turn
"""


def take_turn(
    conn: psycopg.Connection, task: str, *, worker: str, lease_seconds: float, gap_seconds: float
) -> Turn | None:
    """The turn at ``task`` for ``worker``; ``None`` while another worker holds it or its time has not come.

    The turn holds a lease of ``lease_seconds`` (:func:`renew_turn` keeps it) and the next one cannot begin within
    ``gap_seconds`` of this one, whoever takes it; ``0`` only keeps two turns from running at once. One statement, so it
    needs no lock of its own.
    """
    if task not in UPKEEP_TASKS:
        raise ValueError("an upkeep task is one of extend, sweep")
    if not lease_seconds > 0 or not gap_seconds >= 0:
        raise ValueError("a turn needs a positive lease and a gap that is not negative")
    row = conn.execute(
        _TAKE_TURN_SQL, {"task": task, "worker": worker, "lease": lease_seconds, "gap": gap_seconds}
    ).fetchone()
    return None if row is None else Turn(task, row[0])


def renew_turn(conn: psycopg.Connection, turn: Turn, lease_seconds: float) -> bool:
    """Renew the lease of the turn; ``False`` if it is over (ended, or taken over after its lease ran out)."""
    row = conn.execute(
        """
        UPDATE public.earthx_overview_upkeep SET lease_until = clock_timestamp() + make_interval(secs => %s)
        WHERE task = %s AND turn = %s AND lease_until IS NOT NULL
        RETURNING 1
        """,
        (lease_seconds, turn.task, turn.number),
    ).fetchone()
    return row is not None


def end_turn(conn: psycopg.Connection, turn: Turn) -> bool:
    """End the turn, so the next worker need not wait for its lease; ``False`` if it was over already."""
    row = conn.execute(
        """
        UPDATE public.earthx_overview_upkeep SET worker = NULL, lease_until = NULL
        WHERE task = %s AND turn = %s AND lease_until IS NOT NULL
        RETURNING 1
        """,
        (turn.task, turn.number),
    ).fetchone()
    return row is not None


# The ready pyramids whose term ran out and that nothing can still extend. A confirmation newer than ``checked_at`` holds
# an ordinary pyramid back only while the extension is possible (:data:`EXTEND_WINDOW`); a prototype source's is never
# extended, so a confirmation means nothing for it (a run does not even write one).
_EXPIRABLE = """
    status = 'ready'
    AND checked_at + CASE WHEN left(dataset_id, %(length)s) = %(prefix)s THEN %(proto)s ELSE %(term)s END < clock_timestamp()
    AND (left(dataset_id, %(length)s) = %(prefix)s OR confirmed_at IS NULL OR confirmed_at <= checked_at
         OR checked_at + %(window)s < clock_timestamp())
"""


def _terms() -> dict[str, object]:
    return {
        "length": len(PROTOTYPE_PREFIX),
        "prefix": PROTOTYPE_PREFIX,
        "proto": PROTOTYPE_TTL,
        "term": OVERVIEW_TTL,
        "window": EXTEND_WINDOW,
    }


def expired(conn: psycopg.Connection) -> list[tuple[str, str, datetime]]:
    """The ready pyramids that ran out: ``(dataset, version, checked_at)``.

    The term is 30 days from ``checked_at``, 7 for a prototype source (:func:`~earthx.objectstore.overviews.term_of`).
    A pyramid the source confirmed after its ``checked_at`` is left to :func:`to_extend` while the extension is still
    possible (:data:`EXTEND_WINDOW`), so that a round that came first does not expire a confirmed pyramid; after the
    window, whatever the confirmation, and for a prototype source at all times, it expires.
    """
    return [
        (row[0], row[1], row[2])
        for row in conn.execute(
            f"SELECT dataset_id, version, checked_at FROM public.earthx_overview WHERE {_EXPIRABLE} ORDER BY checked_at",
            _terms(),
        ).fetchall()
    ]


def mark_expired(
    conn: psycopg.Connection, dataset_id: str, version: str, checked_at: datetime, *, lost: bool = False
) -> bool:
    """Close a ready pyramid as ``failed`` with ``expired``; ``True`` only if this call did it.

    It is the first step, before any object is deleted: the update is conditional on the row still being ready at
    ``checked_at`` and still expirable (a pyramid that was extended meanwhile is neither), so only the caller whose update
    matched deletes the objects. ``lost`` is for a pyramid whose objects are already gone (the bucket rule was faster):
    the term and the confirmation then no longer matter.

    The row stays, so nothing builds the same version again by itself (:func:`request_missing` finds a row); a
    successful `materialize` run of that version makes it buildable again (``catalog.pgstac.rearm_overview``).
    """
    condition = "status = 'ready'" if lost else _EXPIRABLE
    row = conn.execute(
        f"""
        UPDATE public.earthx_overview
        SET status = 'failed', failure_kind = %(kind)s, updated_at = clock_timestamp()
        WHERE dataset_id = %(dataset)s AND version = %(version)s AND checked_at = %(checked)s AND {condition}
        RETURNING 1
        """,
        {**_terms(), "kind": EXPIRED, "dataset": dataset_id, "version": version, "checked": checked_at},
    ).fetchone()
    return row is not None


def to_extend(conn: psycopg.Connection, datasets: Collection[str]) -> list[tuple[str, str, datetime]]:
    """The ready pyramids of ``datasets`` that the source confirmed after their ``checked_at`` and that can still be extended:
    ``(dataset, version, confirmed_at)``.

    Only within :data:`EXTEND_WINDOW` of ``checked_at``: later, the bucket rule may have deleted a part of the objects, and
    an extension would make a pyramid with holes look whole. A prototype source's pyramid is never extended (adr/0032 §8.4).
    """
    return [
        (row[0], row[1], row[2])
        for row in conn.execute(
            """
            SELECT dataset_id, version, confirmed_at FROM public.earthx_overview
            WHERE status = 'ready' AND confirmed_at > checked_at AND dataset_id = ANY(%(datasets)s)
              AND left(dataset_id, %(length)s) <> %(prefix)s AND checked_at + %(window)s > clock_timestamp()
            ORDER BY confirmed_at
            """,
            {**_terms(), "datasets": sorted(datasets)},
        ).fetchall()
    ]


def mark_extended(conn: psycopg.Connection, dataset_id: str, version: str, confirmed_at: datetime) -> bool:
    """``checked_at`` := ``confirmed_at`` once every object carries it; ``False`` if the row is not ready, already at least
    that new, or past :data:`EXTEND_WINDOW`."""
    row = conn.execute(
        """
        UPDATE public.earthx_overview SET checked_at = %(confirmed)s, updated_at = clock_timestamp()
        WHERE dataset_id = %(dataset)s AND version = %(version)s AND status = 'ready' AND checked_at < %(confirmed)s
          AND checked_at + %(window)s > clock_timestamp()
        RETURNING 1
        """,
        {"confirmed": confirmed_at, "dataset": dataset_id, "version": version, "window": EXTEND_WINDOW},
    ).fetchone()
    return row is not None


def protected_versions(conn: psycopg.Connection) -> set[tuple[str, str]]:
    """``(dataset, version)`` whose objects may stay: a build in progress, a ready pyramid, and a failed one that
    :func:`claim` will try again. The objects of any other row (a failure that is not retried, an expired pyramid) and
    of no row at all belong to nobody.
    """
    return {
        (row[0], row[1])
        for row in conn.execute(
            """
            SELECT dataset_id, version FROM public.earthx_overview
            WHERE status IN ('building', 'ready')
               OR (status = 'failed' AND failure_kind = ANY(%s) AND attempts < %s)
            """,
            (sorted(RETRYABLE), MAX_ATTEMPTS),
        )
    }
