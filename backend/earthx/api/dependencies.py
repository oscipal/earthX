"""What the federating client needs besides pgstac: a gateway, and a cache pool.

Two database drivers live in this process on purpose (docs/plans/m1-07-stac-api.md
§5): ``stac-fastapi-pgstac`` speaks ``asyncpg``/``buildpg`` to pgstac itself, and this
module opens a second, small ``psycopg`` pool for the pieces M1-04 and M1-06 already
built on ``psycopg`` — the registry's collection load and the search cache. Rebuilding
either on ``asyncpg`` would touch code that is already accepted and tested, for a pool
this process's traffic does not make the bottleneck.

Two later tasks put the *same* pool to a third use that its name no longer quite
covers: M3-11a reads a materialized dataset's own items through it
(``catalog.pgstac.fetch_item``, from ``api.coverage_route``'s and ``api.tiler``'s
``earthx_cache_pool``), and M3-11c's ``local-sql`` area way
(``catalog.local_coverage.area_coverage``) unions them. Small still, on purpose — only
this process's own traffic, never a bulk read.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass

from psycopg_pool import AsyncConnectionPool

from earthx.catalog.registry import DatasetRegistry
from earthx.gateway import Gateway, GatewayError, Policy, host_of, inspect_url

LOGGER = logging.getLogger("earthx.api.dependencies")

# Small on purpose (§5 of the plan): this process's own traffic, never a bulk read
# — a handful of item reads and one union over a materialized collection's own
# footprints per request, not a batch load (module docstring).
_CACHE_POOL_MIN_SIZE = 1
_CACHE_POOL_MAX_SIZE = 5

# M3-07a: the geocoder's own gateway, built and validated separately from the
# registry's (below). An unset `EARTHX_GEOCODER_URL` turns place search off — the
# safe end of the range, like an empty `EARTHX_ALLOWED_HOSTS`.
GEOCODER_URL_ENV = "EARTHX_GEOCODER_URL"
GEOCODER_USER_AGENT_ENV = "EARTHX_GEOCODER_USER_AGENT"
DEFAULT_GEOCODER_USER_AGENT = "EarthX/0.1 (+https://github.com/oscipal/earthX)"

# Measured against the live service in the plan step (plan §3): Russia's outline at
# the smallest threshold we ask for is a little over 0.6 MB. Tighter than the
# registry gateway's defaults on purpose — this gateway only ever talks to one host
# for one small answer, never a dataset's assets.
_GEOCODER_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_GEOCODER_CONNECTIONS_PER_HOST = 1
_GEOCODER_READ_TIMEOUT_S = 10.0


@dataclass(frozen=True, slots=True)
class GeocoderConfig:
    base_url: str
    user_agent: str


def resolve_geocoder_config(environ: Mapping[str, str] | None = None) -> GeocoderConfig | None:
    """The geocoder's settings from the environment, or None if place search is off.

    The usage policy of the public service (plan §2.1) asks that it can be switched
    "at our request at any time" "without requiring a software update" — an
    environment variable is what makes that possible without a release.
    """
    values = environ if environ is not None else os.environ
    raw = values.get(GEOCODER_URL_ENV, "").strip()
    if not raw:
        return None
    user_agent = values.get(GEOCODER_USER_AGENT_ENV, "").strip() or DEFAULT_GEOCODER_USER_AGENT
    return GeocoderConfig(base_url=raw.rstrip("/"), user_agent=user_agent)


def build_geocoder(environ: Mapping[str, str] | None = None) -> tuple[Gateway, GeocoderConfig] | None:
    """The geocoder's own gateway and its resolved settings, or None if place search
    is unset or not usable.

    A bad ``EARTHX_GEOCODER_URL`` disables place search rather than this whole
    process — nothing else in `api` depends on it. Checked once at startup, not on
    every request: only ``https``, no credentials, the standard port, and no query
    string of its own (appending our own request parameters to one would otherwise
    silently replace or merge with whatever was already there).
    """
    config = resolve_geocoder_config(environ)
    if config is None:
        return None
    try:
        if "?" in config.base_url:
            raise GatewayError(f"{GEOCODER_URL_ENV} must not carry a query string")
        policy = Policy(
            allowed_hosts=frozenset({host_of(config.base_url)}),
            max_response_bytes=_GEOCODER_MAX_RESPONSE_BYTES,
            max_connections_per_host=_GEOCODER_CONNECTIONS_PER_HOST,
            read_timeout_s=_GEOCODER_READ_TIMEOUT_S,
        )
        inspect_url(config.base_url, policy)
    except GatewayError:
        # Never the value itself (KLAERUNGEN D "keine internen URLs ... in Logs"):
        # a GatewayError's own text never repeats the raw URL, only the reason
        # (gateway/errors.py), so `exc_info=True` here cannot leak it either.
        LOGGER.warning(f"{GEOCODER_URL_ENV} is set but not usable; place search stays off", exc_info=True)
        return None
    return Gateway(policy), config


def policy_from_registry(registry: DatasetRegistry) -> Policy:
    """The gateway's allowlist, from the sources the registry actually names.

    KLAERUNGEN B13 / the ``Policy`` docstring: from M1-04 on, the registry decides the
    allowlist, not an environment variable — a dataset added to the registry is
    automatically one the gateway may reach, and nothing else is.
    """
    hosts = {host_of(config.source.endpoint) for config in registry}
    # The assets lie on a different host from the catalogue, and without this line the
    # search works while every read of a COG is refused (adr/0006 §3.3, D12). The field
    # has no default: a dataset that names no asset host opens nothing, which is the
    # safe end of the range.
    hosts |= {host for config in registry for host in config.source.asset_hosts}
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
