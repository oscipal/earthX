"""The thread that builds pyramids, with spawned children, a real Postgres and a moto bucket
(M5-30b part 8b-2, adr/0032 §5.2, §8.2).

The children are the stand-ins of `overview_targets.py` (the real one is run in `processing/test_overview_build.py`
and in `test_overview_child.py`). The items come from a seam (`write_items`); the SQL behind it is tested against a real
pgstac in `tests/integration/test_overview_items.py`. Times are short: a lease of 3 s, a heartbeat every 0.3 s.
"""

from __future__ import annotations

import ast
import io
import json
import logging
import multiprocessing
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest

from earthx.jobs import overview_builder
from earthx.jobs.config import WorkerConfig
from earthx.jobs.entry import ChildTarget
from earthx.jobs.overviews import MAX_ATTEMPTS
from earthx.jobs.worker import Supervisor
from earthx.objectstore.errors import StoreUnavailable
from earthx.objectstore.overviews import CHECKED_AT, upload_tile
from earthx.objectstore.results import Store
from tests.earthx.jobs.support import add_run, status_of, wait_until
from tests.earthx.objectstore.conftest import BUCKET

from .test_overviews import _age, _request, _row

BACKEND = Path(__file__).resolve().parents[3]
HOSTS = {"dem": ("dem.example.invalid",), "proto-dem": ("proto.example.invalid",), "land": ("land.example.invalid",)}
FAST: dict[str, Any] = {
    "slots": 1,
    "lease_seconds": 3.0,
    "heartbeat_seconds": 0.3,
    "poll_seconds": 0.2,
    "sweep_seconds": 0.3,
    "cancel_grace_seconds": 1.0,
    "terminate_grace_seconds": 1.0,
    "progress_seconds": 0.0,
    "cleanup_first_seconds": 1e9,
    "cleanup_seconds": 1e9,
    "backoff_seconds": 0.0,
}
OLD = datetime.now(UTC).replace(microsecond=0) - timedelta(days=10)
PREVIOUS = "aaaaaaaaaaaaaaaa"


def _children() -> list[multiprocessing.process.BaseProcess]:
    return [p for p in multiprocessing.active_children() if p.name == "earthx-overview"]


