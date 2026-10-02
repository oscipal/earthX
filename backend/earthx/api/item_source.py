"""Where `api` and `tiler` get an item from, and the one place that decides
whether a dataset is federated or materialized (adr/0011 §7 D2, M4-01a).

The tiler's tiles, the AOI download and the STAC API's single-item route all fetch
an item by dataset and id; later the job intake will too. They share
:func:`build_item_source`, and the routing — through the adapter and `gateway`, or
out of our own pgstac — reads the Python registry through :func:`item_holding_of`,
nowhere else.

pgstac carries the same ``earthx:source.item_holding`` on every collection
``catalog.load`` wrote. Two truths agree only as long as that load runs after every
registry change, so :func:`check_item_holdings` compares them when a process starts
and refuses to start where they disagree (Otto, M4-01a F2).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from earthx.adapters import UnknownCollection, get_item
from earthx.catalog.pgstac import fetch_item, read_item_holdings
from earthx.catalog.registry import DatasetRegistry, ItemHolding, UnknownDatasetError
from earthx.catalog.search_cache import PostgresSearchCache
from earthx.gateway import Gateway

LOGGER = logging.getLogger("earthx.api.item_source")

ItemSource = Callable[[str, str], Awaitable[dict[str, Any]]]

__all__ = [
    "ItemHoldingMismatch",
    "ItemSource",
    "MaterializedCatalogUnavailable",
    "MaterializedItemNotFound",
    "build_item_source",
    "check_item_holdings",
    "item_holding_of",
]


class MaterializedItemNotFound(LookupError):
    """No item with this id in a materialized dataset's own pgstac collection."""


class MaterializedCatalogUnavailable(RuntimeError):
    """A materialized dataset's items live only in pgstac, and this process has no
    pool to reach it with (`api/dependencies.py::cache_pool` was not opened).

    Unlike a federated dataset — where the same pool is only a cache, and its
    absence merely means a slower re-fetch of the source (E5) — a materialized
    dataset's items have no other place to come from at all.
    """


class ItemHoldingMismatch(RuntimeError):
    """pgstac and the registry disagree about how a dataset's items are held."""


def item_holding_of(registry: DatasetRegistry, dataset_id: str) -> ItemHolding:
    """Federated or materialized, as the registry says — or :class:`UnknownCollection`."""
    try:
        return registry.get(dataset_id).source.item_holding
    except UnknownDatasetError:
        raise UnknownCollection(dataset_id) from None


def build_item_source(registry: DatasetRegistry, gateway: Gateway, pool: Any) -> ItemSource:
    """How a process gets an item: federated through the adapter and gateway, or
    materialized straight out of pgstac (M3-11a, K-05).

    A closure rather than a dependency of its own, so that a test can put a recorded
    item in its place without a database and without a network (adr/0002 §2).
    """

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        if item_holding_of(registry, dataset_id) is ItemHolding.MATERIALIZED:
            # No cache in front of this: the read is already local, and the item
            # cache below exists to spare a *federated* dataset a round trip to a
            # remote source, which is not the question here.
            if pool is None:
                raise MaterializedCatalogUnavailable(dataset_id)
            async with pool.connection() as conn:
                item = await fetch_item(conn, dataset_id, item_id)
            if item is None:
                raise MaterializedItemNotFound(item_id)
            return item
        if pool is None:
            return await get_item(dataset_id, item_id, gateway=gateway, registry=registry)
        async with pool.connection() as conn:
            return await get_item(
                dataset_id, item_id, gateway=gateway, registry=registry, cache=PostgresSearchCache(conn)
            )

    return item_source


async def check_item_holdings(registry: DatasetRegistry, conn: Any) -> tuple[str, ...]:
    """Refuse to go on where pgstac and the registry hold a dataset's items differently.

    Only a collection that both know is compared (Otto, M4-01a F2): there a
    different ``item_holding`` means the load did not run after a registry change,
    and every request would be routed one way while pgstac answers the other. A
    collection only pgstac knows is logged and left to be refused per request; a
    registry entry pgstac does not know is pgstac's own 404 (adr/0005 rule I).

    Returns the ids only pgstac knows, for the caller's log and for tests.
    """
    stored = await read_item_holdings(conn)
    known = {config.dataset_id: config.source.item_holding.value for config in registry}
    mismatched = sorted(dataset_id for dataset_id in stored.keys() & known.keys() if stored[dataset_id] != known[dataset_id])
    if mismatched:
        raise ItemHoldingMismatch(
            f"pgstac holds the items of {mismatched} differently from the registry; "
            "run `python -m earthx.catalog.load`"
        )
    unknown = tuple(sorted(stored.keys() - known.keys()))
    if unknown:
        LOGGER.warning(
            "pgstac carries collections the registry does not know; requests for them are refused",
            extra={"collections": list(unknown)},
        )
    return unknown
