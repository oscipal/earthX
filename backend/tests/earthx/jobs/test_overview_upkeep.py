"""Extension, expiry and orphans of the pyramids, against a real Postgres and a moto bucket
(M5-30b part 8b-3, adr/0032 §5.3, §8.4; Otto's answers 1 = 1 and 4 = 1 of 13.11.2026)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest

from earthx.jobs import overview_upkeep, overviews
from earthx.jobs.config import WorkerConfig
from earthx.jobs.worker import Supervisor
from earthx.objectstore.errors import ObjectStoreError
from earthx.objectstore.overviews import CHECKED_AT, upload_tile
from earthx.objectstore.results import Store
from tests.earthx.jobs.support import wait_until
from tests.earthx.objectstore.conftest import BUCKET

V1, V2, V3 = "1" * 16, "2" * 16, "3" * 16
LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def tile(tmp_path: Path) -> Path:
    path = tmp_path / "tile.tif"
    path.write_bytes(b"tile")
    return path


def _row(
    db: psycopg.Connection,
    dataset_id: str,
    version: str,
    *,
    status: str = "ready",
    checked: str | None = "5 days",
    confirmed: str | None = None,
) -> None:
    """A pyramid row; ``checked``/``confirmed`` say how long ago (``None`` for never)."""
    db.execute(
        """
        INSERT INTO public.earthx_overview
            (dataset_id, version, status, failure_kind, checked_at, confirmed_at, lease_until)
        VALUES (%(d)s, %(v)s, %(s)s,
                CASE WHEN %(s)s = 'failed' THEN 'source_4xx' END,
                CASE WHEN %(c)s::text IS NULL THEN NULL ELSE clock_timestamp() - %(c)s::interval END,
                CASE WHEN %(f)s::text IS NULL THEN NULL ELSE clock_timestamp() - %(f)s::interval END,
                CASE WHEN %(s)s = 'building' THEN clock_timestamp() + interval '1 hour' END)
        """,
        {"d": dataset_id, "v": version, "s": status, "c": checked, "f": confirmed},
    )


def _objects(store: Store, tile: Path, dataset_id: str, version: str, at: datetime = LONG_AGO, count: int = 2) -> None:
    for n in range(count):
        upload_tile(store, dataset_id, version, 1, n, 0, tile, checked_at=at)


def _keys(store: Store) -> list[str]:
    return sorted(store.s3.list_keys("overviews/"))


def _state(db: psycopg.Connection, dataset_id: str, version: str) -> tuple[str, str | None]:
    row = db.execute(
        "SELECT status, failure_kind FROM public.earthx_overview WHERE dataset_id = %s AND version = %s",
        (dataset_id, version),
    ).fetchone()
    assert row is not None
    return row


def _checked_at(db: psycopg.Connection, dataset_id: str, version: str) -> datetime:
    row = db.execute(
        "SELECT checked_at FROM public.earthx_overview WHERE dataset_id = %s AND version = %s", (dataset_id, version)
    ).fetchone()
    assert row is not None
    return row[0]


def _confirmed_time(db: psycopg.Connection, dataset_id: str, version: str) -> datetime:
    row = db.execute(
        "SELECT confirmed_at FROM public.earthx_overview WHERE dataset_id = %s AND version = %s", (dataset_id, version)
    ).fetchone()
    assert row is not None
    return row[0]


def _metadata(store: Store, key: str) -> dict:
    return store.s3._internal.head_object(Bucket=BUCKET, Key=key)["Metadata"]


class TestToExtend:
    def test_only_a_confirmation_newer_than_checked_at_asks_for_an_extension(self, db: psycopg.Connection) -> None:
        _row(db, "dem", V1, checked="20 days", confirmed="1 day")
        _row(db, "dem", V2, checked="20 days", confirmed=None)
        _row(db, "dem", V3, checked="2 days", confirmed="10 days")
        assert [(d, v) for d, v, _ in overviews.to_extend(db, {"dem"})] == [("dem", V1)]

    def test_only_a_ready_pyramid_of_a_dataset_this_worker_knows_and_never_a_prototype_source(
        self, db: psycopg.Connection
    ) -> None:
        _row(db, "dem", V1, checked="20 days", confirmed="1 day")
        _row(db, "land", V1, checked="20 days", confirmed="1 day")
        _row(db, "proto-dem", V1, checked="3 days", confirmed="1 day")
        _row(db, "dem", V2, status="failed", checked=None, confirmed="1 day")
        assert [(d, v) for d, v, _ in overviews.to_extend(db, {"dem", "proto-dem"})] == [("dem", V1)]


class TestExtend:
    def test_a_confirmed_pyramid_is_extended_without_a_read_at_the_source(
        self, db: psycopg.Connection, store: Store, tile: Path
    ) -> None:
        _row(db, "dem", V1, checked="20 days", confirmed="1 hour")
        _objects(store, tile, "dem", V1)
        confirmed = _confirmed_time(db, "dem", V1)

        assert overview_upkeep.extend(db, store, {"dem"}, threading.Event()) == 1

        assert _checked_at(db, "dem", V1) == confirmed
        assert {_metadata(store, key)[CHECKED_AT] for key in _keys(store)} == {confirmed.isoformat()}
        assert overviews.to_extend(db, {"dem"}) == [], "extended once, not again"

    def test_a_pyramid_nobody_confirmed_is_not_extended(self, db: psycopg.Connection, store: Store, tile: Path) -> None:
        """No `materialize` run, or one the source did not answer: no `confirmed_at`, no extension."""
        _row(db, "dem", V1, checked="20 days", confirmed=None)
        _objects(store, tile, "dem", V1)
        before = _checked_at(db, "dem", V1)
        assert overview_upkeep.extend(db, store, {"dem"}, threading.Event()) == 0
        assert _checked_at(db, "dem", V1) == before
        assert {_metadata(store, key)[CHECKED_AT] for key in _keys(store)} == {LONG_AGO.isoformat()}

    def test_a_confirmation_older_than_checked_at_changes_nothing(
        self, db: psycopg.Connection, store: Store, tile: Path
    ) -> None:
        _row(db, "dem", V1, checked="2 days", confirmed="9 days")
        _objects(store, tile, "dem", V1)
        assert overview_upkeep.extend(db, store, {"dem"}, threading.Event()) == 0
        assert {_metadata(store, key)[CHECKED_AT] for key in _keys(store)} == {LONG_AGO.isoformat()}

    def test_a_prototype_source_is_never_extended_even_when_confirmed(
        self, db: psycopg.Connection, store: Store, tile: Path
    ) -> None:
        _row(db, "proto-dem", V1, checked="5 days", confirmed="1 hour")
        _objects(store, tile, "proto-dem", V1)
        assert overview_upkeep.extend(db, store, {"proto-dem"}, threading.Event()) == 0
        assert {_metadata(store, key)[CHECKED_AT] for key in _keys(store)} == {LONG_AGO.isoformat()}

    def test_other_versions_and_datasets_are_left_alone(self, db: psycopg.Connection, store: Store, tile: Path) -> None:
        _row(db, "dem", V1, checked="20 days", confirmed="1 hour")
        _row(db, "dem", V2, checked="20 days", confirmed=None)
        _objects(store, tile, "dem", V1)
        _objects(store, tile, "dem", V2)
        overview_upkeep.extend(db, store, {"dem"}, threading.Event())
        assert {_metadata(store, key)[CHECKED_AT] for key in _keys(store) if f"/{V2}/" in key} == {LONG_AGO.isoformat()}

    def test_a_pyramid_whose_objects_are_gone_is_expired_instead_of_extended(
        self, db: psycopg.Connection, store: Store
    ) -> None:
        """The bucket rule was faster than the confirmation: the next version builds a new one."""
        _row(db, "dem", V1, checked="40 days", confirmed="1 hour")
        assert overview_upkeep.extend(db, store, {"dem"}, threading.Event()) == 0
        assert _state(db, "dem", V1) == ("failed", "expired")

    def test_a_store_that_fails_keeps_the_row_as_it_was_so_the_next_round_tries_again(
        self, db: psycopg.Connection, store: Store, tile: Path
    ) -> None:
        _row(db, "dem", V1, checked="20 days", confirmed="1 hour")
        _objects(store, tile, "dem", V1)
        before = _checked_at(db, "dem", V1)
        working = store.s3.rewrite_object
        calls: list[str] = []

        def rewrite_once_then_fail(key: str, **kwargs: Any) -> None:
            calls.append(key)
            if len(calls) == 2:
                raise RuntimeError("the store went away")
            working(key, **kwargs)

        object.__setattr__(store.s3, "rewrite_object", rewrite_once_then_fail)
        with pytest.raises(RuntimeError):
            overview_upkeep.extend(db, store, {"dem"}, threading.Event())
        assert _checked_at(db, "dem", V1) == before, "checked_at moves only after every object has the new time"
        assert _state(db, "dem", V1) == ("ready", None)

    def test_a_stopping_worker_extends_nothing_more(self, db: psycopg.Connection, store: Store, tile: Path) -> None:
        _row(db, "dem", V1, checked="20 days", confirmed="1 hour")
        _objects(store, tile, "dem", V1)
        stopping = threading.Event()
        stopping.set()
        assert overview_upkeep.extend(db, store, {"dem"}, stopping) == 0


class TestExpiry:
    def test_a_pyramid_past_its_term_loses_its_objects_and_is_closed_as_expired(
        self, db: psycopg.Connection, store: Store, tile: Path
    ) -> None:
        _row(db, "dem", V1, checked="31 days")
        _row(db, "dem", V2, checked="29 days")
        _objects(store, tile, "dem", V1)
        _objects(store, tile, "dem", V2)
        swept = overview_upkeep.sweep(db, store)
        assert swept.expired == 1
        assert _state(db, "dem", V1) == ("failed", "expired") and _state(db, "dem", V2) == ("ready", None)
        assert all(f"/{V2}/" in key for key in _keys(store)) and len(_keys(store)) == 2

    def test_a_prototype_source_lives_seven_days_not_thirty(self, db: psycopg.Connection, store: Store, tile: Path) -> None:
        _row(db, "proto-dem", V1, checked="8 days")
        _row(db, "proto-dem", V2, checked="6 days")
        _row(db, "dem", V3, checked="8 days")
        for dataset_id, version in (("proto-dem", V1), ("proto-dem", V2), ("dem", V3)):
            _objects(store, tile, dataset_id, version)
        assert overview_upkeep.sweep(db, store).expired == 1
        assert _state(db, "proto-dem", V1) == ("failed", "expired")
        assert _state(db, "proto-dem", V2) == ("ready", None) and _state(db, "dem", V3) == ("ready", None)

    def test_a_pyramid_the_source_confirmed_is_left_to_the_extension_not_expired(
        self, db: psycopg.Connection, store: Store, tile: Path
    ) -> None:
        _row(db, "dem", V1, checked="35 days", confirmed="1 hour")
        _objects(store, tile, "dem", V1)
        assert overview_upkeep.sweep(db, store).expired == 0
        assert _state(db, "dem", V1) == ("ready", None) and len(_keys(store)) == 2

    def test_an_expired_pyramid_is_not_asked_for_again_by_the_hourly_round(self, db: psycopg.Connection, store: Store) -> None:
        db.execute("INSERT INTO public.earthx_materialize_runs (dataset_id, started_at, finished_at, status, source_version, items_written, items_deleted, listed, missing, withheld) VALUES ('dem', now(), now(), 'loaded', 'v1', 1, 0, 1, 0, 0)")
        version = db.execute("SELECT public.earthx_overview_version('v1')").fetchone()[0]
        _row(db, "dem", version, checked="40 days")
        overview_upkeep.sweep(db, store)
        assert overviews.request_missing(db, ["dem"]) == 0

    def test_building_and_failed_rows_never_expire(self, db: psycopg.Connection, store: Store) -> None:
        _row(db, "dem", V1, status="building", checked=None)
        _row(db, "dem", V2, status="failed", checked=None)
        assert overview_upkeep.sweep(db, store).expired == 0

    def test_a_store_that_fails_leaves_the_row_ready_for_the_next_round(
        self, db: psycopg.Connection, store: Store, tile: Path
    ) -> None:
        _row(db, "dem", V1, checked="31 days")
        _objects(store, tile, "dem", V1)

        def refuse(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("the store went away")

        object.__setattr__(store.s3, "delete_objects", refuse)
        with pytest.raises(RuntimeError):
            overview_upkeep.sweep(db, store)
        assert _state(db, "dem", V1) == ("ready", None)


class TestOrphans:
    def test_objects_without_a_row_are_deleted_and_the_others_stay(
        self, db: psycopg.Connection, store: Store, tile: Path
    ) -> None:
        _row(db, "dem", V1)
        _row(db, "dem", V2, status="building", checked=None)
        _row(db, "dem", V3, status="failed", checked=None)
        for version in (V1, V2, V3):
            _objects(store, tile, "dem", version, count=1)
        _objects(store, tile, "dem", "4" * 16, count=1)
        _objects(store, tile, "gone", V1, count=1)
        swept = overview_upkeep.sweep(db, store)
        assert swept.orphans == 2
        assert [key.split("/")[1:3] for key in _keys(store)] == [["dem", V1], ["dem", V2], ["dem", V3]]

    def test_the_rows_of_a_prototype_source_that_catalog_load_removed_leave_orphans_that_go(
        self, db: psycopg.Connection, store: Store, tile: Path
    ) -> None:
        _row(db, "proto-dem", V1, checked="1 day")
        _objects(store, tile, "proto-dem", V1)
        db.execute("DELETE FROM public.earthx_overview WHERE dataset_id LIKE 'proto-%'")
        assert overview_upkeep.sweep(db, store).orphans == 2
        assert _keys(store) == []

    def test_a_key_of_no_known_shape_under_the_prefix_is_deleted_and_results_are_not_touched(
        self, db: psycopg.Connection, store: Store, tile: Path
    ) -> None:
        store.s3.put_object("overviews/stray.tif", tile.open("rb"), "image/tiff")
        store.s3.put_object("overviews/dem/stray", tile.open("rb"), "image/tiff")
        store.s3.put_object("results/abc/result.tif", tile.open("rb"), "image/tiff")
        assert overview_upkeep.sweep(db, store).orphans == 2
        assert sorted(store.s3.list_keys("")) == ["results/abc/result.tif"]

    def test_the_keys_are_listed_before_the_rows_are_read(
        self, db: psycopg.Connection, store: Store, tile: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A build that claims its row between the two steps keeps its objects: it is in the rows the sweep reads last."""
        _objects(store, tile, "dem", V1, count=1)
        listing = overview_upkeep.overview_keys

        def listed_then_claimed(s: Store) -> Iterator[str]:
            keys = list(listing(s))
            _row(db, "dem", V1, status="building", checked=None)
            return iter(keys)

        monkeypatch.setattr(overview_upkeep, "overview_keys", listed_then_claimed)
        assert overview_upkeep.sweep(db, store).orphans == 0
        assert len(_keys(store)) == 1

    def test_an_empty_store_and_empty_tables_are_fine(self, db: psycopg.Connection, store: Store) -> None:
        assert overview_upkeep.sweep(db, store) == overview_upkeep.Swept(0, 0)

    def test_the_log_counts_and_names_nothing(
        self, db: psycopg.Connection, store: Store, tile: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="earthx")
        _row(db, "dem", V1, checked="31 days")
        _objects(store, tile, "dem", V1)
        _objects(store, tile, "stranger", V2)
        overview_upkeep.sweep(db, store)
        text = " ".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
        assert "overview pyramids swept" in text
        assert "stranger" not in text and V1 not in text and "overviews/" not in text


