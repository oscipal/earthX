"""A spacing per host for the reads that GDAL performs itself (M5-30b part 8, adr/0032 §8.2, F4, F3 = 1).

The spacing of ``Policy.min_interval_s`` (M5-18 §3.2) lives in the gateway's HTTP client; GDAL opens its own
connections and never meets it. :class:`HostPacer` is the same idea for the threads that read files through GDAL, the
overview build above all: ``wait(host)`` before a file is opened, ``account(host, requests)`` once it is read, with
the number of requests GDAL made for it (:func:`earthx.gateway.gdal.counting_gdal_lines`). On average the starts
of two requests to one host are then at least the interval apart, however many requests a file took.

The interval is ``EARTHX_OVERVIEW_HOST_INTERVAL_S`` (default 0.25 s, the FSDI's fair-use rule), unless the policy
names the host in ``host_intervals``. The state is in memory and per object; it knows nothing of datasets.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Mapping

from earthx.gateway.policy import Policy, _check_interval, normalize_host

__all__ = ["DEFAULT_OVERVIEW_HOST_INTERVAL_S", "OVERVIEW_HOST_INTERVAL_ENV", "HostPacer", "overview_interval_from_env"]

OVERVIEW_HOST_INTERVAL_ENV = "EARTHX_OVERVIEW_HOST_INTERVAL_S"
DEFAULT_OVERVIEW_HOST_INTERVAL_S = 0.25


def overview_interval_from_env(environ: Mapping[str, str] | None = None) -> float:
    """``EARTHX_OVERVIEW_HOST_INTERVAL_S`` in seconds, 0.25 if unset or empty; the error names the variable only."""
    raw = (environ if environ is not None else os.environ).get(OVERVIEW_HOST_INTERVAL_ENV, "").strip()
    if not raw:
        return DEFAULT_OVERVIEW_HOST_INTERVAL_S
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{OVERVIEW_HOST_INTERVAL_ENV}: not a number") from None
    try:
        return _check_interval(value)
    except ValueError as error:
        raise ValueError(f"{OVERVIEW_HOST_INTERVAL_ENV}: {error}") from None


class HostPacer:
    """Starts of file reads per host, at least ``interval`` per request apart, safe to share between threads.

    Each :meth:`wait` takes one slot of the host (the earliest start is the host's cursor, which moves on by one
    interval), so readers that ask at the same moment are spaced too; :meth:`account` then charges the other
    requests of the file (or gives the slot back when there were none, a warm cache). With one reader that
    puts the next start at ``start + requests * interval``, which counts the time the file took as part of the spacing.
    ``wait`` and ``account`` come in pairs of one thread: ``try: …; finally: account``.

    ``clock`` and ``sleep`` are injectable for tests. A host is compared in the gateway's spelling.
    """

    def __init__(
        self,
        interval_s: float = DEFAULT_OVERVIEW_HOST_INTERVAL_S,
        *,
        policy: Policy | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval_s = _check_interval(interval_s)
        self._policy = policy
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._cursor: dict[str, float] = {}
        self._open = threading.local()

    @classmethod
    def from_env(
        cls, policy: Policy | None = None, environ: Mapping[str, str] | None = None, **kwargs: object
    ) -> HostPacer:
        """A pacer with the interval of ``EARTHX_OVERVIEW_HOST_INTERVAL_S``; a bad value raises ``ValueError``."""
        return cls(overview_interval_from_env(environ), policy=policy, **kwargs)  # type: ignore[arg-type]

    def interval_for(self, host: str) -> float:
        """The host's entry in the policy's ``host_intervals`` (a parent's too), else the pacer's interval."""
        name = normalize_host(host)
        own = self._policy.host_interval(name) if self._policy is not None else None
        return self._interval_s if own is None else own

    def wait(self, host: str) -> None:
        """Block until a file may be opened on ``host``, and take its slot."""
        name = normalize_host(host)
        interval = self.interval_for(name)
        with self._lock:
            now = self._clock()
            start = max(now, self._cursor.get(name, now))
            self._cursor[name] = start + interval
        if start > now:
            self._sleep(start - now)
        pending = self._pending()
        pending[name] = pending.get(name, 0) + 1

    def account(self, host: str, requests: int) -> None:
        """Charge the ``requests`` GDAL made for the file that :meth:`wait` let start; the next start moves back."""
        if isinstance(requests, bool) or not isinstance(requests, int) or requests < 0:
            raise ValueError("requests is a whole number, 0 or more")
        name = normalize_host(host)
        pending = self._pending()
        if pending.get(name, 0) < 1:
            raise RuntimeError("account() without a wait() of this thread for the host")
        pending[name] -= 1
        with self._lock:
            self._cursor[name] += (requests - 1) * self.interval_for(name)

    def _pending(self) -> dict[str, int]:
        if not hasattr(self._open, "counts"):
            self._open.counts = {}
        return self._open.counts  # type: ignore[no-any-return]
