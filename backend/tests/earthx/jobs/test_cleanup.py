"""Cleaning up after the expiry (adr/0013 §8 point 8, adr/0015 §12 point 9, F13; plan M4-08a §3.7)."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from earthx.jobs import bundles, permalinks
from earthx.jobs.cleanup import CleanupResult, cleanup, cleanup_batch
from earthx.jobs.config import WorkerConfig
from earthx.jobs.queue import CLEANUP_LOCK_KEY
from earthx.jobs.submit import dismiss, job_run, job_status, restore, submit
from earthx.jobs.worker import Supervisor
from earthx.objectstore.errors import StoreUnavailable
from earthx.objectstore.results import Store, delete_result, new_result_id, upload_result
from earthx.processing.recipe import cache_key
from tests.conftest import own_log_text
from tests.earthx.jobs.support import add_run, make_recipe, run_row, wait_until


def _count(db: psycopg.Connection, table: str) -> int:
    row = db.execute(f"SELECT count(*) FROM public.{table}").fetchone()
    assert row is not None
    return row[0]


def _tables(db: psycopg.Connection) -> tuple[int, int, int]:
    return _count(db, "earthx_recipe"), _count(db, "earthx_run"), _count(db, "earthx_job")


def _stored_result(store: Store, tmp_path: Path) -> str:
    result_id = new_result_id()
    path = tmp_path / "x.tif"
    path.write_bytes(b"bytes")
    for name in ("result.tif", "mask.tif"):
        upload_result(store, result_id, name, path)
    return result_id


class TestExpiry:
    def test_what_expired_goes_with_its_objects_and_what_did_not_stays(
        self, db: psycopg.Connection, store: Store, tmp_path: Path
    ) -> None:
        gone, kept = _stored_result(store, tmp_path), _stored_result(store, tmp_path)
        add_run(db, status="successful", result_id=gone, expires_in="-1 minute", jobs=2)
        add_run(db, status="successful", result_id=kept, expires_in="3 days", jobs=2)
        add_run(db, status="failed", expires_in="-1 day")
        result = cleanup(db, store)
        assert (result.runs, result.jobs, result.recipes, result.objects) == (2, 3, 2, 1)
        assert _tables(db) == (1, 1, 2)
        assert sorted(store.s3.list_keys("results/")) == [f"results/{kept}/mask.tif", f"results/{kept}/result.tif"]

    def test_nothing_expired_changes_nothing(self, db: psycopg.Connection, store: Store) -> None:
        add_run(db, status="successful", result_id="R" * 22, expires_in="1 hour")
        add_run(db)
        assert cleanup(db, store).total == 0
        assert _tables(db) == (2, 2, 2)

    def test_a_run_that_is_running_is_left_to_the_lease_sweeper(self, db: psycopg.Connection, store: Store) -> None:
        add_run(db, status="running", expires_in="-1 day", lease_seconds=60)
        assert cleanup(db, store).total == 0
        assert _count(db, "earthx_run") == 1

    def test_a_run_that_never_started_goes_after_its_term_too(self, db: psycopg.Connection, store: Store) -> None:
        add_run(db, status="accepted", expires_in="-1 second")
        assert cleanup(db, store).runs == 1

    def test_a_finished_object_that_is_already_gone_is_no_problem(self, db: psycopg.Connection, store: Store) -> None:
        add_run(db, status="successful", result_id=new_result_id(), expires_in="-1 hour")
        assert cleanup(db, store).runs == 1


class TestPermalinks:
    """M4-19e: a fixed term of 30 days from creation; the row goes whole, and looking never lengthens it."""

    @staticmethod
    def _made(db: psycopg.Connection, age: str) -> str:
        made = permalinks.create(db, {"order": {"aoi": "9.01 47.01"}, "view": {}})
        db.execute(
            "UPDATE public.earthx_permalink SET created_at = clock_timestamp() - %s::interval, "
            "expires_at = clock_timestamp() + interval '30 days' - %s::interval WHERE permalink_id = %s",
            (age, age, made.permalink_id),
        )
        return made.permalink_id

    def test_after_30_days_the_row_is_gone_whole_and_before_it_stays(
        self, db: psycopg.Connection, store: Store
    ) -> None:
        old, young = self._made(db, "30 days 1 minute"), self._made(db, "29 days 23 hours")
        assert permalinks.read(db, old) is None  # already refused before the cleanup came
        result = cleanup(db, store)
        assert result.permalinks == 1 and result.total == 1
        assert [r[0] for r in db.execute("SELECT permalink_id FROM public.earthx_permalink")] == [young]
        assert permalinks.read(db, young) is not None

    def test_reading_does_not_move_the_term(self, db: psycopg.Connection, store: Store) -> None:
        made = permalinks.create(db, {"order": {}, "view": {}})
        for _ in range(3):
            assert permalinks.read(db, made.permalink_id) is not None
        row = db.execute("SELECT expires_at FROM public.earthx_permalink").fetchone()
        assert row is not None and row[0] == made.expires_at
        assert made.expires_at - datetime.now(UTC) <= permalinks.TTL

    def test_batches_go_on_until_none_is_left(self, db: psycopg.Connection, store: Store) -> None:
        for _ in range(5):
            self._made(db, "31 days")
        assert cleanup(db, store, batch=2).permalinks == 5 and _count(db, "earthx_permalink") == 0


class TestBundles:
    """UI-01e: the term is the one stored at creation; the row goes whole, and looking never lengthens it."""

    @staticmethod
    def _made(db: psycopg.Connection, ends_in: str) -> str:
        bundle_id = bundles.create(db, ["A" * 22], datetime.now(UTC))
        db.execute(
            "UPDATE public.earthx_bundle SET expires_at = clock_timestamp() + %s::interval WHERE bundle_id = %s",
            (ends_in, bundle_id),
        )
        return bundle_id

    def test_what_has_expired_is_gone_whole_and_the_rest_stays(self, db: psycopg.Connection, store: Store) -> None:
        old, young = self._made(db, "-1 minute"), self._made(db, "1 minute")
        assert bundles.read(db, old) is None  # already refused before the cleanup came
        result = cleanup(db, store)
        assert result.bundles == 1 and result.total == 1
        assert [r[0] for r in db.execute("SELECT bundle_id FROM public.earthx_bundle")] == [young]
        assert bundles.read(db, young) is not None

    def test_reading_does_not_move_the_term(self, db: psycopg.Connection, store: Store) -> None:
        bundle_id = self._made(db, "1 day")
        before = db.execute("SELECT expires_at FROM public.earthx_bundle").fetchone()
        for _ in range(3):
            assert bundles.read(db, bundle_id) is not None
        assert db.execute("SELECT expires_at FROM public.earthx_bundle").fetchone() == before

    def test_batches_go_on_until_none_is_left(self, db: psycopg.Connection, store: Store) -> None:
        for _ in range(5):
            self._made(db, "-1 day")
        assert cleanup(db, store, batch=2).bundles == 5 and _count(db, "earthx_bundle") == 0

    def test_a_malformed_identifier_is_none_and_never_reaches_a_row(self, db: psycopg.Connection) -> None:
        assert not bundles.is_bundle_id("short") and not bundles.is_bundle_id("A" * 21 + "%")
        assert bundles.is_bundle_id("A" * 22)


def _delete(db: psycopg.Connection, job_id: str, *, ended: bool = True) -> None:
    """Delete the job as `api` does; with ``ended`` the term is over by a second."""
    assert dismiss(db, job_id) is not None
    if ended:
        db.execute(
            "UPDATE public.earthx_job SET deleted_until = clock_timestamp() - interval '1 second' WHERE job_id = %s",
            (job_id,),
        )


def _keys(store: Store) -> list[str]:
    return sorted(store.s3.list_keys("results/"))


class TestDeletedJobs:
    """NM4-27: a deleted job goes when its term ends, and the result with it only if no other job needs it."""

    def test_the_only_job_takes_the_run_the_object_and_the_recipe_with_it(
        self, db: psycopg.Connection, store: Store, tmp_path: Path
    ) -> None:
        _, (job_id,) = add_run(db, status="successful", result_id=_stored_result(store, tmp_path), expires_in="6 days")
        _delete(db, job_id)
        result = cleanup(db, store)
        assert (result.deleted_jobs, result.runs, result.objects, result.recipes) == (1, 1, 1, 1)
        assert _tables(db) == (0, 0, 0)
        assert _keys(store) == []

    def test_inside_the_term_nothing_goes(self, db: psycopg.Connection, store: Store, tmp_path: Path) -> None:
        result_id = _stored_result(store, tmp_path)
        _, (job_id,) = add_run(db, status="successful", result_id=result_id, expires_in="6 days")
        _delete(db, job_id, ended=False)
        assert cleanup(db, store).total == 0
        assert _tables(db) == (1, 1, 1) and len(_keys(store)) == 2
        assert restore(db, job_id) is not None

    def test_a_failed_job_goes_without_an_object(self, db: psycopg.Connection, store: Store) -> None:
        _, (job_id,) = add_run(db, status="failed", expires_in="6 days")
        _delete(db, job_id)
        assert cleanup(db, store).objects == 0
        assert _tables(db) == (0, 0, 0)

    def test_a_job_that_lives_keeps_the_object_the_run_and_its_recipe(
        self, db: psycopg.Connection, store: Store, tmp_path: Path
    ) -> None:
        recipe = make_recipe()
        result_id = _stored_result(store, tmp_path)
        run_id, (first,) = add_run(
            db, status="successful", key=cache_key(recipe), result_id=result_id, expires_in="6 days"
        )
        second = submit(db, recipe)
        assert job_run(db, second) == run_id, "a hit, on a recipe of its own"
        _delete(db, first)
        result = cleanup(db, store)
        assert (result.deleted_jobs, result.runs, result.objects, result.recipes) == (1, 0, 0, 1)
        assert _count(db, "earthx_run") == 1 and _count(db, "earthx_job") == 1
        assert len(_keys(store)) == 2
        status = job_status(db, second)
        assert status is not None and status.status == "successful" and status.result_id == result_id

    def test_the_run_is_left_with_a_recipe_that_stays(self, db: psycopg.Connection, store: Store) -> None:
        recipe = make_recipe()
        run_id, (first,) = add_run(
            db, status="successful", key=cache_key(recipe), result_id="R" * 22, expires_in="6 days"
        )
        second = submit(db, recipe)
        gone = run_row(db, run_id, "recipe_id")[0]
        _delete(db, first)
        cleanup(db, store)
        status = job_status(db, second)
        assert status is not None
        assert run_row(db, run_id, "recipe_id") == (status.recipe_id,) and status.recipe_id != gone
        assert db.execute("SELECT count(*) FROM public.earthx_recipe WHERE recipe_id = %s", (gone,)).fetchone() == (0,)

    def test_a_job_still_inside_its_term_keeps_the_object_for_its_restore(
        self, db: psycopg.Connection, store: Store, tmp_path: Path
    ) -> None:
        result_id = _stored_result(store, tmp_path)
        _, (early, late) = add_run(db, status="successful", result_id=result_id, expires_in="6 days", jobs=2)
        _delete(db, early)
        _delete(db, late, ended=False)
        result = cleanup(db, store)
        assert (result.deleted_jobs, result.runs, result.objects) == (1, 0, 0)
        assert len(_keys(store)) == 2
        restored = restore(db, late)
        assert restored is not None and restored.status == "successful" and restored.result_id == result_id

    def test_a_dismissed_job_does_not_keep_the_object(
        self, db: psycopg.Connection, store: Store, tmp_path: Path
    ) -> None:
        _, (deleted, dismissed) = add_run(
            db, status="successful", result_id=_stored_result(store, tmp_path), expires_in="6 days", jobs=2
        )
        db.execute("UPDATE public.earthx_job SET dismissed = true WHERE job_id = %s", (dismissed,))
        _delete(db, deleted)
        assert cleanup(db, store).runs == 1
        assert _tables(db) == (0, 0, 0) and _keys(store) == []

    def test_a_job_that_hangs_on_the_run_while_the_cleanup_waits_for_it_keeps_the_object(
        self, db: psycopg.Connection, store: Store, tmp_path: Path
    ) -> None:
        """What `submit` does for a hit: it holds the run, adds its job, and only then lets the cleanup in."""
        result_id = _stored_result(store, tmp_path)
        run_id, (job_id,) = add_run(db, status="successful", result_id=result_id, expires_in="6 days")
        recipe_id = db.execute("SELECT recipe_id FROM public.earthx_job").fetchone()[0]
        _delete(db, job_id)
        outcome: list[CleanupResult] = []

        def sweep() -> None:
            with psycopg.connect(autocommit=True) as conn:
                outcome.append(cleanup(conn, store))

        with psycopg.connect(autocommit=True) as holder, holder.transaction():
            holder.execute("SELECT 1 FROM public.earthx_run WHERE run_id = %s FOR SHARE", (run_id,))
            thread = threading.Thread(target=sweep)
            thread.start()
            wait_until(
                lambda: (
                    db.execute(
                        "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' AND datname = current_database()"
                    ).fetchone()
                    == (1,)
                )
            )
            holder.execute(
                "INSERT INTO public.earthx_job (job_id, run_id, recipe_id) VALUES (%s, %s, %s)",
                ("N" * 22, run_id, recipe_id),
            )
        thread.join(20)
        assert [(r.deleted_jobs, r.runs, r.objects) for r in outcome] == [(1, 0, 0)]
        assert _count(db, "earthx_run") == 1 and len(_keys(store)) == 2
        assert db.execute("SELECT job_id FROM public.earthx_job").fetchall() == [("N" * 22,)]

    def test_when_the_store_fails_the_job_stays_and_the_next_try_finishes(
        self, db: psycopg.Connection, store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, (job_id,) = add_run(db, status="successful", result_id=_stored_result(store, tmp_path), expires_in="6 days")
        _delete(db, job_id)

        def fails(store: Store, result_id: str) -> None:
            raise StoreUnavailable("the store did not answer")

        monkeypatch.setattr("earthx.jobs.cleanup.delete_result", fails)
        with pytest.raises(StoreUnavailable):
            cleanup(db, store)
        assert _tables(db) == (1, 1, 1) and len(_keys(store)) == 2
        monkeypatch.setattr("earthx.jobs.cleanup.delete_result", delete_result)
        assert cleanup(db, store).deleted_jobs == 1
        assert _tables(db) == (0, 0, 0) and _keys(store) == []

    def test_it_works_in_batches_until_nothing_is_left(self, db: psycopg.Connection, store: Store) -> None:
        for _ in range(7):
            _delete(db, add_run(db, status="failed", expires_in="6 days")[1][0])
        add_run(db, status="failed", expires_in="6 days")
        assert cleanup(db, store, batch=3).deleted_jobs == 7
        assert _tables(db) == (1, 1, 1)

    def test_the_log_names_numbers_and_nothing_else(
        self, db: psycopg.Connection, store: Store, caplog: pytest.LogCaptureFixture
    ) -> None:
        _, (job_id,) = add_run(db, status="successful", result_id="R" * 22, expires_in="6 days")
        recipe_id = db.execute("SELECT recipe_id FROM public.earthx_job").fetchone()[0]
        _delete(db, job_id)
        with caplog.at_level(logging.DEBUG, logger="earthx"):
            cleanup(db, store)
        text = "\n".join(own_log_text(record) for record in caplog.records)
        assert caplog.records and "deleted_jobs" in text
        for forbidden in (job_id, recipe_id, "R" * 22):
            assert forbidden not in text


class TestObjectsBeforeRows:
    def test_when_the_store_fails_no_row_is_deleted_and_the_next_try_finishes(
        self, db: psycopg.Connection, store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result_id = _stored_result(store, tmp_path)
        add_run(db, status="successful", result_id=result_id, expires_in="-1 hour")
        add_run(db, status="failed", expires_in="-1 hour")
        before = _tables(db)

        def fails(store: Store, result_id: str) -> None:
            raise StoreUnavailable("the store did not answer")

        monkeypatch.setattr("earthx.jobs.cleanup.delete_result", fails)
        with pytest.raises(StoreUnavailable):
            cleanup(db, store)
        assert _tables(db) == before
        assert len(list(store.s3.list_keys("results/"))) == 2
        monkeypatch.setattr(
            "earthx.jobs.cleanup.delete_result", delete_result
        )  # not `undo()`: it would also drop the moto endpoint
        assert cleanup(db, store).runs == 2
        assert _tables(db) == (0, 0, 0)
        assert list(store.s3.list_keys("results/")) == []

    def test_an_object_that_is_deleted_comes_before_the_row_that_names_it(
        self, db: psycopg.Connection, store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        add_run(db, status="successful", result_id=_stored_result(store, tmp_path), expires_in="-1 hour")
        seen: list[int] = []

        def watch(store: Store, result_id: str) -> None:
            seen.append(_count(db, "earthx_run"))  # a second connection sees the rows as they were committed

        monkeypatch.setattr("earthx.jobs.cleanup.delete_result", watch)
        cleanup(db, store)
        assert seen == [1], "the row was still there when the object was deleted"


class TestBatches:
    def test_it_works_in_batches_until_nothing_is_left(self, db: psycopg.Connection, store: Store) -> None:
        for _ in range(7):
            add_run(db, status="failed", expires_in="-1 hour")
        add_run(db, status="failed", expires_in="2 days")
        assert cleanup_batch(db, store, batch=3).runs == 3  # type: ignore[union-attr]
        assert _count(db, "earthx_run") == 5
        result = cleanup(db, store, batch=3)
        assert (result.runs, result.jobs) == (4, 4)
        assert _tables(db) == (1, 1, 1)

    def test_only_one_supervisor_cleans_at_a_time(self, db: psycopg.Connection, store: Store) -> None:
        add_run(db, status="failed", expires_in="-1 hour")
        with psycopg.connect(autocommit=True) as other, other.transaction():
            other.execute("SELECT pg_advisory_xact_lock(%s)", (CLEANUP_LOCK_KEY,))
            assert cleanup_batch(db, store) is None
            assert _count(db, "earthx_run") == 1
        assert cleanup_batch(db, store) is not None
        assert _count(db, "earthx_run") == 0

    def test_two_cleaners_at_the_same_time_delete_each_row_once(self, db: psycopg.Connection, store: Store) -> None:
        for _ in range(20):
            add_run(db, status="failed", expires_in="-1 hour")
        barrier = threading.Barrier(2)
        totals: list[int] = []

        def work() -> None:
            with psycopg.connect(autocommit=True) as conn:
                barrier.wait()
                totals.append(cleanup(conn, store, batch=5).runs)

        threads = [threading.Thread(target=work) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        assert sum(totals) == 20, "each row was deleted once, by whichever cleaner held the lock"
        assert _tables(db) == (0, 0, 0)


class TestRecipes:
    """Adr/0015 F13: a recipe lives while a job or run refers to it; only a run or a hit lengthens that."""

    def test_a_recipe_goes_with_its_run_and_not_with_another_result_of_the_same_order(
        self, db: psycopg.Connection, store: Store
    ) -> None:
        recipe = make_recipe()
        job = submit(db, recipe)
        recipe_id = job_status(db, job).recipe_id  # type: ignore[union-attr]
        db.execute("UPDATE public.earthx_run SET expires_at = clock_timestamp() - interval '1 hour'")
        # A later order hangs on a result of the same key only through a run of its own:
        add_run(db, status="successful", result_id="R" * 22, expires_in="5 days")
        cleanup(db, store)
        assert db.execute(
            "SELECT count(*) FROM public.earthx_recipe WHERE recipe_id = %s", (recipe_id,)
        ).fetchone() == (0,)
        assert _count(db, "earthx_recipe") == 1

    def test_a_recipe_with_only_a_dismissed_job_stays_until_the_run_expires(
        self, db: psycopg.Connection, store: Store
    ) -> None:
        _, (job_id,) = add_run(db, status="successful", result_id="R" * 22, expires_in="2 days")
        db.execute("UPDATE public.earthx_job SET dismissed = true WHERE job_id = %s", (job_id,))
        cleanup(db, store)
        assert _tables(db) == (1, 1, 1)

    def test_looking_at_a_job_does_not_lengthen_its_recipe_s_life(self, db: psycopg.Connection, store: Store) -> None:
        _, (job_id,) = add_run(db, status="successful", result_id="R" * 22, expires_in="-1 minute")
        for _ in range(3):
            assert job_status(db, job_id) is not None
        assert cleanup(db, store).recipes == 1
        assert _tables(db) == (0, 0, 0)

    def test_a_cache_hit_gives_the_new_recipe_the_life_of_the_result_it_uses(
        self, db: psycopg.Connection, store: Store
    ) -> None:
        recipe = make_recipe()
        from earthx.processing.recipe import cache_key

        add_run(db, status="successful", key=cache_key(recipe), result_id="R" * 22, expires_in="30 hours")
        hit = submit(db, recipe)
        run_id = db.execute("SELECT run_id FROM public.earthx_job WHERE job_id = %s", (hit,)).fetchone()
        assert run_id is not None
        db.execute("UPDATE public.earthx_run SET expires_at = clock_timestamp() - interval '1 second'")
        result = cleanup(db, store)
        assert (result.runs, result.jobs, result.recipes) == (1, 2, 2), "the hit's recipe goes with the result it used"

    def test_an_orphan_recipe_is_deleted_and_one_with_a_run_is_not(self, db: psycopg.Connection, store: Store) -> None:
        db.execute("INSERT INTO public.earthx_recipe (recipe_id, body) VALUES ('o' || repeat('x', 21), '{}')")
        add_run(db)
        assert cleanup(db, store).recipes == 1
        assert _tables(db) == (1, 1, 1)


class TestInTheSupervisor:
    def test_the_supervisor_cleans_up_on_its_own_schedule(
        self, db: psycopg.Connection, store: Store, tmp_path: Path
    ) -> None:
        add_run(db, status="failed", expires_in="-1 hour")
        config = WorkerConfig(
            slots=1,
            lease_seconds=3.0,
            heartbeat_seconds=0.3,
            poll_seconds=0.2,
            sweep_seconds=0.2,
            cleanup_first_seconds=0.2,
            cleanup_seconds=3600.0,
            workdir=tmp_path / "work",
        )
        supervisor = Supervisor(config, store)
        supervisor.start()
        try:
            wait_until(lambda: _tables(db) == (0, 0, 0), timeout=15)
        finally:
            supervisor.stop(30)

    def test_a_failing_store_does_not_stop_the_supervisor(
        self, db: psycopg.Connection, store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        add_run(db, status="successful", result_id=new_result_id(), expires_in="-1 hour")
        calls: list[int] = []

        def fails(store: Store, result_id: str) -> None:
            calls.append(1)
            raise StoreUnavailable("the store did not answer")

        monkeypatch.setattr("earthx.jobs.cleanup.delete_result", fails)
        config = WorkerConfig(
            slots=1, sweep_seconds=0.2, cleanup_first_seconds=0.1, cleanup_seconds=0.2, workdir=tmp_path / "w"
        )
        supervisor = Supervisor(config, store)
        supervisor.start()
        try:
            wait_until(lambda: len(calls) >= 2, timeout=15)
            assert supervisor.healthy()
            assert _count(db, "earthx_run") == 1
        finally:
            supervisor.stop(30)
