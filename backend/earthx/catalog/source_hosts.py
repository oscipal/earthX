"""The shared turn, places and breaker per host in Postgres (M5-37, docs/plans/m5/m5-37-zeiger-je-host.md §3, §4).

:class:`PostgresHostCoordinator` is the gateway's :class:`~earthx.gateway.HostCoordinator` for `materialize` and the
harvester: every instance that asks a host through one takes its turns from the same row of ``earthx_source_host``
and its places from ``earthx_source_lease`` (migration 022). The pattern is the place search's rate slot
(``geocode_cache.py``): one statement per call, ``clock_timestamp()`` read in the statement, waiting on the caller's own
time, no connection held while it waits, no lock beyond the statement.

The connection must be in autocommit and must not be the one of the caller's transaction: a turn taken inside a run's
transaction would be seen by the other instances only at its commit, and would hold the row's lock until then. A failure
of the database is the caller's: whoever cannot take a turn does not send.

The rows name a host and nothing else: no dataset, no address, no AOI.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import psycopg

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
#: The wait before asking again for a place when all are taken, drawn between these bounds.
PLACE_POLL_S = (0.25, 1.0)

_RESERVE = """
INSERT INTO public.earthx_source_host AS h (host, next_start)
VALUES (%(host)s, clock_timestamp() + make_interval(secs => %(interval)s))
ON CONFLICT (host) DO UPDATE
    SET next_start = greatest(h.next_start, clock_timestamp()) + make_interval(secs => %(interval)s),
        updated_at = clock_timestamp()
RETURNING extract(epoch FROM h.next_start - make_interval(secs => %(interval)s) - clock_timestamp())::float8
"""

_SUCCEEDED = """
UPDATE public.earthx_source_host
SET failures = 0, pauses = 0, paused_at = NULL, paused_until = NULL, updated_at = clock_timestamp()
WHERE host = %(host)s AND (failures > 0 OR pauses > 0 OR paused_until IS NOT NULL)
RETURNING true
"""

# A pause opens at the threshold, unless one is running: attempts that were already under way when it opened fail too,
# and must not double it. After the pause the first attempt is the probe; ``failures`` still stands at the threshold, so
# one more failure opens the next pause at once, twice as long. ``paused_at`` is this statement's time exactly when this
# statement opened the pause, which is how the caller learns it did.
_OPENS = """(h.failures + 1 >= %(threshold)s AND (h.paused_until IS NULL OR h.paused_until <= clock_timestamp()))"""
_PAUSE = """make_interval(secs => least(%(pause)s * power(2, h.pauses), %(max_pause)s))"""
_FAILED = f"""
INSERT INTO public.earthx_source_host AS h (host, next_start, failures)
VALUES (%(host)s, clock_timestamp() + make_interval(secs => %(retry_after)s), 1)
ON CONFLICT (host) DO UPDATE
    SET failures = h.failures + 1,
        pauses = h.pauses + CASE WHEN {_OPENS} THEN 1 ELSE 0 END,
        paused_at = CASE WHEN {_OPENS} THEN statement_timestamp() ELSE h.paused_at END,
        paused_until = CASE WHEN {_OPENS} THEN clock_timestamp() + {_PAUSE} ELSE h.paused_until END,
        next_start = greatest(
            h.next_start,
            clock_timestamp() + make_interval(secs => %(retry_after)s),
            CASE WHEN {_OPENS} THEN clock_timestamp() + {_PAUSE} END
        ),
        updated_at = clock_timestamp()
RETURNING h.failures, h.paused_at = statement_timestamp(),
          extract(epoch FROM h.paused_until - clock_timestamp())::float8
"""

# The lowest number up to the cap without a live place: written, or taken over when it is past its term. Two callers on
# the same number: one wins, the other gets no row back and asks again. The number is part of the key, so there are
# never more live places than the cap.
_ACQUIRE = """
INSERT INTO public.earthx_source_lease AS l (host, slot, holder, until)
SELECT %(host)s, s, %(holder)s, clock_timestamp() + make_interval(secs => %(term)s)
FROM generate_series(1, %(cap)s::integer) AS s
WHERE NOT EXISTS (
    SELECT 1 FROM public.earthx_source_lease o
    WHERE o.host = %(host)s AND o.slot = s AND o.until > clock_timestamp()
)
ORDER BY s
LIMIT 1
ON CONFLICT (host, slot) DO UPDATE
    SET holder = EXCLUDED.holder, until = EXCLUDED.until
    WHERE l.until <= clock_timestamp()
