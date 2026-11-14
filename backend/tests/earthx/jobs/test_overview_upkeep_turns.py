"""The upkeep of the pyramids on one worker at a time, against a real Postgres and a moto bucket (M5-38, migration 019).

Extension and sweep were right on every worker but ran N times; now a worker takes the turn of the task in the
database or skips its round. What is tested: the turn itself (one holder, a lease that is renewed and taken over, a gap
after a sweep), and two workers that start the same round at the same moment.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from earthx.jobs import overview_upkeep, overviews
from earthx.jobs.config import WorkerConfig
from earthx.jobs.worker import Supervisor
from earthx.objectstore.errors import ObjectStoreError
from earthx.objectstore.overviews import CHECKED_AT, OVERVIEW_PREFIX
from earthx.objectstore.results import Store
from tests.earthx.jobs.support import wait_until
from tests.earthx.jobs.test_overview_upkeep import (
    FAST,
    LONG_AGO,
    V1,
    V2,
    _checked_at,
    _confirmed_time,
    _keys,
    _metadata,
    _objects,
    _row,
    _state,
)

TURN = {"lease_seconds": 30.0, "gap_seconds": 0.0}


@pytest.fixture
def tile(tmp_path: Path) -> Path:
    path = tmp_path / "tile.tif"
    path.write_bytes(b"tile")
    return path


@pytest.fixture
def connect(db: psycopg.Connection) -> Iterator[Callable[[], psycopg.Connection]]:
    """Further autocommit connections to the same database, one per worker."""
    made: list[psycopg.Connection] = []

    def open_one() -> psycopg.Connection:
        made.append(psycopg.connect(autocommit=True))
        return made[-1]

    yield open_one
    for connection in made:
        connection.close()


def _config(tmp_path: Path, **overrides: float) -> WorkerConfig:
    """A worker's configuration whose turn is renewed before every object, so a lost turn shows at once."""
    values: dict[str, Any] = {"lease_seconds": 30.0, "heartbeat_seconds": 0.001, "cleanup_seconds": 3600.0}
    return WorkerConfig(**{**values, **overrides, "workdir": tmp_path})


