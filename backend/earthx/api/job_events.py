"""Progress of a job for a browser: one database connection per process, many clients (adr/0013 §5.4, F7).

The worker writes a job's progress to its row and sends ``NOTIFY earthx_job_progress`` in
the same transaction (`jobs/queue.py`). This process holds **exactly one** ``LISTEN``
connection, outside any pool, and hands every message to all the clients that follow that
run, from memory. Ten clients or a thousand do not change the number of connections the
database sees (``max_connections`` is 100).

**The row is the truth, the message only a wake-up call.** A message names a run, nothing
else; for each message the process reads the rows of the jobs that follow the run, once for
all of them, and puts the newest state in each client's slot. A slot holds one state: a slow
client never delays another and never sees an old state after a new one. A client that
connects registers first and has its row read by that same reader, so nothing sent in between
is lost, and states reach it in the order they were read; a state it gets twice is sent once. When the connection breaks the process connects again
(1 s, doubling up to 30 s), runs ``LISTEN`` first, and reads the row of every client — what
was sent meanwhile does not come again, and does not need to.

A pooler in transaction mode (M6) breaks ``LISTEN``: the connection would have to go to
Postgres directly or through a pool in session mode (adr/0013 §5.4).

Nothing here logs a job identifier. The run number appears only inside the process.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

import psycopg
from psycopg_pool import ConnectionPool

from earthx.jobs.queue import PROGRESS_CHANNEL
from earthx.jobs.submit import JobStatus, job_run, run_jobs

LOGGER = logging.getLogger("earthx.api.job_events")

#: Shows in ``pg_stat_activity``; the test of "one connection per process" counts by it.
APPLICATION_NAME = "earthx-api-listen"

#: The most clients one process serves at once (M4-08b K5). A starting value without a
#: measurement: it bounds memory and file descriptors of the process, not the database, which
#: sees one connection however many follow.
MAX_FOLLOWERS = 500

#: A job in one of these states changes no more.
TERMINAL = frozenset({"successful", "failed", "dismissed"})

# A connection that only listens would never notice a network that dropped without a word: the
# operating system's own keep-alive starts after about two hours. These make libpq notice in
# about a minute and a half (idle 30 s, then 3 probes 20 s apart); the client's `EventSource`
# asks again meanwhile.
_KEEPALIVE = {"keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 20, "keepalives_count": 3}

_RECONNECT_FIRST_S = 1.0
_RECONNECT_LAST_S = 30.0
_FIRST_CONNECT_WAIT_S = 10.0


class TooManyFollowers(RuntimeError):
    """The process serves as many clients as it will."""


class Subscription:
    """One client's slot: the newest state of its job, and a wake-up for whoever waits on it."""

    __slots__ = ("_closed", "_event", "_latest", "job_id", "run_id")

    def __init__(self, job_id: str, run_id: int) -> None:
        self.job_id = job_id
        self.run_id = run_id
        self._latest: JobStatus | None = None
        self._event = asyncio.Event()
        self._closed = False

    def put(self, state: JobStatus) -> None:
        self._latest = state
        self._event.set()

    def close(self) -> None:
        self._closed = True
        self._event.set()

    async def next(self) -> JobStatus | None:
        """The newest state not yet taken, waiting for one; ``None`` once the hub has closed."""
        while True:
            await self._event.wait()
            self._event.clear()
            if self._closed:
                return None
            if self._latest is not None:
                state, self._latest = self._latest, None
                return state


