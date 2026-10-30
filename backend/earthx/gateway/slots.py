"""A limit on the GDAL readers that run at once against one host (adr/0005 §6, DS-03 plan §6.9 F2d).

The gateway's own client holds one semaphore per host. GDAL does not go through that client: it opens its
connections itself, so a measurement that reads many scenes in threads would otherwise load one bucket without
bound. :class:`ReadSlots` is the same limit for those readers.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from earthx.gateway.errors import UrlRejected
from earthx.gateway.policy import Policy, normalize_host


class ReadSlots:
    """At most ``policy.max_connections_per_host`` GDAL reads to one host run at once in this process.

    ``with slots.slot(host):`` blocks until fewer than that many readers hold a slot for the host, and gives the
    slot back when the block ends, by an error too. This caps readers, not sockets: GDAL decides how many
    connections a reader opens (adr/0005 §6 sets the number; the cap is on the callers that wait for it).

    One instance per process, shared by every search, so the load on a source stays fixed however many users
    search at once (DS-03 plan §6.9 F2d). The host is compared in the gateway's one spelling (``normalize_host``),
    so ``Bucket.Example.org`` and ``bucket.example.org.`` share a slot. A host the policy does not allow gets no
    slot (:class:`~earthx.gateway.UrlRejected`): a reader there would never pass ``check_url`` anyway. Thread-safe;
    knows nothing of datasets. A slot is not reentrant: a thread that holds one must not ask for the same host again.
    """

    def __init__(self, policy: Policy) -> None:
        if policy.max_connections_per_host < 1:
            raise ValueError("max_connections_per_host is at least 1")
        self._policy = policy
        self._limit = policy.max_connections_per_host
        self._lock = threading.Lock()
        self._semaphores: dict[str, threading.BoundedSemaphore] = {}

    @contextmanager
    def slot(self, host: str) -> Iterator[None]:
        """Wait for a free slot of ``host``, hold it for the block."""
        name = normalize_host(host)
        if not self._policy.allows_host(name):
            raise UrlRejected("host is not on the allowlist", host=name)
        semaphore = self._semaphore(name)
        with semaphore:
            yield

    def _semaphore(self, host: str) -> threading.BoundedSemaphore:
        with self._lock:
            if host not in self._semaphores:
                self._semaphores[host] = threading.BoundedSemaphore(self._limit)
            return self._semaphores[host]
