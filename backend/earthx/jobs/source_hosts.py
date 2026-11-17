"""The shared turn, places and breaker per host for the pyramid build's supervisor (M5-37 PR 2, plan §5.4).

The rules are the functions of migrations 022 and 023, the same that ``earthx.catalog.source_hosts`` calls for
`materialize` and the harvester: `jobs` may import neither `catalog` nor `gateway` (architekturplan.md 3.1), so it
calls them itself, synchronously, on the supervisor's own connection in autocommit. The numbers of the breaker and of a
place are the same as there; a test holds both modules together.

Nothing here reaches a source: the child reads, and asks the supervisor for each turn over its pipe (B9).
"""

from __future__ import annotations

import logging
import math
import random
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import psycopg

__all__ = [
    "BREAKER_THRESHOLD",
    "HEARTBEAT_S",
    "LEASE_TERM_S",
    "MAX_PAUSE_S",
    "MAX_RETRY_AFTER_S",
    "PAUSE_S",
    "HostTurns",
    "SourceHosts",
    "TurnKeeper",
]

LOGGER = logging.getLogger("earthx.jobs")

#: As in ``earthx.catalog.source_hosts`` (J3; Otto, 16.11.2026).
BREAKER_THRESHOLD = 3
PAUSE_S = 300.0
MAX_PAUSE_S = 3600.0
MAX_RETRY_AFTER_S = 600.0
LEASE_TERM_S = 30.0
HEARTBEAT_S = 10.0
#: A pyramid build waits out a pause (J4): any turn within this is taken.
BUILD_MAX_WAIT_S = 2 * MAX_PAUSE_S
#: The wait before asking again for a place when all are held, drawn between these bounds.
PLACE_POLL_S = (0.25, 1.0)

_RESERVE = "SELECT public.earthx_source_reserve(%s, %s, %s)"
_PAUSE_LEFT = "SELECT public.earthx_source_pause_left(%s)"
_REPORT = "SELECT opened, recovered, pause_s FROM public.earthx_source_report(%s, %s, %s, %s, %s, %s)"
_ACQUIRE = "SELECT public.earthx_source_acquire(%s, %s, %s, %s)"
_RENEW = "SELECT public.earthx_source_renew(%s, %s, %s, %s)"
_RELEASE = "SELECT public.earthx_source_release(%s, %s, %s)"
_ACCOUNT = "SELECT public.earthx_source_account(%s, %s, %s)"


@dataclass(frozen=True, slots=True)
class HostTurns:
    """What a pyramid build may take of one host: places at once and the spacing between two requests."""

    connections: int
    interval_s: float

    def __post_init__(self) -> None:
        if isinstance(self.connections, bool) or not isinstance(self.connections, int) or self.connections < 1:
            raise ValueError("a cap of places is a whole number, 1 or more")
        if math.isnan(self.interval_s) or not 0 <= self.interval_s <= 300:
            raise ValueError("an interval per host lies between 0 and 300 seconds")


class SourceHosts:
    """The calls of the supervisor, one statement each, on a connection in autocommit."""

    def __init__(self, conn: psycopg.Connection) -> None:
        if not conn.autocommit:
            raise ValueError("the shared turns need a connection in autocommit")
        self._conn = conn

    def reserve(self, host: str, interval_s: float, max_wait_s: float) -> float:
        """Seconds until the host's next turn, taken unless further than ``max_wait_s`` off."""
        return max(0.0, self._one(_RESERVE, (host, float(interval_s), float(max_wait_s))))

    def pause_left(self, host: str) -> float:
        return self._one(_PAUSE_LEFT, (host,))

    def account(self, host: str, interval_s: float, requests: int) -> None:
        """Charge the requests GDAL made for one file to the host's turn (migration 023)."""
        self._one(_ACCOUNT, (host, float(interval_s), int(requests)))

    def report(self, host: str, *, failed: bool, retry_after_s: float | None = None) -> tuple[bool, bool, float]:
        """``(opened, recovered, pause_s)``: whether this failure paused the host, or this success ended a pause."""
        retry_after = 0.0 if retry_after_s is None or math.isnan(retry_after_s) else float(retry_after_s)
        row = self._row(
            _REPORT,
            (
                host,
                bool(failed),
                min(max(retry_after, 0.0), MAX_RETRY_AFTER_S),
                BREAKER_THRESHOLD,
                PAUSE_S,
                MAX_PAUSE_S,
            ),
        )
        return bool(row[0]), bool(row[1]), float(row[2])

    def acquire(self, host: str, cap: int, holder: uuid.UUID) -> int | None:
        """One of the host's ``cap`` places for :data:`LEASE_TERM_S`, its number; ``None`` while all are held."""
        return self._one(_ACQUIRE, (host, cap, holder, LEASE_TERM_S))

    def renew(self, host: str, slot: int, holder: uuid.UUID) -> bool:
        return bool(self._one(_RENEW, (host, slot, holder, LEASE_TERM_S)))

    def release(self, host: str, slot: int, holder: uuid.UUID) -> None:
        self._one(_RELEASE, (host, slot, holder))

    def _one(self, sql: str, params: tuple[Any, ...]) -> Any:
        return self._row(sql, params)[0]

    def _row(self, sql: str, params: tuple[Any, ...]) -> tuple[Any, ...]:
        row = self._conn.execute(sql, params).fetchone()
        if row is None:
            raise psycopg.DataError("a function of migrations 022 or 023 returned no row")
        return row


