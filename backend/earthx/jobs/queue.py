"""The queue's state changes, as SQL on `earthx_run` (adr/0013 §5.2, §5.4–§5.6).

Every function takes a connection and does one thing in one transaction. The
supervisor in `worker.py` calls them; nothing here starts a process.

**The rules these statements keep:**

* A run belongs to one attempt. Every change after the pick-up names the attempt
  number it was picked up with and touches no row if another attempt owns the run
  by now (a worker that woke up late cannot overwrite a newer one's result).
* The cap and the limit per host are counted from the rows, under a lock taken in
  a statement of its own, in READ COMMITTED (:func:`claim`).
* Progress and every state change send a notification in the same transaction, so
  a rolled-back change sends none. The row is the truth; the notification only
  wakes whoever listens (§5.4).
* A message or a log line carries the run's number and numbers, never a job ID, a
  hash, a recipe or an address (Q8).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from earthx.objectstore.results import RESULT_TTL

__all__ = [
    "CACHE_MIN_REMAINING",
    "CLAIM_LOCK_KEY",
    "CLEANUP_LOCK_KEY",
    "PROGRESS_CHANNEL",
    "RETRYABLE",
    "WAKE_CHANNEL",
    "Claim",
    "claim",
    "finish_cancelled",
    "finish_failed",
    "finish_successful",
    "heartbeat",
    "notify_progress",
    "release",
    "requeue_expired",
    "write_progress",
]

WAKE_CHANNEL = "earthx_jobs_wake"
PROGRESS_CHANNEL = "earthx_job_progress"

# Two fixed keys for `pg_advisory_xact_lock`, one per purpose: 'jobs' in ASCII, plus 1 and 2.
CLAIM_LOCK_KEY = 0x6A6F6273_00000001
CLEANUP_LOCK_KEY = 0x6A6F6273_00000002

#: A cache hit needs at least this much of its result's life left (adr/0013 §5.8, F9;
#: adr/0015 §8.3, T1). Next to the 7 days of Q10 on purpose.
CACHE_MIN_REMAINING = timedelta(hours=24)

#: The only reasons a second attempt can help (adr/0013 §5.6, Auflage F8). Everything
#: else, an unknown error included, fails at once.
RETRYABLE = frozenset({"source_timeout", "source_5xx", "lease_lost"})

# Statement 1 takes the lock and nothing else. Statement 2 counts and picks. They must
# be two statements: in READ COMMITTED a statement's snapshot is taken when it starts,
# so a count in the statement that waits for the lock would be a count from before the
# wait, and the cap would hold only until two workers pick up at the same moment
# (adr/0013 §5.2, measured as M2: 4 to 6 running with a cap of 3).
CLAIM_LOCK_SQL = "SELECT pg_advisory_xact_lock(%(key)s)"

CLAIM_SQL = """
WITH running AS (
    SELECT hosts FROM public.earthx_run WHERE status = 'running'
),
next AS (
    SELECT r.run_id
    FROM public.earthx_run r
    WHERE r.status = 'accepted'
      AND r.pool = ANY(%(pools)s)
      AND r.not_before <= clock_timestamp()
      AND (SELECT count(*) FROM running) < (SELECT global_cap FROM public.earthx_job_limits)
      AND NOT EXISTS (
          SELECT 1 FROM unnest(r.hosts) AS h
          WHERE (SELECT count(*) FROM running x WHERE h = ANY (x.hosts))
                >= (SELECT host_cap FROM public.earthx_job_limits)
      )
    ORDER BY r.priority DESC, r.created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE public.earthx_run r
SET status = 'running',
    attempt = r.attempt + 1,
    worker = %(worker)s,
    started_at = clock_timestamp(),
    lease_until = clock_timestamp() + make_interval(secs => %(lease)s),
    progress = 0,
    error_kind = NULL
FROM next
WHERE r.run_id = next.run_id
RETURNING r.run_id, r.attempt, r.max_seconds,
          (SELECT body FROM public.earthx_recipe WHERE recipe_id = r.recipe_id)
"""


@dataclass(frozen=True, slots=True)
class Claim:
    """One run, picked up by one attempt."""

    run_id: int
    attempt: int
    max_seconds: int
    recipe: dict[str, Any]


def notify_progress(conn: psycopg.Connection, run_id: int, progress: int, status: str) -> None:
    """Send the progress message of a run; in the caller's transaction, so a rollback sends none."""
    payload = json.dumps({"run": run_id, "p": progress, "s": status}, separators=(",", ":"))
    conn.execute("SELECT pg_notify(%s, %s)", (PROGRESS_CHANNEL, payload))


def _wake(conn: psycopg.Connection) -> None:
    conn.execute("SELECT pg_notify(%s, '')", (WAKE_CHANNEL,))


def claim(
    conn: psycopg.Connection, *, worker: str, lease_seconds: float, pools: tuple[str, ...] = ("default",)
) -> Claim | None:
    """The next run that fits under the cap and the limit per host, now owned by ``worker``.

    ``None`` when nothing waits or the cap is full. The transaction runs in READ
    COMMITTED, set here and not left to the server's default (adr/0013 §5.2); the
    connection is in autocommit mode, so this transaction is the outermost one.
    """
    with conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        conn.execute(CLAIM_LOCK_SQL, {"key": CLAIM_LOCK_KEY})
        row = conn.execute(CLAIM_SQL, {"pools": list(pools), "worker": worker, "lease": lease_seconds}).fetchone()
        if row is None:
            return None
        notify_progress(conn, row[0], 0, "running")
        return Claim(run_id=row[0], attempt=row[1], max_seconds=row[2], recipe=row[3])


def heartbeat(conn: psycopg.Connection, run_id: int, attempt: int, lease_seconds: float) -> bool | None:
    """Renew the lease. Returns ``cancel_requested``, or ``None`` if this attempt no longer owns the run."""
    row = conn.execute(
        """
        UPDATE public.earthx_run
        SET lease_until = clock_timestamp() + make_interval(secs => %s)
        WHERE run_id = %s AND attempt = %s AND status = 'running'
        RETURNING cancel_requested
        """,
        (lease_seconds, run_id, attempt),
    ).fetchone()
    return None if row is None else bool(row[0])


def write_progress(conn: psycopg.Connection, run_id: int, attempt: int, percent: int) -> bool | None:
    """Store the progress (0–99 while running) and notify; returns ``cancel_requested`` or ``None`` if not owned."""
    percent = max(0, min(99, percent))
    with conn.transaction():
        row = conn.execute(
            """
            UPDATE public.earthx_run SET progress = %s
            WHERE run_id = %s AND attempt = %s AND status = 'running'
            RETURNING cancel_requested
            """,
            (percent, run_id, attempt),
        ).fetchone()
        if row is None:
            return None
        notify_progress(conn, run_id, percent, "running")
        return bool(row[0])


def finish_successful(
    conn: psycopg.Connection, run_id: int, attempt: int, result_id: str, result: dict[str, Any]
) -> bool:
    """Close the run as successful, only for the attempt that owns it; ``False`` if it no longer does.

    ``expires_at`` becomes the finish plus 7 days (Q10).
    """
    with conn.transaction():
        row = conn.execute(
            """
            UPDATE public.earthx_run
            SET status = 'successful', result_id = %s, result = %s, progress = 100, error_kind = NULL,
                worker = NULL, lease_until = NULL, cancel_requested = false,
                finished_at = clock_timestamp(), expires_at = clock_timestamp() + %s
            WHERE run_id = %s AND attempt = %s AND status = 'running'
            RETURNING run_id
            """,
            (result_id, Jsonb(result), RESULT_TTL, run_id, attempt),
        ).fetchone()
        if row is None:
            return False
        notify_progress(conn, run_id, 100, "successful")
        return True


# One statement for "this attempt ended without a result": the run goes back to the
# queue if the reason allows another attempt and attempts are left, and fails
# otherwise. `again` is computed once, next to the row, so both columns agree.
_END_ATTEMPT_SQL = """
WITH ended AS (
    SELECT run_id, (%(retry)s AND attempt < max_attempts) AS again
    FROM public.earthx_run
    WHERE run_id = %(run)s AND attempt = %(attempt)s AND status = 'running'
)
UPDATE public.earthx_run r
SET status = CASE WHEN e.again THEN 'accepted' ELSE 'failed' END,
    error_kind = %(kind)s,
    worker = NULL,
    lease_until = NULL,
    cancel_requested = false,
    progress = CASE WHEN e.again THEN 0 ELSE r.progress END,
    not_before = CASE WHEN e.again
                 THEN clock_timestamp() + make_interval(
                        secs => %(base)s * power(2, r.attempt - 1) * (0.8 + random() * 0.4))
                 ELSE r.not_before END,
    finished_at = CASE WHEN e.again THEN NULL ELSE clock_timestamp() END,
    expires_at = CASE WHEN e.again THEN r.expires_at ELSE clock_timestamp() + %(ttl)s END
FROM ended e
WHERE r.run_id = e.run_id
RETURNING r.status, r.progress
"""


def _lock_attempt(
    conn: psycopg.Connection, run_id: int, attempt: int, *, lease_expired_only: bool = False
) -> tuple[bool, bool] | None:
    """Lock the run for this attempt, then read ``(cancel_requested, a live job hangs on it)``.

    ``None`` if the attempt no longer owns the run (or, with ``lease_expired_only``, if its
    lease was renewed since). Two statements, on purpose, like the pick-up: in READ COMMITTED
    the second one starts after the lock is held and so sees every job a concurrent
    ``submit`` committed while this one waited. Counting in the statement that waits for the
    lock would use the picture from before the wait and could dismiss a run that has a live
    job (the same stale count as the cap, adr/0013 §5.2).
    """
    locked = conn.execute(
        """
        SELECT 1 FROM public.earthx_run
        WHERE run_id = %s AND attempt = %s AND status = 'running'
          AND (NOT %s OR lease_until < clock_timestamp())
        FOR UPDATE
        """,
        (run_id, attempt, lease_expired_only),
    ).fetchone()
    if locked is None:
        return None
    row = conn.execute(
        """
        SELECT cancel_requested,
               EXISTS (SELECT 1 FROM public.earthx_job j WHERE j.run_id = %s AND NOT j.dismissed)
        FROM public.earthx_run WHERE run_id = %s
        """,
        (run_id, run_id),
    ).fetchone()
    assert row is not None
    return bool(row[0]), bool(row[1])


def _dismiss_locked(conn: psycopg.Connection, run_id: int) -> str:
    conn.execute(
        """
        UPDATE public.earthx_run
        SET status = 'dismissed', worker = NULL, lease_until = NULL, cancel_requested = false,
            finished_at = clock_timestamp()
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = conn.execute("SELECT progress FROM public.earthx_run WHERE run_id = %s", (run_id,)).fetchone()
    notify_progress(conn, run_id, row[0] if row else 0, "dismissed")
    return "dismissed"


def finish_failed(
    conn: psycopg.Connection,
    run_id: int,
    attempt: int,
    kind: str,
    *,
    backoff_seconds: float = 30.0,
    lease_expired_only: bool = False,
) -> str | None:
    """End an attempt with a failure named ``kind``; returns the run's new status or ``None`` if not owned.

    Back to ``accepted`` with a delay of ``backoff_seconds × 2^(attempt−1)`` ±20 % if ``kind`` is
    in :data:`RETRYABLE` and attempts are left (adr/0013 §5.6), ``failed`` otherwise. A run that
    was being cancelled and has no live job any more is ``dismissed`` instead: nobody waits for
    a second attempt of it.
    """
    with conn.transaction():
        state = _lock_attempt(conn, run_id, attempt, lease_expired_only=lease_expired_only)
        if state is None:
            return None
        cancel_requested, live = state
        if cancel_requested and not live:
            return _dismiss_locked(conn, run_id)
        row = conn.execute(
            _END_ATTEMPT_SQL,
            {
                "retry": kind in RETRYABLE,
                "run": run_id,
                "attempt": attempt,
                "kind": kind,
                "base": backoff_seconds,
                "ttl": RESULT_TTL,
            },
        ).fetchone()
        assert row is not None
        notify_progress(conn, run_id, row[1], row[0])
        if row[0] == "accepted":
            _wake(conn)
        return row[0]


def release(conn: psycopg.Connection, run_id: int, attempt: int) -> str | None:
    """Give a run back at shutdown: as a lost lease, but without waiting for the backoff (plan K5)."""
    return finish_failed(conn, run_id, attempt, "lease_lost", backoff_seconds=0.0)


def finish_cancelled(conn: psycopg.Connection, run_id: int, attempt: int) -> str | None:
    """The child stopped because a cancel was asked for.

    ``dismissed`` if no live job hangs on the run any more. If one does (it attached after
    the cancel was asked for, adr/0013 §5.5), the run goes back to the queue instead.
    """
    with conn.transaction():
        state = _lock_attempt(conn, run_id, attempt)
        if state is None:
            return None
        _, live = state
        if not live:
            return _dismiss_locked(conn, run_id)
        conn.execute(
            """
            UPDATE public.earthx_run
            SET status = 'accepted', worker = NULL, lease_until = NULL, cancel_requested = false,
                progress = 0, not_before = clock_timestamp()
            WHERE run_id = %s
            """,
            (run_id,),
        )
        notify_progress(conn, run_id, 0, "accepted")
        _wake(conn)
        return "accepted"


def requeue_expired(conn: psycopg.Connection, *, backoff_seconds: float = 30.0) -> int:
    """Runs whose lease ran out: back to the queue, or failed once attempts are used up (adr/0013 §5.6).

    Returns how many runs were handled. Any supervisor may call this; each run is handled once,
    because the change names the attempt it found.
    """
    handled = 0
    expired = conn.execute(
        """
        SELECT run_id, attempt FROM public.earthx_run
        WHERE status = 'running' AND lease_until < clock_timestamp()
        """
    ).fetchall()
    for run_id, attempt in expired:
        if (
            finish_failed(conn, run_id, attempt, "lease_lost", backoff_seconds=backoff_seconds, lease_expired_only=True)
            is not None
        ):
            handled += 1
    return handled
