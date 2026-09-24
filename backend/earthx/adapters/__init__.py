"""Source protocols: discovery, search, access resolution, aggregation.

One adapter per source protocol (architekturplan.md 6.1). ``earth_search`` speaks
Earth Search v1 (Sentinel-2 L2A as COG); ``eopf_stac`` speaks the EOPF Sentinel Zarr
Samples Service (the same dataset again, as Zarr, M2-09b). Both answer search and
access resolution; Earth Search also answers the coverage aggregation of adr/0004
since M2-05. Discovery follows with the harvester (M5).

Everything an adapter sends goes through ``gateway``; what it needs to know about a
dataset it reads from ``catalog``. Which adapter serves which collection is decided
by the caller from ``earthx:source`` (adr/0005 rule I) — from M1-07 on that caller is
the federating client in ``api``, through :func:`search_items`/:func:`get_item`
below, which dispatch on the registry entry's own ``earthx:source.adapter`` rather
than making the caller pick a module. A dataset added to the registry under an
``AdapterKind`` this dispatch does not know is a dispatch mistake, not a wrong
answer: :class:`UnsupportedSource`, the same error each adapter's own
``resolve_dataset`` raises for a mismatch it catches itself.
"""

from __future__ import annotations

from types import ModuleType
from typing import Any

from earthx.adapters import earth_search, eopf_stac
from earthx.adapters.cache import CacheValue, SearchCache
from earthx.adapters.earth_search_coverage import aggregate_coverage
from earthx.adapters.federated_search import (
    DEFAULT_LIMIT,
    MAX_IDS,
    MAX_INTERSECTS_POINTS,
    MAX_LIMIT,
    InvalidQuery,
    ItemPage,
    SearchParams,
    UnknownCollection,
    UnsupportedFilter,
    UnsupportedSource,
    UpstreamShapeError,
)
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import AdapterKind, DatasetRegistry, UnknownDatasetError
from earthx.gateway import Gateway

# One module per adapter kind — the only place that has to know every adapter this
# platform speaks. Adding a third source means one more line here, not a change to
# every caller of `search_items`/`get_item`.
_ADAPTERS = {
    AdapterKind.EARTH_SEARCH_V1: earth_search,
    AdapterKind.EOPF_STAC_V1: eopf_stac,
}


def _adapter_for(dataset_id: str, registry: DatasetRegistry) -> ModuleType:
    """The module that serves ``dataset_id``, or the error its absence means."""
    try:
        kind = registry.get(dataset_id).source.adapter
    except UnknownDatasetError:
        raise UnknownCollection(dataset_id) from None
    try:
        return _ADAPTERS[kind]
    except KeyError:
        raise UnsupportedSource(f"{dataset_id} is served by {kind}, which no adapter dispatch knows") from None


def _check_capabilities(dataset_id: str, adapter: ModuleType, params: SearchParams | None) -> None:
    """M3-08 F4a: a filter this dataset's own source cannot honour is refused by
    name here, before the adapter ever builds a request — the posture M2-17 already
    took for *every* federated collection when no adapter could honour either filter
    (`api/federating_client.py`); this narrows that refusal to the one collection
    (and, in principle, the one filter) that genuinely cannot.

    Both current adapters support both filters (measured, M3-08 plan §2.1); this
    only matters once a third source does not, which `test_every_adapter_supports_
    intersects_and_ids` (`tests/earthx/adapters/test_dispatch.py`) turns into a
    build failure rather than a silent gap the day that happens — K8 requires the
    landing page's ``item-search`` promise to match the weakest adapter, and this is
    the one place that promise could quietly stop being true.
    """
    if params is None:
        return
    if params.intersects is not None and not getattr(adapter, "SUPPORTS_INTERSECTS", False):
        raise UnsupportedFilter(f"{dataset_id} does not support intersects")
    if params.ids is not None and not getattr(adapter, "SUPPORTS_IDS", False):
        raise UnsupportedFilter(f"{dataset_id} does not support ids")


async def search_items(
    dataset_id: str,
    params: SearchParams | None = None,
    *,
    gateway: Gateway,
    registry: DatasetRegistry = REGISTRY,
    cache: SearchCache | None = None,
) -> ItemPage:
    """Search items of one federated collection, whichever source serves it."""
    adapter = _adapter_for(dataset_id, registry)
    _check_capabilities(dataset_id, adapter, params)
    return await adapter.search_items(dataset_id, params, gateway=gateway, registry=registry, cache=cache)


async def get_item(
    dataset_id: str,
    item_id: str,
    *,
    gateway: Gateway,
    registry: DatasetRegistry = REGISTRY,
    cache: SearchCache | None = None,
) -> dict[str, Any]:
    """One item by id, without a search in front of it, whichever source serves it."""
    adapter = _adapter_for(dataset_id, registry)
    return await adapter.get_item(dataset_id, item_id, gateway=gateway, registry=registry, cache=cache)


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_IDS",
    "MAX_INTERSECTS_POINTS",
    "MAX_LIMIT",
    "CacheValue",
    "InvalidQuery",
    "ItemPage",
    "SearchCache",
    "SearchParams",
    "UnknownCollection",
    "UnsupportedFilter",
    "UnsupportedSource",
    "UpstreamShapeError",
    "aggregate_coverage",
    "get_item",
    "search_items",
]