class JobEvents:
    """The one ``LISTEN`` connection of this process and the clients that follow runs through it."""

    def __init__(self, pool: ConnectionPool, *, max_followers: int = MAX_FOLLOWERS) -> None:
        self._pool = pool
        self._max = max_followers
        self._subs: dict[int, set[Subscription]] = defaultdict(set)
        self._count = 0
        self._dirty: set[int] = set()
        self._wake = asyncio.Event()
        self._connected = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    # --- life ------------------------------------------------------------

    async def start(self) -> None:
        """Start listening; returns once ``LISTEN`` stands, or after a wait if the database is not there yet."""
        self._tasks = [asyncio.create_task(self._listen()), asyncio.create_task(self._fan_out())]
        try:
            await asyncio.wait_for(self._connected.wait(), _FIRST_CONNECT_WAIT_S)
        except TimeoutError:
            LOGGER.warning("the progress connection is not up yet; it keeps trying")

    async def stop(self) -> None:
        """Stop, and end every stream so the server can shut down."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        self._connected.clear()
        for subs in list(self._subs.values()):
            for sub in list(subs):
                sub.close()

    @property
    def listening(self) -> bool:
        return self._connected.is_set()

    @property
    def followers(self) -> int:
        return self._count

    async def wait_listening(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._connected.wait(), timeout)
        except TimeoutError:
            return False
        return True

    # --- clients ---------------------------------------------------------

    async def subscribe(self, job_id: str) -> Subscription:
        """Follow ``job_id``; :class:`TooManyFollowers` when full, ``LookupError`` for an unknown job.

        The client is registered and its run marked, so its first state is read by the same reader
        that serves every later one — one reader per process, so states reach a client in the order
        they were read and an old one never follows a new one.
        """
        self._check_room()
        run_id = await asyncio.to_thread(self._job_run, job_id)
        if run_id is None:
            raise LookupError("no such job")
        self._check_room()
        sub = Subscription(job_id, run_id)
        self._subs[run_id].add(sub)
        self._count += 1
        self._mark(run_id)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        subs = self._subs.get(sub.run_id)
        if subs is not None and sub in subs:
            subs.discard(sub)
            self._count -= 1
            if not subs:
                del self._subs[sub.run_id]

    def _check_room(self) -> None:
        if self._count >= self._max:
            raise TooManyFollowers("this process serves as many streams as it will")

    # --- the rows --------------------------------------------------------

    def _job_run(self, job_id: str) -> int | None:
        with self._pool.connection() as conn:
            return job_run(conn, job_id)

    def _read(self, run_id: int, job_ids: list[str]) -> list[JobStatus]:
        with self._pool.connection() as conn:
            return run_jobs(conn, run_id, job_ids)

    # --- the connection --------------------------------------------------

    def _mark(self, run_id: int) -> None:
        if run_id in self._subs:
            self._dirty.add(run_id)
            self._wake.set()

    async def _listen(self) -> None:
        delay = _RECONNECT_FIRST_S
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(
                    "", autocommit=True, application_name=APPLICATION_NAME, **_KEEPALIVE
                ) as conn:
                    await conn.execute(f"LISTEN {PROGRESS_CHANNEL}")
                    # LISTEN stands, so a state read now cannot miss a message sent after it.
                    for run_id in list(self._subs):
                        self._mark(run_id)
                    self._connected.set()
                    delay = _RECONNECT_FIRST_S
                    async for notice in conn.notifies():
                        run_id = _run_of(notice.payload)
                        if run_id is not None:
                            self._mark(run_id)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                # The class only: a driver's text can name the host or the user.
                LOGGER.warning("the progress connection is down: %s", type(error).__name__)
            self._connected.clear()
            await asyncio.sleep(delay)
            delay = min(delay * 2, _RECONNECT_LAST_S)

    async def _fan_out(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            dirty, self._dirty = self._dirty, set()
            for run_id in dirty:
                subs = list(self._subs.get(run_id, ()))
                if not subs:
                    continue
                try:
                    states = await asyncio.to_thread(self._read, run_id, [sub.job_id for sub in subs])
                except Exception as error:
                    LOGGER.warning("reading the state of a run failed: %s", type(error).__name__)
                    self._dirty.add(run_id)
                    await asyncio.sleep(_RECONNECT_FIRST_S)
                    self._wake.set()
                    continue
                by_job = {state.job_id: state for state in states}
                for sub in subs:
                    state = by_job.get(sub.job_id)
                    if state is not None:
                        sub.put(state)


def _run_of(payload: str) -> int | None:
    """The run a message names; anything that is not the worker's own shape is ignored."""
    try:
        data: Any = json.loads(payload)
        run_id = data["run"]
    except (ValueError, TypeError, KeyError):
        return None
    return run_id if isinstance(run_id, int) and not isinstance(run_id, bool) else None