RETURNING l.slot
"""

_BEAT = """
UPDATE public.earthx_source_lease SET until = clock_timestamp() + make_interval(secs => %(term)s)
WHERE host = %(host)s AND slot = %(slot)s AND holder = %(holder)s
RETURNING true
"""

_RELEASE = "DELETE FROM public.earthx_source_lease WHERE host = %(host)s AND slot = %(slot)s AND holder = %(holder)s"


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
        sleep: Callable[[float], object] = asyncio.sleep,
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

    async def reserve(self, host: str, interval_s: float) -> float:
        """The host's next turn, moved on by ``interval_s``: seconds until it, at least 0. Always takes a turn."""
        row = await self._one(_RESERVE, {"host": host, "interval": float(interval_s)})
        return max(0.0, row[0])

    async def report(self, host: str, *, failed: bool, retry_after_s: float | None = None) -> None:
        """A success resets the breaker; a failure counts, pauses the host at the threshold, and applies ``Retry-After``."""
        if not failed:
            await self._one(_SUCCEEDED, {"host": host}, optional=True)
            return
        retry_after = min(max(float(retry_after_s or 0.0), 0.0), MAX_RETRY_AFTER_S)
        failures, opened, remaining = await self._one(
            _FAILED,
            {
                "host": host,
                "retry_after": retry_after,
                "threshold": BREAKER_THRESHOLD,
                "pause": PAUSE_S,
                "max_pause": MAX_PAUSE_S,
            },
        )
        if opened:
            LOGGER.warning(
                "source host paused", extra={"host": host, "failures": failures, "pause_s": round(remaining or 0.0)}
            )

    @asynccontextmanager
    async def place(self, host: str, cap: int) -> AsyncIterator[int]:
        """One of the host's ``cap`` places, renewed while the block runs and given back after it; yields its number."""
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
            raise ValueError("a cap of places is a whole number, 1 or more")
        holder = uuid.uuid4()
        slot = await self._acquire(host, cap, holder)
        key = {"host": host, "slot": slot, "holder": holder}
        # Stopped by a signal rather than cancelled, so that a renewal under way finishes on the shared connection.
        done = asyncio.Event()
        beat = asyncio.create_task(self._beat(key, done))
        try:
            yield slot
        finally:
            done.set()
            await beat
            try:
                await self._one(_RELEASE, key, optional=True)
            except psycopg.Error as error:
                # The place runs out by itself within its term; the caller's own outcome must not be replaced by this.
                LOGGER.warning("source place not given back", extra={"host": host, "error": type(error).__name__})

    async def _acquire(self, host: str, cap: int, holder: uuid.UUID) -> int:
        params = {"host": host, "holder": holder, "term": self._term, "cap": cap}
        while True:
            row = await self._one(_ACQUIRE, params, optional=True)
            if row is not None:
                return int(row[0])
            await self._sleep(self._draw(*PLACE_POLL_S))

    async def _beat(self, key: dict[str, object], done: asyncio.Event) -> None:
        while True:
            try:
                await asyncio.wait_for(done.wait(), self._heartbeat)
            except TimeoutError:
                pass
            else:
                return
            try:
                renewed = await self._one(_BEAT, {**key, "term": self._term}, optional=True)
            except psycopg.Error as error:
                LOGGER.warning("source place not renewed", extra={"host": key["host"], "error": type(error).__name__})
                continue
            if renewed is None:
                # Taken over after its term ran out (this instance stood still too long); the request ends as it is.
                LOGGER.warning("source place lost", extra={"host": key["host"]})
                return

    async def _one(self, sql: str, params: dict[str, object], *, optional: bool = False) -> tuple | None:
        async with self._conn.cursor() as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone()
        if row is None and not optional:
            raise psycopg.DataError("the statement returned no row")
        return row
