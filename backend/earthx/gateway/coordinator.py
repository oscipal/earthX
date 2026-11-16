"""Spacing, places and a breaker per host that several instances share (M5-37, docs/plans/m5/m5-37-zeiger-je-host.md §5.1).

`gateway` keeps no state beyond its object and knows no database (KLAERUNGEN B8, B9). A shell that wants a host's
limits to hold across instances hands a :class:`HostCoordinator` in (``Gateway(policy, coordinator=…)``); its one
implementation lives with the shell and keeps the state in Postgres (``earthx.catalog.source_hosts``). Without one the
gateway keeps spacing and cap in its own object, as before.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

__all__ = ["MAX_SHARED_WAIT_S", "HostCoordinator"]

#: A caller waits at most this long for a turn; a host whose turn is further off rests for the run instead (M5-37 J4).
MAX_SHARED_WAIT_S = 60.0


class HostCoordinator(Protocol):
    """What the gateway asks before and after each attempt at a host, shared by every instance that asks the same."""

    async def reserve(self, host: str, interval_s: float, max_wait_s: float) -> float:
        """Seconds until the host's next turn, at least 0; taken and moved on by ``interval_s`` unless further than
        ``max_wait_s`` off, so that a caller who will not wait does not lengthen the queue or a pause."""
        ...

    async def pause_left(self, host: str) -> float:
        """Seconds the host is still paused by the breaker, 0 if it is not."""
        ...

    def place(self, host: str, cap: int) -> AbstractAsyncContextManager[object]:
        """Hold one of the host's ``cap`` places for the block; waits for a free one, gives it back on any exit."""
        ...

    async def report(self, host: str, *, failed: bool, retry_after_s: float | None = None) -> None:
        """Say how an attempt ended: a failure counts towards the breaker, a ``Retry-After`` moves the turn on."""
        ...
