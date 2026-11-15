"""The thread that builds overview pyramids: claims a build, runs the child, uploads what it left (M5-30b part 8b-2, adr/0032 §5.2, §8.2).

One thread of the supervisor, **not a recipe slot**: a build takes hours (GLO-30 about 6 to 7 h at the spacing of the
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

**Between builds,** once an hour like the clean-up, the thread extends the pyramids the source confirmed
(:mod:`earthx.jobs.overview_upkeep`): thousands of copies on the store's side, which the maintenance thread, that also
sweeps the leases of the runs, must not wait for. While another worker extends, the thread skips its round.

**How a build ends**, as for a run (`worker.py`): the lease was lost (the row is not ours, nothing is written, the child
is killed); shutdown (the child is ended and the build given back without using up an attempt,
:func:`~earthx.jobs.overviews.release`); the child said ``failed`` (its name goes to the row; :func:`claim
<earthx.jobs.overviews.claim>` retries only what :data:`~earthx.jobs.overviews.RETRYABLE_BUILD` names, at most three times in
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

from earthx.jobs import overview_upkeep, overviews
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
#: What an outcome that is not a failure is called in the log; any other outcome is the kind of a failed build.
_STATUS = {"ready": "ready", "released": "released", "lease_lost_here": "lease_lost"}
#: The parts of what a failed child says that the supervisor logs, and no others (a child is trusted, a log line is not).
_DETAIL = ("step", "error", "reason", "tile")
_DETAIL_LENGTH = 200
#: The omitted tiles of a build the log names one by one; more are counted.
_OMITTED_LOGGED = 20

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
        next_extension = time.monotonic() + self._config.cleanup_first_seconds
        while not self._stopping.is_set():
            try:
                conn = conn if conn is not None and not conn.closed else self._connect()
                build = overviews.claim(
                    conn, worker=self._name, lease_seconds=self._config.lease_seconds, hosts=self._pyramids
                )
                self._database_ok()
                if build is None:
                    if time.monotonic() >= next_extension:
                        round_started = time.monotonic()
                        next_extension = round_started + self._config.cleanup_seconds
                        self._extend(conn)
                        self._retry_omitted(conn, round_started)
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

    def _extend(self, conn: psycopg.Connection) -> None:
        """Hourly, when no build waits: extend the pyramids the source confirmed since (adr/0032 §5.3), if no other worker does."""
        try:
            overview_upkeep.extend_in_turn(
                conn, self._store, set(self._pyramids), self._stopping, worker=self._name, config=self._config
            )
        except ObjectStoreError as error:
            LOGGER.warning("overview extension failed at the object store", extra={"error": type(error).__name__})

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
        # ``outcome`` is the short name the row got; ``status`` says plainly whether the build worked, and a failed one is a warning.
        status = _STATUS.get(outcome, "failed")
        LOGGER.log(
            logging.INFO if status != "failed" else logging.WARNING,
            "overview build ended",
            extra={
                "dataset": build.dataset_id,
                "attempt": build.attempt,
                "outcome": outcome,
                "status": status,
                **({"failure_kind": outcome} if status == "failed" else {}),
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
        omitted: dict[str, dict[str, str]] = manifest.get("omitted") or {}
        if not overviews.finish_ready(
            conn, build, checked_at=checked_at, base_hashes=manifest["base_hashes"], omitted=omitted
        ):
            return "lease_lost_here"
        self._log_omitted(build.dataset_id, base, omitted)
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
        *,
        write_progress: bool = True,
    ) -> dict[str, Any]:
        """Run one child on ``job``; its ``done`` info, else the build ends here with the reason.

        ``write_progress`` is off for the retry of omitted tiles, which has no build row to write to.
        """
        (workdir / JOB_NAME).write_text(json.dumps(job), encoding="utf-8")
        parent, child = self._context.Pipe(duplex=True)
        process = self._context.Process(target=self._target, args=(str(workdir), child), name="earthx-overview", daemon=True)
        process.start()
        child.close()
        try:
            return self._watch(conn, build, process, parent, beat, write_progress)
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
        write_progress: bool = True,
    ) -> dict[str, Any]:
        config = self._config
        final: tuple[str, Any] | None = None
        said: dict[Any, Any] = {}
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
                                if write_progress and percent != last_percent and time.monotonic() - last_write >= config.progress_seconds:
                                    last_percent, last_write = percent, time.monotonic()
                                    if not overviews.write_progress(conn, build, percent):
                                        raise _LeaseLost
                            elif message[0] == "done" and len(message) == 2 and isinstance(message[1], dict):
                                final = ("done", message[1])
                            elif message[0] == "failed" and len(message) in (2, 3) and isinstance(message[1], str):
                                final = ("failed", message[1])
                                said = message[2] if len(message) == 3 and isinstance(message[2], dict) else {}
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
            # The kind, where it happened and why (class and a reason with no address), so that a failed build is not a mystery.
            LOGGER.warning(
                "overview child failed",
                extra={
                    "dataset": build.dataset_id,
                    "attempt": build.attempt,
                    "failure_kind": final[1],
                    **{key: str(said[key])[:_DETAIL_LENGTH] for key in _DETAIL if key in said},
                },
            )
            raise _Failed(final[1])
        return final[1]

    def _log_omitted(self, dataset_id: str, base: int, omitted: Mapping[str, Mapping[str, str]]) -> None:
        """One warning for each tile the pyramid was built without (the first :data:`_OMITTED_LOGGED`), then the count."""
        for key in sorted(omitted)[:_OMITTED_LOGGED]:
            detail = omitted[key]
            LOGGER.warning(
                "overview base tile omitted",
                extra={
                    "dataset": dataset_id,
                    "tile": f"{base}/{key}",
                    "failure_kind": str(detail.get("kind", ""))[:_DETAIL_LENGTH],
                    "error": str(detail.get("error", ""))[:_DETAIL_LENGTH],
                    "reason": str(detail.get("reason", ""))[:_DETAIL_LENGTH],
                },
            )
        if len(omitted) > _OMITTED_LOGGED:
            LOGGER.warning("overview base tiles omitted", extra={"dataset": dataset_id, "count": len(omitted)})

    # --- the retry of the omitted tiles --------------------------------------------------

    def _retry_omitted(self, conn: psycopg.Connection, round_started: float) -> int | None:
        """Hourly, when no build waits: read the omitted base tiles of the ready pyramids again; the number of tiles recovered.

        One worker at a time, on the turn of the upkeep (:func:`~earthx.jobs.overview_upkeep.retry_in_turn`, task
        ``retry``): the others skip the round, and ``None`` is returned if another worker has the turn or a round of
        another worker counts for this one. Nothing that is served is touched: the version is not deleted, only the
        omitted base tiles and the tiles above them are made again and put over the version, each object with the time of
        this read, and the row's ``checked_at`` stays the oldest. A pyramid whose host a build, or another retry, is reading
        from is left for the next round (a lease per host in the database, :func:`~earthx.jobs.overviews.take_hosts`).
        """
        with contextlib.suppress(psycopg.Error):
            overviews.drop_stale_omitted(conn)
        due = overviews.omitted_due(conn, self._pyramids)
        if not due:
            return 0

        def work(renew: Callable[[], None]) -> int:
            recovered = 0
            try:
                for (dataset_id, version), tiles in due.items():
                    # A build, or another retry, reading from the host keeps this one out: a lease row per host in the
                    # database, decided under the lock `claim` takes (`overviews.take_hosts`).
                    hosts = overviews.take_hosts(
                        conn, self._pyramids[dataset_id], worker=self._name, lease_seconds=self._config.lease_seconds
                    )
                    if hosts is None:
                        continue
                    last = time.monotonic()

                    def beat(hosts: overviews.HostLease = hosts) -> None:
                        nonlocal last
                        if self._stopping.is_set():
                            raise _Shutdown
                        renew()
                        if time.monotonic() - last >= self._config.heartbeat_seconds:
                            last = time.monotonic()
                            if not overviews.renew_hosts(conn, hosts, self._config.lease_seconds):
                                raise _LeaseLost

                    try:
                        recovered += self._retry_one(conn, dataset_id, version, tiles, beat)
                    except _LeaseLost:
                        LOGGER.warning("overview retry stopped", extra={"dataset": dataset_id, "reason": "host lease lost"})
                    finally:
                        with contextlib.suppress(psycopg.Error):
                            overviews.release_hosts(conn, hosts)
            except _Shutdown:
                LOGGER.warning("overview retry stopped", extra={"reason": "worker stopping"})
            return recovered

        return overview_upkeep.retry_in_turn(conn, work, worker=self._name, config=self._config, round_started=round_started)

    def _retry_one(
        self, conn: psycopg.Connection, dataset_id: str, version: str, tiles: Sequence[str], beat: Callable[[], None]
    ) -> int:
        workdir = self._config.workdir / WORKDIR
        shutil.rmtree(workdir, ignore_errors=True)
        workdir.mkdir(parents=True)
        build = overviews.Build(dataset_id, version, "", 0, tuple(self._pyramids[dataset_id]))
        try:
            if free_bytes(workdir) < DISK_BYTES:
                LOGGER.warning("overview retry skipped", extra={"dataset": dataset_id, "failure_kind": "disk_space"})
                return 0
            if write_items(conn, dataset_id, workdir / ITEMS_NAME, beat) == 0:
                return 0
            job = {"dataset_id": dataset_id, "hosts": list(build.hosts), "only": list(tiles)}
            self._step(conn, build, workdir, {**job, "mode": "patch_plan"}, beat, write_progress=False)
            needs = json.loads((workdir / PLAN_NAME).read_text(encoding="utf-8"))["fetch"]
            for name in needs:
                beat()
                z, x, y = (int(part) for part in name.split("/"))
                stored = read_tile(self._store, dataset_id, version, z, x, y)
                if stored is not None:
                    path = workdir / TILES_DIR / str(z) / str(x) / f"{y}.tif"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(stored.data)
            read_at = datetime.now(UTC)
            self._step(conn, build, workdir, {**job, "mode": "patch"}, beat, write_progress=False)
            manifest = json.loads((workdir / MANIFEST_NAME).read_text(encoding="utf-8"))
            base = int(manifest["base_zoom"])
            for name in manifest["tiles"]:
                beat()
                z, x, y = (int(part) for part in name.split("/"))
                path = workdir / TILES_DIR / str(z) / str(x) / f"{y}.tif"
                upload_tile(self._store, dataset_id, version, z, x, y, path, checked_at=read_at)
            still = manifest.get("omitted") or {}
            if not overviews.settle_retry(
                conn,
                dataset_id,
                version,
                recovered=manifest.get("recovered") or [],
                still=still,
                base_hashes=manifest.get("base_hashes") or {},
            ):
                return 0
            self._log_omitted(dataset_id, base, still)
            LOGGER.info(
                "overview retry ended",
                extra={"dataset": dataset_id, "recovered": len(manifest.get("recovered") or []), "omitted": len(still)},
            )
            return len(manifest.get("recovered") or [])
        except (_LeaseLost, _Shutdown):
            raise
        except _Failed as failed:
            # Said by the child with its detail already (`overview child failed`); nothing about the pyramid changes.
            LOGGER.warning("overview retry failed", extra={"dataset": dataset_id, "failure_kind": failed.kind})
            return 0
        except (ObjectStoreError, OSError) as error:
            LOGGER.warning("overview retry failed", extra={"dataset": dataset_id, "error": type(error).__name__})
            return 0
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

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
