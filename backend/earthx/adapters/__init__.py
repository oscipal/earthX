"""Source protocols: discovery, search, access resolution, aggregation.

One adapter per source protocol (architekturplan.md 6.1). ``earth_search`` speaks
Earth Search v1 (Sentinel-2 L2A as COG); ``eopf_stac`` speaks the EOPF Sentinel Zarr
Samples Service (the same dataset again, as Zarr, M2-09b). Both answer search and
access resolution; Earth Search also answers the coverage aggregation of adr/0004
since M2-05. ``cop_dem_bucket`` (M3-11b) speaks a third, structurally different
protocol: it never searches, it *materializes* — it turns a bucket's own tile list
into STAC items, once, for the one-off command in ``discovery``. Discovery follows
with the harvester proper (M5).

Everything an adapter sends goes through ``gateway``; what it needs to know about a
dataset it reads from ``catalog``. Which adapter serves which collection is decided
by the caller from ``earthx:source`` (adr/0005 rule I) — from M1-07 on that caller is
the federating client in ``api``, through :func:`search_items`/:func:`get_item`
below, which dispatch on the registry entry's own ``earthx:source.adapter`` rather
than making the caller pick a module. A dataset added to the registry under an
``AdapterKind`` this dispatch does not know is a dispatch mistake, not a wrong
answer: :class:`UnsupportedSource`, the same error each adapter's own
``resolve_dataset`` raises for a mismatch it catches itself.

:func:`materialize_items` is a second, separate dispatch (``_MATERIALIZERS``, not
``_ADAPTERS``): a materializing adapter answers no search and no single-item
request, so it has no place in the table :func:`search_items`/:func:`get_item`
read — ``_adapter_for`` below refuses a materialized dataset before it ever looks
there (M3-11a K-05), and a materializing ``AdapterKind`` is simply absent from
``_ADAPTERS`` rather than present with nothing useful to do.
"""

from __future__ import annotations

from types import ModuleType
from typing import Any

from earthx.adapters import cop_dem_bucket, earth_search, eopf_stac
from earthx.adapters.cache import CacheValue, SearchCache
from earthx.adapters.cop_dem_bucket import MaterializeOutcome, NotMaterialized
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
from earthx.catalog.registry import AdapterKind, DatasetConfig, DatasetRegistry, ItemHolding, UnknownDatasetError
from earthx.gateway import Gateway

# One module per adapter kind — the only place that has to know every adapter this
# platform speaks. Adding a fourth *federated* source means one more line here, not
# a change to every caller of `search_items`/`get_item`. `cop_dem_bucket` is
# deliberately absent (see `_MATERIALIZERS` below).
_ADAPTERS = {
    AdapterKind.EARTH_SEARCH_V1: earth_search,
    AdapterKind.EOPF_STAC_V1: eopf_stac,
}

# The materializing counterpart of `_ADAPTERS`, read only by `materialize_items`
# below — never by `search_items`/`get_item`, which a materialized dataset never
# reaches (`_adapter_for` refuses it first).
_MATERIALIZERS = {
    AdapterKind.COP_DEM_BUCKET: cop_dem_bucket,
}


def _adapter_for(dataset_id: str, registry: DatasetRegistry) -> ModuleType:
    """The module that serves ``dataset_id``, or the error its absence means."""
    try:
        config = registry.get(dataset_id)
    except UnknownDatasetError:
        raise UnknownCollection(dataset_id) from None
    if config.source.item_holding is ItemHolding.MATERIALIZED:
        # M3-11a K-05: a materialized dataset's items live in our own pgstac, not
        # at a live source — there is no search or item-fetch request for this
        # module to build. The federating client dispatches such a collection to
        # `super()` (pgstac) before it ever calls `search_items`/`get_item`; the
        # tiler's item source does the equivalent through `catalog.pgstac.fetch_item`.
        raise UnsupportedSource(
            f"{dataset_id} holds items materialized in pgstac; adapters.search_items/get_item do not serve it"
        )
    kind = config.source.adapter
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


async def materialize_items(
    config: DatasetConfig,
    *,
    gateway: Gateway,
    known_version: str | None,
) -> MaterializeOutcome:
    """Build the items of one materialized dataset, whichever adapter produced it.

    Takes the registry entry itself, not a ``dataset_id``/``registry`` pair like
    :func:`search_items`/:func:`get_item`: the one caller (the one-off command in
    ``discovery``, M3-11b) already holds the entry it is materializing, and handing
    it straight through avoids a second registry lookup that could disagree with
    the one the caller already made.
    """
    if config.source.item_holding is not ItemHolding.MATERIALIZED:
        raise NotMaterialized(
            f"{config.dataset_id} is not materialized; adapters.materialize_items does not build its items"
        )
    try:
        module = _MATERIALIZERS[config.source.adapter]
    except KeyError:
        raise UnsupportedSource(
            f"{config.dataset_id} is materialized by {config.source.adapter}, which no materializer dispatch knows"
        ) from None
    return await module.materialize_items(config, gateway=gateway, known_version=known_version)


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_IDS",
    "MAX_INTERSECTS_POINTS",
    "MAX_LIMIT",
    "CacheValue",
    "InvalidQuery",
    "ItemPage",
    "MaterializeOutcome",
    "NotMaterialized",
    "SearchCache",
    "SearchParams",
    "UnknownCollection",
    "UnsupportedFilter",
    "UnsupportedSource",
    "UpstreamShapeError",
    "aggregate_coverage",
    "get_item",
    "materialize_items",
    "search_items",
]
