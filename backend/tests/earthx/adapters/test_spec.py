"""``AdapterSpec`` and the adapter table (adr/0011 §5, F1; M4-01b).

Three things: a spec cannot be built in a shape §5.2 rules out; every entry of the
real registry gets from the real table exactly what its holding needs, and every
capability it does not need is refused by name without a request (Otto's condition
on M4-01b); and an app is not built around a table that cannot answer its registry.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from earthx.adapters import (
    ADAPTER_SPECS,
    AdapterSpecMismatch,
    SearchParams,
    UnsupportedFilter,
    UnsupportedSource,
    check_adapter_specs,
    coverage,
    get_item,
    materialize_items,
    search_items,
)
from earthx.adapters.spec import AdapterSpec, AdapterSpecs, FilterSupport, spec_table
from earthx.catalog.coverage import CoverageProviderMismatch, CoverageQuery
from earthx.catalog.datasets import COP_DEM_GLO_30, REGISTRY, SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.registry import AdapterKind, CoverageProvider, DatasetConfig, DatasetRegistry, ItemHolding
from earthx.gateway import Policy, host_of
from earthx.gateway.client import Gateway

ADAPTERS_DIR = Path(__file__).resolve().parents[3] / "earthx" / "adapters"

CAPABILITIES = ("search", "fetch", "materialize", "coverage", "intersects", "ids")


async def _never(*args: object, **kwargs: object) -> None:
    raise AssertionError("a spec under test was called")


def _spec(**fields: object) -> AdapterSpec:
    values: dict[str, object] = {
        "kind": AdapterKind.EARTH_SEARCH_V1,
        "search": _never,
        "fetch": _never,
        "materialize": None,
        "coverage": {},
        "filters": FilterSupport(intersects=True, ids=True, cql2=False),
    }
    values.update(fields)
    return AdapterSpec(**values)


def _without(kind: AdapterKind) -> AdapterSpecs:
    return spec_table(*(spec for other, spec in ADAPTER_SPECS.items() if other is not kind))


class TestTheShapeOfASpec:
    def test_search_without_fetch_is_refused(self) -> None:
        with pytest.raises(ValueError, match="search and fetch"):
            _spec(fetch=None)

    def test_fetch_without_search_is_refused(self) -> None:
        with pytest.raises(ValueError, match="search and fetch"):
            _spec(search=None, filters=None)

    def test_search_without_filters_is_refused(self) -> None:
        with pytest.raises(ValueError, match="filters"):
            _spec(filters=None)

    def test_filters_without_search_is_refused(self) -> None:
        with pytest.raises(ValueError, match="filters"):
            _spec(search=None, fetch=None)

    def test_local_sql_coverage_is_never_an_adapters(self) -> None:
        with pytest.raises(ValueError, match="local-sql"):
            _spec(coverage={CoverageProvider.LOCAL_SQL: _never})

    def test_no_field_has_a_default(self) -> None:
        with pytest.raises(TypeError):
            AdapterSpec(kind=AdapterKind.EARTH_SEARCH_V1)  # type: ignore[call-arg]

    def test_the_coverage_map_cannot_be_changed_afterwards(self) -> None:
        answers = {CoverageProvider.SAMPLE: _never}
        spec = _spec(coverage=answers)
        answers[CoverageProvider.UPSTREAM_AGGREGATION] = _never
        assert list(spec.coverage) == [CoverageProvider.SAMPLE]
        with pytest.raises(TypeError):
            spec.coverage[CoverageProvider.UPSTREAM_AGGREGATION] = _never  # type: ignore[index]

    def test_a_kind_twice_in_a_table_is_refused(self) -> None:
        with pytest.raises(ValueError, match="twice"):
            spec_table(_spec(), _spec())

    def test_the_table_cannot_be_changed_afterwards(self) -> None:
        with pytest.raises(TypeError):
            ADAPTER_SPECS[AdapterKind.EARTH_SEARCH_V1] = _spec()  # type: ignore[index]


def _required(config: DatasetConfig) -> set[str]:
    """What adr/0011 §5 asks of the source of this entry."""
    if config.source.item_holding is ItemHolding.FEDERATED:
        # K8: the landing page promises `intersects` and `ids` for every federated
        # collection (adr/0005 rule VI).
        needed = {"search", "fetch", "intersects", "ids"}
    else:
        needed = {"materialize"}
    if config.coverage.provider is not CoverageProvider.LOCAL_SQL and not config.capabilities.single_coverage_product:
        needed.add("coverage")
    return needed


def _offered(config: DatasetConfig, adapters: AdapterSpecs) -> set[str]:
    spec = adapters.get(config.source.adapter)
    if spec is None:
        return set()
    offered = {name for name in ("search", "fetch", "materialize") if getattr(spec, name) is not None}
    if config.coverage.provider in spec.coverage:
        offered.add("coverage")
    if spec.filters is not None:
        offered |= {name for name in ("intersects", "ids") if getattr(spec.filters, name)}
    return offered


def _missing(config: DatasetConfig, adapters: AdapterSpecs) -> list[str]:
    return sorted(_required(config) - _offered(config, adapters))


def _recording_gateway() -> tuple[Gateway, list[httpx.Request]]:
    """Lets every registry host through the policy, so a request that should not
    happen reaches the transport and is recorded instead of being refused early."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(500)

    async def sleep(seconds: float) -> None:
        return None

    hosts = frozenset(
        host for config in REGISTRY for host in (host_of(config.source.endpoint), *config.source.asset_hosts)
    )
    policy = Policy(allowed_hosts=hosts)
    return Gateway(
        policy, transport=httpx.MockTransport(handler), resolve=lambda h, p: ("93.184.216.34",), sleep=sleep
    ), seen