FAST: dict[str, Any] = {
    "slots": 1,
    "lease_seconds": 3.0,
    "heartbeat_seconds": 0.3,
    "poll_seconds": 0.2,
    "sweep_seconds": 0.3,
    "progress_seconds": 0.0,
    "cleanup_first_seconds": 0.3,
    "cleanup_seconds": 1e9,
    "backoff_seconds": 0.0,
}


@pytest.fixture
def start(db: psycopg.Connection, store: Store, tmp_path: Path) -> Iterator[Callable[..., Supervisor]]:
    made: list[Supervisor] = []

    def run(**kwargs: Any) -> Supervisor:
        supervisor = Supervisor(WorkerConfig(**{**FAST, "workdir": tmp_path / f"w{len(made)}"}), store, **kwargs)
        made.append(supervisor)
        supervisor.start()
        return supervisor

    yield run
    for supervisor in made:
        supervisor.stop(30)


class TestInTheWorker:
    def test_the_thread_of_the_builds_extends_a_confirmed_pyramid_in_its_hourly_round(
        self, db: psycopg.Connection, store: Store, tile: Path, start: Callable[..., Supervisor]
    ) -> None:
        _row(db, "dem", V1, checked="20 days", confirmed="1 hour")
        _objects(store, tile, "dem", V1)
        confirmed = _confirmed_time(db, "dem", V1)
        start(pyramids={"dem": ("dem.example.invalid",)})
        wait_until(lambda: _checked_at(db, "dem", V1) == confirmed, 15)
        assert {_metadata(store, key)[CHECKED_AT] for key in _keys(store)} == {confirmed.isoformat()}

    def test_a_dataset_the_worker_does_not_know_is_not_extended(
        self, db: psycopg.Connection, store: Store, tile: Path, start: Callable[..., Supervisor]
    ) -> None:
        _row(db, "other", V1, checked="20 days", confirmed="1 hour")
        _objects(store, tile, "other", V1)
        start(pyramids={"dem": ("dem.example.invalid",)})
        time.sleep(1.5)
        assert {_metadata(store, key)[CHECKED_AT] for key in _keys(store)} == {LONG_AGO.isoformat()}

    def test_the_hourly_round_of_the_maintenance_thread_expires_and_deletes_orphans(
        self, db: psycopg.Connection, store: Store, tile: Path, start: Callable[..., Supervisor]
    ) -> None:
        _row(db, "dem", V1, checked="31 days")
        _objects(store, tile, "dem", V1)
        _objects(store, tile, "dem", V2)
        start()
        wait_until(lambda: _keys(store) == [], 15)
        assert _state(db, "dem", V1) == ("failed", "expired")

    def test_a_store_that_fails_under_the_sweep_does_not_stop_the_worker(
        self, db: psycopg.Connection, store: Store, tile: Path, start: Callable[..., Supervisor]
    ) -> None:
        _row(db, "dem", V1, checked="31 days")
        _objects(store, tile, "dem", V1)

        def refuse(*args: Any, **kwargs: Any) -> None:
            raise ObjectStoreError("object store DeleteObjects failed")

        object.__setattr__(store.s3, "delete_objects", refuse)
        supervisor = start()
        time.sleep(1.5)
        assert supervisor.healthy()
        assert _state(db, "dem", V1) == ("ready", None)
