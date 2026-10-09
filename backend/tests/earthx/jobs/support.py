"""Orders and rows for the queue tests; every value is invented (hosts end in `.invalid`)."""

from __future__ import annotations

import copy
import secrets
import time
from collections.abc import Callable, Sequence
from typing import Any

import psycopg

from earthx.processing.operators import REGISTRY
from earthx.processing.recipe import Recipe, recipe_from_data
from tests.earthx.processing.recipes import SQUARE, recipe_data, resolved

HOST = "store.example.invalid"


def make_recipe(
    item: str = "ITEM_A",
    *,
    host: str = HOST,
    versioned: bool = True,
    steps: list[dict[str, Any]] | None = None,
    recipe_id: str | None = None,
) -> Recipe:
    """A recipe of the real registry (no steps: an export), read from `https://{host}/{item}/…`."""
    data = recipe_data(steps=copy.deepcopy(steps) if steps is not None else [])
    entries = [resolved(item, asset, href=f"https://{host}/{item}/{asset}.tif") for asset in ("red", "nir")]
    if not versioned:
        for entry in entries:
            entry["version"] = None
    data["inputs"][0]["groups"] = [[item]]
    data["inputs"][0]["resolved"] = entries
    data["aoi"] = copy.deepcopy(SQUARE)
    if recipe_id is not None:
        data["recipe_id"] = recipe_id
    return recipe_from_data(data, REGISTRY)


def add_run(
    conn: psycopg.Connection,
    *,
    status: str = "accepted",
    hosts: Sequence[str] = (HOST,),
    key: str | None = None,
    cacheable: bool = True,
    priority: int = 0,
    attempt: int = 0,
    max_attempts: int = 3,
    max_seconds: int = 600,
    lease_seconds: float | None = None,
    not_before_seconds: float = 0.0,
    expires_in: str = "7 days",
    result_id: str | None = None,
    created_ago: str = "0 seconds",
    jobs: int = 1,
) -> tuple[int, list[str]]:
    """A run with its own recipe and ``jobs`` jobs on it, written the way `submit` writes them, by SQL."""
    recipe_id = secrets.token_urlsafe(16)
    conn.execute("INSERT INTO public.earthx_recipe (recipe_id, body) VALUES (%s, '{}')", (recipe_id,))
    row = conn.execute(
        """
        INSERT INTO public.earthx_run
            (cache_key, cacheable, recipe_id, status, hosts, priority, attempt, max_attempts, max_seconds,
             lease_until, not_before, expires_at, result_id, created_at, worker)
        VALUES (%(key)s, %(cacheable)s, %(recipe)s, %(status)s, %(hosts)s, %(priority)s, %(attempt)s,
                %(max_attempts)s, %(max_seconds)s,
                CASE WHEN %(lease)s::float8 IS NULL THEN NULL
                     ELSE clock_timestamp() + make_interval(secs => %(lease)s::float8) END,
                clock_timestamp() + make_interval(secs => %(not_before)s::float8),
                clock_timestamp() + %(expires)s::interval, %(result_id)s,
                clock_timestamp() - %(created_ago)s::interval,
                CASE WHEN %(status)s = 'running' THEN 'test-worker' ELSE NULL END)
        RETURNING run_id
        """,
        {
            "key": key or "c1:" + secrets.token_hex(32),
            "cacheable": cacheable,
            "recipe": recipe_id,
            "status": status,
            "hosts": list(hosts),
            "priority": priority,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "max_seconds": max_seconds,
            "lease": lease_seconds,
            "not_before": not_before_seconds,
            "expires": expires_in,
            "result_id": result_id,
            "created_ago": created_ago,
        },
    ).fetchone()
    assert row is not None
    run_id = row[0]
    job_ids = []
    for _ in range(jobs):
        job_id = secrets.token_urlsafe(16)
        conn.execute(
            "INSERT INTO public.earthx_job (job_id, run_id, recipe_id) VALUES (%s, %s, %s)", (job_id, run_id, recipe_id)
        )
        job_ids.append(job_id)
    return run_id, job_ids


def run_row(conn: psycopg.Connection, run_id: int, *columns: str) -> tuple[Any, ...]:
    row = conn.execute(f"SELECT {', '.join(columns)} FROM public.earthx_run WHERE run_id = %s", (run_id,)).fetchone()
    assert row is not None
    return row


def status_of(conn: psycopg.Connection, run_id: int) -> str:
    return run_row(conn, run_id, "status")[0]


def wait_until(condition: Callable[[], bool], timeout: float = 20.0, interval: float = 0.02) -> None:
    """Poll until ``condition()`` holds; the failure says what was waited for."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(interval)
    raise AssertionError(f"not true within {timeout} s: {getattr(condition, '__name__', condition)}")


def most_at_once(conn: psycopg.Connection) -> int:
    """The most runs that ran at the same time, from the times the rows themselves recorded."""
    rows = conn.execute("SELECT started_at, finished_at FROM public.earthx_run").fetchall()
    events = sorted([(start, 1) for start, _ in rows] + [(end, -1) for _, end in rows], key=lambda e: (e[0], e[1]))
    current = best = 0
    for _, step in events:
        current += step
        best = max(best, current)
    return best