async def _ask(capability: str, config: DatasetConfig, gateway: Gateway) -> object:
    if capability == "search":
        return await search_items(config, adapters=ADAPTER_SPECS, gateway=gateway)
    if capability == "fetch":
        return await get_item(config, "SYNTH_ITEM", adapters=ADAPTER_SPECS, gateway=gateway)
    if capability == "materialize":
        return await materialize_items(config, adapters=ADAPTER_SPECS, gateway=gateway, known_version=None)
    if capability == "coverage":
        query = CoverageQuery(dataset_id=config.dataset_id, level=3)
        return await coverage(query, config, adapters=ADAPTER_SPECS, gateway=gateway)
    if capability == "intersects":
        params = SearchParams(intersects={"type": "Point", "coordinates": [10.0, 49.0]})
        return await search_items(config, params, adapters=ADAPTER_SPECS, gateway=gateway)
    assert capability == "ids"
    return await search_items(config, SearchParams(ids=("SYNTH_ITEM",)), adapters=ADAPTER_SPECS, gateway=gateway)


ENTRIES = [pytest.param(config, id=config.dataset_id) for config in REGISTRY]
NOT_NEEDED = [
    pytest.param(config, capability, id=f"{config.dataset_id}-{capability}")
    for config in REGISTRY
    for capability in CAPABILITIES
    if capability not in _required(config)
]


class TestEveryRegistryEntryAgainstTheTable:
    """Otto's condition on M4-01b: each entry of the real registry, complete against
    adr/0011 §5 — every capability is offered by its spec or refused by name;
    materialized needs materialization; federated needs search and item fetch."""

    @pytest.mark.parametrize("config", ENTRIES)
    def test_what_its_holding_needs_is_offered(self, config: DatasetConfig) -> None:
        assert _missing(config, ADAPTER_SPECS) == []

    @pytest.mark.anyio
    @pytest.mark.parametrize(("config", "capability"), NOT_NEEDED)
    async def test_what_it_does_not_need_is_refused_without_a_request(
        self, config: DatasetConfig, capability: str
    ) -> None:
        gateway, seen = _recording_gateway()
        async with gateway:
            with pytest.raises((UnsupportedSource, UnsupportedFilter, CoverageProviderMismatch)):
                await _ask(capability, config, gateway)
        assert seen == []


class TestTheCheckFailsForAManipulatedEntry:
    """The counter-test Otto asked for: a manipulated entry or table is found."""

    def test_a_materialized_entry_whose_adapter_cannot_materialize(self) -> None:
        manipulated = replace(
            COP_DEM_GLO_30, source=replace(COP_DEM_GLO_30.source, adapter=AdapterKind.EARTH_SEARCH_V1)
        )
        assert _missing(manipulated, ADAPTER_SPECS) == ["materialize"]

    def test_a_federated_entry_whose_adapter_cannot_search(self) -> None:
        manipulated = replace(SENTINEL_2_L2A, source=replace(SENTINEL_2_L2A.source, adapter=AdapterKind.COP_DEM_BUCKET))
        assert _missing(manipulated, ADAPTER_SPECS) == ["coverage", "fetch", "ids", "intersects", "search"]

    def test_a_provider_the_adapter_does_not_answer(self) -> None:
        manipulated = replace(
            SENTINEL_2_L2A, coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.SAMPLE)
        )
        assert _missing(manipulated, ADAPTER_SPECS) == ["coverage"]

    def test_a_table_whose_source_lost_a_filter(self) -> None:
        weaker = replace(
            ADAPTER_SPECS[AdapterKind.EOPF_STAC_V1], filters=FilterSupport(intersects=True, ids=False, cql2=True)
        )
        table = spec_table(weaker, *(spec for kind, spec in ADAPTER_SPECS.items() if kind is not weaker.kind))
        assert _missing(SENTINEL_2_L2A_ZARR3, table) == ["ids"]

    def test_a_table_without_the_entrys_kind(self) -> None:
        assert _missing(COP_DEM_GLO_30, _without(AdapterKind.COP_DEM_BUCKET)) == ["materialize"]


