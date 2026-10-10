"""The supervisor with spawned children, against a real Postgres and a moto bucket (adr/0013 §8; plan M4-08a §3.4).

The children are the stand-ins of `child_targets.py`: they speak the same messages as the
real one (`test_child.py` runs that) and can succeed, fail with a chosen name, die by a
signal, hang, or cooperate with a cancel. Times are short: a lease of 3 s, a heartbeat every
0.3 s, a cancel grace of 1 s.
"""

from __future__ import annotations

import ast
import json
import logging
import multiprocessing
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from earthx.jobs import queue
from earthx.jobs.config import WorkerConfig
from earthx.jobs.entry import ChildTarget
from earthx.jobs.submit import dismiss, job_status, submit
from earthx.jobs.worker import Supervisor
from earthx.objectstore.errors import StoreUnavailable
from earthx.objectstore.results import Store, upload_result
from tests.conftest import format_without_timestamp
from tests.earthx.jobs.support import ATTACHMENTS, make_export, make_recipe, most_at_once, run_row, wait_until
from tests.earthx.objectstore.conftest import BUCKET

BACKEND = Path(__file__).resolve().parents[3]
FAST: dict[str, Any] = {
    "slots": 2,
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


@pytest.fixture
def make_supervisor(
    db: psycopg.Connection, store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[..., Supervisor]]:
    """A supervisor on the session's database and the moto bucket; every one is stopped at the end."""
    made: list[Supervisor] = []

    def make(target: str = "succeed", **overrides: Any) -> Supervisor:
        config = WorkerConfig(**{**FAST, "workdir": tmp_path / f"work{len(made)}", **overrides})
        supervisor = Supervisor(
            config,
            store,
            target=ChildTarget("tests.earthx.jobs.child_targets", target),
            name=f"test-{len(made)}",
        )
        made.append(supervisor)
        return supervisor

    yield make
    for supervisor in made:
        supervisor.stop(30)


def _stored(store: Store) -> list[str]:
    return sorted(store.s3.list_keys("results/"))


def _state(db: psycopg.Connection, job_id: str) -> str:
    status = job_status(db, job_id)
    assert status is not None
    return status.status


def _wait_for(db: psycopg.Connection, job_id: str, status: str, timeout: float = 30) -> None:
    wait_until(lambda: _state(db, job_id) == status, timeout)


def _run_id(db: psycopg.Connection) -> int:
    row = db.execute("SELECT run_id FROM public.earthx_run ORDER BY run_id LIMIT 1").fetchone()
    assert row is not None
    return row[0]


class TestASuccessfulRun:
    def test_the_run_is_computed_uploaded_and_closed(
        self, db: psycopg.Connection, store: Store, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        supervisor = make_supervisor("succeed")
        supervisor.start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "successful")
        status = job_status(db, job_id)
        assert status is not None and status.result_id is not None and status.progress == 100
        assert status.result and status.result["blocks"] == 2
        assert _stored(store) == [f"results/{status.result_id}/mask.tif", f"results/{status.result_id}/result.tif"]
        assert run_row(db, _run_id(db), "attempt", "worker", "lease_until", "error_kind") == (1, None, None, None)

    def test_the_work_directory_is_gone_afterwards(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor], tmp_path: Path
    ) -> None:
        supervisor = make_supervisor("succeed", slots=1)
        supervisor.start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "successful")
        wait_until(lambda: list((tmp_path / "work0").iterdir()) == [])

    def test_the_workers_are_woken_so_a_long_poll_interval_does_not_delay_a_run(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        supervisor = make_supervisor("succeed", poll_seconds=30.0, heartbeat_seconds=1.0, lease_seconds=3.0)
        supervisor.start()
        time.sleep(0.5)  # the slots are asleep now
        started = time.monotonic()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "successful", timeout=15)
        assert time.monotonic() - started < 10

    def test_progress_is_written_while_the_child_runs(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILD_DELAY", "1.5")
        supervisor = make_supervisor("succeed", slots=1)
        supervisor.start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "running")
        wait_until(lambda: (job_status(db, job_id) or 0).progress >= 40)  # type: ignore[union-attr, operator]
        _wait_for(db, job_id, "successful")

    def test_only_the_slots_run_at_a_time(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILD_DELAY", "0.6")
        supervisor = make_supervisor("succeed", slots=2)
        supervisor.start()
        jobs = [submit(db, make_recipe(f"ITEM_{n}", host=f"h{n}.example.invalid")) for n in range(6)]
        for job in jobs:
            _wait_for(db, job, "successful", timeout=60)
        assert most_at_once(db) == 2


class TestFailures:
    @pytest.mark.parametrize(
        "kind", ["source_4xx", "source_429", "rejected", "recipe_invalid", "out_of_memory", "unknown"]
    )
    def test_a_failure_that_cannot_be_helped_fails_at_once_with_its_name(
        self,
        db: psycopg.Connection,
        make_supervisor: Callable[..., Supervisor],
        monkeypatch: pytest.MonkeyPatch,
        kind: str,
    ) -> None:
        monkeypatch.setenv("CHILD_KIND", kind)
        make_supervisor("fail").start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "failed")
        status = job_status(db, job_id)
        assert status is not None and status.error_kind == kind
        assert run_row(db, _run_id(db), "attempt")[0] == 1

    @pytest.mark.parametrize("kind", ["source_5xx", "source_timeout"])
    def test_a_failure_of_the_source_is_tried_three_times_and_then_fails(
        self,
        db: psycopg.Connection,
        make_supervisor: Callable[..., Supervisor],
        monkeypatch: pytest.MonkeyPatch,
        kind: str,
    ) -> None:
        monkeypatch.setenv("CHILD_KIND", kind)
        make_supervisor("fail").start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "failed")
        assert run_row(db, _run_id(db), "attempt", "error_kind") == (3, kind)

    def test_a_second_attempt_can_succeed_and_clears_the_error(
        self,
        db: psycopg.Connection,
        store: Store,
        make_supervisor: Callable[..., Supervisor],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CHILD_KIND", "source_5xx")
        make_supervisor("fail_first_attempt").start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "successful")
        assert run_row(db, _run_id(db), "attempt", "error_kind", "status") == (2, None, "successful")
        assert len(_stored(store)) == 2

    def test_a_child_killed_by_a_signal_is_a_crash_and_is_not_tried_again(
        self,
        db: psycopg.Connection,
        make_supervisor: Callable[..., Supervisor],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.INFO, logger="earthx.jobs")
        make_supervisor("die_by_signal").start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "failed")
        assert run_row(db, _run_id(db), "attempt", "error_kind") == (1, "child_crashed")
        wait_until(lambda: any(r.getMessage() == "child ended without a word" for r in caplog.records))
        crash = next(r for r in caplog.records if r.getMessage() == "child ended without a word")
        assert (crash.signal, crash.peak_mb) == (9, 321.5), "the signal and the last peak the child reported"  # type: ignore[attr-defined]

    def test_a_child_that_ends_without_a_word_is_a_crash_too(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        make_supervisor("exit_silently").start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "failed")
        assert run_row(db, _run_id(db), "error_kind", "attempt") == ("child_crashed", 1)

    def test_a_real_memory_error_in_the_child_is_named_and_not_tried_again(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        make_supervisor("run_out_of_memory").start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "failed")
        assert run_row(db, _run_id(db), "error_kind", "attempt") == ("out_of_memory", 1)

    def test_a_run_over_its_time_is_killed_and_not_tried_again(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        job_id = submit(db, make_recipe())
        db.execute("UPDATE public.earthx_run SET max_seconds = 2")
        make_supervisor("hang").start()
        _wait_for(db, job_id, "failed")
        assert run_row(db, _run_id(db), "error_kind", "attempt") == ("runtime_exceeded", 1)

    def test_a_failed_upload_fails_the_run_and_leaves_nothing_in_the_store(
        self,
        db: psycopg.Connection,
        store: Store,
        make_supervisor: Callable[..., Supervisor],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        calls: list[str] = []

        def second_file_fails(store: Store, result_id: str, name: str, path: Path) -> None:
            calls.append(name)
            if name == "mask.tif":
                raise StoreUnavailable("the store did not answer")
            upload_result(store, result_id, name, path)

        monkeypatch.setattr("earthx.jobs.worker.upload_result", second_file_fails)
        make_supervisor("succeed").start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "failed")
        assert calls == ["result.tif", "mask.tif"]
        assert run_row(db, _run_id(db), "error_kind", "attempt") == ("upload_failed", 1)
        assert _stored(store) == [], "what was uploaded before the failure is deleted again"

    def test_a_child_that_claims_success_without_files_fails_the_run(
        self, db: psycopg.Connection, store: Store, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        make_supervisor("done_without_files").start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "failed")
        assert run_row(db, _run_id(db), "error_kind") == ("unknown",)
        assert _stored(store) == []


class TestAnExport:
    """M4-11a: the attachments reach the child, and only ``export.zip`` is uploaded."""

    def test_the_child_gets_the_attachments_and_export_zip_is_uploaded(
        self, db: psycopg.Connection, store: Store, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        make_supervisor("export").start()
        job_id = submit(db, make_export(), attachments=ATTACHMENTS)
        _wait_for(db, job_id, "successful")
        status = job_status(db, job_id)
        assert status is not None and status.result is not None and status.result["files"] == ["export.zip"]
        assert _stored(store) == [f"results/{status.result_id}/export.zip"]
        body = store.s3._internal.get_object(Bucket=BUCKET, Key=f"results/{status.result_id}/export.zip")
        assert json.loads(body["Body"].read()) == ATTACHMENTS.to_json()

    def test_a_raster_child_that_reports_an_export_zip_fails_and_uploads_nothing(
        self, db: psycopg.Connection, store: Store, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        make_supervisor("export_without_attachments").start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "failed")
        assert run_row(db, _run_id(db), "error_kind") == ("unknown",)
        assert _stored(store) == []

    def test_a_child_naming_a_file_outside_the_two_sets_fails_and_uploads_nothing(
        self, db: psycopg.Connection, store: Store, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        make_supervisor("name_a_foreign_file").start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "failed")
        assert run_row(db, _run_id(db), "error_kind") == ("unknown",)
        assert _stored(store) == []


class TestDiskSpace:
    """Otto, 08.10.2026: a run that would not fit on the worker's disk ends before its child starts."""

    def test_too_little_free_space_fails_the_run_at_once_without_a_second_attempt(
        self,
        db: psycopg.Connection,
        store: Store,
        make_supervisor: Callable[..., Supervisor],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        need = run_need(db, submit(db, make_export(), attachments=ATTACHMENTS))
        monkeypatch.setattr("earthx.jobs.worker.free_bytes", lambda path: need - 1)
        marker = tmp_path / "child-started"
        monkeypatch.setenv("CHILD_MARKER", str(marker))
        make_supervisor("export").start()
        wait_until(lambda: run_row(db, _run_id(db), "status")[0] == "failed")
        assert run_row(db, _run_id(db), "error_kind", "attempt") == ("disk_space", 1)
        assert _stored(store) == []
        assert not marker.exists(), "no child was started"
        wait_until(lambda: list((tmp_path / "work0").iterdir()) == [])

    def test_exactly_enough_free_space_runs(
        self,
        db: psycopg.Connection,
        store: Store,
        make_supervisor: Callable[..., Supervisor],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        job_id = submit(db, make_export(), attachments=ATTACHMENTS)
        need = run_need(db, job_id)
        monkeypatch.setattr("earthx.jobs.worker.free_bytes", lambda path: need)
        make_supervisor("export").start()
        _wait_for(db, job_id, "successful")

    def test_the_failure_says_what_to_do_and_names_no_number(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job_id = submit(db, make_recipe())
        monkeypatch.setattr("earthx.jobs.worker.free_bytes", lambda path: 0)
        make_supervisor("succeed").start()
        _wait_for(db, job_id, "failed")
        status = job_status(db, job_id)
        assert status is not None and status.error_kind == "disk_space"


def run_need(db: psycopg.Connection, job_id: str) -> int:
    row = db.execute(
        "SELECT r.disk_bytes FROM public.earthx_run r JOIN public.earthx_job j USING (run_id) WHERE j.job_id = %s",
        (job_id,),
    ).fetchone()
    assert row is not None and row[0] > 0
    return row[0]


class TestCancel:
    def test_a_running_child_that_listens_stops_at_the_next_block(
        self, db: psycopg.Connection, store: Store, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        make_supervisor("cooperate", slots=1).start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "running")
        wait_until(lambda: run_row(db, _run_id(db), "progress")[0] >= 1)
        started = time.monotonic()
        dismiss(db, job_id)
        wait_until(lambda: run_row(db, _run_id(db), "status")[0] == "dismissed")
        assert time.monotonic() - started < 5
        assert _stored(store) == []

    def test_a_child_that_does_not_listen_is_killed_after_the_grace(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        make_supervisor("hang", slots=1).start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "running")
        wait_until(lambda: run_row(db, _run_id(db), "progress")[0] >= 1)
        started = time.monotonic()
        dismiss(db, job_id)
        wait_until(lambda: run_row(db, _run_id(db), "status")[0] == "dismissed")
        assert 1.0 <= time.monotonic() - started < 10, "not before the grace of 1 s, and not much later"
        assert run_row(db, _run_id(db), "error_kind", "attempt") == (None, 1)

    def test_another_live_job_keeps_the_run_computing(
        self,
        db: psycopg.Connection,
        store: Store,
        make_supervisor: Callable[..., Supervisor],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CHILD_DELAY", "1.5")
        make_supervisor("succeed", slots=1).start()
        mine, theirs = submit(db, make_recipe()), submit(db, make_recipe())
        _wait_for(db, mine, "running")
        dismiss(db, mine)
        _wait_for(db, theirs, "successful")
        assert _state(db, mine) == "dismissed"
        assert len(_stored(store)) == 2


class TestLeaseAndAttempts:
    def test_an_upload_longer_than_the_lease_does_not_lose_the_run(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def slow(store: Store, result_id: str, name: str, path: Path) -> None:
            time.sleep(1.6)
            upload_result(store, result_id, name, path)

        monkeypatch.setattr("earthx.jobs.worker.upload_result", slow)
        make_supervisor("succeed", slots=1, lease_seconds=1.0, heartbeat_seconds=0.3).start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "successful", timeout=30)
        assert run_row(db, _run_id(db), "attempt") == (1,), "the lease was renewed during the upload"

    def test_a_run_that_another_attempt_owns_is_not_finished_and_its_upload_is_deleted(
        self,
        db: psycopg.Connection,
        store: Store,
        make_supervisor: Callable[..., Supervisor],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CHILD_DELAY", "1.5")
        make_supervisor("succeed", slots=1, lease_seconds=60.0, heartbeat_seconds=30.0).start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "running")
        db.execute("UPDATE public.earthx_run SET attempt = 2, worker = 'someone-else'")
        wait_until(lambda: not [p for p in multiprocessing.active_children() if p.name == "earthx-run"])
        time.sleep(1.0)
        assert run_row(db, _run_id(db), "status", "attempt", "worker", "result_id") == (
            "running",
            2,
            "someone-else",
            None,
        )
        assert _stored(store) == []

    def test_a_heartbeat_that_finds_no_ownership_ends_the_child_and_writes_nothing(
        self, db: psycopg.Connection, store: Store, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        make_supervisor("hang", slots=1).start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "running")
        db.execute("UPDATE public.earthx_run SET attempt = 2, worker = 'someone-else'")
        wait_until(lambda: not [p for p in multiprocessing.active_children() if p.name == "earthx-run"])
        assert run_row(db, _run_id(db), "status", "attempt", "error_kind") == ("running", 2, None)

    def test_a_supervisor_that_is_killed_leaves_a_run_that_is_queued_again_after_the_lease(
        self,
        db: psycopg.Connection,
        store_env: dict[str, str],
        make_supervisor: Callable[..., Supervisor],
        tmp_path: Path,
    ) -> None:
        job_id = submit(db, make_recipe())
        env = {
            **os.environ,
            **store_env,
            "SP_WORKDIR": str(tmp_path / "doomed"),
            "PYTHONPATH": f"{BACKEND}:{os.environ.get('PYTHONPATH', '')}",
        }
        doomed = subprocess.Popen(
            [sys.executable, "-m", "tests.earthx.jobs.supervisor_process"],
            cwd=BACKEND,
            env=env,
            stdout=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            assert doomed.stdout is not None and doomed.stdout.readline().strip() == "started"
            _wait_for(db, job_id, "running")
            assert run_row(db, _run_id(db), "worker")[0] == "doomed"
        finally:
            os.killpg(doomed.pid, signal.SIGKILL)  # the supervisor and its child, with no word
            doomed.wait(20)
        successor = make_supervisor("succeed", slots=1, lease_seconds=1.0, heartbeat_seconds=0.3)
        successor.start()
        _wait_for(db, job_id, "successful", timeout=30)
        assert run_row(db, _run_id(db), "attempt") == (2,), "the first attempt died with its supervisor"


class TestShutdown:
    def test_a_stopped_supervisor_ends_its_children_and_gives_the_runs_back(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        supervisor = make_supervisor("hang", slots=2)
        supervisor.start()
        jobs = [submit(db, make_recipe(f"ITEM_{n}", host=f"h{n}.example.invalid")) for n in range(2)]
        for job in jobs:
            _wait_for(db, job, "running")
        children = [p for p in multiprocessing.active_children() if p.name == "earthx-run"]
        assert len(children) == 2
        with psycopg.connect(autocommit=True) as listener:
            listener.execute(f"LISTEN {queue.WAKE_CHANNEL}")
            started = time.monotonic()
            supervisor.stop(30)
            woken = list(listener.notifies(timeout=0.5))
        assert time.monotonic() - started < 15
        assert not any(child.is_alive() for child in children)
        rows = db.execute("SELECT status, attempt, worker, lease_until FROM public.earthx_run").fetchall()
        assert rows == [("accepted", 1, None, None)] * 2
        assert woken, "the workers were woken to pick the runs up"
        assert not supervisor.healthy()

    def test_what_was_given_back_is_picked_up_by_another_supervisor_at_once(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        first = make_supervisor("hang", slots=1)
        first.start()
        job_id = submit(db, make_recipe())
        _wait_for(db, job_id, "running")
        first.stop(30)
        second = make_supervisor("succeed", slots=1)
        second.start()
        _wait_for(db, job_id, "successful", timeout=15)
        assert run_row(db, _run_id(db), "attempt") == (2,)

    def test_a_run_picked_up_in_the_moment_of_the_shutdown_is_given_back_before_a_child_starts(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        supervisor = make_supervisor("succeed", slots=1)
        started: list[object] = []
        real_claim = queue.claim

        def claim_and_stop(conn: psycopg.Connection, **kwargs: Any) -> queue.Claim | None:
            picked = real_claim(conn, **kwargs)
            if picked is not None:
                supervisor._stopping.set()
            return picked

        monkeypatch.setattr(queue, "claim", claim_and_stop)
        monkeypatch.setattr(supervisor, "_start_child", lambda *args: started.append(args))
        job_id = submit(db, make_recipe())
        run_id = _run_id(db)
        supervisor.start()
        # Status and attempt in one statement: read apart, a pick-up between the two reads
        # looks like "accepted, attempt 1" before the run was given back (plan M4-08a-fix2).
        wait_until(lambda: run_row(db, run_id, "status", "attempt") == ("accepted", 1))
        assert started == [], "no child was started for it"
        assert run_row(db, run_id, "worker", "lease_until") == (None, None)
        assert _state(db, job_id) == "accepted"

    def test_a_stopped_supervisor_picks_up_nothing_more(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        supervisor = make_supervisor("succeed")
        supervisor.start()
        supervisor.stop(30)
        job_id = submit(db, make_recipe())
        time.sleep(1.0)
        assert _state(db, job_id) == "accepted"


class TestTwoSupervisorsOneCap:
    def test_the_cap_holds_whatever_the_number_of_supervisors(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Otto, 07.10.2026: two supervisors against the same database, cap 4, never more than 4."""
        monkeypatch.setenv("CHILD_DELAY", "0.5")
        db.execute("UPDATE public.earthx_job_limits SET global_cap = 4, host_cap = 8")
        first, second = make_supervisor("succeed", slots=4), make_supervisor("succeed", slots=4)
        jobs = [submit(db, make_recipe(f"ITEM_{n}", host=f"h{n % 3}.example.invalid")) for n in range(16)]
        first.start()
        second.start()
        for job in jobs:
            _wait_for(db, job, "successful", timeout=90)
        assert most_at_once(db) == 4, "reached, and never exceeded, with eight slots on offer"

    def test_the_limit_per_host_holds_across_supervisors_too(
        self, db: psycopg.Connection, make_supervisor: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CHILD_DELAY", "0.4")
        db.execute("UPDATE public.earthx_job_limits SET global_cap = 8, host_cap = 2")
        jobs = [submit(db, make_recipe(f"ITEM_{n}", host="one.example.invalid")) for n in range(8)]
        first, second = make_supervisor("succeed", slots=3), make_supervisor("succeed", slots=3)
        first.start()
        second.start()
        for job in jobs:
            _wait_for(db, job, "successful", timeout=90)
        assert most_at_once(db) == 2


class TestStartAndHealth:
    def test_it_is_healthy_while_the_database_answers_and_not_before_start_or_after_stop(
        self, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        supervisor = make_supervisor("succeed", health_seconds=30.0)
        assert not supervisor.healthy()
        supervisor.start()
        assert supervisor.healthy()
        supervisor.stop(30)
        assert not supervisor.healthy()

    def test_it_is_not_healthy_when_the_database_was_not_reached_for_too_long(
        self, make_supervisor: Callable[..., Supervisor]
    ) -> None:
        supervisor = make_supervisor("succeed", health_seconds=5.0)
        supervisor.start()
        supervisor._last_database_ok = time.monotonic() - 60
        assert not supervisor.healthy()
        wait_until(supervisor.healthy, timeout=10)  # the slots poll again within 0.2 s

    def test_it_does_not_start_without_the_queue_tables(
        self, make_supervisor: Callable[..., Supervisor], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PGDATABASE", "template1")
        with pytest.raises(RuntimeError, match="migration 006"):
            make_supervisor("succeed").start()

    def test_it_starts_a_log_line_with_the_number_of_slots(
        self, make_supervisor: Callable[..., Supervisor], caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO, logger="earthx.jobs")
        make_supervisor("succeed", slots=2).start()
        assert "worker started with 2 slots" in [record.getMessage() for record in caplog.records]

    def test_the_work_directory_is_cleared_of_runs_a_crash_left_and_nothing_else(
        self, make_supervisor: Callable[..., Supervisor], tmp_path: Path
    ) -> None:
        root = tmp_path / "work0"
        (root / "12-1").mkdir(parents=True)
        (root / "12-1" / "result.tif").write_text("left over")
        (root / "keep.txt").write_text("not mine")
        (root / "notarun").mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "precious").write_text("x")
        (root / "5-5").symlink_to(outside, target_is_directory=True)
        make_supervisor("succeed").start()
        assert sorted(path.name for path in root.iterdir()) == ["5-5", "keep.txt", "notarun"]
        assert (outside / "precious").read_text() == "x"


class TestChildrenAreSpawned:
    def test_the_context_is_spawn(self, make_supervisor: Callable[..., Supervisor]) -> None:
        assert make_supervisor()._context.get_start_method() == "spawn"

    def test_no_module_of_jobs_starts_a_process_any_other_way(self) -> None:
        """Adr/0013 §10a F3: children come only from `get_context("spawn")`, never from a global setting."""
        sources = {path: path.read_text() for path in (BACKEND / "earthx" / "jobs").glob("*.py")}
        for path, source in sources.items():
            for forbidden in (
                "set_start_method",
                "forkserver",
                "os.fork",
                'get_context("fork")',
                "multiprocessing.Pool",
            ):
                assert forbidden not in source, f"{path.name}: {forbidden}"
        contexts = [
            (path.name, ast.unparse(node))
            for path, source in sources.items()
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("get_context")
        ]
        assert contexts == [("worker.py", "multiprocessing.get_context('spawn')")]
        calls = [
            node
            for node in ast.walk(ast.parse(sources[BACKEND / "earthx" / "jobs" / "worker.py"]))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "Process"
        ]
        assert calls and all(ast.unparse(call.func) == "self._context.Process" for call in calls)

    def test_the_supervisor_loads_neither_the_core_nor_the_submit_interface(self) -> None:
        """Plan K3: importing the supervisor in a fresh process loads no `processing`, no rasterio, no `submit`."""
        script = (
            "import sys; sys.modules['boto3'] = None; import earthx.jobs.worker\n"
            "bad = [n for n in sys.modules if n.split('.')[0] in ('rasterio', 'numpy', 'numexpr') or"
            " n.startswith(('earthx.processing', 'earthx.jobs.submit', 'earthx.jobs.child', 'earthx.readers', 'earthx.gateway'))]\n"
            "print(sorted(bad))"
        )
        output = subprocess.run(
            [sys.executable, "-c", script], cwd=BACKEND, capture_output=True, text=True, check=True, timeout=120
        )
        assert output.stdout.strip() == "[]"


class TestLogs:
    def test_no_log_line_of_any_way_a_run_can_end_names_the_recipe_the_hash_the_address_the_aoi_or_an_id(
        self,
        db: psycopg.Connection,
        make_supervisor: Callable[..., Supervisor],
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Success, a named failure, a crash by signal and a failed upload; each ends a run and each logs."""
        caplog.set_level(logging.DEBUG, logger="earthx")
        monkeypatch.setenv("CHILD_KIND", "source_4xx")
        hosts = {
            "ITEM_OK": "ok.example.invalid",
            "ITEM_FAIL": "fail.example.invalid",
            "ITEM_DIE": "die.example.invalid",
        }
        jobs = {
            item: submit(db, make_recipe(item, host=host, recipe_id=item[5:].ljust(22, "Q")))
            for item, host in hosts.items()
        }
        make_supervisor("by_item", slots=3).start()
        for item, job in jobs.items():
            _wait_for(db, job, "successful" if item == "ITEM_OK" else "failed")
        wait_until(lambda: sum(r.getMessage() == "run ended" for r in caplog.records) == 3)

        def failing_upload(store: Store, result_id: str, name: str, path: Path) -> None:
            raise StoreUnavailable("the store did not answer")

        monkeypatch.setattr("earthx.jobs.worker.upload_result", failing_upload)
        late = submit(db, make_recipe("ITEM_OK", host="late.example.invalid"))
        _wait_for(db, late, "failed")
        wait_until(lambda: sum(r.getMessage() == "run ended" for r in caplog.records) == 4)

        lines = "\n".join(format_without_timestamp(r) for r in caplog.records if r.name.startswith("earthx"))
        outcomes = sorted(r.outcome for r in caplog.records if r.getMessage() == "run ended")  # type: ignore[attr-defined]
        assert outcomes == sorted(["source_4xx", "successful", "child_crashed", "upload_failed"])
        status = job_status(db, jobs["ITEM_OK"])
        assert status is not None and status.result_id is not None
        secrets_ = [
            "c1:",
            *hosts.values(),
            "late.example.invalid",
            *hosts,
            *jobs.values(),
            late,
            status.result_id,
            "OK" + "Q" * 20,
            "47.0",
            "9.0",
            "https://",
        ]
        for secret in secrets_:
            assert secret not in lines, secret
        assert '"run": ' in lines

    def test_a_database_error_is_logged_by_its_class_and_never_its_text(
        self, make_supervisor: Callable[..., Supervisor], caplog: pytest.LogCaptureFixture
    ) -> None:
        supervisor = make_supervisor("succeed", slots=1)
        with caplog.at_level(logging.WARNING, logger="earthx.jobs"):
            supervisor._database_error(
                "slot", psycopg.errors.UniqueViolation("Key (cache_key)=(c1:secret) already exists.")
            )
        assert "secret" not in "".join(format_without_timestamp(r) for r in caplog.records)
        assert caplog.records[0].error == "UniqueViolation"  # type: ignore[attr-defined]


def test_the_threads_of_a_supervisor_are_daemons_so_a_forgotten_one_cannot_hold_the_process(
    make_supervisor: Callable[..., Supervisor],
) -> None:
    supervisor = make_supervisor("succeed")
    supervisor.start()
    assert supervisor._threads and all(thread.daemon for thread in supervisor._threads)
    assert threading.current_thread() not in supervisor._threads
