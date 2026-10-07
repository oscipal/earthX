"""Cleaning up after the expiry (adr/0013 §5.8, adr/0015 §7.1, §7.2 A1; Q10).

Every hour one supervisor deletes what has expired, in batches: first the objects of an
expired run in the object store, then its rows. A crash between the two leaves rows whose
object is gone, which `api` has not served since ``expires_at`` anyway; the other order
would leave objects nobody knows (the bucket rule is the net for those).

**What lives how long.** A run, and so its jobs and its result, lives until ``expires_at``:
seven days after it finished (Q10), counted from its creation for a run that never
finished. A recipe has no term of its own: it stays while a job or a run refers to it, so
it lives as long as the latest result that uses it, and only a run or a cache hit lengthens
that (adr/0015 F13). Nothing here is lengthened by looking.

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

LOGGER = logging.getLogger("earthx.jobs")

#: Rows per batch (adr/0013 §5.8).
BATCH = 5000


@dataclass(frozen=True, slots=True)
class CleanupResult:
    runs: int = 0
    jobs: int = 0
    recipes: int = 0
    objects: int = 0

    @property
    def total(self) -> int:
        return self.runs + self.jobs + self.recipes


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
        return CleanupResult(runs=runs, jobs=jobs, recipes=recipes, objects=objects)


def cleanup(conn: psycopg.Connection, store: Store, *, batch: int = BATCH) -> CleanupResult:
    """Batches until nothing expired is left; the sum of what was deleted."""
    runs = jobs = recipes = objects = 0
    while True:
        done = cleanup_batch(conn, store, batch=batch)
        if done is None or done.total == 0:
            break
        runs, jobs, recipes, objects = (
            runs + done.runs,
            jobs + done.jobs,
            recipes + done.recipes,
            objects + done.objects,
        )
        if done.runs < batch and done.recipes < batch:
            break
    result = CleanupResult(runs, jobs, recipes, objects)
    if result.total:
        LOGGER.info(
            "expired runs cleaned up",
            extra={"runs": runs, "jobs": jobs, "recipes": recipes, "objects": objects},
        )
    return result
