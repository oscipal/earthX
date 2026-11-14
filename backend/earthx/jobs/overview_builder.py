"""The thread that builds overview pyramids: claims a build, runs the child, uploads what it left (M5-30b part 8b-2, adr/0032 §5.2, §8.2).

One thread of the supervisor, **not a recipe slot**: a build takes hours (GLO-30 about 3.6 h at the spacing of the
sources), and a slot held that long would stop the runs of the users. It never shows in the job API and has no user: its
state is the row of `earthx_overview` (:mod:`earthx.jobs.overviews`).

**One build, in the order it runs:**

1. the items of the dataset are read from pgstac with SQL (`jobs` imports no `catalog`) into ``items.jsonl`` in the work
   directory, a page at a time with the lease renewed between pages;
2. a first child (``"mode": "plan"``) names the base tiles and the hash of the items each one reads, without reading a
   source; the tiles of the last ready version with the same hash are fetched from the store into the work directory and
   named in ``reuse``; an item without ``updated`` has no hash, so nothing of its tile is reused (plan §8.10);
3. a second child (``"mode": "build"``) reads the tiles that are not reused and makes the levels above, decoding the reused
   ones; it knows no database and no object store (B9);
4. **this thread uploads** from the work directory, because the core may not reach the object store: new tiles are put
   with ``checked-at``, reused base tiles are copied on the store's side from the old version (a copy keeps its old
   ``checked-at``); the row closes as ready with the oldest ``checked-at`` and the hashes of the base tiles.

**How a build ends**, as for a run (`worker.py`): the lease was lost (the row is not ours, nothing is written, the child
is killed); shutdown (the child is ended and the build given back without using up an attempt,
:func:`~earthx.jobs.overviews.release`); the child said ``failed`` (its name goes to the row; :func:`claim
<earthx.jobs.overviews.claim>` retries only what :data:`~earthx.jobs.queue.RETRYABLE` names, at most three times in
all and not before an hour); the child ended without a word (``child_crashed``, not retried); it said nothing for
:data:`STALL_SECONDS` (``stalled``, not retried).

The thread logs the dataset id and the name of a failure, never an address, an item or a tile.
"""

from __future__ import annotations

import contextlib
import json
import logging
import multiprocessing
import shutil
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from earthx.jobs import overviews
from earthx.jobs.config import WorkerConfig
from earthx.jobs.entry import ChildTarget
from earthx.objectstore.errors import ObjectStoreError
from earthx.objectstore.overviews import delete_version, read_tile, term_of, upload_tile
from earthx.objectstore.results import Store

__all__ = ["DISK_BYTES", "STALL_SECONDS", "WORKDIR", "OverviewBuilder", "write_items"]

LOGGER = logging.getLogger("earthx.jobs")

#: The work directory of the one build of this container, inside ``WorkerConfig.workdir``.
WORKDIR = "overview-build"
#: Free space a build needs before it starts: the tiles of GLO-30 are about 1 GB (adr/0032 §8.1).
DISK_BYTES = 2 * 1024**3
#: A child that sends no word (a tile at a time) for this long is killed; a hung read would hold the lease for ever.
STALL_SECONDS = 1800.0
# The names of the files in the work directory, as `earthx.processing.overview_build` has them; `jobs` may not load
# that module in the supervisor (GDAL), a test holds the two lists together.
ITEMS_NAME, JOB_NAME, PLAN_NAME, MANIFEST_NAME, TILES_DIR = "items.jsonl", "job.json", "plan.json", "manifest.json", "tiles"

_PAGE = 1000

_ITEMS_SQL = """
SELECT i.id, pgstac.get_item(i.id, i.collection)
FROM (
    SELECT id, collection FROM pgstac.items WHERE collection = %s AND id > %s ORDER BY id LIMIT %s
) i
ORDER BY i.id
"""


class _LeaseLost(Exception):
    """This attempt no longer owns the build."""


class _Shutdown(Exception):
    """The worker is stopping."""