@pytest.fixture
def items(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The seam for the items: a line per item; the datasets read are recorded."""
    asked: list[str] = []

    def write(conn: psycopg.Connection, dataset_id: str, path: Path, beat: Callable[[], None]) -> int:
        asked.append(dataset_id)
        path.write_text('{"id": "a"}\n{"id": "b"}\n')
        beat()
        return 2

    monkeypatch.setattr(overview_builder, "write_items", write)
    return asked


@pytest.fixture
def make(
    db: psycopg.Connection, store: Store, tmp_path: Path, items: list[str]
) -> Iterator[Callable[..., Supervisor]]:
    """A started supervisor with pyramids and a stand-in child; every one is stopped at the end."""
    made: list[Supervisor] = []

    def build(
        target: str = "succeed",
        *,
        start: bool = True,
        pyramids: dict[str, tuple[str, ...]] | None = None,
        module: str = "overview_targets",
        **overrides: Any,
    ) -> Supervisor:
        config = WorkerConfig(**{**FAST, "workdir": tmp_path / f"work{len(made)}", **overrides})
        supervisor = Supervisor(
            config,
            store,
            target=ChildTarget("tests.earthx.jobs.child_targets", "succeed"),
            overview_target=ChildTarget(f"tests.earthx.jobs.{module}", target),
            pyramids=pyramids or HOSTS,
            name=f"test-{len(made)}",
        )
        made.append(supervisor)
        if start:
            supervisor.start()
        return supervisor

    yield build
    for supervisor in made:
        supervisor.stop(30)


def _keys(store: Store, dataset_id: str, version: str) -> list[str]:
    return sorted(store.s3.list_keys(f"overviews/{dataset_id}/{version}/"))


def _head(store: Store, key: str) -> dict:
    return store.s3._internal.head_object(Bucket=BUCKET, Key=key)


def _status(db: psycopg.Connection, dataset_id: str, version: str) -> tuple[str, str | None, int]:
    """Status, failure kind and attempt of the row, ``("none", None, 0)`` while there is none."""
    row = db.execute(
        "SELECT status, failure_kind, attempts FROM public.earthx_overview WHERE dataset_id = %s AND version = %s",
        (dataset_id, version),
    ).fetchone()
    return ("none", None, 0) if row is None else (row[0], row[1], row[2])


def _wait_for(db: psycopg.Connection, dataset_id: str, version: str, status: str, timeout: float = 30) -> None:
    def reached() -> bool:
        found = db.execute(
            "SELECT status FROM public.earthx_overview WHERE dataset_id = %s AND version = %s", (dataset_id, version)
        ).fetchone()
        return found is not None and found[0] == status

    wait_until(reached, timeout)


def _row_progress(db: psycopg.Connection, version: str) -> int | None:
    row = db.execute("SELECT progress FROM public.earthx_overview WHERE version = %s", (version,)).fetchone()
    return None if row is None else row[0]


def _previous(db: psycopg.Connection, store: Store, hashes: dict[str, str], tiles: list[str]) -> None:
    """A ready pyramid of an older version of `dem`, with its objects."""
    db.execute(
        """
        INSERT INTO public.earthx_overview (dataset_id, version, status, checked_at, base_hashes, progress)
        VALUES ('dem', %s, 'ready', %s, %s::jsonb, 100)
        """,
        (PREVIOUS, OLD, json.dumps(hashes)),
    )
    for name in tiles:
        z, x, y = (int(part) for part in name.split("/"))
        with tempfile.NamedTemporaryFile() as handle:
            handle.write(b"old-tile")
            handle.flush()
            upload_tile(store, "dem", PREVIOUS, z, x, y, Path(handle.name), checked_at=OLD)


class TestABuild:
    def test_a_request_is_built_uploaded_and_closed_as_ready(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], items: list[str]
    ) -> None:
        version = _request(db, "dem", '"etag-1"')
        before = datetime.now(UTC)
        make()
        _wait_for(db, "dem", version, "ready")
        row = _row(db, "dem", version)
        assert items == ["dem"]
        assert (row["attempts"], row["progress"], row["worker"], row["lease_until"]) == (1, 100, None, None)
        assert before <= row["checked_at"] <= datetime.now(UTC)
        assert row["base_hashes"] == {"1/1": "h1"}, "a tile without a hash has none in the row"
        keys = _keys(store, "dem", version)
        assert keys == sorted(f"overviews/dem/{version}/{name}.tif" for name in ("2/1/1", "2/2/1", "1/0/0", "1/1/0", "0/0/0"))
        head = _head(store, keys[0])
        assert head["Metadata"] == {CHECKED_AT: row["checked_at"].isoformat()}
        assert "CacheControl" not in head

    def test_the_work_directory_is_gone_afterwards_and_no_child_is_left(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], tmp_path: Path
    ) -> None:
        version = _request(db, "dem", "v1")
        supervisor = make()
        _wait_for(db, "dem", version, "ready")
        wait_until(lambda: not _children())
        # The row closes before the work directory is removed: wait for the clean-up, do not race it.
        wait_until(lambda: not (supervisor.config.workdir / overview_builder.WORKDIR).exists())

    def test_the_tiles_of_a_prototype_source_are_served_with_no_store(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor]
    ) -> None:
        version = _request(db, "proto-dem", "v1")
        make()
        _wait_for(db, "proto-dem", version, "ready")
        assert {_head(store, key)["CacheControl"] for key in _keys(store, "proto-dem", version)} == {"no-store"}

    def test_progress_reaches_the_database_while_it_builds(self, db: psycopg.Connection, make: Callable[..., Supervisor]) -> None:
        version = _request(db, "dem", "v1")
        make("hang")  # says 1 of 5 and then nothing
        wait_until(lambda: _row_progress(db, version) == 20)

    def test_only_a_dataset_with_a_pyramid_is_built(self, db: psycopg.Connection, make: Callable[..., Supervisor]) -> None:
        _request(db, "stranger", "v1")
        make()
        time.sleep(1.0)
        assert db.execute("SELECT count(*) FROM public.earthx_overview").fetchone() == (0,)

    def test_without_pyramids_there_is_no_thread(self, db: psycopg.Connection, store: Store, tmp_path: Path) -> None:
        supervisor = Supervisor(WorkerConfig(**{**FAST, "workdir": tmp_path / "w"}), store)
        supervisor.start()
        try:
            assert "overview" not in {thread.name for thread in supervisor._threads}
        finally:
            supervisor.stop(30)

    def test_with_pyramids_the_thread_is_one_of_its_own_and_no_slot(
        self, make: Callable[..., Supervisor]
    ) -> None:
        supervisor = make(slots=2)
        names = sorted(thread.name for thread in supervisor._threads)
        assert names == ["listen", "maintain", "overview", "slot-0", "slot-1"]
        assert supervisor.healthy()

    def test_a_left_over_work_directory_is_cleared_at_the_start(self, make: Callable[..., Supervisor], tmp_path: Path) -> None:
        leftover = tmp_path / "work0" / overview_builder.WORKDIR
        leftover.mkdir(parents=True)
        (leftover / "items.jsonl").write_text("x")
        make()
        assert not leftover.exists()


class TestItDoesNotBlockTheRuns:
    def test_a_run_finishes_while_a_build_holds_its_thread(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One slot only: the build must not take it (adr/0032 §8.2; Otto's answer 3 = 1)."""
        monkeypatch.setenv("OVERVIEW_DELAY", "8")
        version = _request(db, "dem", "v1")
        make(slots=1)
        wait_until(lambda: _status(db, "dem", version)[0] == "building" and len(_children()) == 1)
        run_id, _ = add_run(db)
        wait_until(lambda: status_of(db, run_id) == "successful", 30)
        assert _status(db, "dem", version)[0] == "building", "the build was still running"


class TestFailures:
    def test_a_named_failure_of_the_child_closes_the_row_with_that_name_and_no_object_stays(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILD_KIND", "source_unreachable")
        version = _request(db, "dem", "v1")
        make("fail")
        _wait_for(db, "dem", version, "failed")
        assert _status(db, "dem", version) == ("failed", "source_unreachable", 1)
        assert _keys(store, "dem", version) == []

    def test_a_kind_that_cannot_be_helped_by_a_second_attempt_is_never_retried(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILD_KIND", "source_4xx")
        version = _request(db, "dem", "v1")
        make("fail")
        _wait_for(db, "dem", version, "failed")
        _age(db, "dem", version, updated="3 hours")
        time.sleep(1.5)
        assert _status(db, "dem", version) == ("failed", "source_4xx", 1)

    def test_a_source_that_timed_out_is_tried_again_but_not_before_an_hour(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILD_KIND", "source_timeout")
        version = _request(db, "dem", "v1")
        make("fail_once")
        _wait_for(db, "dem", version, "failed")
        time.sleep(1.5)
        assert _status(db, "dem", version) == ("failed", "source_timeout", 1), "it waits for the hour"
        _age(db, "dem", version, updated="2 hours")
        _wait_for(db, "dem", version, "ready")
        assert _status(db, "dem", version) == ("ready", None, 2)
        assert len(_keys(store, "dem", version)) == 5

    def test_it_is_tried_three_times_in_all(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILD_KIND", "source_5xx")
        version = _request(db, "dem", "v1")
        make("fail")
        for attempt in range(1, MAX_ATTEMPTS + 1):
            wait_until(lambda attempt=attempt: _status(db, "dem", version) == ("failed", "source_5xx", attempt), 30)
            _age(db, "dem", version, updated="2 hours")
        time.sleep(1.5)
        assert _status(db, "dem", version) == ("failed", "source_5xx", MAX_ATTEMPTS)

    def test_a_child_that_dies_by_a_signal_is_crashed_and_not_retried(
        self, db: psycopg.Connection, make: Callable[..., Supervisor]
    ) -> None:
        version = _request(db, "dem", "v1")
        make("crash")
        _wait_for(db, "dem", version, "failed")
        _age(db, "dem", version, updated="3 hours")
        time.sleep(1.5)
        assert _status(db, "dem", version) == ("failed", "child_crashed", 1)

    def test_a_child_that_ends_without_a_word_is_crashed_too(
        self, db: psycopg.Connection, make: Callable[..., Supervisor]
    ) -> None:
        version = _request(db, "dem", "v1")
        make("exit_silently")
        _wait_for(db, "dem", version, "failed")
        assert _status(db, "dem", version)[1] == "child_crashed"

    def test_a_child_that_says_nothing_for_too_long_is_killed_as_stalled(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(overview_builder, "STALL_SECONDS", 1.0)
        version = _request(db, "dem", "v1")
        make("hang")
        _wait_for(db, "dem", version, "failed")
        assert _status(db, "dem", version)[1] == "stalled"
        wait_until(lambda: not _children())

    def test_the_first_step_failing_closes_the_row_too(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILD_KIND", "unknown")
        version = _request(db, "dem", "v1")
        make("plan_fails")
        _wait_for(db, "dem", version, "failed")
        assert _status(db, "dem", version) == ("failed", "unknown", 1)

    def test_a_dataset_without_items_fails_before_a_child_starts(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(overview_builder, "write_items", lambda conn, dataset_id, path, beat: 0)
        version = _request(db, "dem", "v1")
        make()
        _wait_for(db, "dem", version, "failed")
        assert _status(db, "dem", version) == ("failed", "no_items", 1)

    def test_too_little_disk_fails_before_a_child_starts_and_is_not_retried(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(overview_builder, "free_bytes", lambda path: overview_builder.DISK_BYTES - 1)
        version = _request(db, "dem", "v1")
        make("crash")
        _wait_for(db, "dem", version, "failed")
        assert _status(db, "dem", version) == ("failed", "disk_space", 1)

    def test_a_failed_upload_closes_the_row_and_takes_what_was_uploaded_back(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real, calls = overview_builder.upload_tile, []

        def flaky(*args: Any, **kwargs: Any) -> None:
            calls.append(args[3:6])
            if len(calls) == 3:
                raise StoreUnavailable("object store PutObject failed")
            real(*args, **kwargs)

        monkeypatch.setattr(overview_builder, "upload_tile", flaky)
        version = _request(db, "dem", "v1")
        make()
        _wait_for(db, "dem", version, "failed")
        assert _status(db, "dem", version) == ("failed", "upload_failed", 1)
        assert len(calls) == 3
        assert _keys(store, "dem", version) == []

    def test_a_bug_in_the_shell_is_named_unknown_and_logged_by_its_class_only(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        def broken(*args: Any, **kwargs: Any) -> None:
            raise KeyError("secret-looking-detail")

        caplog.set_level(logging.DEBUG, logger="earthx")
        monkeypatch.setattr(overview_builder, "upload_tile", broken)
        version = _request(db, "dem", "v1")
        make()
        _wait_for(db, "dem", version, "failed")
        wait_until(lambda: "overview build ended" in caplog.text)
        assert _status(db, "dem", version)[1] == "unknown"
        assert "secret-looking-detail" not in caplog.text


class TestTheLease:
    def test_a_build_taken_over_is_not_written_by_this_attempt_and_its_child_is_killed(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor]
    ) -> None:
        version = _request(db, "dem", "v1")
        make("hang")
        wait_until(lambda: _status(db, "dem", version)[0] == "building" and len(_children()) == 1)
        db.execute("UPDATE public.earthx_overview SET attempts = 2 WHERE dataset_id = 'dem'")
        wait_until(lambda: not _children(), 15)
        time.sleep(0.5)
        row = _row(db, "dem", version)
        assert (row["status"], row["attempts"]) == ("building", 2), "the other attempt's row is as it left it"
        assert _keys(store, "dem", version) == []

    def test_a_lost_lease_is_given_a_second_attempt_at_once(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], tmp_path: Path
    ) -> None:
        """A worker that died leaves a `building` row; the next claim marks it lease_lost and builds again, without the hour."""
        version = _request(db, "dem", "v1")
        db.execute(
            """
            INSERT INTO public.earthx_overview (dataset_id, version, status, worker, lease_until, hosts)
            VALUES ('dem', %s, 'building', 'dead', clock_timestamp() - interval '1 minute', '{dem.example.invalid}')
            """,
            (version,),
        )
        make()
        _wait_for(db, "dem", version, "ready")
        assert _status(db, "dem", version) == ("ready", None, 2)

    def test_a_shutdown_gives_the_build_back_without_using_up_an_attempt(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor]
    ) -> None:
        version = _request(db, "dem", "v1")
        supervisor = make("hang")
        wait_until(lambda: _status(db, "dem", version)[0] == "building" and len(_children()) == 1)
        supervisor.stop(30)
        assert not _children()
        assert db.execute("SELECT count(*) FROM public.earthx_overview").fetchone() == (0,), "attempt 1 leaves no row"
        assert _keys(store, "dem", version) == []
        assert db.execute("SELECT count(*) FROM public.earthx_overview_request").fetchone() == (1,)

    def test_a_shutdown_in_a_later_attempt_keeps_the_row_with_its_earlier_number(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILD_KIND", "source_timeout")
        version = _request(db, "dem", "v1")
        supervisor = make("fail_once")
        _wait_for(db, "dem", version, "failed")
        monkeypatch.setenv("OVERVIEW_DELAY", "30")
        _age(db, "dem", version, updated="2 hours")
        wait_until(lambda: _status(db, "dem", version) == ("building", None, 2) and len(_children()) == 1)
        supervisor.stop(30)
        assert _status(db, "dem", version) == ("failed", "lease_lost", 1)


class TestReuse:
    def test_a_base_tile_whose_items_did_not_change_is_reused_from_the_old_version_and_not_read(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PLAN_HASHES", json.dumps({"1/1": "h1", "2/1": "h2"}))
        _previous(db, store, {"1/1": "h1", "2/1": "other"}, ["2/1/1", "2/2/1"])
        version = _request(db, "dem", "v2")
        make()
        _wait_for(db, "dem", version, "ready")
        key = f"overviews/dem/{version}/2/1/1.tif"
        assert store.s3.get_bytes(key) == b"old-tile", "reused, not read"
        assert store.s3.get_bytes(f"overviews/dem/{version}/2/2/1.tif") == b"read", "its items changed: read again"
        assert _head(store, key)["Metadata"] == {CHECKED_AT: OLD.isoformat()}, "a reused tile keeps the term of its source"

    def test_the_row_takes_the_older_time_when_a_tile_was_reused(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _previous(db, store, {"1/1": "h1"}, ["2/1/1"])
        version = _request(db, "dem", "v2")
        make()
        _wait_for(db, "dem", version, "ready")
        row = _row(db, "dem", version)
        assert row["checked_at"] == OLD
        level = datetime.fromisoformat(_head(store, f"overviews/dem/{version}/1/0/0.tif")["Metadata"][CHECKED_AT])
        assert level > OLD, "a level made by this build carries the time of the read; the row carries the oldest"

    def test_items_without_updated_have_no_hash_and_every_tile_is_read_again(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PLAN_HASHES", json.dumps({"1/1": None, "2/1": None}))
        _previous(db, store, {"1/1": "h1"}, ["2/1/1"])
        version = _request(db, "dem", "v2")
        make()
        _wait_for(db, "dem", version, "ready")
        assert store.s3.get_bytes(f"overviews/dem/{version}/2/1/1.tif") == b"read"
        row = _row(db, "dem", version)
        assert row["base_hashes"] == {} and row["checked_at"] > OLD

    def test_a_pyramid_without_hashes_in_its_row_gives_nothing_to_reuse(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor]
    ) -> None:
        _previous(db, store, {}, ["2/1/1"])
        version = _request(db, "dem", "v2")
        make()
        _wait_for(db, "dem", version, "ready")
        assert store.s3.get_bytes(f"overviews/dem/{version}/2/1/1.tif") == b"read"

    def test_an_old_tile_that_is_gone_from_the_store_is_read_again(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor]
    ) -> None:
        _previous(db, store, {"1/1": "h1"}, [])
        version = _request(db, "dem", "v2")
        make()
        _wait_for(db, "dem", version, "ready")
        assert store.s3.get_bytes(f"overviews/dem/{version}/2/1/1.tif") == b"read"
        assert _row(db, "dem", version)["checked_at"] > OLD

    def test_only_a_ready_pyramid_of_the_same_dataset_is_reused_from(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor]
    ) -> None:
        _previous(db, store, {"1/1": "h1"}, ["2/1/1"])
        db.execute("UPDATE public.earthx_overview SET dataset_id = 'land'")
        version = _request(db, "dem", "v2")
        make()
        _wait_for(db, "dem", version, "ready")
        assert store.s3.get_bytes(f"overviews/dem/{version}/2/1/1.tif") == b"read"

    def test_a_store_that_fails_while_the_old_tile_is_fetched_fails_the_build(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _previous(db, store, {"1/1": "h1"}, ["2/1/1"])

        def refuse(*args: Any, **kwargs: Any) -> None:
            raise StoreUnavailable("object store GetObject failed")

        monkeypatch.setattr(overview_builder, "read_tile", refuse)
        version = _request(db, "dem", "v2")
        make()
        _wait_for(db, "dem", version, "failed")
        assert _status(db, "dem", version)[1] == "store_failed"


class TestARealChild:
    """The whole way with the real child of `overview_child`, on two synthetic files (the sources behind the seams of `end_to_end`)."""

    HOST = "store.example.invalid"

    @staticmethod
    def _sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, updated: str | None) -> list[dict]:
        import numpy as np
        import rasterio
        from rasterio.transform import from_bounds

        items, files = [], {}
        for name, west, value in (("a", 8.0, 100.0), ("b", 12.0, 300.0)):
            path = tmp_path / f"{name}.tif"
            profile = {
                "driver": "GTiff", "width": 60, "height": 60, "count": 1, "dtype": "float32", "crs": "EPSG:4326",
                "transform": from_bounds(west, 46, west + 1, 47, 60, 60), "nodata": -9999.0,
            }  # fmt: skip
            with rasterio.open(path, "w", **profile) as target:
                target.write(np.full((60, 60), value, dtype="float32"), 1)
            href = f"https://{TestARealChild.HOST}/{name}.tif"
            files[href] = str(path)
            properties = {} if updated is None else {"updated": updated}
            items.append(
                {
                    "id": name, "bbox": [west, 46, west + 1, 47], "properties": properties,
                    "assets": {"data": {"href": href}},
                }  # fmt: skip
            )
        monkeypatch.setenv("CHILD_FILES", json.dumps(files))
        return items

    @staticmethod
    def _serve_items(monkeypatch: pytest.MonkeyPatch, items: list[dict]) -> None:
        def write(conn: psycopg.Connection, dataset_id: str, path: Path, beat: Callable[[], None]) -> int:
            path.write_text("".join(json.dumps(item) + "\n" for item in items))
            return len(items)

        monkeypatch.setattr(overview_builder, "write_items", write)

    def test_a_build_reads_the_files_uploads_every_level_and_a_new_version_copies_the_unchanged_tiles(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        items = self._sources(tmp_path, monkeypatch, "2026-01-01T00:00:00Z")
        self._serve_items(monkeypatch, items)
        pyramids = {"cop-dem-glo-30": (self.HOST,)}
        first = _request(db, "cop-dem-glo-30", "v1")
        make("overview_end_to_end", module="child_targets", pyramids=pyramids)
        _wait_for(db, "cop-dem-glo-30", first, "ready", timeout=120)
        names = {key.split(f"{first}/")[1] for key in _keys(store, "cop-dem-glo-30", first)}
        assert names == {"6/33/22.tif", "6/34/22.tif", *(f"{z}/{33 >> (6 - z)}/{22 >> (6 - z)}.tif" for z in range(6)),
                         *(f"{z}/{34 >> (6 - z)}/{22 >> (6 - z)}.tif" for z in range(6))}
        base = store.s3.get_bytes(f"overviews/cop-dem-glo-30/{first}/6/33/22.tif")
        assert base[:2] in (b"II", b"MM"), "a GeoTIFF"
        row = _row(db, "cop-dem-glo-30", first)
        assert set(row["base_hashes"]) == {"33/22", "34/22"}

        second = _request(db, "cop-dem-glo-30", "v2")
        _wait_for(db, "cop-dem-glo-30", second, "ready", timeout=120)
        assert store.s3.get_bytes(f"overviews/cop-dem-glo-30/{second}/6/33/22.tif") == base, "reused: the same bytes"
        copied = _head(store, f"overviews/cop-dem-glo-30/{second}/6/33/22.tif")["Metadata"]
        assert copied == _head(store, f"overviews/cop-dem-glo-30/{first}/6/33/22.tif")["Metadata"]
        assert _row(db, "cop-dem-glo-30", second)["checked_at"] == row["checked_at"]

    def test_items_without_updated_are_read_again_for_a_new_version(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        items = self._sources(tmp_path, monkeypatch, None)
        self._serve_items(monkeypatch, items)
        first = _request(db, "cop-dem-glo-30", "v1")
        make("overview_end_to_end", module="child_targets", pyramids={"cop-dem-glo-30": (self.HOST,)})
        _wait_for(db, "cop-dem-glo-30", first, "ready", timeout=120)
        assert _row(db, "cop-dem-glo-30", first)["base_hashes"] == {}
        second = _request(db, "cop-dem-glo-30", "v2")
        _wait_for(db, "cop-dem-glo-30", second, "ready", timeout=120)
        assert _row(db, "cop-dem-glo-30", second)["checked_at"] > _row(db, "cop-dem-glo-30", first)["checked_at"]

    def test_a_host_the_registry_does_not_name_fails_the_build_with_a_kind_and_uploads_nothing(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._serve_items(monkeypatch, self._sources(tmp_path, monkeypatch, "2026-01-01T00:00:00Z"))
        version = _request(db, "cop-dem-glo-30", "v1")
        make("overview_end_to_end", module="child_targets", pyramids={"cop-dem-glo-30": ("other.example.invalid",)})
        _wait_for(db, "cop-dem-glo-30", version, "failed", timeout=120)
        status, kind, _ = _status(db, "cop-dem-glo-30", version)
        assert kind == "rejected", "not a kind a second attempt can help"
        assert _keys(store, "cop-dem-glo-30", version) == []


class TestTheReusedBytesAreUploadedFromTheWorkDirectory:
    """The old version may be gone by the end of a build that takes hours: nothing reads it then (review 8b-2 finding 1)."""

    def test_a_previous_version_deleted_while_the_build_runs_does_not_fail_the_upload(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _previous(db, store, {"1/1": "h1"}, ["2/1/1"])
        monkeypatch.setenv("OVERVIEW_DELAY", "2")
        version = _request(db, "dem", "v2")
        supervisor = make()
        job = supervisor.config.workdir / overview_builder.WORKDIR / "job.json"
        # The build step has begun once job.json names it; by then the old tile is in the work directory.
        wait_until(lambda: job.exists() and json.loads(job.read_text())["mode"] == "build" and len(_children()) == 1)
        overview_builder.delete_version(store, "dem", PREVIOUS)
        _wait_for(db, "dem", version, "ready")
        assert store.s3.get_bytes(f"overviews/dem/{version}/2/1/1.tif") == b"old-tile"

    def test_a_reused_tile_keeps_the_time_of_its_own_object_and_the_row_takes_the_oldest(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], tmp_path: Path
    ) -> None:
        _previous(db, store, {"1/1": "h1"}, ["2/1/1"])
        older = OLD - timedelta(days=2)
        with tempfile.NamedTemporaryFile() as handle:
            handle.write(b"old-tile")
            handle.flush()
            upload_tile(store, "dem", PREVIOUS, 2, 1, 1, Path(handle.name), checked_at=older)
        version = _request(db, "dem", "v2")
        make()
        _wait_for(db, "dem", version, "ready")
        assert _row(db, "dem", version)["checked_at"] == older
        assert _head(store, f"overviews/dem/{version}/2/1/1.tif")["Metadata"] == {CHECKED_AT: older.isoformat()}
        fresh = _head(store, f"overviews/dem/{version}/2/2/1.tif")["Metadata"][CHECKED_AT]
        assert datetime.fromisoformat(fresh) > OLD, "tiles that were read now carry the time of the read"

    def test_a_tile_with_too_little_term_left_is_read_again_not_reused(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor]
    ) -> None:
        """Its term ends within the margin: reusing it would shorten the new pyramid to that (review 8b-2 finding 1)."""
        _previous(db, store, {"1/1": "h1"}, [])
        with tempfile.NamedTemporaryFile() as handle:
            handle.write(b"old-tile")
            handle.flush()
            almost = datetime.now(UTC) - timedelta(days=26)
            upload_tile(store, "dem", PREVIOUS, 2, 1, 1, Path(handle.name), checked_at=almost)
        db.execute("UPDATE public.earthx_overview SET checked_at = clock_timestamp() - interval '10 days'")
        version = _request(db, "dem", "v2")
        make()
        _wait_for(db, "dem", version, "ready")
        assert store.s3.get_bytes(f"overviews/dem/{version}/2/1/1.tif") == b"read"
        assert _row(db, "dem", version)["checked_at"] > OLD

    def test_a_previous_version_with_too_little_term_left_is_not_a_source_at_all(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor]
    ) -> None:
        _previous(db, store, {"1/1": "h1"}, ["2/1/1"])
        db.execute("UPDATE public.earthx_overview SET checked_at = clock_timestamp() - interval '26 days'")
        version = _request(db, "dem", "v2")
        make()
        _wait_for(db, "dem", version, "ready")
        assert store.s3.get_bytes(f"overviews/dem/{version}/2/1/1.tif") == b"read"


class TestObjectsOfOtherAttempts:
    def test_a_stale_attempt_that_fails_does_not_delete_the_objects_of_the_attempt_that_took_over(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Review 8b-2 finding 2: the clean-up after a failed upload checks that the build is still its own."""
        version = _request(db, "dem", "v1")
        real, calls = overview_builder.upload_tile, []

        def taken_over(*args: Any, **kwargs: Any) -> None:
            calls.append(1)
            if len(calls) == 2:
                # Another attempt finished the same version meanwhile and its objects stand there.
                db.execute(
                    "UPDATE public.earthx_overview SET attempts = 2, status = 'ready', worker = NULL, lease_until = NULL,"
                    " checked_at = now()"
                )
                with tempfile.NamedTemporaryFile() as handle:
                    handle.write(b"theirs")
                    handle.flush()
                    real(store, "dem", version, 9, 9, 9, Path(handle.name), checked_at=datetime.now(UTC))
                raise StoreUnavailable("object store PutObject failed")
            real(*args, **kwargs)

        monkeypatch.setattr(overview_builder, "upload_tile", taken_over)
        make()
        wait_until(lambda: len(calls) >= 2 and not _children() and _status(db, "dem", version)[0] == "ready", 20)
        time.sleep(0.5)
        assert store.s3.get_bytes(f"overviews/dem/{version}/9/9/9.tif") == b"theirs"
        assert _row(db, "dem", version)["attempts"] == 2 and _status(db, "dem", version)[0] == "ready"

    def test_a_stale_attempt_that_is_stopped_does_not_delete_them_either(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        version = _request(db, "dem", "v1")
        real, calls = overview_builder.upload_tile, []
        holder: list[Supervisor] = []

        def taken_over_then_stop(*args: Any, **kwargs: Any) -> None:
            calls.append(1)
            if len(calls) == 2:
                db.execute("UPDATE public.earthx_overview SET attempts = 2")
                with tempfile.NamedTemporaryFile() as handle:
                    handle.write(b"theirs")
                    handle.flush()
                    real(store, "dem", version, 9, 9, 9, Path(handle.name), checked_at=datetime.now(UTC))
                holder[0]._stopping.set()
            real(*args, **kwargs)

        monkeypatch.setattr(overview_builder, "upload_tile", taken_over_then_stop)
        holder.append(make())
        wait_until(lambda: len(calls) >= 2 and not _children(), 20)
        time.sleep(0.5)
        assert store.s3.get_bytes(f"overviews/dem/{version}/9/9/9.tif") == b"theirs"

    def test_objects_an_earlier_attempt_left_under_the_same_version_are_removed_before_the_upload(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor]
    ) -> None:
        version = _request(db, "dem", "v1")
        store.s3.put_object(f"overviews/dem/{version}/9/0/0.tif", io.BytesIO(b"stale"), "image/tiff")
        make()
        _wait_for(db, "dem", version, "ready")
        assert len(_keys(store, "dem", version)) == 5, "only the tiles of this attempt"
        assert not any("/9/0/0.tif" in key for key in _keys(store, "dem", version))


class TestTheShellAndTheCore:
    def test_the_names_of_the_files_are_those_of_the_core(self) -> None:
        from earthx.processing import overview_build as core

        assert (overview_builder.ITEMS_NAME, overview_builder.JOB_NAME, overview_builder.PLAN_NAME) == (
            core.ITEMS_NAME,
            core.JOB_NAME,
            core.PLAN_NAME,
        )
        assert (overview_builder.MANIFEST_NAME, overview_builder.TILES_DIR) == (core.MANIFEST_NAME, core.TILES_DIR)

    def test_the_builder_loads_neither_the_core_nor_the_readers(self) -> None:
        """K3: the supervisor stays free of GDAL, and so does the thread that builds."""
        script = (
            "import sys; sys.modules['boto3'] = None; import earthx.jobs.worker, earthx.jobs.overview_builder\n"
            "bad = [n for n in sys.modules if n.split('.')[0] in ('rasterio', 'numpy', 'morecantile') or"
            " n.startswith(('earthx.processing', 'earthx.jobs.child', 'earthx.jobs.overview_child', 'earthx.readers',"
            " 'earthx.gateway', 'earthx.catalog'))]\n"
            "print(sorted(bad))"
        )
        output = subprocess.run(
            [sys.executable, "-c", script], cwd=BACKEND, capture_output=True, text=True, check=True, timeout=120
        )
        assert output.stdout.strip() == "[]"

    def test_the_builder_starts_its_children_only_through_the_context_the_supervisor_gives_it(self) -> None:
        source = (BACKEND / "earthx" / "jobs" / "overview_builder.py").read_text()
        calls = [
            ast.unparse(node.func)
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "Process"
        ]
        assert calls == ["self._context.Process"]
        assert "get_context" not in source and "fork" not in source

    def test_the_default_target_is_the_overview_child_and_not_the_one_of_the_runs(self, store: Store, tmp_path: Path) -> None:
        builder = overview_builder.OverviewBuilder(
            WorkerConfig(workdir=tmp_path),
            store,
            name="x",
            pyramids={},
            context=multiprocessing.get_context("spawn"),
            stopping=threading.Event(),
            connect=lambda: None,  # type: ignore[arg-type, return-value]
            database_ok=lambda: None,
        )
        assert builder._target == ChildTarget("earthx.jobs.overview_child", "run_child")


class TestLogs:
    @staticmethod
    def _lines(caplog: pytest.LogCaptureFixture) -> str:
        return " ".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records if "earthx" in record.name)

    def test_a_failed_child_is_logged_with_its_kind_where_and_why_and_the_build_says_it_failed(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], caplog: pytest.LogCaptureFixture
    ) -> None:
        """Otto, 15.11.2026: the kind, the exception class with a short reason, and the tile as z/x/y, for every child failure."""
        caplog.set_level(logging.DEBUG, logger="earthx")
        failed = _request(db, "dem", "v1")
        make("fail_with_detail")
        _wait_for(db, "dem", failed, "failed")
        wait_until(lambda: "overview build ended" in self._lines(caplog))
        child = next(r for r in caplog.records if r.getMessage() == "overview child failed")
        assert (child.failure_kind, child.step, child.error, child.tile) == ("unknown", "build", "RasterioIOError", "6/33/22")
        assert child.reason == "HTTP response code on <address> 0" and child.dataset == "dem" and child.levelno == logging.WARNING
        ended = next(r for r in caplog.records if r.getMessage() == "overview build ended")
        assert (ended.status, ended.failure_kind, ended.outcome) == ("failed", "unknown", "unknown")
        assert ended.levelno == logging.WARNING

    def test_a_bare_kind_from_a_child_is_still_logged_and_a_ready_build_is_not_a_failure(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="earthx")
        monkeypatch.setenv("CHILD_KIND", "source_timeout")
        failed = _request(db, "dem", "v1")
        make("fail")
        _wait_for(db, "dem", failed, "failed")
        wait_until(lambda: "overview child failed" in self._lines(caplog))
        child = next(r for r in caplog.records if r.getMessage() == "overview child failed")
        assert child.failure_kind == "source_timeout" and not hasattr(child, "tile")

    def test_a_build_that_worked_says_ready_at_info(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="earthx")
        ready = _request(db, "dem", "v1")
        make()
        _wait_for(db, "dem", ready, "ready")
        wait_until(lambda: "overview build ended" in self._lines(caplog))
        ended = next(r for r in caplog.records if r.getMessage() == "overview build ended")
        assert (ended.status, ended.levelno) == ("ready", logging.INFO) and not hasattr(ended, "failure_kind")

    def test_no_line_names_an_item_or_an_address_and_only_the_failure_line_names_a_tile(
        self, db: psycopg.Connection, make: Callable[..., Supervisor], caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="earthx")
        monkeypatch.setenv("CHILD_KIND", "source_timeout")
        failed = _request(db, "dem", "v1")
        make("fail")
        _wait_for(db, "dem", failed, "failed")

        def lines() -> str:
            return TestLogs._lines(caplog)

        wait_until(lambda: "overview build ended" in lines())
        text = lines()
        assert "dem.example.invalid" not in text and "overviews/" not in text
        assert "overview build ended" in text and "source_timeout" in text


def _omitted(db: psycopg.Connection, dataset_id: str, version: str) -> dict[str, tuple[str, str, str, int]]:
    return {
        tile: (kind, error, reason, attempts)
        for tile, kind, error, reason, attempts in db.execute(
            "SELECT tile, kind, error, reason, attempts FROM public.earthx_overview_omitted "
            "WHERE dataset_id = %s AND version = %s",
            (dataset_id, version),
        )
    }


def _age_omitted(db: psycopg.Connection, dataset_id: str, version: str, interval: str = "2 hours") -> None:
    db.execute(
        "UPDATE public.earthx_overview_omitted SET tried_at = clock_timestamp() - %s::interval "
        "WHERE dataset_id = %s AND version = %s",
        (interval, dataset_id, version),
    )


class TestAnOmittedTile:
    """One file that stays unreadable omits only its base tile; the pyramid is ready, with the gap recorded and logged."""

    def test_the_build_is_ready_with_the_gap_in_the_table_and_in_the_log(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="earthx")
        version = _request(db, "dem", '"etag-1"')
        make("omit")
        _wait_for(db, "dem", version, "ready")
        wait_until(lambda: any(r.getMessage() == "overview build ended" for r in caplog.records))
        assert _status(db, "dem", version) == ("ready", None, 1)
        assert _omitted(db, "dem", version) == {
            "2/1": ("unreadable", "RasterioIOError", "not recognized as a supported file format", 1)
        }
        assert "overviews/dem/%s/2/2/1.tif" % version not in _keys(store, "dem", version)
        assert "2/1/1" in " ".join(k.removeprefix(f"overviews/dem/{version}/") for k in _keys(store, "dem", version))
        line = next(r for r in caplog.records if r.getMessage() == "overview base tile omitted")
        assert (line.dataset, line.tile, line.failure_kind, line.error) == ("dem", "2/2/1", "unreadable", "RasterioIOError")
        assert line.reason == "not recognized as a supported file format" and line.levelno == logging.WARNING
        text = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records if "earthx" in r.name)
        assert "example.invalid" not in text and "overviews/" not in text and '"a"' not in text
        ended = next(r for r in caplog.records if r.getMessage() == "overview build ended")
        assert ended.status == "ready" and ended.levelno == logging.INFO

    def test_a_pyramid_without_a_gap_has_no_rows(self, db: psycopg.Connection, make: Callable[..., Supervisor]) -> None:
        version = _request(db, "dem", '"etag-1"')
        make()
        _wait_for(db, "dem", version, "ready")
        assert _omitted(db, "dem", version) == {}


class TestTheHourlyRetry:
    """The retry reads the omitted tiles again, once an hour, and puts the tiles it makes over the served version."""

    FAST_ROUND: dict[str, Any] = {"cleanup_first_seconds": 0.2, "cleanup_seconds": 1e9}

    def _pyramid(self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], target: str) -> str:
        """A ready pyramid with a gap, as the build leaves it, built by a supervisor that is then stopped."""
        version = _request(db, "dem", '"etag-1"')
        supervisor = make("omit", cleanup_first_seconds=1e9)
        _wait_for(db, "dem", version, "ready")
        supervisor.stop(30)
        assert list(_omitted(db, "dem", version)) == ["2/1"]
        return version

    def _objects(self, store: Store, version: str) -> dict[str, tuple[bytes, str]]:
        found = {}
        for key in _keys(store, "dem", version):
            head = _head(store, key)
            body = store.s3._internal.get_object(Bucket=BUCKET, Key=key)["Body"].read()
            found[key] = (body, head["Metadata"][CHECKED_AT])
        return found

    def test_the_retry_fills_the_gap_without_deleting_what_is_served(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor]
    ) -> None:
        version = self._pyramid(db, store, make, "patch_ok")
        before = self._objects(store, version)
        row = _row(db, "dem", version)
        _age_omitted(db, "dem", version)
        make("patch_ok", **self.FAST_ROUND)
        wait_until(lambda: _omitted(db, "dem", version) == {}, 30)
        after = self._objects(store, version)
        assert set(before) < set(after), "nothing was deleted, and the omitted tile is there now"
        assert f"overviews/dem/{version}/2/2/1.tif" in after
        made = {key for key in after if after[key][0] == b"made again"}
        assert made == {f"overviews/dem/{version}/{name}.tif" for name in ("2/2/1", "1/1/0", "0/0/0")}
        for key in set(before) - made:
            assert after[key] == before[key], "an object that was served is untouched, its checked-at too"
        for key in made:
            assert after[key][1] > row["checked_at"].isoformat(), "each object made again has its own, later checked-at"
        again = _row(db, "dem", version)
        assert again["status"] == "ready" and again["checked_at"] == row["checked_at"]
        assert again["base_hashes"]["2/1"] == "h2" and again["base_hashes"]["1/1"] == "h1"

    def test_a_retry_that_fails_again_is_recorded_and_changes_nothing_else(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="earthx")
        version = self._pyramid(db, store, make, "patch_again")
        before = self._objects(store, version)
        row = _row(db, "dem", version)
        _age_omitted(db, "dem", version)
        make("patch_again", **self.FAST_ROUND)
        wait_until(lambda: _omitted(db, "dem", version)["2/1"][3] == 2, 30)
        assert _omitted(db, "dem", version)["2/1"][:3] == ("source_5xx", "RasterioIOError", "HTTP response code: 503")
        assert self._objects(store, version) == before
        again = _row(db, "dem", version)
        assert (again["status"], again["checked_at"], again["base_hashes"]) == ("ready", row["checked_at"], row["base_hashes"])
        wait_until(lambda: any(r.getMessage() == "overview retry ended" for r in caplog.records))
        retried = [r for r in caplog.records if r.getMessage() == "overview base tile omitted"]
        assert retried[-1].failure_kind == "source_5xx" and retried[-1].tile == "2/2/1"

    def test_a_tile_is_tried_once_an_hour_not_sooner(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor]
    ) -> None:
        version = self._pyramid(db, store, make, "patch_ok")
        make("patch_ok", **self.FAST_ROUND)  # the tile was tried a moment ago, by the build
        time.sleep(1.5)
        assert list(_omitted(db, "dem", version)) == ["2/1"]

    def test_a_retry_whose_step_breaks_for_another_reason_leaves_the_pyramid_as_it_is(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor], caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="earthx")
        version = self._pyramid(db, store, make, "patch_breaks")
        before = self._objects(store, version)
        _age_omitted(db, "dem", version)
        make("patch_breaks", **self.FAST_ROUND)
        wait_until(lambda: any(r.getMessage() == "overview retry failed" for r in caplog.records), 30)
        child = next(r for r in caplog.records if r.getMessage() == "overview child failed")
        assert (child.step, child.error, child.tile) == ("patch", "ArithmeticError", "2/2/1")
        assert list(_omitted(db, "dem", version)) == ["2/1"] and self._objects(store, version) == before

    def test_the_rows_of_a_pyramid_that_is_no_longer_ready_are_dropped(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor]
    ) -> None:
        version = self._pyramid(db, store, make, "patch_ok")
        db.execute("UPDATE public.earthx_overview SET status = 'failed', failure_kind = 'expired' WHERE dataset_id = 'dem'")
        make("patch_ok", **self.FAST_ROUND)
        wait_until(lambda: _omitted(db, "dem", version) == {}, 30)
        assert not any("made again" in str(v[0]) for v in self._objects(store, version).values())

    def test_no_retry_reads_from_a_host_a_build_is_reading_from(
        self, db: psycopg.Connection, store: Store, make: Callable[..., Supervisor]
    ) -> None:
        version = self._pyramid(db, store, make, "patch_ok")
        _age_omitted(db, "dem", version)
        db.execute(
            "INSERT INTO public.earthx_overview (dataset_id, version, status, hosts, worker, lease_until) "
            "VALUES ('proto-dem', 'bbbbbbbbbbbbbbbb', 'building', ARRAY['dem.example.invalid'], 'other', clock_timestamp() + interval '1 hour')"
        )
        make("patch_ok", **self.FAST_ROUND)
        time.sleep(1.5)
        assert list(_omitted(db, "dem", version)) == ["2/1"]
