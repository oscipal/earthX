"""The queue's state changes against a real Postgres (adr/0013 §5.2, §5.4–§5.6, §8 points 1–4, 13).

`pytest.mark.parametrize` carries one case per row of the table in adr/0013 §5.6.
"""

from __future__ import annotations

import json
import multiprocessing
import threading
import time
from collections.abc import Callable
from datetime import timedelta

import psycopg
import pytest

from earthx.gateway import UpstreamError, UpstreamTimeout, UpstreamUnreachable
from earthx.jobs import queue
from earthx.jobs.queue import (
    CLAIM_LOCK_KEY,
    CLAIM_SQL,
    PROGRESS_CHANNEL,
    RETRYABLE,
    claim,
    finish_cancelled,
    finish_failed,
    finish_successful,
    heartbeat,
    release,
    requeue_expired,
    write_progress,
)
from earthx.processing import failure_kind
from earthx.processing.errors import (
    AoiOutsideInputs,
    GridMismatch,
    RecipeInvalid,
    ScalingMismatch,
    UnknownOperator,
    UnsupportedRecipe,
)
from earthx.readers import AssetRejected
from tests.earthx.jobs import claimers
from tests.earthx.jobs.support import add_run, run_row, status_of, wait_until


def _pick(conn: psycopg.Connection, worker: str = "w1", lease: float = 60.0):
    return claim(conn, worker=worker, lease_seconds=lease)


def _lease_runs_out(conn: psycopg.Connection, run_id: int) -> None:
    conn.execute(
        "UPDATE public.earthx_run SET lease_until = clock_timestamp() - interval '1 second' WHERE run_id = %s",
        (run_id,),
    )


class TestClaim:
    def test_nothing_waiting_gives_nothing(self, db: psycopg.Connection) -> None:
        assert _pick(db) is None

    def test_the_run_is_owned_by_the_worker_with_a_lease_and_its_recipe(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db)
        db.execute("UPDATE public.earthx_recipe SET body = '{\"recipe_version\": 1}'")
        picked = _pick(db, "worker-7", lease=60)
        assert picked is not None
        assert (picked.run_id, picked.attempt, picked.max_seconds, picked.recipe) == (
            run_id,
            1,
            600,
            {"recipe_version": 1},
        )
        status, worker, attempt, lease_left, started = run_row(
            db,
            run_id,
            "status",
            "worker",
            "attempt",
            "extract(epoch FROM lease_until - clock_timestamp())",
            "started_at IS NOT NULL",
        )
        assert (status, worker, attempt, started) == ("running", "worker-7", 1, True)
        assert 55 < lease_left <= 60

    def test_a_run_is_picked_up_once(self, db: psycopg.Connection) -> None:
        add_run(db)
        assert _pick(db) is not None
        assert _pick(db) is None

    def test_priority_first_then_the_oldest(self, db: psycopg.Connection) -> None:
        old, _ = add_run(db, hosts=["a"], created_ago="3 hours")
        newer, _ = add_run(db, hosts=["b"], created_ago="1 hour")
        urgent, _ = add_run(db, hosts=["c"], priority=5, created_ago="1 minute")
        order = [_pick(db).run_id for _ in range(3)]  # type: ignore[union-attr]
        assert order == [urgent, old, newer]

    def test_a_run_that_waits_for_its_backoff_is_not_picked_up(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db, not_before_seconds=3600)
        assert _pick(db) is None
        db.execute("UPDATE public.earthx_run SET not_before = clock_timestamp() - interval '1 second'")
        picked = _pick(db)
        assert picked is not None and picked.run_id == run_id

    def test_only_the_pools_the_worker_serves(self, db: psycopg.Connection) -> None:
        db.execute("INSERT INTO public.earthx_recipe (recipe_id, body) VALUES ('p' || repeat('x', 21), '{}')")
        db.execute(
            "INSERT INTO public.earthx_run (cache_key, cacheable, recipe_id, status, pool, hosts, max_seconds, expires_at)"
            " VALUES ('c1:p', true, 'p' || repeat('x', 21), 'accepted', 'gpu', ARRAY['a'], 600, now() + interval '1 day')"
        )
        assert _pick(db) is None
        assert claim(db, worker="w", lease_seconds=60, pools=("gpu",)) is not None

    def test_runs_that_are_not_waiting_are_left_alone(self, db: psycopg.Connection) -> None:
        for status in ("running", "successful", "failed", "dismissed"):
            add_run(db, status=status)
        assert _pick(db) is None


