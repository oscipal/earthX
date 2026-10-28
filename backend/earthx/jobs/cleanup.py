"""Cleaning up after the expiry (adr/0013 §5.8, adr/0015 §7.1, §7.2 A1; Q10).

Every hour one supervisor deletes what has expired, in batches: first the objects of an
expired run in the object store, then its rows. A crash between the two leaves rows whose
object is gone, which `api` has not served since ``expires_at`` anyway; the other order
would leave objects nobody knows (the bucket rule is the net for those).

**What lives how long.** A run, and so its jobs and its result, lives until ``expires_at``:
seven days after it finished (Q10), counted from its creation for a run that never
finished. A recipe has no term of its own: it stays while a job or a run refers to it, so
it lives as long as the latest result that uses it, and only a new run lengthens that. A cache
hit does not: the bucket rule counts from the write of the object, so a run whose term a hit
had moved would point at deleted bytes (adr/0015 F13, as amended in §7.1). A permalink has a fixed term from its creation and is deleted whole
(M4-19e, adr/0015 §13), a bundle of jobs likewise (UI-01e). Nothing here is lengthened by looking.

**A deleted job (NM4-27)** goes when its term ends (``deleted_until``), earlier than its run would. Its row goes
always. The result goes with it only if nothing else needs it: no job on the run is alive, none is still inside its
own term (it could be restored), so the run is no cache hit either. Otherwise the run stays for the others and, if it
pointed at the recipe of the deleted job, points at a recipe that stays; the recipe of the deleted job then goes with
the next sweep of recipes. A run is locked before its jobs, as :func:`earthx.jobs.submit.dismiss` does.

Foreign keys are RESTRICT, so a deletion in the wrong order fails loudly instead of taking
valid rows along. Only one supervisor works at a time: the batch holds a transaction-level
advisory lock that is taken without waiting, which also holds behind a pooler in
transaction mode.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import psycopg

from earthx.jobs.queue import CLEANUP_LOCK_KEY
from earthx.objectstore.results import Store, delete_result

__all__ = ["BATCH", "CleanupResult", "cleanup", "cleanup_batch"]

#: The states of a run that is over; a run that is not is left to the worker.
_OVER = ("successful", "failed", "dismissed")

LOGGER = logging.getLogger("earthx.jobs")

#: Rows per batch (adr/0013 §5.8).
BATCH = 5000


@dataclass(frozen=True, slots=True)
class CleanupResult:
    runs: int = 0
    jobs: int = 0
    recipes: int = 0
    objects: int = 0
    permalinks: int = 0
    bundles: int = 0
    #: Jobs removed because the term of their deletion ended (NM4-27); with their run, `runs` counts it too.
    deleted_jobs: int = 0

    @property
    def total(self) -> int:
        return self.runs + self.jobs + self.recipes + self.permalinks + self.bundles + self.deleted_jobs


def cleanup_batch(conn: psycopg.Connection, store: Store, *, batch: int = BATCH) -> CleanupResult | None:
    """One batch in one transaction; ``None`` if another supervisor holds the lock.

    A failure of the object store raises, and the transaction rolls back: no row of the
    batch is gone, and the next hour tries again.
    """
    with conn.transaction():
        locked = conn.execute("SELECT pg_try_advisory_xact_lock(%s)", (CLEANUP_LOCK_KEY,)).fetchone()
        if locked is None or not locked[0]:
            return None
        # A run that is running is left to the lease sweeper; the others are over.
        expired = conn.execute(
            """
            SELECT run_id, result_id FROM public.earthx_run
            WHERE expires_at < clock_timestamp() AND status <> 'running'
            ORDER BY expires_at LIMIT %s
            FOR UPDATE
            """,
            (batch,),
        ).fetchall()
        run_ids = [run_id for run_id, _ in expired]
        objects = 0
        for _, result_id in expired:
            if result_id is not None:
                delete_result(store, result_id)
                objects += 1
        jobs = runs = 0
        if run_ids:
            jobs = conn.execute("DELETE FROM public.earthx_job WHERE run_id = ANY(%s)", (run_ids,)).rowcount
            runs = conn.execute("DELETE FROM public.earthx_run WHERE run_id = ANY(%s)", (run_ids,)).rowcount
        deleted_jobs, deleted_runs, deleted_objects = _deleted_jobs(conn, store, batch)
        runs += deleted_runs
        objects += deleted_objects
        recipes = conn.execute(
            """
            DELETE FROM public.earthx_recipe WHERE recipe_id IN (
                SELECT r.recipe_id FROM public.earthx_recipe r
                WHERE NOT EXISTS (SELECT 1 FROM public.earthx_job j WHERE j.recipe_id = r.recipe_id)
                  AND NOT EXISTS (SELECT 1 FROM public.earthx_run n WHERE n.recipe_id = r.recipe_id)
                LIMIT %s
            )
            """,
            (batch,),
        ).rowcount
        permalinks = conn.execute(
            """
            DELETE FROM public.earthx_permalink WHERE permalink_id IN (
                SELECT permalink_id FROM public.earthx_permalink
                WHERE expires_at < clock_timestamp() ORDER BY expires_at LIMIT %s
            )
            """,
            (batch,),
        ).rowcount
        bundles = conn.execute(
            """
            DELETE FROM public.earthx_bundle WHERE bundle_id IN (
                SELECT bundle_id FROM public.earthx_bundle
                WHERE expires_at < clock_timestamp() ORDER BY expires_at LIMIT %s
            )
            """,
            (batch,),
        ).rowcount
        return CleanupResult(
            runs=runs,
            jobs=jobs,
            recipes=recipes,
            objects=objects,
            permalinks=permalinks,
            bundles=bundles,
            deleted_jobs=deleted_jobs,
        )


def _deleted_jobs(conn: psycopg.Connection, store: Store, batch: int) -> tuple[int, int, int]:
    """Remove the jobs whose term after a deletion has ended; ``(jobs, runs, objects)`` removed.

    The runs are locked first, in the order of their number, and only then are their jobs read: the read
    is a statement of its own, so it sees every job a concurrent ``submit`` or ``restore`` committed while the
    lock was waited for (the same two steps as ``jobs.queue._lock_attempt``).
    """
    run_ids = [
        row[0]
        for row in conn.execute(
            """
            SELECT DISTINCT run_id FROM public.earthx_job
            WHERE deleted_until < clock_timestamp() ORDER BY run_id LIMIT %s
            """,
            (batch,),
        ).fetchall()
    ]
    if not run_ids:
        return 0, 0, 0
    runs = conn.execute(
        """
        SELECT run_id, result_id, status, recipe_id FROM public.earthx_run
        WHERE run_id = ANY(%s) ORDER BY run_id FOR UPDATE
        """,
        (run_ids,),
    ).fetchall()
    jobs = conn.execute(
        """
        SELECT job_id, run_id, recipe_id,
               deleted_until < clock_timestamp() AS due,
               NOT dismissed AND deleted_until IS NULL AS alive,
               deleted_until >= clock_timestamp() AS waiting
        FROM public.earthx_job WHERE run_id = ANY(%s)
        """,
        (run_ids,),
    ).fetchall()
    removed = whole_runs = objects = 0
    for run_id, result_id, status, run_recipe in runs:
        mine = [job for job in jobs if job[1] == run_id]
        due = [job for job in mine if job[3]]
        if not due:
            continue
        needed = any(job[4] or job[5] for job in mine)
        if not needed and status in _OVER:
            if result_id is not None:
                delete_result(store, result_id)
                objects += 1
            conn.execute("DELETE FROM public.earthx_job WHERE run_id = %s", (run_id,))
            conn.execute("DELETE FROM public.earthx_run WHERE run_id = %s", (run_id,))
            removed += len(due)
            whole_runs += 1
            continue
        if run_recipe in {job[2] for job in due}:
            # The run keeps a recipe of its own for the foreign key; one that stays, so the deleted one can go.
            stays = next((job[2] for job in mine if not job[3]), None)
            if stays is None:
                continue
            conn.execute("UPDATE public.earthx_run SET recipe_id = %s WHERE run_id = %s", (stays, run_id))
        removed += conn.execute(
            "DELETE FROM public.earthx_job WHERE job_id = ANY(%s)", ([job[0] for job in due],)
        ).rowcount
    return removed, whole_runs, objects


def cleanup(conn: psycopg.Connection, store: Store, *, batch: int = BATCH) -> CleanupResult:
    """Batches until nothing expired is left; the sum of what was deleted."""
    runs = jobs = recipes = objects = permalinks = bundles = deleted_jobs = 0
    while True:
        done = cleanup_batch(conn, store, batch=batch)
        if done is None or done.total == 0:
            break
        runs, jobs, recipes, objects, permalinks, bundles, deleted_jobs = (
            runs + done.runs,
            jobs + done.jobs,
            recipes + done.recipes,
            objects + done.objects,
            permalinks + done.permalinks,
            bundles + done.bundles,
            deleted_jobs + done.deleted_jobs,
        )
        if (
            done.runs < batch
            and done.recipes < batch
            and done.permalinks < batch
            and done.bundles < batch
            and done.deleted_jobs < batch
        ):
            break
    result = CleanupResult(runs, jobs, recipes, objects, permalinks, bundles, deleted_jobs)
    if result.total:
        LOGGER.info(
            "expired runs, deleted jobs, permalinks and bundles cleaned up",
            extra={
                "runs": runs,
                "jobs": jobs,
                "recipes": recipes,
                "objects": objects,
                "permalinks": permalinks,
                "bundles": bundles,
                "deleted_jobs": deleted_jobs,
            },
        )
    return result
