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
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal

from earthx.adapters import (
    AdapterSpecs,
    InvalidQuery,
    RetiredCollection,
    UnknownCollection,
    UnsupportedSource,
    dataset_config,
    get_item,
    search_items,
)
from earthx.adapters.federated_search import SearchParams
from earthx.catalog.pgstac import fetch_item, read_item_holdings, search_items_by_ids
from earthx.catalog.registry import DatasetRegistry, ItemHolding
from earthx.catalog.search_cache import PostgresSearchCache
from earthx.gateway import Gateway, GatewayError, UpstreamError, UpstreamTimeout

LOGGER = logging.getLogger("earthx.api.item_source")

ItemSource = Callable[[str, str], Awaitable[dict[str, Any]]]
#: Many items of one dataset by id in one call (at most ``adapters.MAX_IDS``); the ones the source has, in no set order.
ItemBatchSource = Callable[[str, Sequence[str]], Awaitable[list[dict[str, Any]]]]

__all__ = [
    "ItemBatchSource",
    "ItemHoldingMismatch",
    "ItemSource",
    "MaterializedCatalogUnavailable",
    "MaterializedItemNotFound",
    "OrderRefused",
    "Stage",
    "build_item_batch_source",
    "build_item_source",
    "check_item_holdings",
    "fetch_item_or_refuse",
    "fetch_items_or_refuse",
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


def build_item_batch_source(
    registry: DatasetRegistry, adapters: AdapterSpecs, gateway: Gateway, pool: Any
) -> ItemBatchSource:
    """How a process gets up to ``MAX_IDS`` items by id in one request: one search of the source, or one query of pgstac.

    The creation of a mosaic selection names up to two thousand scenes, too many for one request each
    (:func:`build_item_source`). Neither the item cache nor the search cache is used: a selection that exists is not
    fetched again, and one that does not is created once.
    """

    async def batch_source(dataset_id: str, item_ids: Sequence[str]) -> list[dict[str, Any]]:
        config = dataset_config(registry, dataset_id)
        if config.source.item_holding is ItemHolding.MATERIALIZED:
            if pool is None:
                raise MaterializedCatalogUnavailable(dataset_id)
            async with pool.connection() as conn:
                return await search_items_by_ids(conn, dataset_id, item_ids)  # type: ignore[return-value]
        params = SearchParams(ids=tuple(item_ids), limit=len(item_ids))
        page = await search_items(config, params, adapters=adapters, gateway=gateway)
        return list(page.items)

    return batch_source


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


#: Where an order was turned away, as a fixed identifier for the log (M4-07b, Otto's review of #123).
#: In the order of the intake: the order itself, its size, dataset, licence, operators, items,
#: AOI against the items, resolving an asset, its address, bands, version, the recipe as a whole.
Stage = Literal[
    "order", "size", "dataset", "license", "applicable", "items", "aoi", "resolve", "hosts", "bands", "version", "recipe"
]  # fmt: skip


class OrderRefused(Exception):
    """An order, or an item it names, is turned away.

    ``detail`` is English, short and redacted: it names datasets, items and fields,
    never an AOI, an address or a hash (adr/0014 §4.7). The caller turns
    ``status_code`` and ``detail`` into its own answer, in one line. ``stage`` says
    where, as one of a fixed set, so a log line can name it without repeating anything
    the order contained.
    """

    def __init__(self, status_code: int, detail: str, stage: Stage) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.stage: Stage = stage


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
    fetched = await _or_refuse(
        item_source(dataset, item), dataset, f"no item {item!r} in {dataset!r}", "the source did not deliver the item", not_found
    )
    if fetched.get("id") != item:
        raise OrderRefused(502, malformed_item_detail(item), "items")
    return fetched


async def fetch_items_or_refuse(
    batch_source: ItemBatchSource, dataset: str, item_ids: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """The items with these ids, by id, from one call of ``batch_source``, or the :class:`OrderRefused` of its failure.

    A source failure maps as it does for one item (:func:`fetch_item_or_refuse`). An id the source does not return is a
    ``404`` that names it; an item it returns under an id nobody asked for is left out.
    """
    found = await _or_refuse(
        batch_source(dataset, item_ids),
        dataset,
        f"no items in {dataset!r}",
        "the source did not deliver the items",
        404,
    )
    wanted = set(item_ids)
    by_id = {item["id"]: item for item in found if isinstance(item, dict) and item.get("id") in wanted}
    missing = sorted(wanted - by_id.keys())
    if missing:
        raise OrderRefused(404, f"no item {missing[0]!r} in {dataset!r}", "items")
    return by_id


async def _or_refuse(call: Awaitable[Any], dataset: str, absent: str, not_delivered: str, not_found: int) -> Any:
    """``await call``, with the failures of the item source mapped to :class:`OrderRefused`; ``absent`` says what a 404 meant."""
    try:
        return await call
    except RetiredCollection as error:
        raise OrderRefused(410, error.retired.message, "items") from None
    except UnknownCollection:
        raise OrderRefused(not_found, f"no dataset {dataset!r}", "items") from None
    except MaterializedItemNotFound:
        # The materialized counterpart of the federated `UpstreamError` 404 below —
        # same message, so a caller cannot tell which path answered it.
        raise OrderRefused(not_found, absent, "items") from None
    except MaterializedCatalogUnavailable:
        raise OrderRefused(503, "the catalogue is not available", "items") from None
    except UnsupportedSource as error:
        raise OrderRefused(501, str(error), "items") from None
    except InvalidQuery as error:
        raise OrderRefused(400, str(error), "items") from None
    except UpstreamError as error:
        if error.status_code == 404:
            raise OrderRefused(not_found, absent, "items") from None
        # The source answered something we do not pass on. Its text is not repeated:
        # it can carry the query, and the query can carry an AOI (projektplan.md 7).
        raise OrderRefused(502, not_delivered, "items") from None
    except UpstreamTimeout:
        raise OrderRefused(504, "the source did not answer in time", "items") from None
    except GatewayError:
        # Unreachable, too large, too many redirects: the source's side of the line.
        # Broad on purpose — a gateway error that has no branch of its own is still an
        # answer about the source, and a 500 would call it our mistake.
        raise OrderRefused(502, "the item could not be fetched", "items") from None