class TestCapAndLimitPerHost:
    def test_with_the_cap_full_nothing_is_picked_up(self, db: psycopg.Connection) -> None:
        db.execute("UPDATE public.earthx_job_limits SET global_cap = 2")
        add_run(db, status="running", hosts=["a"])
        add_run(db, status="running", hosts=["b"])
        add_run(db, hosts=["c"])
        assert _pick(db) is None

    def test_a_finished_run_frees_a_place(self, db: psycopg.Connection) -> None:
        db.execute("UPDATE public.earthx_job_limits SET global_cap = 1")
        add_run(db, hosts=["a"])
        add_run(db, hosts=["b"])
        first = _pick(db)
        assert first is not None and _pick(db) is None
        assert finish_successful(db, first.run_id, first.attempt, "R" * 22, {})
        assert _pick(db) is not None

    def test_a_host_at_its_limit_is_skipped_and_the_next_run_goes_first(self, db: psycopg.Connection) -> None:
        add_run(db, status="running", hosts=["a"])
        add_run(db, status="running", hosts=["a"])
        blocked, _ = add_run(db, hosts=["a"], created_ago="2 hours")
        free, _ = add_run(db, hosts=["b"], created_ago="1 hour")
        picked = _pick(db)
        assert picked is not None and picked.run_id == free
        assert status_of(db, blocked) == "accepted"
        assert _pick(db) is None

    def test_a_run_over_several_hosts_needs_room_on_each_and_counts_for_each(self, db: psycopg.Connection) -> None:
        add_run(db, status="running", hosts=["a", "b"])
        add_run(db, status="running", hosts=["a"])
        add_run(db, hosts=["a", "c"])  # a is full
        only_c, _ = add_run(db, hosts=["c"])
        picked = _pick(db)
        assert picked is not None and picked.run_id == only_c

    def test_the_numbers_are_read_from_the_row_at_every_pickup(self, db: psycopg.Connection) -> None:
        add_run(db, status="running", hosts=["a"])
        add_run(db, status="running", hosts=["a"])
        waiting, _ = add_run(db, hosts=["a"])
        assert _pick(db) is None
        db.execute("UPDATE public.earthx_job_limits SET host_cap = 3")
        picked = _pick(db)
        assert picked is not None and picked.run_id == waiting


def _blocked_on_the_lock() -> str:
    return "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"


def _one_statement_variant() -> str:
    """The pick-up with the lock inside the statement that counts: what adr/0013 §5.2 warns against."""
    variant = CLAIM_SQL.replace(
        "WITH running AS (", "WITH lock AS (SELECT pg_advisory_xact_lock(%(key)s) AS l), running AS (", 1
    ).replace(
        "    FROM public.earthx_run r\n    WHERE r.status = 'accepted'",
        "    FROM public.earthx_run r, lock\n    WHERE r.status = 'accepted'",
        1,
    )
    assert variant.count("lock") > CLAIM_SQL.count("lock"), (
        "the variant was not built; the counter-sample would prove nothing"
    )
    return variant


