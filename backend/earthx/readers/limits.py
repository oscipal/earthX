"""The cap per host on the files a process reads, for the process that sets one (M5-36 §5.2).

GDAL opens its connections itself, so the gateway's counter (:class:`~earthx.gateway.ReadSlots`) has to be taken where a
file is opened. The tiler sets its counter here once at start (:func:`limit_reads`); every
:class:`~earthx.readers.cog.CogReader` of the process then holds a slot of its host from open to close, and the Zarr
stores share a gateway on the same counter. A process that sets nothing (worker, runner, ``materialize``, ``api``,
whose searches take their slots themselves) reads as before.

**One holder per host and context.** A context that holds a host's slot does not take a second one for it: a route that
took its slots in the event loop before the thread pool (:func:`hold_hosts`), or a reader that opens a second file of
the same host in the same thread, would otherwise wait for itself. A thread pool of its own does not inherit the
context; :func:`carry_held` hands it over where the threads read for one holder.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterable, Iterator
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import Any, TypeVar

from earthx.gateway import ReadSlots

__all__ = ["carry_held", "hold_hosts", "limit_reads", "process_slots", "read_slot"]

_SLOTS: ReadSlots | None = None
# The hosts this context holds a slot of, one entry per hold (a reader may close after a later one opened).
_HELD: ContextVar[tuple[str, ...]] = ContextVar("earthx_held_hosts", default=())
_T = TypeVar("_T")


def limit_reads(slots: ReadSlots | None) -> None:
    """Set the counter of this process, or take it away with ``None`` (tests)."""
    global _SLOTS
    _SLOTS = slots


def process_slots() -> ReadSlots | None:
    """The counter of this process, ``None`` where none is set."""
    return _SLOTS


def _counted(host: str | None) -> bool:
    slots = _SLOTS
    return slots is not None and host is not None and host not in _HELD.get() and slots.policy.allows_host(host)


def _add(hosts: Iterable[str]) -> None:
    _HELD.set(_HELD.get() + tuple(hosts))


def _remove(hosts: Iterable[str]) -> None:
    held = list(_HELD.get())
    for host in hosts:
        if host in held:
            held.remove(host)
    _HELD.set(tuple(held))


@contextmanager
def read_slot(host: str | None) -> Iterator[None]:
    """Hold a slot of ``host`` in this thread for the block, unless nothing is to be counted.

    Nothing is counted without a counter, for a file on disk (``None``), for a host this context holds already and for
    a host off the counter's allowlist (the object store of the results, adr/0015 §14c, is no source).
    """
    if not _counted(host):
        yield
        return
    assert _SLOTS is not None and host is not None
    with _SLOTS.slot(host):
        _add([host])
        try:
            yield
        finally:
            _remove([host])


@asynccontextmanager
async def hold_hosts(hosts: Iterable[str | None]) -> AsyncIterator[None]:
    """Hold a slot of each of ``hosts`` on the event loop for the block, in the order of their names (no deadlock
    between two requests that need the same hosts), so that the threads of the request never wait for one."""
    async with AsyncExitStack() as stack:
        taken = sorted({host for host in hosts if _counted(host)})
        for host in taken:
            assert _SLOTS is not None
            await stack.enter_async_context(_SLOTS.aslot(host))
        _add(taken)
        try:
            yield
        finally:
            _remove(taken)


def carry_held(function: Callable[..., _T]) -> Callable[..., _T]:
    """``function`` running with the hosts this context holds, in whichever thread calls it."""
    held = _HELD.get()

    def run(*args: Any, **kwargs: Any) -> _T:
        token = _HELD.set(held)
        try:
            return function(*args, **kwargs)
        finally:
            _HELD.reset(token)

    return run
