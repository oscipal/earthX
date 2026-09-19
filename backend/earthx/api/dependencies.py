"""What the federating client needs besides pgstac: a gateway, and a cache pool.

Two database drivers live in this process on purpose (docs/plans/m1-07-stac-api.md
§5): ``stac-fastapi-pgstac`` speaks ``asyncpg``/``buildpg`` to pgstac itself, and this
module opens a second, small ``psycopg`` pool for the pieces M1-04 and M1-06 already
built on ``psycopg`` — the registry's collection load and the search cache. Rebuilding
either on ``asyncpg`` would touch code that is already accepted and tested, for a pool
this process's traffic does not make the bottleneck.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg_pool import AsyncConnectionPool

from earthx.catalog.registry import DatasetRegistry
from earthx.gateway import Gateway, Policy, host_of

# Small on purpose (§5 of the plan): this pool serves only the registry existence
# check and the search cache, never pgstac's own item storage.
_CACHE_POOL_MIN_SIZE = 1
_CACHE_POOL_MAX_SIZE = 5


def policy_from_registry(registry: DatasetRegistry) -> Policy:
    """The gateway's allowlist, from the sources the registry actually names.

    KLAERUNGEN B13 / the ``Policy`` docstring: from M1-04 on, the registry decides the
    allowlist, not an environment variable — a dataset added to the registry is
    automatically one the gateway may reach, and nothing else is.
    """
    hosts = {host_of(config.source.endpoint) for config in registry}
    return Policy(allowed_hosts=frozenset(hosts))


def build_gateway(registry: DatasetRegistry) -> Gateway:
    """One gateway for the process, built once at startup like the DB pools are."""
    return Gateway(policy_from_registry(registry))


@asynccontextmanager
async def cache_pool() -> AsyncIterator[AsyncConnectionPool]:
    """A small pool for the search cache, opened for the process lifetime.

    Connection details come from the standard ``PG*`` environment variables (libpq
    convention), the same ones ``earthx.catalog.load`` and CI already use — no
    second place to configure them.
    """
    pool = AsyncConnectionPool(
        conninfo="",
        min_size=_CACHE_POOL_MIN_SIZE,
        max_size=_CACHE_POOL_MAX_SIZE,
        kwargs={"autocommit": True},
        open=False,
    )
    await pool.open(wait=True)
    try:
        yield pool
    finally:
        await pool.close()
