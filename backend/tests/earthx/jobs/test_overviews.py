"""The state of the overview pyramids: claim, lease, finish, retry, one build per host, what is missing
(M5-30b part 8b, adr/0032 §5.2, §8.2)."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from earthx.jobs.config import WorkerConfig
from earthx.jobs.overviews import (
    MAX_ATTEMPTS,
    Build,
    claim,
    finish_failed,
    finish_ready,
    heartbeat,
    request_missing,
    write_progress,
)
from earthx.jobs.worker import Supervisor
from earthx.objectstore.results import Store
from tests.earthx.jobs.support import add_run, wait_until

HOSTS = {"dem": ("dem.example.invalid",), "land": ("land.example.invalid",), "also-dem": ("dem.example.invalid",)}
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def _request(db: psycopg.Connection, dataset_id: str, source_version: str, *, age: str = "0 seconds") -> str:
    row = db.execute(
        """
        INSERT INTO public.earthx_overview_request (dataset_id, source_version, requested_at)
        VALUES (%s, %s, clock_timestamp() - %s::interval) RETURNING version
        """,
        (dataset_id, source_version, age),
    ).fetchone()
    assert row is not None
    return row[0]


def _row(db: psycopg.Connection, dataset_id: str, version: str) -> dict:
    cursor = db.execute(
        "SELECT * FROM public.earthx_overview WHERE dataset_id = %s AND version = %s", (dataset_id, version)
    )
    names = [column.name for column in cursor.description]
    row = cursor.fetchone()
    assert row is not None
    return dict(zip(names, row, strict=True))


def _claim(db: psycopg.Connection, hosts: dict | None = None) -> Build | None:
    return claim(db, worker="w1", lease_seconds=60, hosts=HOSTS if hosts is None else hosts)


def _age(
    db: psycopg.Connection, dataset_id: str, version: str, *, updated: str = "2 hours", lease: str | None = None
) -> None:
    db.execute(
        """
        UPDATE public.earthx_overview SET updated_at = clock_timestamp() - %s::interval,
            lease_until = CASE WHEN %s::text IS NULL THEN lease_until ELSE clock_timestamp() - %s::interval END
        WHERE dataset_id = %s AND version = %s
        """,
        (updated, lease, lease, dataset_id, version),
    )


def _fail(db: psycopg.Connection, build: Build, kind: str) -> None:
    assert finish_failed(db, build, kind)


class TestClaim:
    def test_nothing_is_requested_nothing_is_claimed(self, db: psycopg.Connection) -> None:
        assert _claim(db) is None

    def test_a_request_is_claimed_with_its_version_and_its_hosts_and_a_lease(self, db: psycopg.Connection) -> None:
        version = _request(db, "dem", '"etag-1"')
        build = _claim(db)
        assert build == Build("dem", version, '"etag-1"', 1, ("dem.example.invalid",))
        row = _row(db, "dem", version)
        assert (row["status"], row["attempts"], row["worker"], row["progress"], row["hosts"]) == (
            "building",
            1,
            "w1",
            0,
            ["dem.example.invalid"],
        )
        remaining = db.execute(
            "SELECT lease_until - clock_timestamp() FROM public.earthx_overview WHERE dataset_id = 'dem'"
        ).fetchone()
        assert remaining is not None and timedelta(seconds=50) < remaining[0] <= timedelta(seconds=60)

    def test_a_request_is_claimed_once(self, db: psycopg.Connection) -> None:
        _request(db, "dem", "v1")
        assert _claim(db) is not None
        assert _claim(db) is None

    def test_only_the_latest_request_of_a_dataset_is_built(self, db: psycopg.Connection) -> None:
        _request(db, "dem", "old", age="2 days")
        new = _request(db, "dem", "new", age="1 hour")
        build = _claim(db)
        assert build is not None and build.version == new and build.source_version == "new"
        assert _claim(db) is None, "the older version is never built any more"

    def test_a_dataset_this_worker_does_not_know_is_left_alone(self, db: psycopg.Connection) -> None:
        _request(db, "stranger", "v1")
        assert _claim(db) is None
        assert db.execute("SELECT count(*) FROM public.earthx_overview").fetchone() == (0,)

    def test_the_oldest_request_goes_first(self, db: psycopg.Connection) -> None:
        _request(db, "land", "v1", age="1 minute")
        _request(db, "dem", "v1", age="1 hour")
        first = _claim(db)
        assert first is not None and first.dataset_id == "dem"

    def test_a_request_whose_pyramid_is_ready_is_not_built_again(self, db: psycopg.Connection) -> None:
        version = _request(db, "dem", "v1")
        build = _claim(db)
        assert build is not None and finish_ready(db, build, checked_at=NOW, base_hashes={})
        assert _claim(db) is None
        assert _row(db, "dem", version)["status"] == "ready"


class TestOneBuildPerHost:
    def test_a_second_dataset_on_the_same_host_waits_for_the_first(self, db: psycopg.Connection) -> None:
        _request(db, "dem", "v1", age="1 hour")
        _request(db, "also-dem", "v1", age="1 minute")
        first = _claim(db)
        assert first is not None and first.dataset_id == "dem"
        assert _claim(db) is None
        assert finish_ready(db, first, checked_at=NOW, base_hashes={})
        second = _claim(db)
        assert second is not None and second.dataset_id == "also-dem"

    def test_a_failed_build_frees_the_host(self, db: psycopg.Connection) -> None:
        _request(db, "dem", "v1", age="1 hour")
        _request(db, "also-dem", "v1", age="1 minute")
        first = _claim(db)
        assert first is not None
        _fail(db, first, "unknown")
        second = _claim(db)
        assert second is not None and second.dataset_id == "also-dem"

    def test_datasets_on_other_hosts_build_side_by_side(self, db: psycopg.Connection) -> None:
        _request(db, "dem", "v1")
        _request(db, "land", "v1")
        assert {b.dataset_id for b in (_claim(db), _claim(db)) if b is not None} == {"dem", "land"}

    def test_a_dataset_without_a_host_is_not_held_back(self, db: psycopg.Connection) -> None:
        _request(db, "local", "v1")
        _request(db, "local-too", "v1")
        hosts = {"local": (), "local-too": ()}
        assert {b.dataset_id for b in (_claim(db, hosts), _claim(db, hosts)) if b is not None} == {"local", "local-too"}

    def test_two_workers_at_the_same_moment_start_one_build(self, db: psycopg.Connection) -> None:
        _request(db, "dem", "v1")
        _request(db, "also-dem", "v1")
        picked: list[Build | None] = []
        barrier = threading.Barrier(8)

        def work(name: str) -> None:
            with psycopg.connect(autocommit=True) as conn:
                barrier.wait()
                picked.append(claim(conn, worker=name, lease_seconds=60, hosts=HOSTS))

        threads = [threading.Thread(target=work, args=(f"w{n}",)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len([build for build in picked if build is not None]) == 1
        assert db.execute("SELECT count(*) FROM public.earthx_overview WHERE status = 'building'").fetchone() == (1,)


class TestLease:
    def test_a_heartbeat_renews_the_lease_of_the_attempt_that_owns_it(self, db: psycopg.Connection) -> None:
        version = _request(db, "dem", "v1")
        build = _claim(db)
        assert build is not None
        _age(db, "dem", version, lease="0 seconds")
        assert heartbeat(db, build, 120)
        remaining = db.execute("SELECT lease_until - clock_timestamp() FROM public.earthx_overview").fetchone()
        assert remaining is not None and remaining[0] > timedelta(seconds=100)

    def test_another_attempt_changes_nothing(self, db: psycopg.Connection) -> None:
        version = _request(db, "dem", "v1")
        build = _claim(db)
        assert build is not None
        stale = Build(build.dataset_id, build.version, build.source_version, build.attempt + 1, build.hosts)
        assert not heartbeat(db, stale, 60)
        assert not write_progress(db, stale, 50)
        assert not finish_ready(db, stale, checked_at=NOW, base_hashes={})
        assert not finish_failed(db, stale, "unknown")
        assert _row(db, "dem", version)["status"] == "building"

    def test_progress_is_a_percentage_below_one_hundred_while_building(self, db: psycopg.Connection) -> None:
        version = _request(db, "dem", "v1")
        build = _claim(db)
        assert build is not None
        assert write_progress(db, build, 42)
        assert _row(db, "dem", version)["progress"] == 42
        assert write_progress(db, build, 400)
        assert _row(db, "dem", version)["progress"] == 99
        assert write_progress(db, build, -3)
        assert _row(db, "dem", version)["progress"] == 0

    def test_a_finished_build_takes_no_more_changes(self, db: psycopg.Connection) -> None:
        _request(db, "dem", "v1")
        build = _claim(db)
        assert build is not None
        assert finish_ready(db, build, checked_at=NOW, base_hashes={})
        assert not heartbeat(db, build, 60)
        assert not write_progress(db, build, 10)
        assert not finish_failed(db, build, "unknown")

    def test_a_build_whose_lease_ran_out_is_failed_by_the_next_claim_and_tried_again(
        self, db: psycopg.Connection
    ) -> None:
        version = _request(db, "dem", "v1")
        first = _claim(db)
        assert first is not None
        _age(db, "dem", version, updated="0 seconds", lease="1 second")
        second = _claim(db)
        assert second is not None and second.attempt == 2, "a lost lease does not wait for the delay of a failure"
        assert not heartbeat(db, first, 60), "the first attempt is not the owner any more"
        assert _row(db, "dem", version)["status"] == "building"

    def test_a_build_that_lost_its_lease_for_the_last_time_stays_failed(self, db: psycopg.Connection) -> None:
        version = _request(db, "dem", "v1")
        for attempt in range(1, MAX_ATTEMPTS + 1):
            build = _claim(db)
            assert build is not None and build.attempt == attempt
            _age(db, "dem", version, updated="0 seconds", lease="1 second")
        assert _claim(db) is None
        row = _row(db, "dem", version)
        assert (row["status"], row["failure_kind"], row["attempts"]) == ("failed", "lease_lost", MAX_ATTEMPTS)


class TestFinish:
    def test_ready_keeps_the_time_and_the_hashes_and_ends_the_lease(self, db: psycopg.Connection) -> None:
        version = _request(db, "dem", "v1")
        build = _claim(db)
        assert build is not None
        assert finish_ready(db, build, checked_at=NOW, base_hashes={"6/33/21": "ab" * 32})
        row = _row(db, "dem", version)
        assert (row["status"], row["progress"], row["checked_at"], row["worker"], row["lease_until"]) == (
            "ready",
            100,
            NOW,
            None,
            None,
        )
        assert row["base_hashes"] == {"6/33/21": "ab" * 32}

    def test_a_time_without_a_zone_is_refused(self, db: psycopg.Connection) -> None:
        _request(db, "dem", "v1")
        build = _claim(db)
        assert build is not None
        with pytest.raises(ValueError, match="timezone"):
            finish_ready(db, build, checked_at=datetime(2026, 11, 11), base_hashes={})

    def test_failed_names_its_kind(self, db: psycopg.Connection) -> None:
        version = _request(db, "dem", "v1")
        build = _claim(db)
        assert build is not None
        assert finish_failed(db, build, "source_timeout")
        row = _row(db, "dem", version)
        assert (row["status"], row["failure_kind"], row["worker"], row["lease_until"]) == (
            "failed",
            "source_timeout",
            None,
            None,
        )

    @pytest.mark.parametrize(
        "kind",
        ["", "Source", "a b", "https://example.invalid/x.tif", "/data/tile.tif", "x" * 41, "1abc", "a-b", "a\nb"],
    )
    def test_a_failure_kind_that_could_carry_an_address_is_refused(self, db: psycopg.Connection, kind: str) -> None:
        _request(db, "dem", "v1")
        build = _claim(db)
        assert build is not None
        with pytest.raises(ValueError, match="short name"):
            finish_failed(db, build, kind)
        assert db.execute("SELECT status FROM public.earthx_overview").fetchone() == ("building",)


class TestRetry:
    def _failed(self, db: psycopg.Connection, kind: str, *, updated: str) -> str:
        version = _request(db, "dem", "v1")
        build = _claim(db)
        assert build is not None
        _fail(db, build, kind)
        _age(db, "dem", version, updated=updated)
        return version

    @pytest.mark.parametrize("kind", ["source_timeout", "source_5xx"])
    def test_a_failure_a_second_attempt_can_help_is_tried_again_after_an_hour(
        self, db: psycopg.Connection, kind: str
    ) -> None:
        version = self._failed(db, kind, updated="2 hours")
        again = _claim(db)
        assert again is not None and again.attempt == 2
        row = _row(db, "dem", version)
        assert (row["status"], row["failure_kind"], row["progress"], row["base_hashes"]) == ("building", None, 0, {})

    def test_not_before_the_hour_is_over(self, db: psycopg.Connection) -> None:
        self._failed(db, "source_timeout", updated="10 minutes")
        assert _claim(db) is None

    @pytest.mark.parametrize("kind", ["unknown", "child_crashed", "runtime_exceeded", "upload_failed", "bad_data"])
    def test_any_other_failure_stays_failed(self, db: psycopg.Connection, kind: str) -> None:
        version = self._failed(db, kind, updated="30 days")
        assert _claim(db) is None
        assert _row(db, "dem", version)["status"] == "failed"

    def test_a_dataset_gets_no_more_than_the_attempts_it_has(self, db: psycopg.Connection) -> None:
        version = _request(db, "dem", "v1")
        for attempt in range(1, MAX_ATTEMPTS + 1):
            build = _claim(db)
            assert build is not None and build.attempt == attempt
            _fail(db, build, "source_5xx")
            _age(db, "dem", version, updated="2 hours")
        assert _claim(db) is None
        assert _row(db, "dem", version)["attempts"] == MAX_ATTEMPTS

    def test_a_new_source_version_is_built_whatever_became_of_the_old_one(self, db: psycopg.Connection) -> None:
        self._failed(db, "unknown", updated="1 minute")
        new = _request(db, "dem", "v2")
        build = _claim(db)
        assert build is not None and build.version == new and build.attempt == 1


class TestRequestMissing:
    @staticmethod
    def _run(db: psycopg.Connection, dataset_id: str, source_version: str, *, started: str = "0 seconds") -> None:
        db.execute(
            """
            INSERT INTO public.earthx_materialize_runs
                (dataset_id, started_at, finished_at, status, source_version, items_written, items_deleted, listed, missing, withheld)
            VALUES (%s, clock_timestamp() - %s::interval, clock_timestamp() - %s::interval, 'loaded', %s, 1, 0, 1, 0, 0)
            """,
            (dataset_id, started, started, source_version),
        )

    @staticmethod
    def _requests(db: psycopg.Connection) -> list[tuple[str, str]]:
        return db.execute(
            "SELECT dataset_id, source_version FROM public.earthx_overview_request ORDER BY dataset_id, source_version"
        ).fetchall()

    def test_the_latest_version_of_a_dataset_without_a_pyramid_is_asked_for(self, db: psycopg.Connection) -> None:
        self._run(db, "dem", "v1", started="2 days")
        self._run(db, "dem", "v2", started="1 day")
        assert request_missing(db, ["dem", "land"]) == 1
        assert self._requests(db) == [("dem", "v2")]

    def test_a_dataset_that_was_never_materialized_is_not(self, db: psycopg.Connection) -> None:
        assert request_missing(db, ["dem"]) == 0
        assert self._requests(db) == []

    def test_a_dataset_not_named_is_not(self, db: psycopg.Connection) -> None:
        self._run(db, "other", "v1")
        assert request_missing(db, ["dem"]) == 0
        assert request_missing(db, []) == 0
        assert self._requests(db) == []

    @pytest.mark.parametrize(
        ("state", "column", "value"),
        [
            ("ready", "checked_at", "now()"),
            ("building", "lease_until", "now() + interval '1 hour'"),
            ("failed", "failure_kind", "'unknown'"),
        ],
    )
    def test_a_pyramid_in_any_state_is_no_gap(
        self, db: psycopg.Connection, state: str, column: str, value: str
    ) -> None:
        self._run(db, "dem", "v1")
        version = db.execute("SELECT public.earthx_overview_version('v1')").fetchone()[0]
        db.execute(
            f"INSERT INTO public.earthx_overview (dataset_id, version, status, {column}) VALUES ('dem', %s, %s, {value})",
            (version, state),
        )
        assert request_missing(db, ["dem"]) == 0
        assert self._requests(db) == []

    def test_a_pyramid_of_an_older_version_is_a_gap_for_the_newer_one(self, db: psycopg.Connection) -> None:
        self._run(db, "dem", "v1", started="2 days")
        self._run(db, "dem", "v2")
        old = db.execute("SELECT public.earthx_overview_version('v1')").fetchone()[0]
        db.execute(
            "INSERT INTO public.earthx_overview (dataset_id, version, status, checked_at) VALUES ('dem', %s, 'ready', now())",
            (old,),
        )
        assert request_missing(db, ["dem"]) == 1
        assert self._requests(db) == [("dem", "v2")]

    def test_asking_twice_asks_once_and_the_request_is_then_built(self, db: psycopg.Connection) -> None:
        self._run(db, "dem", "v1")
        request_missing(db, ["dem"])
        request_missing(db, ["dem"])
        assert self._requests(db) == [("dem", "v1")]
        build = _claim(db)
        assert build is not None and build.source_version == "v1"
        assert request_missing(db, ["dem"]) == 0, "building is no gap"

    def test_an_unchanged_run_names_the_same_version_and_asks_nothing_more(self, db: psycopg.Connection) -> None:
        self._run(db, "dem", "v1", started="1 day")
        request_missing(db, ["dem"])
        db.execute(
            """
            INSERT INTO public.earthx_materialize_runs
                (dataset_id, started_at, finished_at, status, source_version, items_written, items_deleted, listed, missing, withheld)
            VALUES ('dem', now(), now(), 'unchanged', 'v1', 0, 0, 0, 0, 0)
            """
        )
        request_missing(db, ["dem"])
        assert self._requests(db) == [("dem", "v1")]

    def test_a_version_that_came_back_is_the_latest_request_again(self, db: psycopg.Connection) -> None:
        self._run(db, "dem", "v1", started="3 days")
        _request(db, "dem", "v2", age="1 day")
        self._run(db, "dem", "v1")  # the source went back to v1 and materialize loaded it
        request_missing(db, ["dem"])
        build = _claim(db)
        assert build is not None and build.source_version == "v1"


class TestHourlyRound:
    """The round of the supervisor that also cleans up asks for the pyramids that are missing (F1)."""

    @staticmethod
    def _supervisor(tmp_path: Path, store: Store, **kwargs: object) -> Supervisor:
        config = WorkerConfig(
            slots=1, sweep_seconds=0.1, cleanup_first_seconds=0.1, cleanup_seconds=3600.0, workdir=tmp_path / "work"
        )
        return Supervisor(config, store, **kwargs)  # type: ignore[arg-type]

    def test_it_asks_for_the_latest_version_of_each_pyramid_dataset_and_for_no_other(
        self, db: psycopg.Connection, store: Store, tmp_path: Path
    ) -> None:
        TestRequestMissing._run(db, "dem", "v1")
        TestRequestMissing._run(db, "not-a-pyramid", "v1")
        supervisor = self._supervisor(tmp_path, store, pyramids={"dem": ["dem.example.invalid"]})
        assert supervisor.pyramids == {"dem": ("dem.example.invalid",)}
        supervisor.start()
        try:
            wait_until(lambda: TestRequestMissing._requests(db) == [("dem", "v1")], timeout=15)
        finally:
            supervisor.stop(30)

    def test_without_pyramids_it_asks_for_nothing(self, db: psycopg.Connection, store: Store, tmp_path: Path) -> None:
        TestRequestMissing._run(db, "dem", "v1")
        supervisor = self._supervisor(tmp_path, store)
        supervisor.start()
        try:
            time.sleep(1.0)
            assert supervisor.healthy()
            assert TestRequestMissing._requests(db) == []
        finally:
            supervisor.stop(30)

    def test_the_clean_up_still_runs_after_it(self, db: psycopg.Connection, store: Store, tmp_path: Path) -> None:
        TestRequestMissing._run(db, "dem", "v1")
        add_run(db, status="failed", expires_in="-1 hour")
        supervisor = self._supervisor(tmp_path, store, pyramids={"dem": []})
        supervisor.start()
        try:
            wait_until(lambda: db.execute("SELECT count(*) FROM public.earthx_run").fetchone() == (0,), timeout=15)
            assert TestRequestMissing._requests(db) == [("dem", "v1")]
        finally:
            supervisor.stop(30)
