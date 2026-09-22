"""The EOPF STAC adapter against synthetic, recorded-looking answers.

Mirrors ``test_earth_search.py`` where the rules are the same (adr/0005 applies to
any federated source) and diverges exactly where the source does: the page marker
field is ``token``, not ``next`` (M2-09b plan §3.1), there is never a ``numberMatched``,
and every item comes back normalised to STAC 1.0 (adr/0007 §6 point 4).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

from earthx.adapters.eopf_stac import get_item, resolve_dataset, search_items
from earthx.adapters.federated_search import SearchParams, UnknownCollection, UnsupportedSource, UpstreamShapeError
from earthx.catalog.datasets import SENTINEL_2_L2A_ZARR3
from earthx.catalog.registry import DatasetRegistry
from earthx.gateway import Policy
from earthx.gateway.client import Gateway

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "eopf_stac"
HOST = "stac.core.eopf.eodc.eu"
POLICY = Policy(allowed_hosts=frozenset({HOST}))
DATASET_ID = SENTINEL_2_L2A_ZARR3.dataset_id


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def body_of(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def gateway_for(handler: Callable[[httpx.Request], httpx.Response]) -> Gateway:
    async def sleep(seconds: float) -> None:
        return None

    return Gateway(POLICY, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep)


def answering(*responses: httpx.Response) -> tuple[Gateway, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return gateway_for(handler), seen


class TestSearch:
    async def test_a_page_comes_back_normalised_to_stac_1_0(self) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            page = await search_items(DATASET_ID, SearchParams(limit=2), gateway=gateway)
        assert [item["id"] for item in page.items] == [
            "SYNTH_S2A_MSIL2A_20260921T141821_T26WME",
            "SYNTH_S2A_MSIL2A_20260921T141821_T26WMD",
        ]
        first = page.items[0]
        assert first["stac_version"] == "1.0.0"
        assert first["properties"]["proj:epsg"] == 32626
        assert first["assets"]["SR_10m"]["eo:bands"][0]["common_name"] == "red"
        assert first["assets"]["SR_10m"]["raster:bands"] == [{"nodata": 0, "data_type": "uint16", "spatial_resolution": 10}]

    async def test_there_is_never_a_matched_count(self) -> None:
        """adr/0007 §12.6: `numberMatched` is missing from every answer, not just
        truncated ones — the coverage sample of M2-09b-3 is why, not a bug here."""
        gateway, _ = answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            page = await search_items(DATASET_ID, SearchParams(limit=2), gateway=gateway)
        assert page.matched is None

    async def test_the_search_asks_for_the_upstream_collection_id(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await search_items(DATASET_ID, SearchParams(bbox=(-33.0, 34.0, 179.0, 72.0)), gateway=gateway)
        assert seen[0].url.path == "/search"
        assert seen[0].headers["host"] == HOST
        assert body_of(seen[0])["collections"] == [SENTINEL_2_L2A_ZARR3.source.source_collection_id]

    async def test_every_search_carries_our_own_fixed_sortby(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await search_items(DATASET_ID, gateway=gateway)
        assert body_of(seen[0])["sortby"] == [
            {"field": "properties.datetime", "direction": "desc"},
            {"field": "id", "direction": "asc"},
        ]

    async def test_an_empty_result_is_an_empty_page_not_an_error(self) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            page = await search_items(DATASET_ID, gateway=gateway)
        assert page.items == ()
        assert page.matched is None
        assert page.next_page_token is None


class TestCollectionIsOurs:
    async def test_an_unknown_collection_never_reaches_the_source(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            with pytest.raises(UnknownCollection, match="no-such-collection"):
                await search_items("no-such-collection", gateway=gateway)
        assert seen == []

    async def test_a_collection_of_another_adapter_is_not_served_here(self) -> None:
        other = replace(SENTINEL_2_L2A_ZARR3, source=replace(SENTINEL_2_L2A_ZARR3.source, adapter="some-other-protocol"))
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            with pytest.raises(UnsupportedSource):
                await search_items(other.dataset_id, gateway=gateway, registry=DatasetRegistry((other,)))
        assert seen == []

    def test_resolve_dataset_is_this_adapters_own_check(self) -> None:
        assert resolve_dataset(DATASET_ID, DatasetRegistry((SENTINEL_2_L2A_ZARR3,))) is SENTINEL_2_L2A_ZARR3


class TestPaging:
    async def test_a_next_link_becomes_a_token_of_our_own(self) -> None:
        upstream_marker = "next:sentinel-2-l2a-zarr3:SYNTH_S2A_MSIL2A_20260921T141821_T26WMD"
        gateway, _ = answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            page = await search_items(DATASET_ID, SearchParams(limit=2), gateway=gateway)
        assert page.next_page_token is not None
        assert page.next_page_token != upstream_marker
        assert upstream_marker not in page.next_page_token

    async def test_the_token_is_sent_back_under_the_sources_own_field_name(self) -> None:
        """M2-09b plan §3.1: this source's paging field is `token`, not `next`."""
        gateway, seen = answering(
            httpx.Response(200, json=load("search_page_1")), httpx.Response(200, json=load("search_empty"))
        )
        async with gateway:
            first = await search_items(DATASET_ID, SearchParams(limit=2), gateway=gateway)
            await search_items(DATASET_ID, SearchParams(limit=2, page_token=first.next_page_token), gateway=gateway)
        assert "token" in body_of(seen[1])
        assert "next" not in body_of(seen[1])
        assert body_of(seen[1])["token"] == "next:sentinel-2-l2a-zarr3:SYNTH_S2A_MSIL2A_20260921T141821_T26WMD"

    async def test_a_next_link_we_cannot_follow_is_an_error_not_a_last_page(self) -> None:
        answer = load("search_page_1")
        for link in answer["links"]:
            if link["rel"] == "next":
                del link["body"]
        gateway, _ = answering(httpx.Response(200, json=answer))
        async with gateway:
            with pytest.raises(UpstreamShapeError, match="marker"):
                await search_items(DATASET_ID, SearchParams(limit=2), gateway=gateway)


class TestGetItem:
    async def test_an_item_comes_back_normalised(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("item")))
        async with gateway:
            item = await get_item(DATASET_ID, "SYNTH_S2A_MSIL2A_20260921T141821_T26WME", gateway=gateway)
        assert item["stac_version"] == "1.0.0"
        assert item["properties"]["proj:epsg"] == 32626
        assert seen[0].url.path == f"/collections/{SENTINEL_2_L2A_ZARR3.source.source_collection_id}/items/SYNTH_S2A_MSIL2A_20260921T141821_T26WME"

    async def test_a_missing_item_stays_the_sources_404(self) -> None:
        from earthx.gateway.errors import UpstreamError

        gateway, _ = answering(httpx.Response(404, json={"detail": "not found"}))
        async with gateway:
            with pytest.raises(UpstreamError) as excinfo:
                await get_item(DATASET_ID, "no-such-item", gateway=gateway)
        assert excinfo.value.status_code == 404

    async def test_an_unknown_collection_is_refused_for_a_single_item_too(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("item")))
        async with gateway:
            with pytest.raises(UnknownCollection):
                await get_item("no-such-collection", "SYNTH_S2A_MSIL2A_20260921T141821_T26WME", gateway=gateway)
        assert seen == []
