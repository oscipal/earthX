"""The supervisor: picks up runs, starts a child for each, keeps its lease, ends it (adr/0013 §5.2–§5.7).

One supervisor per worker container. It holds ``slots`` threads, each with a connection of
its own, one connection that listens for the wake-up call, and one for the sweeper and the
clean-up: with the default two slots, four connections. A slot picks up a run, writes the
recipe into a work directory, starts a child through ``get_context("spawn")``, and then only
watches: it reads the pipe, renews the lease, writes the progress, passes on a cancel, and
decides from what the child said, or did not say, how the run ends.

**What the supervisor never does.** It imports neither `processing` nor `submit`: it needs
no GDAL and no recipe model (plan M4-08a K3), and the child, which does, is named by
:class:`~earthx.jobs.entry.ChildTarget` and imported only there. It does not log a recipe,
a hash, an address, a coordinate or a job ID: a run's number, attempt and the name of the
failure (Q8, adr/0014 §4.7). Database errors are logged by their class name alone, because
the text of one can carry the value that violated a key.

**Why a thread watches rather than a heartbeat thread.** The lease is renewed from the slot's
own loop. A slot that hangs stops renewing, its lease runs out and the sweeper queues the
run again; a separate heartbeat thread would keep a hung slot's lease alive for ever.

**How a run ends**, in the order the checks run:

* the lease was lost (the heartbeat found another attempt or none): the child is killed and
  nothing is written, the run is not ours;
* shutdown: the child is terminated and the run goes back at once (:func:`~earthx.jobs.queue.release`);
* more than ``max_seconds``: the child is killed, ``runtime_exceeded``, no second attempt;
* a cancel was asked for: the child is told, and killed after ``cancel_grace_seconds``;
* the child sent ``done``: the result is uploaded under a result ID of this attempt and the
  run closes only if this attempt still owns it, else the upload is deleted again;
* the child sent ``failed``: its name decides, by :data:`~earthx.jobs.queue.RETRYABLE`;
* the child ended with no word, by a signal or not: ``child_crashed``, never a second
  attempt. An out-of-memory kill cannot be told from another ``SIGKILL`` (adr/0013 §5.6);
  the log line carries the signal number and the last peak the child reported.
"""

from __future__ import annotations

import contextlib
import json
import logging
import multiprocessing
import os
import re
import secrets
import shutil
import socket
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg

from earthx.jobs import queue
from earthx.jobs.cleanup import cleanup
from earthx.jobs.config import WorkerConfig
from earthx.jobs.entry import ChildTarget
from earthx.objectstore.errors import ObjectStoreError
from earthx.objectstore.results import Store, delete_result, new_result_id, upload_result

__all__ = ["EXPORT_FILES", "RESULT_FILES", "Supervisor"]

LOGGER = logging.getLogger("earthx.jobs")

#: What a finished child leaves in its work directory and what is uploaded (plan M4-08a F4).
RESULT_FILES = ("result.tif", "mask.tif")

#: What an export leaves instead (M4-11a). The child names its files; a run with attachments is
#: an export and uploads these, any other run the two above, and nothing else.
EXPORT_FILES = ("export.zip",)

_RUN_DIRECTORY = re.compile(r"^\d+-\d+$")
_SPAWN = multiprocessing.get_context("spawn")


@dataclass
class _Watched:
    """What the supervisor learned about one child while it ran."""

    final: tuple[str, Any] | None = None
    killed_for: str | None = None
    peak_mb: float = 0.0
    blocks: int = 0
    exitcode: int | None = None
    cancel_sent_at: float | None = None
    last_percent: int = -1
    last_write: float = field(default=0.0)


