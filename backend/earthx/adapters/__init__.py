"""Source protocols: search, item fetch, materialization, aggregation.

One adapter per source protocol (architekturplan.md 6.1). ``earth_search`` speaks
Earth Search v1 (Sentinel-2 L2A as COG); ``eopf_stac`` speaks the EOPF Sentinel Zarr
Samples Service (the same dataset again, as Zarr, M2-09b). Both answer search and
item fetch; each also answers a coverage way of adr/0004 §5 — Earth Search its
aggregation, EOPF a declared sample (K-06, M3-11c). ``cop_dem_bucket`` (M3-11b)
speaks a third, structurally different protocol: it never searches, it
*materializes* — it turns a bucket's own tile list into STAC items, once, for the
one-off command in ``discovery``. Discovery follows with the harvester proper (M5).

What each protocol offers is declared once, as an
:class:`~earthx.adapters.spec.AdapterSpec` (adr/0011 F1). The functions below
dispatch on the registry entry's own ``earthx:source.adapter`` through the table
the caller hands in (``adapters=``, no default), so no caller picks a module and
no test patches a private table. What the entry's source does not offer is refused
by name before any request goes out — :class:`UnsupportedSource`,
:class:`UnsupportedFilter`, or for coverage
:class:`~earthx.catalog.coverage.CoverageProviderMismatch` — never answered by
something else.

Everything here takes the registry entry, not a dataset id (adr/0011 F3): the
caller looks it up once through :func:`dataset_config` (adr/0005 rule I). A
materialized entry is never searched or fetched here — its items live in our own
pgstac, which ``api`` asks instead (M3-11a K-05).
"""

from __future__ import annotations

from typing import Any

from earthx.adapters.cache import CacheValue, SearchCache
from earthx.adapters.cop_dem_bucket import MaterializeOutcome
from earthx.adapters.errors import (
    AdapterSpecMismatch,
    InvalidQuery,
    NotMaterialized,
    UnknownCollection,
    UnsupportedFilter,
    UnsupportedSource,
    UpstreamShapeError,
)
from earthx.adapters.federated_search import (
    DEFAULT_LIMIT,
    MAX_IDS,
    MAX_INTERSECTS_POINTS,
    MAX_LIMIT,
    ItemPage,
    SearchParams,
)
from earthx.adapters.spec import ADAPTER_SPECS, AdapterSpec, AdapterSpecs, FilterSupport, check_adapter_specs
from earthx.catalog.coverage import CoverageProviderMismatch, CoverageQuery, CoverageResult
from earthx.catalog.registry import DatasetConfig, DatasetRegistry, ItemHolding, UnknownDatasetError
from earthx.gateway import Gateway


def dataset_config(registry: DatasetRegistry, dataset_id: str) -> DatasetConfig:
    """The registry entry for ``dataset_id``, or :class:`UnknownCollection`.

    adr/0005 rule I, in one place (adr/0011 F3, M4-01b F2): the caller looks the
    entry up once and hands it to every function below, instead of each adapter
    looking it up again in a registry of its own choosing.
    """
    try:
        return registry.get(dataset_id)
    except UnknownDatasetError:
        raise UnknownCollection(dataset_id) from None


def _federated_spec(config: DatasetConfig, adapters: AdapterSpecs) -> AdapterSpec:
    """The spec that searches and fetches for ``config``, or the error its absence means."""
    if config.source.item_holding is ItemHolding.MATERIALIZED:
        # M3-11a K-05: a materialized dataset's items live in our own pgstac, not
        # at a live source — there is no search or item-fetch request to build. The
        # federating client and the item source route such a collection to pgstac
        # before they ever call `search_items`/`get_item`.
        raise UnsupportedSource(
            f"{config.dataset_id} holds items materialized in pgstac; adapters.search_items/get_item do not serve it"
        )
    kind = config.source.adapter
    spec = adapters.get(kind)
    if spec is None:
        raise UnsupportedSource(f"{config.dataset_id} is served by {kind}, which no adapter dispatch knows")
    if spec.search is None or spec.fetch is None or spec.filters is None:
        raise UnsupportedSource(f"{config.dataset_id} is served by {kind}, which offers no search")
    return spec


