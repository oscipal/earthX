"""The body of one worker process in the cap test: pick up, hold for a moment, finish, until the queue is empty.

Kept out of the test module so a spawned process imports only this and `earthx.jobs.queue`.
"""

from __future__ import annotations

import time

import psycopg

from earthx.jobs.queue import claim, finish_successful


def claim_until_empty(worker: str, hold: float) -> int:
    """Returns how many runs this process ran. `PGDATABASE` comes from the environment."""
    done = 0
    with psycopg.connect(autocommit=True) as conn:
        while True:
            picked = claim(conn, worker=worker, lease_seconds=60)
            if picked is not None:
                time.sleep(hold)
                assert finish_successful(conn, picked.run_id, picked.attempt, "R" * 22, {})
                done += 1
                continue
            active = conn.execute("SELECT count(*) FROM public.earthx_run WHERE status IN ('accepted', 'running')")
            if active.fetchone() == (0,):
                return done
            time.sleep(0.005)
