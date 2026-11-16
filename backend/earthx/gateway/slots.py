"""One limit per host and process, for GDAL readers and for the gateway's own requests (adr/0005 §6, M5-36 §4.1).

The gateway's client asks on an event loop; GDAL opens its connections itself, in threads, and never meets the client.
If each kept a counter of its own, one process could put twice the cap on a host. :class:`ReadSlots` is the one counter
both ask: ``with slots.slot(host):`` in a thread, ``async with slots.aslot(host):`` on an event loop.
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from earthx.gateway.errors import UrlRejected
from earthx.gateway.policy import Policy, normalize_host


class _Waiter:
    """One caller in the queue of a host; ``granted`` is set under the lock of :class:`ReadSlots`."""

    __slots__ = ("event", "future", "granted", "loop")

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self.granted = False
        self.loop = loop
        self.event = threading.Event() if loop is None else None
        self.future: asyncio.Future[None] | None = None if loop is None else loop.create_future()

    def wake(self) -> bool:
        """Hand the slot over; False if the waiter can no longer take it (its loop is gone)."""
        if self.event is not None:
            self.granted = True
            self.event.set()
            return True
        future, loop = self.future, self.loop
        assert future is not None and loop is not None
        try:
            loop.call_soon_threadsafe(_resolve, future)
        except RuntimeError:
            return False
        self.granted = True
        return True


def _resolve(future: asyncio.Future[None]) -> None:
    if not future.done():
        future.set_result(None)


class _Host:
    __slots__ = ("held", "limit", "waiters")

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.held = 0
        self.waiters: deque[_Waiter] = deque()


class ReadSlots:
    """At most ``policy.connections_for(host)`` holders per host in this process, threads and event loops together.

    A holder is a GDAL reader (from open to close) or one request of the gateway (with its retries). Waiters are
    served in the order they asked, whichever side they wait on; an event loop is woken through
    ``call_soon_threadsafe`` and never blocks a thread. A slot comes back at the end of the block, by an error or a
    cancellation too. This caps holders, not sockets: GDAL decides how many connections a reader opens.

    One instance per process, shared by every caller, so the load on a source stays fixed however many users ask at
    once (DS-03 plan §6.9 F2d, M5-36). The host is compared in the gateway's one spelling (``normalize_host``). A host
    the policy does not allow gets no slot (:class:`~earthx.gateway.UrlRejected`). Knows nothing of datasets. A slot
    is not reentrant: a holder must not ask for the same host again, or it may wait for itself.
    """

    def __init__(self, policy: Policy) -> None:
        self._policy = policy
        self._lock = threading.Lock()
        self._hosts: dict[str, _Host] = {}

    @property
    def policy(self) -> Policy:
        return self._policy

    @contextmanager
    def slot(self, host: str) -> Iterator[None]:
        """Wait in this thread for a free slot of ``host``, hold it for the block."""
        name = self._name(host)
        waiter = self._take_or_queue(name, None)
        if waiter is not None:
            assert waiter.event is not None
            try:
                waiter.event.wait()
            except BaseException:
                self._give_up(name, waiter)
                raise
        try:
            yield
        finally:
            self._release(name)

    @asynccontextmanager
    async def aslot(self, host: str) -> AsyncIterator[None]:
        """Wait on the running event loop for a free slot of ``host``, hold it for the block."""
        name = self._name(host)
        waiter = self._take_or_queue(name, asyncio.get_running_loop())
        if waiter is not None:
            assert waiter.future is not None
            try:
                await waiter.future
            except BaseException:
                self._give_up(name, waiter)
                raise
        try:
            yield
        finally:
            self._release(name)

    def _name(self, host: str) -> str:
        name = normalize_host(host)
        if not self._policy.allows_host(name):
            raise UrlRejected("host is not on the allowlist", host=name)
        return name

    def _take_or_queue(self, name: str, loop: asyncio.AbstractEventLoop | None) -> _Waiter | None:
        with self._lock:
            state = self._hosts.get(name)
            if state is None:
                state = self._hosts[name] = _Host(self._policy.connections_for(name))
            if state.held < state.limit and not state.waiters:
                state.held += 1
                return None
            waiter = _Waiter(loop)
            state.waiters.append(waiter)
            return waiter

    def _give_up(self, name: str, waiter: _Waiter) -> None:
        """A waiter that stops waiting (cancelled, interrupted) leaves the queue, or passes on the slot it was handed."""
        with self._lock:
            if not waiter.granted:
                self._hosts[name].waiters.remove(waiter)
                return
        self._release(name)

    def _release(self, name: str) -> None:
        with self._lock:
            state = self._hosts[name]
            while state.waiters:
                if state.waiters.popleft().wake():
                    return
            state.held -= 1
