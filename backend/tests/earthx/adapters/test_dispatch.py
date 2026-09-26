"""``earthx.adapters.search_items``/``get_item``: routed by the registry entry's own
``earthx:source.adapter``, not by which module the caller happens to import (M2-09b
plan §4.2 — the federating client and the tiler's item source both call these, and
neither should know which adapter a dataset uses).
"""

from __future__ import annotations

import json
import types
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

import earthx.adapters as adapters_pkg
from earthx.adapters import (
    SearchParams,
    UnknownCollection,
    UnsupportedFilter,
    UnsupportedSource,
    get_item,
    search_items,
)
from earthx.catalog.datasets import SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.registry import AdapterKind, CoverageProvider, DatasetRegistry, ItemHolding
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

pytestmark = pytest.mark.anyio

EARTH_SEARCH_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "earth_search"
EOPF_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "eopf_stac"
BOTH_HOSTS = frozenset({"earth-search.aws.element84.com", "stac.core.eopf.eodc.eu"})


def load(directory: Path, name: str) -> dict[str, Any]:
    return json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def gateway_for(response: httpx.Response) -> tuple[Gateway, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    async def sleep(seconds: float) -> None:
        return None

    policy = Policy(allowed_hosts=BOTH_HOSTS)
    return Gateway(policy, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep), seen


REGISTRY = DatasetRegistry((SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3))


class TestSearchDispatchesByAdapter:
    async def test_a_cog_dataset_goes_to_earth_search(self) -> None:
        gateway, seen = gateway_for(httpx.Response(200, json=load(EARTH_SEARCH_FIXTURES, "search_empty")))
        async with gateway:
            await search_items(SENTINEL_2_L2A.dataset_id, gateway=gateway, registry=REGISTRY)
        assert seen[0].headers["host"] == "earth-search.aws.element84.com"

    async def test_a_zarr_dataset_goes_to_eopf_stac(self) -> None:
        gateway, seen = gateway_for(httpx.Response(200, json=load(EOPF_FIXTURES, "search_empty")))
        async with gateway:
            await search_items(SENTINEL_2_L2A_ZARR3.dataset_id, gateway=gateway, registry=REGISTRY)
        assert seen[0].headers["host"] == "stac.core.eopf.eodc.eu"

    async def test_an_unknown_dataset_is_the_same_error_either_adapter_raises(self) -> None:
        gateway, seen = gateway_for(httpx.Response(200, json=load(EARTH_SEARCH_FIXTURES, "search_empty")))
        async with gateway:
            with pytest.raises(UnknownCollection):
                await search_items("no-such-dataset", gateway=gateway, registry=REGISTRY)
        assert seen == []

    async def test_a_dataset_under_an_adapter_kind_nothing_dispatches_to_is_refused(self) -> None:
        other = replace(SENTINEL_2_L2A, source=replace(SENTINEL_2_L2A.source, adapter="some-other-protocol"))
        gateway, seen = gateway_for(httpx.Response(200, json=load(EARTH_SEARCH_FIXTURES, "search_empty")))
        async with gateway:
            with pytest.raises(UnsupportedSource, match="some-other-protocol"):
                await search_items(other.dataset_id, gateway=gateway, registry=DatasetRegistry((other,)))
        assert seen == []

    async def test_a_materialized_dataset_is_refused_before_any_adapter_is_asked(self) -> None:
        """M3-11a K-05: a materialized dataset's items live in pgstac, not at a live
        source — this dispatch is the federating client's and the tiler's own
        fallback (both call it), so a caller that reaches it anyway for such a
        dataset is a dispatch mistake, refused the same way an unknown
        ``AdapterKind`` is."""
        materialized = replace(
            SENTINEL_2_L2A,
            source=replace(SENTINEL_2_L2A.source, item_holding=ItemHolding.MATERIALIZED),
            coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
        )
        gateway, seen = gateway_for(httpx.Response(200, json=load(EARTH_SEARCH_FIXTURES, "search_empty")))
        async with gateway:
            with pytest.raises(UnsupportedSource, match="materialized"):
                await search_items(
                    materialized.dataset_id, gateway=gateway, registry=DatasetRegistry((materialized,))
                )
        assert seen == []


class TestGetItemDispatchesByAdapter:
    async def test_a_zarr_datasets_item_goes_to_eopf_stac(self) -> None:
        gateway, seen = gateway_for(httpx.Response(200, json=load(EOPF_FIXTURES, "item")))
        async with gateway:
            item = await get_item(
                SENTINEL_2_L2A_ZARR3.dataset_id,
                "SYNTH_S2A_MSIL2A_20260921T141821_T26WME",
                gateway=gateway,
                registry=REGISTRY,
            )
        assert seen[0].headers["host"] == "stac.core.eopf.eodc.eu"
        # Normalised by the eopf_stac adapter, not left at the source's own version —
        # proof the dispatcher called the right module, not just the right host.
        assert item["stac_version"] == "1.0.0"

    async def test_a_materialized_datasets_item_is_refused_here_too(self) -> None:
        """The tiler's own item source dispatches on ``item_holding`` before it ever
        reaches this function (M3-11a §3.3) — this is the safety net for a caller
        that does not."""
        materialized = replace(
            SENTINEL_2_L2A,
            source=replace(SENTINEL_2_L2A.source, item_holding=ItemHolding.MATERIALIZED),
            coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
        )
        gateway, seen = gateway_for(httpx.Response(200, json=load(EOPF_FIXTURES, "item")))
        async with gateway:
            with pytest.raises(UnsupportedSource, match="materialized"):
                await get_item(
                    materialized.dataset_id, "some-item", gateway=gateway, registry=DatasetRegistry((materialized,))
                )
        assert seen == []


class TestSearchParamsIsSharedAcrossAdapters:
    """adr/0005 rule V (M1-06): the same limit cap, regardless of which source answers."""

    def test_the_limit_check_runs_before_any_adapter_is_asked(self) -> None:
        from earthx.adapters import InvalidQuery

        with pytest.raises(InvalidQuery):
            SearchParams(limit=101)


class TestFilterCapabilities:
    """M3-08 F4a: a filter a dataset's own source cannot honour is refused by name
    here, before an adapter ever builds a request for it — no real adapter lacks
    either capability today (measured, M3-08 plan §2.1), so both cases below use a
    stand-in adapter with one flag turned off."""

    async def test_intersects_is_refused_when_the_adapter_does_not_support_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stub = types.SimpleNamespace(SUPPORTS_INTERSECTS=False, SUPPORTS_IDS=True)
        monkeypatch.setitem(adapters_pkg._ADAPTERS, AdapterKind.EARTH_SEARCH_V1, stub)
        gateway, seen = gateway_for(httpx.Response(200, json=load(EARTH_SEARCH_FIXTURES, "search_empty")))
        async with gateway:
            with pytest.raises(UnsupportedFilter, match="intersects"):
                await search_items(
                    SENTINEL_2_L2A.dataset_id,
                    SearchParams(intersects={"type": "Point", "coordinates": [10.0, 49.0]}),
                    gateway=gateway,
                    registry=REGISTRY,
                )
        assert seen == []  # refused before the stub (or anything else) was asked

    async def test_ids_is_refused_when_the_adapter_does_not_support_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stub = types.SimpleNamespace(SUPPORTS_INTERSECTS=True, SUPPORTS_IDS=False)
        monkeypatch.setitem(adapters_pkg._ADAPTERS, AdapterKind.EARTH_SEARCH_V1, stub)
        gateway, seen = gateway_for(httpx.Response(200, json=load(EARTH_SEARCH_FIXTURES, "search_empty")))
        async with gateway:
            with pytest.raises(UnsupportedFilter, match="ids"):
                await search_items(
                    SENTINEL_2_L2A.dataset_id,
                    SearchParams(ids=("known-id",)),
                    gateway=gateway,
                    registry=REGISTRY,
                )
        assert seen == []

    async def test_a_search_without_either_filter_never_calls_the_capability_check_in_vain(self) -> None:
        """`params=None`/plain `SearchParams()` must not need either flag set."""
        gateway, seen = gateway_for(httpx.Response(200, json=load(EARTH_SEARCH_FIXTURES, "search_empty")))
        async with gateway:
            await search_items(SENTINEL_2_L2A.dataset_id, gateway=gateway, registry=REGISTRY)
        assert seen[0].headers["host"] == "earth-search.aws.element84.com"

    def test_every_known_adapter_supports_both_filters(self) -> None:
        """K8: the landing page's ``item-search`` conformance class (adr/0005 rule
        VI, `docs/plans/m1-07-stac-api.md` §6) only holds true while every adapter
        this platform dispatches to can honour both `intersects` and `ids` — this
        turns the day that stops being so into a failing test here, not a landing
        page silently promising more than the weakest adapter can do."""
        for kind, module in adapters_pkg._ADAPTERS.items():
            assert getattr(module, "SUPPORTS_INTERSECTS", False), f"{kind} does not declare SUPPORTS_INTERSECTS"
            assert getattr(module, "SUPPORTS_IDS", False), f"{kind} does not declare SUPPORTS_IDS"
