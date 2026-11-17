"""The gateway of `materialize` and the harvester: limits per host shared by all their instances (M5-37 §5.3).

:func:`open_source_gateway` opens a connection of its own, in autocommit and apart from the run's transaction, and
hands the gateway a :class:`~earthx.catalog.source_hosts.PostgresHostCoordinator` on it: spacing and connections from
``hosts.yaml`` (in the policy) then hold for every run of every instance together, and a host that keeps failing rests
for all of them. Connection details come from the environment (``PGHOST`` and friends), like the run's own connection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import psycopg

from earthx.catalog.source_hosts import PostgresHostCoordinator
from earthx.gateway import Gateway, Policy

__all__ = ["open_source_gateway"]


async def _connect() -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(autocommit=True)


@asynccontextmanager
async def open_source_gateway(
    policy: Policy, *, connect: Callable[[], Awaitable[psycopg.AsyncConnection]] = _connect, **options: Any
) -> AsyncIterator[Gateway]:
    """A gateway under ``policy`` whose turns, places and breaker per host live in Postgres; closed with the block.

    ``options`` go to the :class:`~earthx.gateway.Gateway` as they are (its transport and resolver are seams for tests).
    """
    async with (
        await connect() as conn,
        Gateway(policy, coordinator=PostgresHostCoordinator(conn), **options) as gateway,
    ):
        yield gateway
