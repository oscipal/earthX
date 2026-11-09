"""What each source can do, declared in one place (adr/0011 §5.1 S3, F1; M4-01b).

One :class:`AdapterSpec` per :class:`~earthx.catalog.registry.AdapterKind`: a
function per capability, or ``None`` for "this source does not offer it". ``None``
is an answer, not a gap — the dispatch in ``earthx.adapters`` refuses it by name
before any request goes out (K7), and a source is never asked for something it
cannot do: the DEM bucket has no search to be forced into (K1).

The filter capabilities of a source are data here too
(:class:`~earthx.adapters.federated_search.FilterSupport`, for a STAC API taken from its dialect),
not module constants read with a silent ``False`` default (adr/0011 B7). They are
the *source's* filters, kept apart from the dataset's capability flags in the
registry (adr/0011 B12, KLAERUNGEN B10).

Which table a dispatch reads is the caller's to say (``adapters=``, no default):
``api``, ``tiler`` and ``discovery`` hand in :data:`ADAPTER_SPECS`, a test hands in
a table of its own instead of patching a private one. :func:`check_adapter_specs`
is what an app runs when it is built, so a registry entry nothing can answer for
stops the build instead of failing on its first request.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol

from earthx.adapters import cop_dem_bucket, esa_worldcover_bucket, stac_api
from earthx.adapters.cache import SearchCache
from earthx.adapters.cop_dem_bucket import MaterializeOutcome
from earthx.adapters.earth_search_coverage import aggregate_coverage
from earthx.adapters.errors import AdapterSpecMismatch
from earthx.adapters.federated_search import FilterSupport, ItemPage, SearchParams
from earthx.catalog.coverage import CoverageQuery, CoverageResult
from earthx.catalog.registry import AdapterKind, CoverageProvider, DatasetConfig, DatasetRegistry, ItemHolding
from earthx.gateway import Gateway


class SearchItems(Protocol):
    async def __call__(
        self, config: DatasetConfig, params: SearchParams | None, *, gateway: Gateway, cache: SearchCache | None
    ) -> ItemPage: ...


class FetchItem(Protocol):
    async def __call__(
        self, config: DatasetConfig, item_id: str, *, gateway: Gateway, cache: SearchCache | None
    ) -> dict[str, Any]: ...


class MaterializeItems(Protocol):
    async def __call__(
        self, config: DatasetConfig, *, gateway: Gateway, known_version: str | None
    ) -> MaterializeOutcome: ...


class AnswerCoverage(Protocol):
    async def __call__(
        self, query: CoverageQuery, config: DatasetConfig, *, gateway: Gateway, cache: SearchCache | None
    ) -> CoverageResult: ...


@dataclass(frozen=True, slots=True)
class AdapterSpec:
    """The capabilities of one source protocol. No field has a default (B10)."""

    kind: AdapterKind
    search: SearchItems | None
    fetch: FetchItem | None
    materialize: MaterializeItems | None
    coverage: Mapping[CoverageProvider, AnswerCoverage]
    filters: FilterSupport | None

    def __post_init__(self) -> None:
        if (self.search is None) != (self.fetch is None):
            # A source we search is one whose items we fetch one by one too: the
            # tiles and the download ask for exactly the items a search returned.
            raise ValueError(f"{self.kind}: search and fetch come together or not at all")
        if (self.search is None) != (self.filters is None):
            raise ValueError(f"{self.kind}: filters are declared exactly when search is")
        if CoverageProvider.LOCAL_SQL in self.coverage:
            # adr/0011 B4: our own items are counted by `catalog` over a database
            # connection, which no adapter has.
            raise ValueError(f"{self.kind}: local-sql coverage is catalog's, not an adapter's")
        object.__setattr__(self, "coverage", MappingProxyType(dict(self.coverage)))


AdapterSpecs = Mapping[AdapterKind, AdapterSpec]


def spec_table(*specs: AdapterSpec) -> AdapterSpecs:
    """A read-only table keyed by each spec's own ``kind``; a kind twice is an error."""
    table = {spec.kind: spec for spec in specs}
    if len(table) != len(specs):
        raise ValueError("an adapter kind appears twice in the table")
    return MappingProxyType(table)


ADAPTER_SPECS: AdapterSpecs = spec_table(
    AdapterSpec(
        kind=AdapterKind.EARTH_SEARCH_V1,
        search=stac_api.search_items,
        fetch=stac_api.get_item,
        materialize=None,
        coverage={CoverageProvider.UPSTREAM_AGGREGATION: aggregate_coverage},
        # Measured per source and kept with its dialect (M5-08), so the two cannot drift apart.
        filters=stac_api.EARTH_SEARCH.filters,
    ),
    AdapterSpec(
        kind=AdapterKind.FSDI_STAC_V1,
        search=stac_api.search_items,
        fetch=stac_api.get_item,
        materialize=stac_api.materialize_items,
        # No aggregation at the source: an entry of this kind is materialized and counted by `catalog` (local-sql).
        coverage={},
        filters=stac_api.FSDI.filters,
    ),
    AdapterSpec(
        kind=AdapterKind.COP_DEM_BUCKET,
        search=None,
        fetch=None,
        materialize=cop_dem_bucket.materialize_items,
        coverage={},
        filters=None,
    ),
    AdapterSpec(
        kind=AdapterKind.ESA_WORLDCOVER_BUCKET,
        search=None,
        fetch=None,
        materialize=esa_worldcover_bucket.materialize_items,
        coverage={},
        filters=None,
    ),
)


def check_adapter_specs(registry: DatasetRegistry, adapters: AdapterSpecs) -> None:
    """Refuse an app whose registry asks an adapter for something ``adapters`` lacks.

    Every entry's ``AdapterKind`` must be in the table. Beyond that, only what an
    app itself asks an adapter for (M4-01b §3.3): search and item fetch for a
    federated entry, and coverage unless ``catalog`` answers it (``local-sql``). Whether
    a materialized entry can be materialized is ``discovery``'s question, refused
    by the dispatch there.
    """
    problems: list[str] = []
    for config in registry:
        kind = config.source.adapter
        spec = adapters.get(kind)
        if spec is None:
            problems.append(f"{config.dataset_id}: no adapter spec for {kind}")
            continue
        if config.source.item_holding is ItemHolding.FEDERATED and spec.search is None:
            problems.append(f"{config.dataset_id}: federated, but {kind} offers no search")
        if spec.search is stac_api.search_items and kind not in stac_api.DIALECTS:
            problems.append(f"{config.dataset_id}: {kind} searches as a STAC API, but has no dialect")
        if (config.source.asset_keys or config.source.item_states is not None) and kind not in stac_api.DIALECTS:
            # Only the STAC API adapter applies them; a bucket adapter would pass them over without a word.
            problems.append(f"{config.dataset_id}: {kind} applies no source.asset_keys or source.item_states")
        if config.search_filters and (spec.filters is None or not spec.filters.query):
            problems.append(f"{config.dataset_id}: has search filters, but {kind} applies no query")
        provider = config.coverage.provider
        if provider is not CoverageProvider.LOCAL_SQL and provider not in spec.coverage:
            problems.append(f"{config.dataset_id}: {kind} answers no {provider.value} coverage")
    if problems:
        raise AdapterSpecMismatch("; ".join(problems))