def _together(*work: Callable[[], Any]) -> list[Any]:
    """Run each function in its own thread, all released at the same moment; their results in order."""
    barrier = threading.Barrier(len(work))
    results: list[Any] = [None] * len(work)
    errors: list[BaseException] = []

    def run(index: int) -> None:
        barrier.wait()
        try:
            results[index] = work[index]()
        except BaseException as error:  # noqa: BLE001 - handed to the test
            errors.append(error)

    threads = [threading.Thread(target=run, args=(index,)) for index in range(len(work))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert not any(thread.is_alive() for thread in threads), "a worker hung"
    if errors:
        raise errors[0]
    return results


def _counting(store: Store, name: str, *, delay: float = 0.0, when: Callable[..., bool] = lambda *a, **k: True) -> list:
    """Replace ``store.s3.<name>`` with one that records the workers' calls (and waits ``delay`` on each); the list of
    calls. The test's own calls, from the main thread, are not counted."""
    working = getattr(store.s3, name)
    calls: list = []
    lock = threading.Lock()

    def counted(*args: Any, **kwargs: Any) -> Any:
        if threading.current_thread() is not threading.main_thread() and when(*args, **kwargs):
            with lock:
                calls.append(args)
            time.sleep(delay)
        return working(*args, **kwargs)

    object.__setattr__(store.s3, name, counted)
    return calls


def _upkeep_row(db: psycopg.Connection, task: str) -> tuple:
    row = db.execute(
        "SELECT turn, worker, lease_until IS NOT NULL FROM public.earthx_overview_upkeep WHERE task = %s", (task,)
    ).fetchone()
    assert row is not None
    return row


class TestTheTurn:
    def test_the_first_worker_gets_the_turn_and_a_second_waits_until_it_ends(self, db: psycopg.Connection) -> None:
        first = overviews.take_turn(db, "extend", worker="w1", **TURN)
        assert first == overviews.Turn("extend", 1)
        assert overviews.take_turn(db, "extend", worker="w2", **TURN) is None
        assert overviews.end_turn(db, first)
        second = overviews.take_turn(db, "extend", worker="w2", **TURN)
        assert second == overviews.Turn("extend", 2)
        assert _upkeep_row(db, "extend") == (2, "w2", True)

    def test_the_two_tasks_do_not_block_each_other(self, db: psycopg.Connection) -> None:
        assert overviews.take_turn(db, "extend", worker="w1", **TURN) is not None
        assert overviews.take_turn(db, "sweep", worker="w2", **TURN) is not None

    def test_a_lease_that_ran_out_is_taken_over_and_the_old_turn_changes_nothing(self, db: psycopg.Connection) -> None:
        stale = overviews.take_turn(db, "extend", worker="w1", lease_seconds=0.2, gap_seconds=0)
        assert stale is not None
        assert overviews.take_turn(db, "extend", worker="w2", **TURN) is None
        time.sleep(0.3)
        fresh = overviews.take_turn(db, "extend", worker="w2", **TURN)
        assert fresh is not None and fresh.number == stale.number + 1
        assert not overviews.renew_turn(db, stale, 30.0), "a worker that woke up late cannot renew a newer turn"
        assert not overviews.end_turn(db, stale), "nor end it"
        assert _upkeep_row(db, "extend") == (fresh.number, "w2", True)

    def test_a_renewed_turn_is_not_taken_over(self, db: psycopg.Connection) -> None:
        turn = overviews.take_turn(db, "extend", worker="w1", lease_seconds=1.0, gap_seconds=0)
        assert turn is not None
        for _ in range(3):
            time.sleep(0.4)
            assert overviews.renew_turn(db, turn, 1.0)
        assert overviews.take_turn(db, "extend", worker="w2", **TURN) is None

    def test_an_ended_turn_is_not_renewed_or_ended_again(self, db: psycopg.Connection) -> None:
        turn = overviews.take_turn(db, "sweep", worker="w1", **TURN)
        assert turn is not None
        assert overviews.end_turn(db, turn)
        assert not overviews.renew_turn(db, turn, 30.0)
        assert not overviews.end_turn(db, turn)

    def test_no_turn_begins_within_the_gap_whoever_asks_and_one_begins_after_it(self, db: psycopg.Connection) -> None:
        turn = overviews.take_turn(db, "sweep", worker="w1", lease_seconds=30.0, gap_seconds=0.3)
        assert turn is not None and overviews.end_turn(db, turn)
        assert overviews.take_turn(db, "sweep", worker="w1", lease_seconds=30.0, gap_seconds=0.3) is None
        assert overviews.take_turn(db, "sweep", worker="w2", lease_seconds=30.0, gap_seconds=0.3) is None
        time.sleep(0.35)
        assert overviews.take_turn(db, "sweep", worker="w2", lease_seconds=30.0, gap_seconds=0.3) is not None

    def test_of_many_workers_asking_at_once_exactly_one_gets_the_first_turn(
        self, db: psycopg.Connection, connect: Callable[[], psycopg.Connection]
    ) -> None:
        connections = [connect() for _ in range(6)]
        turns = _together(
            *(
                lambda c=c, n=n: overviews.take_turn(c, "sweep", worker=f"w{n}", **TURN)
                for n, c in enumerate(connections)
            )
        )
        assert [turn for turn in turns if turn is not None] == [overviews.Turn("sweep", 1)]

    @pytest.mark.parametrize("task", ["", "build", "EXTEND", "sweep; DROP TABLE x", "cleanup"])
    def test_a_task_that_is_not_one_of_the_two_is_refused(self, db: psycopg.Connection, task: str) -> None:
        with pytest.raises(ValueError, match="extend, sweep"):
            overviews.take_turn(db, task, worker="w1", **TURN)

    @pytest.mark.parametrize(
        ("lease", "gap"), [(0.0, 0.0), (-1.0, 0.0), (float("nan"), 0.0), (30.0, -1.0), (30.0, float("nan"))]
    )
    def test_a_lease_that_is_not_positive_or_a_negative_gap_is_refused(
        self, db: psycopg.Connection, lease: float, gap: float
    ) -> None:
        with pytest.raises(ValueError, match="positive lease"):
            overviews.take_turn(db, "extend", worker="w1", lease_seconds=lease, gap_seconds=gap)

    def test_the_table_refuses_an_unknown_task_and_a_lease_without_a_worker(self, db: psycopg.Connection) -> None:
        with pytest.raises(psycopg.errors.CheckViolation):
            db.execute("INSERT INTO public.earthx_overview_upkeep (task, next_at) VALUES ('build', now())")
        with pytest.raises(psycopg.errors.CheckViolation):
            db.execute(
                "INSERT INTO public.earthx_overview_upkeep (task, lease_until, next_at) VALUES ('sweep', now(), now())"
            )


class TestTwoWorkersAtOnce:
    def test_two_workers_extending_at_once_copy_each_object_once(
        self, db: psycopg.Connection, store: Store, tile: Path, tmp_path: Path, connect: Callable[[], psycopg.Connection]
    ) -> None:
        _row(db, "dem", V1, checked="20 days", confirmed="1 hour")
        _objects(store, tile, "dem", V1)
        confirmed = _confirmed_time(db, "dem", V1)
        rewrites = _counting(store, "rewrite_object", delay=0.1)
        config = _config(tmp_path)
        a, b = connect(), connect()
        results = _together(
            lambda: overview_upkeep.extend_in_turn(a, store, {"dem"}, threading.Event(), worker="w1", config=config),
            lambda: overview_upkeep.extend_in_turn(b, store, {"dem"}, threading.Event(), worker="w2", config=config),
        )
        assert sorted(results, key=str) == [1, None], "one worker extends, the other skips its round"
        assert len(rewrites) == 2, "each object is copied once, not once per worker"
        assert _checked_at(db, "dem", V1) == confirmed
        assert {_metadata(store, key)[CHECKED_AT] for key in _keys(store)} == {confirmed.isoformat()}
        assert _upkeep_row(db, "extend")[2] is False, "the turn is ended, the next worker need not wait for its lease"

    def test_after_an_extension_the_next_worker_may_extend_at_once_what_it_knows(
        self, db: psycopg.Connection, store: Store, tile: Path, tmp_path: Path
    ) -> None:
        """A worker extends only the datasets it knows, so an extension does not count for the others."""
        _row(db, "dem", V1, checked="20 days", confirmed="1 hour")
        _row(db, "other", V2, checked="20 days", confirmed="1 hour")
        _objects(store, tile, "dem", V1)
        _objects(store, tile, "other", V2)
        config = _config(tmp_path)
        assert overview_upkeep.extend_in_turn(db, store, {"dem"}, threading.Event(), worker="w1", config=config) == 1
        assert overview_upkeep.extend_in_turn(db, store, {"other"}, threading.Event(), worker="w2", config=config) == 1

    def test_two_workers_sweeping_at_once_list_the_store_once(
        self, db: psycopg.Connection, store: Store, tile: Path, tmp_path: Path, connect: Callable[[], psycopg.Connection]
    ) -> None:
        _row(db, "dem", V1, checked="31 days")
        _objects(store, tile, "dem", V1)
        _objects(store, tile, "dem", V2)
        listings = _counting(store, "list_keys", delay=0.2, when=lambda prefix: prefix == OVERVIEW_PREFIX)
        config = _config(tmp_path)
        a, b = connect(), connect()
        results = _together(
            lambda: overview_upkeep.sweep_in_turn(a, store, worker="w1", config=config),
            lambda: overview_upkeep.sweep_in_turn(b, store, worker="w2", config=config),
        )
        assert sorted(results, key=str) == [None, overview_upkeep.Swept(expired=1, orphans=2)]
        assert len(listings) == 1, "the keys under overviews/ are listed once, not once per worker"
        assert _keys(store) == []
        assert _state(db, "dem", V1) == ("failed", "expired")

    def test_a_sweep_counts_for_the_other_workers_until_shortly_before_the_next_round(
        self, db: psycopg.Connection, store: Store, tmp_path: Path
    ) -> None:
        config = _config(tmp_path, cleanup_seconds=1.0)
        assert overview_upkeep.sweep_in_turn(db, store, worker="w1", config=config) == overview_upkeep.Swept()
        assert overview_upkeep.sweep_in_turn(db, store, worker="w2", config=config) is None
        time.sleep(config.cleanup_seconds * overview_upkeep.SWEEP_SHARE + 0.05)
        assert overview_upkeep.sweep_in_turn(db, store, worker="w2", config=config) == overview_upkeep.Swept()

    def test_two_supervisors_started_together_extend_once(
        self, db: psycopg.Connection, store: Store, tile: Path, tmp_path: Path
    ) -> None:
        _row(db, "dem", V1, checked="20 days", confirmed="1 hour")
        _objects(store, tile, "dem", V1)
        confirmed = _confirmed_time(db, "dem", V1)
        rewrites = _counting(store, "rewrite_object", delay=0.3)
        supervisors = [
            Supervisor(
                WorkerConfig(**{**FAST, "workdir": tmp_path / f"w{n}"}),
                store,
                name=f"w{n}",
                pyramids={"dem": ("dem.example.invalid",)},
            )
            for n in range(2)
        ]
        try:
            for supervisor in supervisors:
                supervisor.start()
            wait_until(lambda: _checked_at(db, "dem", V1) == confirmed, 15)
            time.sleep(1.0)
        finally:
            for supervisor in supervisors:
                supervisor.stop(30)
        assert len(rewrites) == 2, "each object is copied once, not once per worker"

    def test_two_supervisors_started_together_sweep_once(
        self, db: psycopg.Connection, store: Store, tile: Path, tmp_path: Path
    ) -> None:
        _row(db, "dem", V1, checked="31 days")
        _objects(store, tile, "dem", V1)
        listings = _counting(store, "list_keys", when=lambda prefix: prefix == OVERVIEW_PREFIX)
        supervisors = [
            Supervisor(WorkerConfig(**{**FAST, "workdir": tmp_path / f"w{n}"}), store, name=f"w{n}") for n in range(2)
        ]
        try:
            for supervisor in supervisors:
                supervisor.start()
            wait_until(lambda: _keys(store) == [], 15)
            time.sleep(1.0)
        finally:
            for supervisor in supervisors:
                supervisor.stop(30)
        assert len(listings) == 1
        assert _state(db, "dem", V1) == ("failed", "expired")


class TestASingleWorker:
    def test_a_long_step_before_the_sweep_does_not_make_the_next_round_miss_it(
        self, db: psycopg.Connection, store: Store, tmp_path: Path
    ) -> None:
        """The gap counts from the start of the worker's round: a clean-up that took long once shortens it."""
        config = _config(tmp_path, cleanup_seconds=1.0)
        took_long = time.monotonic() - 0.5
        assert overview_upkeep.sweep_in_turn(db, store, worker="w1", config=config, round_started=took_long) is not None
        time.sleep(0.45)
        next_round = time.monotonic()
        assert overview_upkeep.sweep_in_turn(db, store, worker="w1", config=config, round_started=next_round) is not None

    def test_a_round_that_started_in_the_future_or_long_ago_gives_no_negative_gap(
        self, db: psycopg.Connection, store: Store, tmp_path: Path
    ) -> None:
        config = _config(tmp_path, cleanup_seconds=1.0)
        long_ago = time.monotonic() - 10.0
        assert overview_upkeep.sweep_in_turn(db, store, worker="w1", config=config, round_started=long_ago) is not None
        assert overview_upkeep.sweep_in_turn(db, store, worker="w2", config=config, round_started=long_ago) is not None
        later = time.monotonic() + 10.0
        assert overview_upkeep.sweep_in_turn(db, store, worker="w3", config=config, round_started=later) is not None
        assert overview_upkeep.sweep_in_turn(db, store, worker="w4", config=config) is None


def _take_over(other: psycopg.Connection, task: str) -> None:
    """Another worker takes the turn, as if this one hung past its lease and the gap."""
    other.execute(
        "UPDATE public.earthx_overview_upkeep SET lease_until = now() - interval '1 second', "
        "next_at = now() - interval '1 second' WHERE task = %s",
        (task,),
    )
    assert overviews.take_turn(other, task, worker="w2", **TURN) is not None


class TestALostTurn:
    def test_a_worker_whose_turn_was_taken_over_stops_extending(
        self,
        db: psycopg.Connection,
        store: Store,
        tile: Path,
        tmp_path: Path,
        connect: Callable[[], psycopg.Connection],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _row(db, "dem", V1, checked="20 days", confirmed="1 hour")
        _objects(store, tile, "dem", V1)
        before = _checked_at(db, "dem", V1)
        other = connect()
        working = store.s3.rewrite_object
        rewrites: list[str] = []

        def rewrite_then_hang(key: str, **kwargs: Any) -> None:
            rewrites.append(key)
            working(key, **kwargs)
            if len(rewrites) == 1:
                # The worker hung past its lease, and another one took the turn.
                other.execute("UPDATE public.earthx_overview_upkeep SET lease_until = now() - interval '1 second'")
                assert overviews.take_turn(other, "extend", worker="w2", **TURN) is not None

        object.__setattr__(store.s3, "rewrite_object", rewrite_then_hang)
        with caplog.at_level(logging.WARNING, logger="earthx.jobs"):
            result = overview_upkeep.extend_in_turn(
                db, store, {"dem"}, threading.Event(), worker="w1", config=_config(tmp_path)
            )
        assert result is None
        assert len(rewrites) == 1, "nothing more is copied once the turn is gone"
        assert _checked_at(db, "dem", V1) == before, "the pyramid is left to the worker that has the turn now"
        assert _upkeep_row(db, "extend") == (2, "w2", True), "and its turn is not ended by the one that lost it"
        assert [r.getMessage() for r in caplog.records] == ["overview upkeep turn lost"]
        assert caplog.records[0].task == "extend"

    def test_a_worker_whose_turn_was_taken_over_stops_deleting(
        self, db: psycopg.Connection, store: Store, tile: Path, tmp_path: Path, connect: Callable[[], psycopg.Connection]
    ) -> None:
        _objects(store, tile, "gone", V1)
        _objects(store, tile, "gone", V2)
        other = connect()
        config = _config(tmp_path)
        listed = 0
        working = store.s3.list_keys

        def list_then_hang(prefix: str) -> Iterator[str]:
            nonlocal listed
            for key in working(prefix):
                listed += 1
                if listed == 2:
                    other.execute(
                        "UPDATE public.earthx_overview_upkeep "
                        "SET lease_until = now() - interval '1 second', next_at = now() - interval '1 second'"
                    )
                    assert overviews.take_turn(other, "sweep", worker="w2", lease_seconds=30.0, gap_seconds=0) is not None
                yield key

        object.__setattr__(store.s3, "list_keys", list_then_hang)
        assert overview_upkeep.sweep_in_turn(db, store, worker="w1", config=config) is None
        assert len(_keys(store)) == 4, "a sweep without its turn deletes nothing"

    def test_a_sweep_that_lost_its_turn_after_listing_deletes_no_orphan(
        self, db: psycopg.Connection, store: Store, tile: Path, tmp_path: Path, connect: Callable[[], psycopg.Connection]
    ) -> None:
        _objects(store, tile, "gone", V1)
        other = connect()
        working = store.s3.list_keys

        def list_then_hang(prefix: str) -> Iterator[str]:
            yield from working(prefix)
            if prefix == OVERVIEW_PREFIX:
                _take_over(other, "sweep")

        object.__setattr__(store.s3, "list_keys", list_then_hang)
        assert overview_upkeep.sweep_in_turn(db, store, worker="w1", config=_config(tmp_path)) is None
        assert len(_keys(store)) == 2

    def test_a_sweep_that_lost_its_turn_while_expiring_stops_and_leaves_the_rest_to_the_orphans(
        self, db: psycopg.Connection, store: Store, tile: Path, tmp_path: Path, connect: Callable[[], psycopg.Connection]
    ) -> None:
        _row(db, "dem", V1, checked="31 days")
        _objects(store, tile, "dem", V1)
        other = connect()
        working = store.s3.list_keys

        def list_then_hang(prefix: str) -> Iterator[str]:
            for n, key in enumerate(working(prefix)):
                if n == 1 and prefix != OVERVIEW_PREFIX:
                    _take_over(other, "sweep")
                yield key

        object.__setattr__(store.s3, "list_keys", list_then_hang)
        assert overview_upkeep.sweep_in_turn(db, store, worker="w1", config=_config(tmp_path)) is None
        assert _state(db, "dem", V1) == ("failed", "expired"), "the row is closed first, as before"
        assert len(_keys(store)) == 2, "nothing is deleted once the turn is gone; the next sweep takes them as orphans"
        object.__setattr__(store.s3, "list_keys", working)
        db.execute("UPDATE public.earthx_overview_upkeep SET lease_until = NULL, worker = NULL, next_at = now()")
        assert overview_upkeep.sweep_in_turn(db, store, worker="w1", config=_config(tmp_path)) == overview_upkeep.Swept(
            orphans=2
        )


class TestFailures:
    def test_a_store_that_fails_ends_the_turn_so_the_next_round_need_not_wait_for_the_lease(
        self, db: psycopg.Connection, store: Store, tile: Path, tmp_path: Path
    ) -> None:
        _row(db, "dem", V1, checked="20 days", confirmed="1 hour")
        _objects(store, tile, "dem", V1)

        def refuse(*args: Any, **kwargs: Any) -> None:
            raise ObjectStoreError("object store CopyObject failed")

        object.__setattr__(store.s3, "rewrite_object", refuse)
        config = _config(tmp_path)
        with pytest.raises(ObjectStoreError):
            overview_upkeep.extend_in_turn(db, store, {"dem"}, threading.Event(), worker="w1", config=config)
        assert _upkeep_row(db, "extend")[1:] == (None, False)
        assert overviews.take_turn(db, "extend", worker="w2", **TURN) is not None

    def test_a_failed_sweep_ends_the_turn_and_still_counts_for_the_round(
        self, db: psycopg.Connection, store: Store, tile: Path, tmp_path: Path
    ) -> None:
        """As before, the store is tried again by the next hourly round, not by another worker within this one."""
        _objects(store, tile, "gone", V1)

        def refuse(*args: Any, **kwargs: Any) -> None:
            raise ObjectStoreError("object store DeleteObjects failed")

        object.__setattr__(store.s3, "delete_objects", refuse)
        config = _config(tmp_path)
        with pytest.raises(ObjectStoreError):
            overview_upkeep.sweep_in_turn(db, store, worker="w1", config=config)
        assert _upkeep_row(db, "sweep")[1:] == (None, False)
        assert overview_upkeep.sweep_in_turn(db, store, worker="w2", config=config) is None

    def test_a_worker_whose_database_went_away_leaves_its_turn_to_run_out(
        self, db: psycopg.Connection, store: Store, tmp_path: Path, connect: Callable[[], psycopg.Connection]
    ) -> None:
        mine = connect()
        working = store.s3.list_keys

        def close_then_list(prefix: str) -> Iterator[str]:
            mine.close()
            return working(prefix)

        object.__setattr__(store.s3, "list_keys", close_then_list)
        with pytest.raises(psycopg.Error):
            overview_upkeep.sweep_in_turn(mine, store, worker="w1", config=_config(tmp_path, lease_seconds=0.2))
        assert _upkeep_row(db, "sweep")[1:] == ("w1", True), "the turn stays until its lease runs out"

    def test_a_prototype_source_is_still_never_extended(
        self, db: psycopg.Connection, store: Store, tile: Path, tmp_path: Path
    ) -> None:
        _row(db, "proto-dem", V1, checked="5 days", confirmed="1 hour")
        _objects(store, tile, "proto-dem", V1)
        config = _config(tmp_path)
        assert overview_upkeep.extend_in_turn(db, store, {"proto-dem"}, threading.Event(), worker="w1", config=config) == 0
        assert {_metadata(store, key)[CHECKED_AT] for key in _keys(store)} == {LONG_AGO.isoformat()}