class TestDispatchWithAHandedInTable:
    """The branches of the dispatch the registry-wide tests above cannot reach,
    because the real table has every kind the real registry names."""

    @pytest.mark.anyio
    async def test_coverage_is_answered_by_the_spec_of_the_entrys_kind(self) -> None:
        asked: list[str] = []

        async def answer(query: CoverageQuery, config: DatasetConfig, **kwargs: object) -> str:
            asked.append(config.dataset_id)
            return "answered"

        table = spec_table(_spec(coverage={CoverageProvider.UPSTREAM_AGGREGATION: answer}))
        gateway, seen = _recording_gateway()
        async with gateway:
            query = CoverageQuery(dataset_id=SENTINEL_2_L2A.dataset_id, level=3)
            assert await coverage(query, SENTINEL_2_L2A, adapters=table, gateway=gateway) == "answered"
        assert asked == [SENTINEL_2_L2A.dataset_id]
        assert seen == []

    @pytest.mark.anyio
    async def test_coverage_for_a_kind_missing_from_the_table_is_refused(self) -> None:
        gateway, seen = _recording_gateway()
        async with gateway:
            with pytest.raises(CoverageProviderMismatch):
                query = CoverageQuery(dataset_id=SENTINEL_2_L2A.dataset_id, level=3)
                await coverage(query, SENTINEL_2_L2A, adapters=_without(AdapterKind.EARTH_SEARCH_V1), gateway=gateway)
        assert seen == []

    @pytest.mark.anyio
    async def test_materializing_a_kind_missing_from_the_table_is_refused(self) -> None:
        gateway, seen = _recording_gateway()
        async with gateway:
            with pytest.raises(UnsupportedSource, match="no materializer"):
                await materialize_items(
                    COP_DEM_GLO_30,
                    adapters=_without(AdapterKind.COP_DEM_BUCKET),
                    gateway=gateway,
                    known_version=None,
                )
        assert seen == []


class TestCheckAdapterSpecs:
    def test_the_real_registry_and_table_agree(self) -> None:
        check_adapter_specs(REGISTRY, ADAPTER_SPECS)

    def test_a_kind_missing_from_the_table_names_the_dataset(self) -> None:
        with pytest.raises(AdapterSpecMismatch, match=SENTINEL_2_L2A_ZARR3.dataset_id):
            check_adapter_specs(REGISTRY, _without(AdapterKind.EOPF_STAC_V1))

    def test_a_federated_entry_without_search_is_refused(self) -> None:
        no_search = _spec(
            search=None, fetch=None, filters=None, coverage={CoverageProvider.UPSTREAM_AGGREGATION: _never}
        )
        table = spec_table(no_search, *(spec for kind, spec in ADAPTER_SPECS.items() if kind is not no_search.kind))
        with pytest.raises(AdapterSpecMismatch, match=f"{SENTINEL_2_L2A.dataset_id}: federated"):
            check_adapter_specs(REGISTRY, table)

    def test_a_coverage_provider_the_adapter_lacks_is_refused(self) -> None:
        sampled = replace(SENTINEL_2_L2A, coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.SAMPLE))
        with pytest.raises(AdapterSpecMismatch, match="sample coverage"):
            check_adapter_specs(DatasetRegistry((sampled,)), ADAPTER_SPECS)

    def test_a_one_off_product_asks_no_adapter_for_coverage(self) -> None:
        one_off = replace(
            SENTINEL_2_L2A,
            coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.SAMPLE),
            capabilities=replace(SENTINEL_2_L2A.capabilities, single_coverage_product=True),
        )
        check_adapter_specs(DatasetRegistry((one_off,)), ADAPTER_SPECS)

    def test_a_materialized_entry_of_a_searching_kind_builds(self) -> None:
        """The app asks no adapter for it (pgstac and `catalog` answer); whether it
        can be materialized is `discovery`'s question (M4-01b §3.3)."""
        materialized = replace(
            SENTINEL_2_L2A,
            source=replace(SENTINEL_2_L2A.source, item_holding=ItemHolding.MATERIALIZED),
            coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
        )
        check_adapter_specs(DatasetRegistry((materialized,)), ADAPTER_SPECS)


class TestAppsAreNotBuiltAroundAMismatch:
    def test_the_api_is_not_built(self) -> None:
        from earthx.api.main import build_app

        with pytest.raises(AdapterSpecMismatch):
            build_app(REGISTRY, adapters=_without(AdapterKind.EARTH_SEARCH_V1))

    def test_the_tiler_is_not_built(self) -> None:
        from earthx.api.tiler import build_app

        with pytest.raises(AdapterSpecMismatch):
            build_app(REGISTRY, adapters=_without(AdapterKind.EARTH_SEARCH_V1))


def test_no_adapter_module_imports_the_registry_entries() -> None:
    """adr/0011 F3: adapters take the entry they are handed; none reaches for
    `catalog.datasets` (and with it a module-wide `REGISTRY`) on its own."""
    offenders = []
    for path in sorted(ADAPTERS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "earthx.catalog.datasets":
                offenders.append(path.name)
            if isinstance(node, ast.Import) and any(alias.name == "earthx.catalog.datasets" for alias in node.names):
                offenders.append(path.name)
    assert offenders == []
