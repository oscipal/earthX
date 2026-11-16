"""The cap per host on the files a process reads, for the process that sets one (M5-36 §5.2).

GDAL opens its connections itself, so the gateway's counter (:class:`~earthx.gateway.ReadSlots`) has to be taken where a
file is opened. The tiler sets its counter here once at start (:func:`limit_reads`); every
:class:`~earthx.readers.cog.CogReader` of the process then holds a slot of its host from open to close, and the Zarr
stores share a gateway on the same counter. A process that sets nothing (worker, runner, ``materialize``, ``api``,
whose searches take their slots themselves) reads as before.

**Taken in the thread that reads, never in the event loop.** A route runs in a thread of the shared pool; had it taken
its slot in the event loop first, a request holding a slot and waiting for a thread, and a thread waiting for that slot,
could wait for each other (review of M5-36 PR 2). In threads every holder of a slot is reading.

**One holder per host and context.** A context that holds a host's slot does not take a second one for it: a reader
that opens a second file of the same host in the same thread (a download, a step over several assets) would otherwise
wait for itself. A reader that opens files in one thread and reads them in others (the first scene of a mosaic tile
with steps) opens them :func:`uncounted` and reads them under :func:`read_slots` in the thread that reads, so the
cap holds for the reads and no thread holds a slot while it waits for another.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar

from earthx.gateway import ReadSlots

__all__ = ["limit_reads", "process_slots", "read_slot", "read_slots", "uncounted"]

_SLOTS: ReadSlots | None = None
# The hosts this context holds a slot of, one entry per hold (a reader may close after a later one opened).
_HELD: ContextVar[tuple[str, ...]] = ContextVar("earthx_held_hosts", default=())


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


@contextmanager
def uncounted(hosts: Iterable[str | None]) -> Iterator[None]:
    """Open files of ``hosts`` in the block without taking a slot, for a reader that reads them later under
    :func:`read_slots` in another thread: a slot held across the reads of other threads would make them wait for it."""
    names = [host for host in hosts if host is not None]
    _add(names)
    try:
        yield
    finally:
        _remove(names)


@contextmanager
def read_slots(hosts: Iterable[str | None]) -> Iterator[None]:
    """Hold a slot of each of ``hosts`` for the block (:func:`read_slot`), in the order of their names."""
    with ExitStack() as stack:
        for host in sorted({host for host in hosts if host is not None}):
            stack.enter_context(read_slot(host))
        yield
