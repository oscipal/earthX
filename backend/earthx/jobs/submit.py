"""What `api` calls: place an order, read its state, dismiss it (architekturplan.md 7.5 `JobRunner`).

`api` reaches the queue only through here (adr/0013 §5): what stands behind it, today the
tables of migration 006, can change without `api` noticing. Every function takes a
connection from the caller and runs in READ COMMITTED, the server's default; under
REPEATABLE READ the attach to an active run could not see the run another order
committed a moment earlier.

**Job and run (F6).** An order becomes a *job* with a random ``job_id`` and its own
``recipe_id``. Equal orders placed at the same time share one internal *run*; a job that
is dismissed cancels the run only if no live job hangs on it, so nobody can cancel
another's job by knowing the same recipe. Nothing returned here carries a run number,
a cache key, a hash or an address (Q8).
"""

from __future__ import annotations

import math
import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import psycopg
from psycopg.types.json import Jsonb

from earthx.jobs.queue import CACHE_MIN_REMAINING, WAKE_CHANNEL
from earthx.objectstore.results import RESULT_TTL
from earthx.processing.operators import REGISTRY
from earthx.processing.plan import estimate
from earthx.processing.recipe import Recipe, cache_key, recipe_hosts, run_key

__all__ = [
    "MIN_RUNTIME_SECONDS",
    "RUNTIME_FACTOR",
    "JobStatus",
    "dismiss",
    "job_status",
    "submit",
]

#: The most a run may take: twice the estimate, at least ten minutes (adr/0013 §5.6).
#: The factor is a starting value; M4-08a leaves calibrating it on real runs open.
RUNTIME_FACTOR = 2.0
MIN_RUNTIME_SECONDS = 600

# `secrets.token_urlsafe(16)`: 128 bits, 22 characters (adr/0014 F15).
_ID = re.compile(r"^[A-Za-z0-9_-]{22}$")

Status = Literal["accepted", "running", "successful", "failed", "dismissed"]


@dataclass(frozen=True, slots=True)
class JobStatus:
    """The state of one job as OGC API Processes names it, plus what a result link needs."""

    job_id: str
    recipe_id: str
    status: Status
    progress: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    #: When the job's rows and result go (7 days after the finish, Q10).
    expires_at: datetime
    #: A short name such as ``source_5xx``, never a text with an address.
    error_kind: str | None
    #: Only for a successful, not dismissed job: where the result lies and what is known about it.
    result_id: str | None
    result: dict[str, Any] | None


def _runtime_limit(recipe: Recipe) -> int:
    seconds = estimate(recipe, REGISTRY).seconds * RUNTIME_FACTOR
    return max(MIN_RUNTIME_SECONDS, math.ceil(seconds))


def submit(conn: psycopg.Connection, recipe: Recipe) -> str:
    """Place the order and return its ``job_id``.

    In one transaction: the recipe row, then a job on a finished run of the same cache key
    if one exists with at least 24 hours of life left (Q11, adr/0013 §5.8), else on the
    active run of the same key, else on a new run. A recipe without a ``recipe_id`` gets a
    new one; every order has its own (adr/0013 §9 point 2).
    """
    recipe_id = recipe.recipe_id or secrets.token_urlsafe(16)
    stored = recipe.model_copy(update={"recipe_id": recipe_id})
    key = run_key(stored)
    cacheable = cache_key(stored) is not None
    hosts = list(recipe_hosts(stored))
    max_seconds = _runtime_limit(stored)
    job_id = secrets.token_urlsafe(16)
    with conn.transaction():
        conn.execute(
            "INSERT INTO public.earthx_recipe (recipe_id, body) VALUES (%s, %s)",
            (recipe_id, Jsonb(stored.model_dump(mode="json"))),
        )
        run_id, created = _run_for(conn, key, cacheable, recipe_id, hosts, max_seconds)
        conn.execute(
            "INSERT INTO public.earthx_job (job_id, run_id, recipe_id) VALUES (%s, %s, %s)",
            (job_id, run_id, recipe_id),
        )
        if created:
            conn.execute("SELECT pg_notify(%s, '')", (WAKE_CHANNEL,))
    return job_id