def _check_filters(dataset_id: str, filters: FilterSupport, params: SearchParams | None) -> None:
    """M3-08 F4a: a filter this dataset's own source cannot honour is refused by
    name here, before the adapter ever builds a request — the posture M2-17 already
    took for *every* federated collection when no adapter could honour either filter
    (`api/federating_client.py`); this narrows that refusal to the one collection
    (and, in principle, the one filter) that genuinely cannot.

    Both current adapters support both filters (measured, M3-08 plan §2.1); this
    only matters once a third source does not, which
    `test_every_known_adapter_supports_both_filters`
    (`tests/earthx/adapters/test_dispatch.py`) turns into a build failure rather
    than a silent gap the day that happens — K8 requires the landing page's
    ``item-search`` promise to match the weakest adapter, and this is the one place
    that promise could quietly stop being true.
    """
    if params is None:
        return
    if params.intersects is not None and not filters.intersects:
        raise UnsupportedFilter(f"{dataset_id} does not support intersects")
    if params.ids is not None and not filters.ids:
        raise UnsupportedFilter(f"{dataset_id} does not support ids")


async def search_items(
    config: DatasetConfig,
    params: SearchParams | None = None,
    *,
    adapters: AdapterSpecs,
    gateway: Gateway,
    cache: SearchCache | None = None,
) -> ItemPage:
    """Search items of one federated collection, whichever source serves it."""
    spec = _federated_spec(config, adapters)
    _check_filters(config.dataset_id, spec.filters, params)
    return await spec.search(config, params, gateway=gateway, cache=cache)


async def get_item(
    config: DatasetConfig,
    item_id: str,
    *,
    adapters: AdapterSpecs,
    gateway: Gateway,
    cache: SearchCache | None = None,
) -> dict[str, Any]:
    """One item by id, without a search in front of it, whichever source serves it."""
    spec = _federated_spec(config, adapters)
    return await spec.fetch(config, item_id, gateway=gateway, cache=cache)


async def materialize_items(
    config: DatasetConfig,
    *,
    adapters: AdapterSpecs,
    gateway: Gateway,
    known_version: str | None,
) -> MaterializeOutcome:
    """Build the items of one materialized dataset, whichever adapter produced it."""
    if config.source.item_holding is not ItemHolding.MATERIALIZED:
        raise NotMaterialized(
            f"{config.dataset_id} is not materialized; adapters.materialize_items does not build its items"
        )
    spec = adapters.get(config.source.adapter)
    if spec is None or spec.materialize is None:
        raise UnsupportedSource(
            f"{config.dataset_id} is materialized by {config.source.adapter}, which no materializer dispatch knows"
        )
    return await spec.materialize(config, gateway=gateway, known_version=known_version)


async def coverage(
    query: CoverageQuery,
    config: DatasetConfig,
    *,
    adapters: AdapterSpecs,
    gateway: Gateway,
    cache: SearchCache | None = None,
) -> CoverageResult:
    """Coverage density or declared sample for one federated collection, dispatched
    by ``(adapter, coverage provider)`` (K-06, M3-11c) — the seam
    ``api.coverage_route`` calls instead of picking ``aggregate_coverage`` or
    ``sample_coverage`` itself. A pair the table does not answer is
    :class:`~earthx.catalog.coverage.CoverageProviderMismatch`, the coverage
    counterpart of :class:`UnsupportedSource`; ``local-sql`` never is, because
    ``catalog`` answers it (adr/0004 §5).
    """
    spec = adapters.get(config.source.adapter)
    answer = None if spec is None else spec.coverage.get(config.coverage.provider)
    if answer is None:
        raise CoverageProviderMismatch(
            f"{config.dataset_id}: no coverage answer for adapter {config.source.adapter.value!r} "
            f"and provider {config.coverage.provider.value!r}"
        )
    return await answer(query, config, gateway=gateway, cache=cache)


__all__ = [
    "ADAPTER_SPECS",
    "DEFAULT_LIMIT",
    "MAX_IDS",
    "MAX_INTERSECTS_POINTS",
    "MAX_LIMIT",
    "AdapterSpec",
    "AdapterSpecMismatch",
    "AdapterSpecs",
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
    "check_adapter_specs",
    "coverage",
    "dataset_config",
    "get_item",
    "materialize_items",
    "search_items",
]