class TurnKeeper:
    """The turn of the one file a child reads at a time: asked for, waited for without blocking, held, then charged.

    The supervisor's loop calls :meth:`ask` on ``("pace", host)``, :meth:`step` whenever :meth:`due_in` says (it is
    ``True`` once the child may start: the supervisor sends ``("go",)``), and :meth:`account` on ``("account", …)``.
    While a turn is asked for or held the child is waiting on the supervisor, not stalled (:attr:`busy`). :meth:`close`
    gives back a place still held when the child ends. ``clock`` and ``draw`` are seams for tests.
    """

    def __init__(
        self,
        hosts: SourceHosts,
        limits: Mapping[str, HostTurns],
        *,
        clock: Callable[[], float] = time.monotonic,
        draw: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._hosts = hosts
        self._limits = limits
        self._clock = clock
        self._draw = draw
        self._host: str | None = None
        self._due = 0.0
        self._slot: int | None = None
        self._holder = uuid.uuid4()
        self._renewed = 0.0

    @property
    def busy(self) -> bool:
        return self._host is not None

    def ask(self, host: str) -> None:
        """Take the host's next turn; ``ValueError`` for a host the build may not read."""
        if host not in self._limits:
            raise ValueError("the child asked for a turn on a host the build does not read")
        self.close()
        limit = self._limits[host]
        self._host = host
        self._holder = uuid.uuid4()
        self._due = self._clock() + self._hosts.reserve(host, limit.interval_s, BUILD_MAX_WAIT_S)

    def due_in(self) -> float | None:
        """Seconds until :meth:`step` has something to do, ``None`` with no turn asked for or held."""
        if self._host is None:
            return None
        if self._slot is not None:
            return max(0.0, self._renewed + HEARTBEAT_S - self._clock())
        return max(0.0, self._due - self._clock())

    def step(self) -> bool:
        """Renew a held place, or, once the turn is due and no pause runs, take a place: ``True`` when the child may go."""
        if self._host is None:
            return False
        now = self._clock()
        if self._slot is not None:
            if now - self._renewed >= HEARTBEAT_S:
                self._renewed = now
                if not self._hosts.renew(self._host, self._slot, self._holder):
                    LOGGER.warning("source place lost", extra={"host": self._host})
            return False
        if now < self._due:
            return False
        left = self._hosts.pause_left(self._host)
        if left > 0:
            self._due = now + left
            return False
        slot = self._hosts.acquire(self._host, self._limits[self._host].connections, self._holder)
        if slot is None:
            self._due = now + self._draw(*PLACE_POLL_S)
            return False
        self._slot, self._renewed = slot, now
        return True

    def account(self, host: str, requests: int, failed: bool, retry_after: float | None) -> None:
        """Charge the file's requests, tell the breaker how the read ended, give the place back."""
        if host != self._host or self._slot is None:
            raise ValueError("the child accounted for a turn it was not given")
        self._hosts.account(host, self._limits[host].interval_s, requests)
        opened, recovered, pause_s = self._hosts.report(host, failed=failed, retry_after_s=retry_after)
        if opened:
            LOGGER.warning("source host paused", extra={"host": host, "pause_s": round(pause_s)})
        elif recovered:
            LOGGER.info("source host answers again", extra={"host": host})
        self.close()

    def close(self) -> None:
        """Give back a place still held; forget the turn."""
        if self._host is not None and self._slot is not None:
            self._hosts.release(self._host, self._slot, self._holder)
        self._host, self._slot = None, None