def _run_for(
    conn: psycopg.Connection, key: str, cacheable: bool, recipe_id: str, hosts: list[str], max_seconds: int
) -> tuple[int, bool]:
    """The run the new job hangs on, and whether this call created it."""
    # A concurrent order may finish the active run between the two looks; a second round finds
    # the result instead. Three rounds are far more than one such race needs.
    for _ in range(3):
        if cacheable:
            hit = conn.execute(
                """
                SELECT run_id FROM public.earthx_run
                WHERE cache_key = %s AND cacheable AND status = 'successful'
                  AND expires_at >= clock_timestamp() + %s
                ORDER BY finished_at DESC LIMIT 1
                """,
                (key, CACHE_MIN_REMAINING),
            ).fetchone()
            if hit is not None:
                return hit[0], False
        created = conn.execute(
            """
            INSERT INTO public.earthx_run (cache_key, cacheable, recipe_id, status, hosts, max_seconds, expires_at)
            VALUES (%s, %s, %s, 'accepted', %s, %s, clock_timestamp() + %s)
            ON CONFLICT (cache_key) WHERE status IN ('accepted', 'running') DO NOTHING
            RETURNING run_id
            """,
            (key, cacheable, recipe_id, hosts, max_seconds, RESULT_TTL),
        ).fetchone()
        if created is not None:
            return created[0], True
        # An order that attaches to a run being cancelled wants its result after all.
        active = conn.execute(
            """
            UPDATE public.earthx_run SET cancel_requested = false
            WHERE cache_key = %s AND status IN ('accepted', 'running')
            RETURNING run_id
            """,
            (key,),
        ).fetchone()
        if active is not None:
            return active[0], False
    raise RuntimeError("the queue could not place the order; try again")


_STATUS_SQL = """
SELECT j.job_id, j.recipe_id, j.dismissed, j.created_at,
       r.status, r.progress, r.started_at, r.finished_at, r.expires_at, r.error_kind, r.result_id, r.result
FROM public.earthx_job j
JOIN public.earthx_run r ON r.run_id = j.run_id
WHERE j.job_id = %s
"""


def _status(row: tuple[Any, ...]) -> JobStatus:
    job_id, recipe_id, dismissed, created_at, status, progress, started, finished, expires, kind, result_id, result = (
        row
    )
    if dismissed:
        status = "dismissed"
    visible = status == "successful"
    return JobStatus(
        job_id=job_id,
        recipe_id=recipe_id,
        status=status,
        progress=100 if visible else int(progress),
        created_at=created_at,
        started_at=started,
        finished_at=finished,
        expires_at=expires,
        error_kind=kind if status == "failed" else None,
        result_id=result_id if visible else None,
        result=result if visible else None,
    )


def job_status(conn: psycopg.Connection, job_id: str) -> JobStatus | None:
    """The state of a job, or ``None`` for an identifier that is malformed or unknown.

    Reads only: looking at a job never changes a row, so it never extends the life of a
    recipe (adr/0015 F13). A malformed identifier does not reach the database.
    """
    if not isinstance(job_id, str) or not _ID.match(job_id):
        return None
    row = conn.execute(_STATUS_SQL, (job_id,)).fetchone()
    return None if row is None else _status(row)


def dismiss(conn: psycopg.Connection, job_id: str) -> JobStatus | None:
    """Dismiss the job (OGC ``dismiss``); returns its state afterwards, ``None`` if unknown.

    The run is cancelled only if no live job hangs on it: waiting at once, running through
    the flag the supervisor reads (adr/0013 §5.5). A finished job counts as dismissed and its
    result stays until it expires, since it may serve other jobs as a cache hit (plan F5).
    """
    if not isinstance(job_id, str) or not _ID.match(job_id):
        return None
    with conn.transaction():
        job = conn.execute(
            "UPDATE public.earthx_job SET dismissed = true WHERE job_id = %s RETURNING run_id", (job_id,)
        ).fetchone()
        if job is None:
            return None
        run_id = job[0]
        # Locking the run orders concurrent dismissals of jobs that share it: the second one
        # waits, then counts the first one's flag too.
        run = conn.execute("SELECT status FROM public.earthx_run WHERE run_id = %s FOR UPDATE", (run_id,)).fetchone()
        live = conn.execute(
            "SELECT count(*) FROM public.earthx_job WHERE run_id = %s AND NOT dismissed", (run_id,)
        ).fetchone()
        if run is not None and live is not None and live[0] == 0:
            if run[0] == "accepted":
                conn.execute(
                    """
                    UPDATE public.earthx_run SET status = 'dismissed', finished_at = clock_timestamp()
                    WHERE run_id = %s AND status = 'accepted'
                    """,
                    (run_id,),
                )
            elif run[0] == "running":
                conn.execute("UPDATE public.earthx_run SET cancel_requested = true WHERE run_id = %s", (run_id,))
                conn.execute("SELECT pg_notify(%s, '')", (WAKE_CHANNEL,))
    return job_status(conn, job_id)
