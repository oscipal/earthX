"""The shared turn, places and breaker per host in Postgres (M5-37, docs/plans/m5/m5-37-zeiger-je-host.md §3, §4).

:class:`PostgresHostCoordinator` is the gateway's :class:`~earthx.gateway.HostCoordinator` for `materialize` and the
harvester: every instance that asks a host through one takes its turns from the same row of ``earthx_source_host``
and its places from ``earthx_source_lease``. The rules are the functions of migration 022, so the pyramid build's
supervisor in `jobs`, which may not import this module, calls the very same ones (plan §5.2). The pattern is the place
search's rate slot (``geocode_cache.py``): one statement per call, the clock read in the database, waiting on the
caller's own time, no connection held while it waits, no lock beyond the statement.

The connection must be in autocommit and must not be the one of the caller's transaction: a turn taken inside a run's
transaction would be seen by the other instances only at its commit, and would hold the row's lock until then. A failure
of the database is the caller's: whoever cannot take a turn does not send.

The rows name a host and nothing else: no dataset, no address, no AOI.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import psycopg

from earthx.gateway import normalize_host
from earthx.gateway.policy import MAX_INTERVAL_S

__all__ = [
    "BREAKER_THRESHOLD",
    "HEARTBEAT_S",
    "LEASE_TERM_S",
    "MAX_PAUSE_S",
    "MAX_RETRY_AFTER_S",
    "PAUSE_S",
    "PostgresHostCoordinator",
]

LOGGER = logging.getLogger("earthx.catalog")

#: Failed attempts in a row, over all callers and instances, that pause a host (J3; adr/0025 §6.2, adr/0032 §8.2).
BREAKER_THRESHOLD = 3
#: The first pause; each pause right after the one before is twice as long, at most :data:`MAX_PAUSE_S` (J3).
PAUSE_S = 300.0
MAX_PAUSE_S = 3600.0
#: A source's ``Retry-After`` moves the host's turn on by at most this much.
MAX_RETRY_AFTER_S = 600.0
#: How long a place lasts without a heartbeat, and how often its holder renews it (Otto, 16.11.2026).
LEASE_TERM_S = 30.0
HEARTBEAT_S = 10.0
#: The wait before asking again for a place when all are held, drawn between these bounds.
PLACE_POLL_S = (0.25, 1.0)

_RESERVE = "SELECT public.earthx_source_reserve(%s, %s, %s)"
_PAUSE_LEFT = "SELECT public.earthx_source_pause_left(%s)"
_REPORT = "SELECT opened, recovered, pause_s FROM public.earthx_source_report(%s, %s, %s, %s, %s, %s)"
_ACQUIRE = "SELECT public.earthx_source_acquire(%s, %s, %s, %s)"
_RENEW = "SELECT public.earthx_source_renew(%s, %s, %s, %s)"
_RELEASE = "SELECT public.earthx_source_release(%s, %s, %s)"


def _seconds(value: float, upper: float, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(value) or not 0 <= value <= upper:
        raise ValueError(f"{what} lies between 0 and {upper:g} seconds")
    return float(value)


class PostgresHostCoordinator:
    """Turns, places and breaker of every host in Postgres, on one connection in autocommit.

    ``sleep`` and ``draw`` (the random wait between two asks for a place) are seams for tests; the terms are too.
    """

    def __init__(
        self,
        conn: psycopg.AsyncConnection,
        *,
        lease_term_s: float = LEASE_TERM_S,
        heartbeat_s: float = HEARTBEAT_S,
        sleep: Callable[[float], Any] = asyncio.sleep,
        draw: Callable[[float, float], float] = random.uniform,
    ) -> None:
        if not conn.autocommit:
            raise ValueError("the shared turns need a connection in autocommit, apart from the caller's transaction")
        if not 0 < heartbeat_s < lease_term_s:
            raise ValueError("a heartbeat comes more often than a place runs out")
        self._conn = conn
        self._term = float(lease_term_s)
        self._heartbeat = float(heartbeat_s)
        self._sleep = sleep
        self._draw = draw

    async def reserve(self, host: str, interval_s: float, max_wait_s: float) -> float:
        """Seconds until the host's next turn; taken and moved on by ``interval_s`` unless more than ``max_wait_s`` off."""
        interval = _seconds(interval_s, MAX_INTERVAL_S, "an interval per host")
        max_wait = _seconds(max_wait_s, MAX_PAUSE_S, "a longest wait for a turn")
        (wait,) = await self._one(_RESERVE, (normalize_host(host), interval, max_wait))
        return max(0.0, wait)

    async def pause_left(self, host: str) -> float:
        """Seconds the host is still paused, 0 if it is not."""
        (left,) = await self._one(_PAUSE_LEFT, (normalize_host(host),))
        return left

    async def report(self, host: str, *, failed: bool, retry_after_s: float | None = None) -> None:
        """A success resets the breaker; a failure counts, pauses the host at the threshold, and applies ``Retry-After``."""
        name = normalize_host(host)
        retry_after = 0.0 if retry_after_s is None or math.isnan(retry_after_s) else retry_after_s
        retry_after = min(max(float(retry_after), 0.0), MAX_RETRY_AFTER_S)
        opened, recovered, pause_s = await self._one(
            _REPORT, (name, bool(failed), retry_after, BREAKER_THRESHOLD, PAUSE_S, MAX_PAUSE_S)
        )
        if opened:
            LOGGER.warning("source host paused", extra={"host": name, "pause_s": round(pause_s)})
        elif recovered:
            LOGGER.info("source host answers again", extra={"host": name})

    @asynccontextmanager
    async def place(self, host: str, cap: int) -> AsyncIterator[int]:
        """One of the host's ``cap`` places, renewed while the block runs and given back after it; yields its number."""
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
            raise ValueError("a cap of places is a whole number, 1 or more")
        name = normalize_host(host)
        holder = uuid.uuid4()
        slot = await self._acquire(name, cap, holder)
        # Stopped by a signal rather than cancelled, so that a renewal under way finishes on the shared connection.
        done = asyncio.Event()
        beat = asyncio.create_task(self._beat(name, slot, holder, done))
        try:
            yield slot
        finally:
            done.set()
            await beat
            try:
                await self._one(_RELEASE, (name, slot, holder))
            except psycopg.Error as error:
                # The place runs out by itself within its term; the caller's own outcome must not be replaced by this.
                LOGGER.warning("source place not given back", extra={"host": name, "error": type(error).__name__})

    async def _acquire(self, host: str, cap: int, holder: uuid.UUID) -> int:
        while True:
            (slot,) = await self._one(_ACQUIRE, (host, cap, holder, self._term))
            if slot is not None:
                return int(slot)
            await self._sleep(self._draw(*PLACE_POLL_S))

    async def _beat(self, host: str, slot: int, holder: uuid.UUID, done: asyncio.Event) -> None:
        while True:
            try:
                await asyncio.wait_for(done.wait(), self._heartbeat)
            except TimeoutError:
                pass
            else:
                return
            try:
                (renewed,) = await self._one(_RENEW, (host, slot, holder, self._term))
            except psycopg.Error as error:
                LOGGER.warning("source place not renewed", extra={"host": host, "error": type(error).__name__})
                continue
            if not renewed:
                # Taken over after its term ran out (this instance stood still too long); the request ends as it is.
                LOGGER.warning("source place lost", extra={"host": host})
                return

    async def _one(self, sql: str, params: tuple[Any, ...]) -> tuple[Any, ...]:
        async with self._conn.cursor() as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone()
        if row is None:
            raise psycopg.DataError("a function of migration 022 returned no row")
        return row