class Supervisor:
    """The slots, the listener and the maintenance thread of one worker container."""

    def __init__(
        self,
        config: WorkerConfig,
        store: Store,
        *,
        target: Callable[[str, Any], None] | None = None,
        name: str | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.target = target if target is not None else ChildTarget()
        self.name = name or f"{socket.gethostname()}-{os.getpid()}-{secrets.token_hex(2)}"
        self._context = _SPAWN
        self._stopping = threading.Event()
        self._wakes = [threading.Event() for _ in range(config.slots)]
        self._threads: list[threading.Thread] = []
        self._last_database_ok = 0.0
        self._started = False

    # --- life cycle -------------------------------------------------------------------

    def start(self) -> None:
        """Check the database, clear the work directory, start the threads. Raises if the database is not ready."""
        self._check_database()
        self._clear_workdir()
        self._stopping.clear()
        self._threads = [
            threading.Thread(target=self._listen, name="listen", daemon=True),
            threading.Thread(target=self._maintain, name="maintain", daemon=True),
            *(
                threading.Thread(target=self._slot, args=(index,), name=f"slot-{index}", daemon=True)
                for index in range(self.config.slots)
            ),
        ]
        for thread in self._threads:
            thread.start()
        self._started = True
        LOGGER.info("worker started with %d slots", self.config.slots)

    def stop(self, timeout: float = 60.0) -> None:
        """Stop picking up, end the children, give their runs back, and wait for the threads."""
        self._stopping.set()
        for wake in self._wakes:
            wake.set()
        deadline = time.monotonic() + timeout
        for thread in self._threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        self._started = False
        LOGGER.info("worker stopped")

    def healthy(self) -> bool:
        """The database was reached within ``health_seconds`` and every thread is alive (adr/0013 §5.3)."""
        if not self._started or self._stopping.is_set():
            return False
        recent = time.monotonic() - self._last_database_ok <= self.config.health_seconds
        return recent and all(thread.is_alive() for thread in self._threads)

    # --- database ---------------------------------------------------------------------

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(autocommit=True, connect_timeout=10, application_name="earthx-worker")

    def _database_ok(self) -> None:
        self._last_database_ok = time.monotonic()

    def _check_database(self) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT to_regclass('public.earthx_run')").fetchone()
            if row is None or row[0] is None:
                raise RuntimeError("the queue tables are missing: migration 006 (catalog-load) has not run")
        self._database_ok()

    def _clear_workdir(self) -> None:
        root = self.config.workdir
        root.mkdir(parents=True, exist_ok=True)
        for entry in root.iterdir():
            if _RUN_DIRECTORY.match(entry.name) and entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)

    @staticmethod
    def _close(conn: psycopg.Connection | None) -> None:
        """Close a connection that failed; its own error says nothing more."""
        if conn is not None:
            with contextlib.suppress(psycopg.Error):
                conn.close()

    def _database_error(self, where: str, error: Exception) -> None:
        # The class only: the text of a database error can name the value that broke a key.
        LOGGER.warning("worker database error", extra={"where": where, "error": type(error).__name__})

    # --- the three kinds of thread ----------------------------------------------------

    def _listen(self) -> None:
        """Wake the slots when a run is placed, retried or cancelled; reconnect when the connection drops."""
        while not self._stopping.is_set():
            try:
                with self._connect() as conn:
                    conn.execute(f"LISTEN {queue.WAKE_CHANNEL}")
                    self._wake_all()  # whatever came in while there was no connection
                    while not self._stopping.is_set():
                        for _ in conn.notifies(timeout=1.0):
                            self._wake_all()
            except psycopg.Error as error:
                self._database_error("listen", error)
                self._stopping.wait(self.config.poll_seconds)
            except Exception as error:  # noqa: BLE001 - a thread that dies prints its text to stderr; only the class is logged
                LOGGER.error("listener failed", extra={"error": type(error).__name__})
                self._stopping.wait(self.config.poll_seconds)

    def _wake_all(self) -> None:
        for wake in self._wakes:
            wake.set()

    def _maintain(self) -> None:
        """Queue runs whose lease ran out, and clean up what expired, hourly."""
        conn: psycopg.Connection | None = None
        next_cleanup = time.monotonic() + self.config.cleanup_first_seconds
        while not self._stopping.is_set():
            try:
                conn = conn if conn is not None and not conn.closed else self._connect()
                handled = queue.requeue_expired(conn, backoff_seconds=self.config.backoff_seconds)
                self._database_ok()
                if handled:
                    LOGGER.warning("runs with a lost lease handled", extra={"runs": handled})
                if time.monotonic() >= next_cleanup:
                    next_cleanup = time.monotonic() + self.config.cleanup_seconds
                    cleanup(conn, self.store)
            except psycopg.Error as error:
                self._database_error("maintain", error)
                self._close(conn)
                conn = None
            except ObjectStoreError as error:
                LOGGER.warning("clean-up failed at the object store", extra={"error": type(error).__name__})
            except Exception as error:  # noqa: BLE001 - see `_listen`
                LOGGER.error("maintenance failed", extra={"error": type(error).__name__})
            self._stopping.wait(self.config.sweep_seconds)

    def _slot(self, index: int) -> None:
        wake = self._wakes[index]
        conn: psycopg.Connection | None = None
        while not self._stopping.is_set():
            try:
                conn = conn if conn is not None and not conn.closed else self._connect()
                picked = queue.claim(conn, worker=self.name, lease_seconds=self.config.lease_seconds)
                self._database_ok()
                if picked is None:
                    wake.wait(self.config.poll_seconds)
                    wake.clear()
                    continue
                if self._stopping.is_set():
                    # Picked up in the moment of the shutdown: give it back before a child is started for it.
                    queue.release(conn, picked.run_id, picked.attempt)
                    break
                self._run_one(conn, picked)
            except psycopg.Error as error:
                self._database_error("slot", error)
                self._close(conn)
                conn = None
                self._stopping.wait(self.config.poll_seconds)
            except Exception as error:  # noqa: BLE001
                # Whatever it was, the run it held is not ended here: its lease runs out and the
                # sweeper queues it again. The class only, never the text (Q8).
                LOGGER.error("slot failed", extra={"error": type(error).__name__})
                self._stopping.wait(1.0)

    # --- one run ----------------------------------------------------------------------

    def _run_one(self, conn: psycopg.Connection, picked: queue.Claim) -> None:
        run_id, attempt = picked.run_id, picked.attempt
        workdir = self.config.workdir / f"{run_id}-{attempt}"
        started = time.monotonic()
        shutil.rmtree(workdir, ignore_errors=True)
        workdir.mkdir(parents=True)
        try:
            (workdir / "recipe.json").write_text(json.dumps(picked.recipe), encoding="utf-8")
            if picked.attachments is not None:
                (workdir / "attachments.json").write_text(json.dumps(picked.attachments), encoding="utf-8")
            process, pipe = self._start_child(workdir)
            try:
                watched = self._watch(conn, picked, process, pipe, started)
            finally:
                self._end_child(process, kill=True)
                pipe.close()
            outcome = self._conclude(conn, picked, watched, workdir)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        LOGGER.info(
            "run ended",
            extra={
                "run": run_id,
                "attempt": attempt,
                "outcome": outcome,
                "seconds": round(time.monotonic() - started, 1),
                "peak_mb": round(watched.peak_mb, 1),
                "blocks": watched.blocks,
                "exitcode": watched.exitcode,
            },
        )

    def _start_child(self, workdir: Path) -> tuple[multiprocessing.process.BaseProcess, Any]:
        parent, child = self._context.Pipe(duplex=True)
        process = self._context.Process(target=self.target, args=(str(workdir), child), name="earthx-run", daemon=True)
        process.start()
        child.close()
        return process, parent

    def _end_child(self, process: multiprocessing.process.BaseProcess, *, kill: bool = False) -> None:
        if process.is_alive():
            if kill:
                process.kill()
            else:
                process.terminate()
                process.join(self.config.terminate_grace_seconds)
                if process.is_alive():
                    process.kill()
        process.join(10)

    def _watch(
        self,
        conn: psycopg.Connection,
        picked: queue.Claim,
        process: multiprocessing.process.BaseProcess,
        pipe: Any,
        started: float,
    ) -> _Watched:
        """Read the child until it is over; keep the lease; carry a cancel to it."""
        config, watched = self.config, _Watched()
        run_id, attempt = picked.run_id, picked.attempt
        last_beat = time.monotonic()
        pipe_open = True
        while True:
            if pipe_open:
                try:
                    if pipe.poll(min(0.5, config.heartbeat_seconds / 2)):
                        self._take(conn, picked, pipe, watched)
                except (EOFError, OSError):
                    pipe_open = False
            else:
                time.sleep(0.05)
            now = time.monotonic()
            if watched.final is not None:
                break
            if not process.is_alive() and not (pipe_open and pipe.poll()):
                break
            if watched.killed_for is None:
                if self._stopping.is_set():
                    watched.killed_for = "shutdown"
                    self._end_child(process)
                    break
                if now - started > picked.max_seconds:
                    watched.killed_for = "runtime"
                    process.kill()
                    break
                if now - last_beat >= config.heartbeat_seconds:
                    last_beat = now
                    flag = queue.heartbeat(conn, run_id, attempt, config.lease_seconds)
                    self._database_ok()
                    if flag is None:
                        watched.killed_for = "lost"
                        process.kill()
                        break
                    self._pass_on_cancel(pipe, watched, flag)
                if (
                    watched.cancel_sent_at is not None
                    and now - watched.cancel_sent_at > config.cancel_grace_seconds
                    and process.is_alive()
                ):
                    watched.killed_for = "cancel"
                    process.kill()
                    break
        process.join(config.terminate_grace_seconds)
        watched.exitcode = process.exitcode
        return watched

    def _take(self, conn: psycopg.Connection, picked: queue.Claim, pipe: Any, watched: _Watched) -> None:
        """One message of the child."""
        message = pipe.recv()
        if not isinstance(message, tuple) or not message:
            return
        kind = message[0]
        if kind == "progress" and len(message) == 4:
            _, done, total, peak = message
            watched.peak_mb = max(watched.peak_mb, float(peak))
            watched.blocks = int(done)
            percent = int(100 * done / total) if total else 0
            now = time.monotonic()
            if percent != watched.last_percent and now - watched.last_write >= self.config.progress_seconds:
                watched.last_percent, watched.last_write = percent, now
                flag = queue.write_progress(conn, picked.run_id, picked.attempt, percent)
                self._database_ok()
                if flag is not None:
                    self._pass_on_cancel(pipe, watched, flag)
        elif kind == "done" and len(message) == 2 and isinstance(message[1], dict):
            watched.final = ("done", message[1])
            watched.peak_mb = max(watched.peak_mb, float(message[1].get("peak_mb", 0.0)))
        elif kind == "failed" and len(message) == 2 and isinstance(message[1], str):
            watched.final = ("failed", message[1])

    def _pass_on_cancel(self, pipe: Any, watched: _Watched, requested: bool) -> None:
        if requested and watched.cancel_sent_at is None:
            watched.cancel_sent_at = time.monotonic()
            with contextlib.suppress(OSError):
                pipe.send("cancel")

    def _conclude(self, conn: psycopg.Connection, picked: queue.Claim, watched: _Watched, workdir: Path) -> str:
        """Write how the run ended, as its attempt; returns a short name for the log."""
        run_id, attempt, config = picked.run_id, picked.attempt, self.config
        if watched.killed_for == "lost":
            return "lease_lost_here"
        if watched.killed_for == "shutdown":
            queue.release(conn, run_id, attempt)
            return "released"
        if watched.final is not None and watched.final[0] == "done":
            return self._upload_and_finish(conn, picked, watched.final[1], workdir)
        if watched.killed_for == "runtime":
            queue.finish_failed(conn, run_id, attempt, "runtime_exceeded", backoff_seconds=config.backoff_seconds)
            return "runtime_exceeded"
        if watched.killed_for == "cancel" or watched.final == ("failed", "cancelled"):
            queue.finish_cancelled(conn, run_id, attempt)
            return "cancelled"
        if watched.final is not None:
            kind = watched.final[1]
        else:
            kind = "child_crashed"
            signal = -watched.exitcode if watched.exitcode is not None and watched.exitcode < 0 else None
            LOGGER.warning(
                "child ended without a word",
                extra={"run": run_id, "attempt": attempt, "signal": signal, "peak_mb": round(watched.peak_mb, 1)},
            )
        queue.finish_failed(conn, run_id, attempt, kind, backoff_seconds=config.backoff_seconds)
        return kind

    def _upload_and_finish(
        self, conn: psycopg.Connection, picked: queue.Claim, info: dict[str, Any], workdir: Path
    ) -> str:
        run_id, attempt = picked.run_id, picked.attempt
        files = tuple(info.get("files") or RESULT_FILES)
        expected = EXPORT_FILES if picked.attachments is not None else RESULT_FILES
        if files != expected:
            LOGGER.warning("child reported files it may not leave", extra={"run": run_id, "attempt": attempt})
            queue.finish_failed(conn, run_id, attempt, "unknown", backoff_seconds=self.config.backoff_seconds)
            return "unknown"
        result_id = new_result_id()

        def upload() -> None:
            for name in files:
                upload_result(self.store, result_id, name, workdir / name)

        try:
            self._while_beating(conn, picked, upload)
        except ObjectStoreError as error:
            LOGGER.warning("upload failed", extra={"run": run_id, "attempt": attempt, "error": type(error).__name__})
            self._forget(result_id)
            queue.finish_failed(conn, run_id, attempt, "upload_failed", backoff_seconds=self.config.backoff_seconds)
            return "upload_failed"
        except OSError:
            self._forget(result_id)
            queue.finish_failed(conn, run_id, attempt, "unknown", backoff_seconds=self.config.backoff_seconds)
            return "unknown"
        except psycopg.Error:
            # The lease could not be renewed, so the run is probably not ours any more: the upload
            # belongs to no run. The bucket rule is the net if this delete fails too.
            self._forget(result_id)
            raise
        try:
            finished = queue.finish_successful(conn, run_id, attempt, result_id, info)
        except psycopg.Error:
            self._forget(result_id)
            raise
        if finished:
            return "successful"
        # Another attempt owns the run now: this upload belongs to no run (adr/0013 §5.6).
        self._forget(result_id)
        return "shielded"

    def _forget(self, result_id: str) -> None:
        with contextlib.suppress(ObjectStoreError):
            delete_result(self.store, result_id)

    def _while_beating(self, conn: psycopg.Connection, picked: queue.Claim, work: Callable[[], None]) -> None:
        """Run ``work`` in a thread and renew the lease meanwhile: an upload can outlast a lease.

        If the heartbeat finds the run taken over, the upload still runs to its end; closing the
        run then fails on the attempt number and the upload is deleted again.
        """
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="upload") as pool:
            future: Future[None] = pool.submit(work)
            while True:
                try:
                    future.result(timeout=self.config.heartbeat_seconds)
                    return
                except FutureTimeout:
                    queue.heartbeat(conn, picked.run_id, picked.attempt, self.config.lease_seconds)
                    self._database_ok()
