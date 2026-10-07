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

from earthx.adapters import AdapterSpecs, InvalidQuery, UnknownCollection, UnsupportedSource, dataset_config, get_item
from earthx.catalog.pgstac import fetch_item, read_item_holdings
from earthx.catalog.registry import DatasetRegistry, ItemHolding
from earthx.catalog.search_cache import PostgresSearchCache
from earthx.gateway import Gateway, GatewayError, UpstreamError, UpstreamTimeout

LOGGER = logging.getLogger("earthx.api.item_source")

ItemSource = Callable[[str, str], Awaitable[dict[str, Any]]]

__all__ = [
    "ItemHoldingMismatch",
    "ItemSource",
    "MaterializedCatalogUnavailable",
    "MaterializedItemNotFound",
    "OrderRefused",
    "build_item_source",
    "check_item_holdings",
    "fetch_item_or_refuse",
    "item_holding_of",
    "malformed_item_detail",
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
    return dataset_config(registry, dataset_id).source.item_holding


def build_item_source(registry: DatasetRegistry, adapters: AdapterSpecs, gateway: Gateway, pool: Any) -> ItemSource:
    """How a process gets an item: federated through the adapter and gateway, or
    materialized straight out of pgstac (M3-11a, K-05).

    A closure rather than a dependency of its own, so that a test can put a recorded
    item in its place without a database and without a network (adr/0002 §2).
    """

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        config = dataset_config(registry, dataset_id)
        if config.source.item_holding is ItemHolding.MATERIALIZED:
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
            return await get_item(config, item_id, adapters=adapters, gateway=gateway)
        async with pool.connection() as conn:
            return await get_item(config, item_id, adapters=adapters, gateway=gateway, cache=PostgresSearchCache(conn))

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


class OrderRefused(Exception):
    """An order, or an item it names, is turned away.

    ``detail`` is English, short and redacted: it names datasets, items and fields,
    never an AOI, an address or a hash (adr/0014 §4.7). The caller turns
    ``status_code`` and ``detail`` into its own answer, in one line.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def malformed_item_detail(item: str) -> str:
    return f"the source did not deliver item {item!r} intact"


async def fetch_item_or_refuse(item_source: ItemSource, dataset: str, item: str, *, not_found: int = 404) -> dict[str, Any]:
    """The item, or the :class:`OrderRefused` its absence or the source's failure maps to.

    The tile routes and the intake turn a ``dataset``/``item`` pair into a STAC item
    through the same ``item_source``, and a source failure means the same thing to
    both. ``not_found`` is the status for a dataset or item that does not exist: the
    tile routes name them in the path and answer ``404``, an order names them in the
    body and answers ``422``.

    An item whose ``id`` is missing or is not the one asked for is the source's
    mistake, the same ``502`` either way (Otto's review of M4-01a): the asset that
    gets opened is named after the item's own id, and a tile must not show another
    scene under the name it asked for.
    """
    try:
        fetched = await item_source(dataset, item)
    except UnknownCollection:
        raise OrderRefused(not_found, f"no dataset {dataset!r}") from None
    except MaterializedItemNotFound:
        # The materialized counterpart of the federated `UpstreamError` 404 below —
        # same message, so a caller cannot tell which path answered it.
        raise OrderRefused(not_found, f"no item {item!r} in {dataset!r}") from None
    except MaterializedCatalogUnavailable:
        raise OrderRefused(503, "the catalogue is not available") from None
    except UnsupportedSource as error:
        raise OrderRefused(501, str(error)) from None
    except InvalidQuery as error:
        raise OrderRefused(400, str(error)) from None
    except UpstreamError as error:
        if error.status_code == 404:
            raise OrderRefused(not_found, f"no item {item!r} in {dataset!r}") from None
        # The source answered something we do not pass on. Its text is not repeated:
        # it can carry the query, and the query can carry an AOI (projektplan.md 7).
        raise OrderRefused(502, "the source did not deliver the item") from None
    except UpstreamTimeout:
        raise OrderRefused(504, "the source did not answer in time") from None
    except GatewayError:
        # Unreachable, too large, too many redirects: the source's side of the line.
        # Broad on purpose — a gateway error that has no branch of its own is still an
        # answer about the source, and a 500 would call it our mistake.
        raise OrderRefused(502, "the item could not be fetched") from None
    if fetched.get("id") != item:
        raise OrderRefused(502, malformed_item_detail(item))
    return fetched