class _Failed(Exception):
    """The build failed with a named kind."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


def free_bytes(path: Path) -> int:
    """Free bytes on the file system of ``path``; a seam of its own, so tests can set it."""
    return shutil.disk_usage(path).free


def write_items(conn: psycopg.Connection, dataset_id: str, path: Path, beat: Callable[[], None]) -> int:
    """Write the items of a dataset's pgstac collection to ``path``, one JSON object a line; the number written.

    By keyset pages on autocommit statements, so that the lease can be renewed between pages on the same connection.
    """
    last, count = "", 0
    with path.open("w", encoding="utf-8") as out:
        while True:
            rows = conn.execute(_ITEMS_SQL, (dataset_id, last, _PAGE)).fetchall()
            if not rows:
                return count
            for _, item in rows:
                if item is not None:
                    out.write(json.dumps(item, separators=(",", ":")) + "\n")
                    count += 1
            last = rows[-1][0]
            beat()


class OverviewBuilder:
    """The thread body: claim, build, finish; one connection of its own."""

    def __init__(
        self,
        config: WorkerConfig,
        store: Store,
        *,
        name: str,
        pyramids: Mapping[str, Sequence[str]],
        context: multiprocessing.context.BaseContext,
        stopping: threading.Event,
        connect: Callable[[], psycopg.Connection],
        database_ok: Callable[[], None],
        target: Callable[[str, Any], None] | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._name = name
        self._pyramids = {dataset_id: tuple(hosts) for dataset_id, hosts in pyramids.items()}
        self._context = context
        self._stopping = stopping
        self._connect = connect
        self._database_ok = database_ok
        self._target = target if target is not None else ChildTarget("earthx.jobs.overview_child", "run_child")

    # --- the thread ------------------------------------------------------------------

    def run(self) -> None:
        """Claim and build until the worker stops; whatever goes wrong is logged by its class and the thread goes on."""
        conn: psycopg.Connection | None = None
        while not self._stopping.is_set():
            try:
                conn = conn if conn is not None and not conn.closed else self._connect()
                build = overviews.claim(
                    conn, worker=self._name, lease_seconds=self._config.lease_seconds, hosts=self._pyramids
                )
                self._database_ok()
                if build is None:
                    self._stopping.wait(self._config.poll_seconds)
                    continue
                if self._stopping.is_set():
                    overviews.release(conn, build)
                    break
                self._build(conn, build)
            except psycopg.Error as error:
                LOGGER.warning("worker database error", extra={"where": "overview", "error": type(error).__name__})
                if conn is not None:
                    with contextlib.suppress(psycopg.Error):
                        conn.close()
                conn = None
                self._stopping.wait(self._config.poll_seconds)
            except Exception as error:  # noqa: BLE001 - the build it held runs out its lease; only the class is logged
                LOGGER.error("overview thread failed", extra={"error": type(error).__name__})
                self._stopping.wait(1.0)

    # --- one build -------------------------------------------------------------------

    def _build(self, conn: psycopg.Connection, build: overviews.Build) -> None:
        started = time.monotonic()
        workdir = self._config.workdir / WORKDIR
        shutil.rmtree(workdir, ignore_errors=True)
        workdir.mkdir(parents=True)
        try:
            outcome = self._attempt(conn, build, workdir)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        LOGGER.info(
            "overview build ended",
            extra={
                "dataset": build.dataset_id,
                "attempt": build.attempt,
                "outcome": outcome,
                "seconds": round(time.monotonic() - started, 1),
            },
        )

    def _attempt(self, conn: psycopg.Connection, build: overviews.Build, workdir: Path) -> str:
        """Run the steps; returns a short name for the log, after the row says how it ended."""
        beat = self._beater(conn, build)
        try:
            return self._steps(conn, build, workdir, beat)
        except _Failed as failed:
            overviews.finish_failed(conn, build, failed.kind)
            return failed.kind
        except _LeaseLost:
            return "lease_lost_here"
        except _Shutdown:
            overviews.release(conn, build)
            return "released"
        except psycopg.Error:
            raise
        except Exception as error:  # noqa: BLE001 - a bug is named by its class and never retried
            LOGGER.error("overview build failed", extra={"dataset": build.dataset_id, "error": type(error).__name__})
            overviews.finish_failed(conn, build, "unknown")
            return "unknown"

    def _steps(self, conn: psycopg.Connection, build: overviews.Build, workdir: Path, beat: Callable[[], None]) -> str:
        if free_bytes(workdir) < DISK_BYTES:
            raise _Failed("disk_space")
        if write_items(conn, build.dataset_id, workdir / ITEMS_NAME, beat) == 0:
            raise _Failed("no_items")
        job = {"dataset_id": build.dataset_id, "hosts": list(build.hosts)}
        self._step(conn, build, workdir, {**job, "mode": "plan"}, beat)
        plan = json.loads((workdir / PLAN_NAME).read_text(encoding="utf-8"))
        base = int(plan["base_zoom"])
        previous = overviews.previous_ready(conn, build.dataset_id, build.version)
        reuse = self._fetch_reusable(build, workdir, base, plan["tiles"], previous, beat)
        read_at = datetime.now(UTC)
        self._step(conn, build, workdir, {**job, "mode": "build", "reuse": sorted(reuse)}, beat)
        manifest = json.loads((workdir / MANIFEST_NAME).read_text(encoding="utf-8"))
        # The pyramid is as old as the oldest of what it holds: the read of this build, or a reused tile's own time.
        checked_at = min([read_at, *reuse.values()])
        try:
            self._own(conn, build)
            # An earlier attempt of this version may have left objects; this attempt's tiles are the only ones that stay.
            delete_version(self._store, build.dataset_id, build.version)
            self._publish(build, workdir, manifest["tiles"], base, reuse, read_at, beat)
        except (ObjectStoreError, OSError) as error:
            LOGGER.warning("overview upload failed", extra={"error": type(error).__name__})
            self._forget(conn, build)
            raise _Failed("upload_failed") from None
        except _Shutdown:
            self._forget(conn, build)
            raise
        if not overviews.finish_ready(conn, build, checked_at=checked_at, base_hashes=manifest["base_hashes"]):
            return "lease_lost_here"
        return "ready"

    def _beater(self, conn: psycopg.Connection, build: overviews.Build) -> Callable[[], None]:
        """A function that renews the lease when it is due and raises if the build is not ours or the worker stops."""
        last = time.monotonic()

        def beat() -> None:
            nonlocal last
            if self._stopping.is_set():
                raise _Shutdown
            if time.monotonic() - last >= self._config.heartbeat_seconds:
                last = time.monotonic()
                if not overviews.heartbeat(conn, build, self._config.lease_seconds):
                    raise _LeaseLost
                self._database_ok()

        return beat

    def _own(self, conn: psycopg.Connection, build: overviews.Build) -> None:
        """Renew the lease now and raise :class:`_LeaseLost` if this attempt no longer owns the build."""
        if not overviews.heartbeat(conn, build, self._config.lease_seconds):
            raise _LeaseLost
        self._database_ok()

    def _forget(self, conn: psycopg.Connection, build: overviews.Build) -> None:
        """Delete what this attempt put in the store, but only while the build is still its own.

        A stale attempt (its lease ran out, another one took over and may have finished the same version) must not delete
        what the new owner uploaded; the sweep of the hourly round is the net for what stays.
        """
        if not overviews.heartbeat(conn, build, self._config.lease_seconds):
            return
        with contextlib.suppress(ObjectStoreError):
            delete_version(self._store, build.dataset_id, build.version)

    # --- the child -------------------------------------------------------------------

    def _step(
        self,
        conn: psycopg.Connection,
        build: overviews.Build,
        workdir: Path,
        job: dict[str, Any],
        beat: Callable[[], None],
    ) -> dict[str, Any]:
        """Run one child on ``job``; its ``done`` info, else the build ends here with the reason."""
        (workdir / JOB_NAME).write_text(json.dumps(job), encoding="utf-8")
        parent, child = self._context.Pipe(duplex=True)
        process = self._context.Process(target=self._target, args=(str(workdir), child), name="earthx-overview", daemon=True)
        process.start()
        child.close()
        try:
            return self._watch(conn, build, process, parent, beat)
        finally:
            if process.is_alive():
                process.kill()
            process.join(10)
            parent.close()

    def _watch(
        self,
        conn: psycopg.Connection,
        build: overviews.Build,
        process: multiprocessing.process.BaseProcess,
        pipe: Any,
        beat: Callable[[], None],
    ) -> dict[str, Any]:
        config = self._config
        final: tuple[str, Any] | None = None
        pipe_open = True
        last_word = last_write = time.monotonic()
        last_percent = -1
        while final is None:
            if pipe_open:
                try:
                    if pipe.poll(min(0.5, config.heartbeat_seconds / 2)):
                        message = pipe.recv()
                        last_word = time.monotonic()
                        if isinstance(message, tuple) and message:
                            if message[0] == "progress" and len(message) == 4:
                                percent = int(100 * message[1] / message[2]) if message[2] else 0
                                if percent != last_percent and time.monotonic() - last_write >= config.progress_seconds:
                                    last_percent, last_write = percent, time.monotonic()
                                    if not overviews.write_progress(conn, build, percent):
                                        raise _LeaseLost
                            elif message[0] == "done" and len(message) == 2 and isinstance(message[1], dict):
                                final = ("done", message[1])
                            elif message[0] == "failed" and len(message) == 2 and isinstance(message[1], str):
                                final = ("failed", message[1])
                except (EOFError, OSError):
                    pipe_open = False
            else:
                time.sleep(0.05)
            if final is None and not process.is_alive() and not (pipe_open and pipe.poll()):
                break
            beat()
            if final is None and time.monotonic() - last_word > STALL_SECONDS:
                process.kill()
                raise _Failed("stalled")
        process.join(config.terminate_grace_seconds)
        if final is None:
            LOGGER.warning("child ended without a word", extra={"dataset": build.dataset_id, "exitcode": process.exitcode})
            raise _Failed("child_crashed")
        if final[0] == "failed":
            raise _Failed(final[1])
        return final[1]

    # --- reuse and upload --------------------------------------------------------------

    def _fetch_reusable(
        self,
        build: overviews.Build,
        workdir: Path,
        base: int,
        hashes: Mapping[str, str | None],
        previous: overviews.Previous | None,
        beat: Callable[[], None],
    ) -> dict[str, datetime]:
        """Put the tiles of the last ready version whose hash did not change into the work directory.

        Returns their ``x/y`` keys with the ``checked-at`` each object carries. A tile whose own term has less than
        :data:`~earthx.jobs.overviews.REUSE_MARGIN` left, or that carries no readable time, is read again instead.
        """
        reuse: dict[str, datetime] = {}
        if previous is None:
            return reuse
        now = datetime.now(UTC)
        term = term_of(build.dataset_id)
        for key, digest in hashes.items():
            if digest is None or previous.base_hashes.get(key) != digest:
                continue
            beat()
            x, y = (int(part) for part in key.split("/"))
            try:
                stored = read_tile(self._store, build.dataset_id, previous.version, base, x, y)
            except ObjectStoreError as error:
                LOGGER.warning("overview reuse failed", extra={"error": type(error).__name__})
                raise _Failed("store_failed") from None
            if stored is None or stored.checked_at is None or stored.checked_at + term - overviews.REUSE_MARGIN <= now:
                continue
            path = workdir / TILES_DIR / str(base) / str(x) / f"{y}.tif"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(stored.data)
            reuse[key] = stored.checked_at
        return reuse

    def _publish(
        self,
        build: overviews.Build,
        workdir: Path,
        tiles: Sequence[str],
        base: int,
        reuse: Mapping[str, datetime],
        read_at: datetime,
        beat: Callable[[], None],
    ) -> None:
        """Upload every tile in the work directory: the time of the read for what this build made, a reused base tile's own."""
        for name in tiles:
            beat()
            z, x, y = (int(part) for part in name.split("/"))
            own = reuse.get(f"{x}/{y}") if z == base else None
            path = workdir / TILES_DIR / str(z) / str(x) / f"{y}.tif"
            upload_tile(self._store, build.dataset_id, build.version, z, x, y, path, checked_at=own or read_at)