class TestTheCapHoldsWhenWorkersPickUpAtTheSameTime:
    """Adr/0013 §8 point 1: the lock in a statement of its own, and READ COMMITTED, are what hold it."""

    def _hold_a_pickup_open_and_start(self, db: psycopg.Connection, second: Callable[[psycopg.Connection], object]):
        """B picks up and has not committed; A starts its pick-up and waits on the lock; then B commits."""
        results: list[object] = []
        with psycopg.connect(autocommit=True) as holder, psycopg.connect(autocommit=True) as late:

            def run_second() -> None:
                results.append(second(late))

            thread = threading.Thread(target=run_second)
            with holder.transaction():
                holder.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                holder.execute("SELECT pg_advisory_xact_lock(%(key)s)", {"key": CLAIM_LOCK_KEY})
                row = holder.execute(CLAIM_SQL, {"pools": ["default"], "worker": "holder", "lease": 60.0}).fetchone()
                assert row is not None
                thread.start()
                wait_until(lambda: db.execute(_blocked_on_the_lock()).fetchone() == (1,))
            thread.join(20)
            assert not thread.is_alive()
        return results[0]

    def _two_waiting(self, db: psycopg.Connection) -> None:
        db.execute("UPDATE public.earthx_job_limits SET global_cap = 1")
        add_run(db, hosts=["a"])
        add_run(db, hosts=["b"])

    def test_the_second_pickup_waits_for_the_first_and_then_sees_it(self, db: psycopg.Connection) -> None:
        self._two_waiting(db)
        result = self._hold_a_pickup_open_and_start(db, lambda conn: _pick(conn, "late"))
        assert result is None
        assert db.execute("SELECT count(*) FROM public.earthx_run WHERE status = 'running'").fetchone() == (1,)

    def test_a_connection_that_defaults_to_repeatable_read_is_still_held_to_the_cap(
        self, db: psycopg.Connection
    ) -> None:
        self._two_waiting(db)

        def late(conn: psycopg.Connection):
            conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            return _pick(conn, "late")

        assert self._hold_a_pickup_open_and_start(db, late) is None
        assert db.execute("SELECT count(*) FROM public.earthx_run WHERE status = 'running'").fetchone() == (1,)

    def test_counter_sample_with_lock_and_count_in_one_statement_the_cap_is_broken(
        self, db: psycopg.Connection
    ) -> None:
        self._two_waiting(db)

        def one_statement(conn: psycopg.Connection):
            with conn.transaction():
                return conn.execute(
                    _one_statement_variant(),
                    {"key": CLAIM_LOCK_KEY, "pools": ["default"], "worker": "late", "lease": 60.0},
                ).fetchone()

        assert self._hold_a_pickup_open_and_start(db, one_statement) is not None
        assert db.execute("SELECT count(*) FROM public.earthx_run WHERE status = 'running'").fetchone() == (2,), (
            "the variant that adr/0013 §5.2 warns against must exceed the cap, or this test checks nothing"
        )

    def test_eight_processes_never_run_more_than_the_cap(
        self, db: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, runs = 3, 36
        db.execute("UPDATE public.earthx_job_limits SET global_cap = %s, host_cap = 8", (cap,))
        for index in range(runs):
            add_run(db, hosts=[f"host{index % 5}"], created_ago=f"{runs - index} seconds")
        context = multiprocessing.get_context("spawn")
        with context.Pool(8) as pool:
            counts = pool.starmap(claimers.claim_until_empty, [(f"proc{index}", 0.05) for index in range(8)])
        assert sum(counts) == runs
        assert db.execute("SELECT count(*) FROM public.earthx_run WHERE status = 'successful'").fetchone() == (runs,)
        assert _most_at_once(db) == cap, "the cap is held and reached"

    def test_eight_processes_never_run_more_than_the_limit_per_host(self, db: psycopg.Connection) -> None:
        db.execute("UPDATE public.earthx_job_limits SET global_cap = 8, host_cap = 2")
        for index in range(24):
            add_run(db, hosts=["only.example.invalid"], created_ago=f"{24 - index} seconds")
        with multiprocessing.get_context("spawn").Pool(8) as pool:
            counts = pool.starmap(claimers.claim_until_empty, [(f"proc{index}", 0.05) for index in range(8)])
        assert sum(counts) == 24
        assert _most_at_once(db) == 2


def _most_at_once(conn: psycopg.Connection) -> int:
    """The most runs that ran at the same time, from the times the rows themselves recorded."""
    rows = conn.execute("SELECT started_at, finished_at FROM public.earthx_run").fetchall()
    events = sorted([(start, 1) for start, _ in rows] + [(end, -1) for _, end in rows], key=lambda e: (e[0], e[1]))
    current = best = 0
    for _, step in events:
        current += step
        best = max(best, current)
    return best


class TestAttemptsAndShielding:
    def test_an_attempt_that_lost_its_run_cannot_finish_or_touch_it(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db)
        first = _pick(db, "w1")
        assert first is not None and first.attempt == 1
        _lease_runs_out(db, run_id)
        assert requeue_expired(db, backoff_seconds=0) == 1
        second = _pick(db, "w2")
        assert second is not None and second.attempt == 2
        # The first attempt wakes up and tries everything it may try:
        assert finish_successful(db, run_id, 1, "OLD" + "x" * 19, {"from": "first"}) is False
        assert finish_failed(db, run_id, 1, "unknown") is None
        assert finish_cancelled(db, run_id, 1) is None
        assert heartbeat(db, run_id, 1, 60) is None
        assert write_progress(db, run_id, 1, 50) is None
        assert release(db, run_id, 1) is None
        assert run_row(db, run_id, "status", "attempt", "worker", "result_id", "progress") == (
            "running",
            2,
            "w2",
            None,
            0,
        )
        assert finish_successful(db, run_id, 2, "R" * 22, {"from": "second"}) is True
        assert run_row(db, run_id, "status", "result_id", "result") == ("successful", "R" * 22, {"from": "second"})

    def test_a_finished_run_cannot_be_finished_again(self, db: psycopg.Connection) -> None:
        add_run(db)
        picked = _pick(db)
        assert picked is not None
        assert finish_successful(db, picked.run_id, picked.attempt, "R" * 22, {})
        assert finish_successful(db, picked.run_id, picked.attempt, "S" * 22, {}) is False
        assert finish_failed(db, picked.run_id, picked.attempt, "unknown") is None

    def test_the_heartbeat_renews_the_lease_and_reports_the_cancel_flag(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db)
        picked = _pick(db, lease=2)
        assert picked is not None
        assert heartbeat(db, run_id, picked.attempt, 60) is False
        assert run_row(db, run_id, "extract(epoch FROM lease_until - clock_timestamp())")[0] > 50
        db.execute("UPDATE public.earthx_run SET cancel_requested = true")
        assert heartbeat(db, run_id, picked.attempt, 60) is True

    def test_success_records_the_result_and_the_expiry_seven_days_on(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db, expires_in="1 hour")
        picked = _pick(db)
        assert picked is not None
        assert finish_successful(db, run_id, picked.attempt, "R" * 22, {"blocks": 4})
        status, progress, worker, lease, left, finished, kind = run_row(
            db,
            run_id,
            "status",
            "progress",
            "worker",
            "lease_until",
            "extract(epoch FROM expires_at - clock_timestamp())",
            "finished_at IS NOT NULL",
            "error_kind",
        )
        assert (status, progress, worker, lease, finished, kind) == ("successful", 100, None, None, True, None)
        assert timedelta(days=7).total_seconds() - 5 < left <= timedelta(days=7).total_seconds()


@pytest.mark.parametrize(
    ("error", "retries"),
    [
        (UpstreamTimeout("slow"), True),
        (UpstreamError(503), True),
        (UpstreamError(500), True),
        (UpstreamError(404), False),
        (UpstreamError(403), False),
        (UpstreamError(429), False),
        (UpstreamUnreachable("refused"), False),
        (AssetRejected("a key"), False),
        (RecipeInvalid("a field"), False),
        (UnknownOperator("an operator"), False),
        (UnsupportedRecipe("more than one item"), False),
        (ScalingMismatch("a band"), False),
        (GridMismatch("two grids"), False),
        (AoiOutsideInputs("outside"), False),
        (MemoryError(), False),
        (KeyError("anything else"), False),
    ],
    ids=lambda value: type(value).__name__ if isinstance(value, BaseException) else str(value),
)
def test_the_table_of_adr_0013_5_6_error_by_error(db: psycopg.Connection, error: BaseException, retries: bool) -> None:
    """The table in §5.6, row by row: what the child names, and whether the run tries again."""
    run_id, _ = add_run(db)
    picked = _pick(db)
    assert picked is not None
    kind = failure_kind(error)
    assert (kind in RETRYABLE) is retries
    assert finish_failed(db, run_id, picked.attempt, kind) == ("accepted" if retries else "failed")
    status, error_kind, finished = run_row(db, run_id, "status", "error_kind", "finished_at IS NOT NULL")
    assert (status, error_kind, finished) == ("accepted" if retries else "failed", kind, not retries)


class TestRetry:
    @pytest.mark.parametrize("kind", sorted(RETRYABLE))
    def test_a_retryable_kind_goes_back_to_the_queue_after_the_backoff(self, db: psycopg.Connection, kind: str) -> None:
        run_id, _ = add_run(db)
        picked = _pick(db)
        assert picked is not None
        assert finish_failed(db, run_id, picked.attempt, kind) == "accepted"
        status, worker, lease, wait, progress, finished = run_row(
            db,
            run_id,
            "status",
            "worker",
            "lease_until",
            "extract(epoch FROM not_before - clock_timestamp())",
            "progress",
            "finished_at",
        )
        assert (status, worker, lease, progress, finished) == ("accepted", None, None, 0, None)
        assert 24 <= wait <= 36, "30 s ± 20 % after the first attempt"
        assert _pick(db) is None, "not before the backoff is over"

    def test_each_attempt_waits_twice_as_long(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db)
        waits = []
        for _ in range(2):
            db.execute("UPDATE public.earthx_run SET not_before = clock_timestamp()")
            picked = _pick(db)
            assert picked is not None
            finish_failed(db, run_id, picked.attempt, "source_5xx")
            waits.append(run_row(db, run_id, "extract(epoch FROM not_before - clock_timestamp())")[0])
        assert 24 <= waits[0] <= 36 and 48 <= waits[1] <= 72

    def test_the_wait_has_jitter(self, db: psycopg.Connection) -> None:
        waits = set()
        for _ in range(12):
            run_id, _ = add_run(db)
            picked = _pick(db)
            assert picked is not None
            finish_failed(db, run_id, picked.attempt, "source_timeout")
            waits.add(round(run_row(db, run_id, "extract(epoch FROM not_before - clock_timestamp())")[0], 1))
            db.execute("UPDATE public.earthx_run SET status = 'dismissed' WHERE run_id = %s", (run_id,))
        assert len(waits) > 3

    def test_at_most_three_attempts(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db)
        for attempt in (1, 2, 3):
            db.execute("UPDATE public.earthx_run SET not_before = clock_timestamp()")
            picked = _pick(db)
            assert picked is not None and picked.attempt == attempt
            status = finish_failed(db, run_id, attempt, "source_5xx")
            assert status == ("accepted" if attempt < 3 else "failed")
        assert run_row(db, run_id, "status", "error_kind") == ("failed", "source_5xx")

    def test_a_kind_nobody_named_fails_at_once(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db)
        picked = _pick(db)
        assert picked is not None
        assert finish_failed(db, run_id, picked.attempt, "never_heard_of_it") == "failed"

    def test_a_failure_expires_seven_days_after_it_ended(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db, expires_in="1 hour")
        picked = _pick(db)
        assert picked is not None
        finish_failed(db, run_id, picked.attempt, "unknown")
        left = run_row(db, run_id, "extract(epoch FROM expires_at - clock_timestamp())")[0]
        assert timedelta(days=7).total_seconds() - 5 < left <= timedelta(days=7).total_seconds()


class TestSweepingLeases:
    def test_a_run_whose_lease_ran_out_is_queued_again(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db, status="running", attempt=1, lease_seconds=-5)
        assert requeue_expired(db, backoff_seconds=0) == 1
        assert run_row(db, run_id, "status", "error_kind", "worker") == ("accepted", "lease_lost", None)

    def test_a_run_out_of_attempts_fails_with_the_lost_lease(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db, status="running", attempt=3, lease_seconds=-5)
        assert requeue_expired(db) == 1
        assert run_row(db, run_id, "status", "error_kind") == ("failed", "lease_lost")

    def test_a_run_with_time_left_is_left_alone(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db, status="running", attempt=1, lease_seconds=30)
        assert requeue_expired(db) == 0
        assert status_of(db, run_id) == "running"

    def test_two_sweepers_at_the_same_time_handle_each_run_once(self, db: psycopg.Connection) -> None:
        for _ in range(10):
            add_run(db, status="running", attempt=1, lease_seconds=-5)
        barrier = threading.Barrier(2)
        handled: list[int] = []

        def sweep() -> None:
            with psycopg.connect(autocommit=True) as conn:
                barrier.wait()
                handled.append(requeue_expired(conn, backoff_seconds=0))

        threads = [threading.Thread(target=sweep) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(20)
        assert sum(handled) == 10
        assert db.execute(
            "SELECT count(*) FROM public.earthx_run WHERE attempt = 1 AND status = 'accepted'"
        ).fetchone() == (10,)


class TestReleaseAtShutdown:
    def test_the_run_goes_back_at_once_without_waiting_for_a_backoff(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db)
        picked = _pick(db)
        assert picked is not None
        assert release(db, run_id, picked.attempt) == "accepted"
        assert run_row(db, run_id, "status", "worker", "lease_until") == ("accepted", None, None)
        assert _pick(db, "other") is not None

    def test_a_run_out_of_attempts_fails_instead(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db, attempt=2)
        picked = _pick(db)
        assert picked is not None and picked.attempt == 3
        assert release(db, run_id, 3) == "failed"


class TestCancelled:
    def test_with_no_live_job_the_run_is_dismissed(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db, jobs=2)
        picked = _pick(db)
        assert picked is not None
        db.execute("UPDATE public.earthx_job SET dismissed = true")
        assert finish_cancelled(db, run_id, picked.attempt) == "dismissed"
        assert run_row(db, run_id, "status", "worker", "finished_at IS NOT NULL") == ("dismissed", None, True)

    def test_a_job_that_attached_in_the_meantime_gets_the_run_queued_again(self, db: psycopg.Connection) -> None:
        run_id, (first, _second) = add_run(db, jobs=2)
        picked = _pick(db)
        assert picked is not None
        db.execute("UPDATE public.earthx_job SET dismissed = true WHERE job_id = %s", (first,))
        db.execute("UPDATE public.earthx_run SET cancel_requested = true")
        assert finish_cancelled(db, run_id, picked.attempt) == "accepted"
        assert run_row(db, run_id, "status", "cancel_requested", "progress") == ("accepted", False, 0)
        assert _pick(db, "next") is not None


class TestNotifications:
    def _listen(self) -> psycopg.Connection:
        listener = psycopg.connect(autocommit=True)
        listener.execute(f"LISTEN {PROGRESS_CHANNEL}")
        return listener

    def _payloads(self, listener: psycopg.Connection) -> list[dict]:
        return [json.loads(n.payload) for n in listener.notifies(timeout=0.3)]

    def test_every_change_of_state_and_every_progress_write_notifies_with_numbers_only(
        self, db: psycopg.Connection
    ) -> None:
        run_id, _ = add_run(db)
        with self._listen() as listener:
            picked = _pick(db)
            assert picked is not None
            write_progress(db, run_id, picked.attempt, 40)
            finish_successful(db, run_id, picked.attempt, "R" * 22, {})
            payloads = self._payloads(listener)
        assert payloads == [
            {"run": run_id, "p": 0, "s": "running"},
            {"run": run_id, "p": 40, "s": "running"},
            {"run": run_id, "p": 100, "s": "successful"},
        ]

    def test_a_rolled_back_change_sends_nothing(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db, status="running", attempt=1)
        with self._listen() as listener:
            with pytest.raises(RuntimeError), db.transaction():
                write_progress(db, run_id, 1, 70)
                raise RuntimeError("rolled back")
            assert self._payloads(listener) == []
        assert run_row(db, run_id, "progress") == (0,)

    def test_the_progress_stays_below_100_until_the_run_succeeds(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db, status="running", attempt=1)
        write_progress(db, run_id, 1, 250)
        assert run_row(db, run_id, "progress") == (99,)
        write_progress(db, run_id, 1, -5)
        assert run_row(db, run_id, "progress") == (0,)

    def test_a_retry_wakes_the_workers(self, db: psycopg.Connection) -> None:
        run_id, _ = add_run(db)
        picked = _pick(db)
        assert picked is not None
        with psycopg.connect(autocommit=True) as listener:
            listener.execute(f"LISTEN {queue.WAKE_CHANNEL}")
            finish_failed(db, run_id, picked.attempt, "source_5xx")
            assert len(list(listener.notifies(timeout=0.3, stop_after=1))) == 1


def test_wait_helper_reports_what_was_waited_for() -> None:
    def never() -> bool:
        return False

    started = time.monotonic()
    with pytest.raises(AssertionError, match="never"):
        wait_until(never, timeout=0.1)
    assert time.monotonic() - started < 2
