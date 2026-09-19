"""T-B: the adapter against recorded-looking, synthetic answers.

Everything goes through the gateway with a mock transport, so these tests also prove
the one thing adr/0005 §3.8 asked for: the status codes of the source survive. A
``404`` stays a ``404`` instead of becoming an ``APIError`` with a text body.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest

from earthx.adapters import (
    InvalidQuery,
    SearchParams,
    UnknownCollection,
    UnsupportedSource,
    UpstreamShapeError,
    get_item,
    search_items,
)
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import DatasetRegistry
from earthx.gateway.errors import UpstreamError, UpstreamTimeout

from .conftest import answering, body_of, gateway_for, load

pytestmark = pytest.mark.anyio

WINDOW = (datetime(2024, 6, 1, tzinfo=timezone.utc), datetime(2024, 6, 30, tzinfo=timezone.utc))


class TestSearch:
    async def test_a_page_comes_back_as_items_and_a_count(self, dataset_id: str) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            page = await search_items(dataset_id, SearchParams(limit=2), gateway=gateway)
        assert [item["id"] for item in page.items] == [
            "SYNTH_T00AAA_20240601T100000_L2A",
            "SYNTH_T00AAA_20240602T100000_L2A",
        ]
        assert page.matched == 3
        assert page.from_cache is False

    async def test_the_search_asks_for_the_upstream_collection_id(self, dataset_id: str) -> None:
        """Our dataset id and the source's collection id are not the same field."""
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await search_items(dataset_id, SearchParams(bbox=(8.0, 47.0, 12.0, 51.0)), gateway=gateway)
        # The gateway connects the checked address and carries the name in Host and SNI
        # (M1-03, F2), so the path and the Host header are what identify the request.
        assert seen[0].url.path == "/v1/search"
        assert seen[0].headers["host"] == "earth-search.aws.element84.com"
        assert body_of(seen[0])["collections"] == [SENTINEL_2_L2A.source.source_collection_id]

    async def test_the_time_window_goes_out_as_a_stac_interval(self, dataset_id: str) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await search_items(dataset_id, SearchParams(start=WINDOW[0], end=WINDOW[1]), gateway=gateway)
        assert body_of(seen[0])["datetime"] == "2024-06-01T00:00:00Z/2024-06-30T00:00:00Z"

    async def test_an_open_end_is_written_as_two_dots(self, dataset_id: str) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await search_items(dataset_id, SearchParams(start=WINDOW[0]), gateway=gateway)
        assert body_of(seen[0])["datetime"] == "2024-06-01T00:00:00Z/.."

    async def test_an_empty_result_is_an_empty_page_not_an_error(self, dataset_id: str) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            page = await search_items(dataset_id, gateway=gateway)
        assert page.items == ()
        assert page.matched == 0
        assert page.next_page_token is None


class TestCollectionIsOurs:
    async def test_an_unknown_collection_never_reaches_the_source(self) -> None:
        """adr/0005 rule I: upstream would answer 200 with matched 0, which reads as
        "there is nothing here" instead of "there is no such thing"."""
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            with pytest.raises(UnknownCollection, match="no-such-collection"):
                await search_items("no-such-collection", gateway=gateway)
        assert seen == []

    async def test_an_unknown_collection_is_refused_for_a_single_item_too(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("item")))
        async with gateway:
            with pytest.raises(UnknownCollection):
                await get_item("no-such-collection", "SYNTH_T00AAA_20240601T100000_L2A", gateway=gateway)
        assert seen == []

    async def test_a_collection_of_another_adapter_is_not_served_here(self) -> None:
        """A second AdapterKind does not exist yet, so a placeholder value stands in
        for one — the guard compares identity with our own kind, not a string."""
        other = replace(SENTINEL_2_L2A, source=replace(SENTINEL_2_L2A.source, adapter="some-other-protocol"))
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            with pytest.raises(UnsupportedSource):
                await search_items(other.dataset_id, gateway=gateway, registry=DatasetRegistry((other,)))
        assert seen == []


class TestPaging:
    async def test_a_next_link_becomes_a_token_of_our_own(self, dataset_id: str) -> None:
        upstream_marker = "2024-06-02T10:00:00.000000Z,SYNTH_T00AAA_20240602T100000_L2A,sentinel-2-c1-l2a"
        gateway, _ = answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            page = await search_items(dataset_id, SearchParams(limit=2), gateway=gateway)
        assert page.next_page_token is not None
        # adr/0005 rule III: ours, not theirs. The upstream marker is carried inside,
        # but it is not what we hand out.
        assert page.next_page_token != upstream_marker
        assert upstream_marker not in page.next_page_token

    async def test_the_token_takes_the_search_to_the_next_page(self, dataset_id: str) -> None:
        gateway, seen = answering(
            httpx.Response(200, json=load("search_page_1")), httpx.Response(200, json=load("search_page_2"))
        )
        async with gateway:
            first = await search_items(dataset_id, SearchParams(limit=2), gateway=gateway)
            second = await search_items(
                dataset_id, SearchParams(limit=2, page_token=first.next_page_token), gateway=gateway
            )
        assert body_of(seen[1])["next"] == (
            "2024-06-02T10:00:00.000000Z,SYNTH_T00AAA_20240602T100000_L2A,sentinel-2-c1-l2a"
        )
        assert [item["id"] for item in second.items] == ["SYNTH_T00AAA_20240603T100000_L2A"]

    async def test_a_next_link_we_cannot_follow_is_an_error_not_a_last_page(self, dataset_id: str) -> None:
        """There are more items and we cannot reach them. Answering with a page that
        looks complete is the same silent truncation rule I refuses elsewhere."""
        answer = load("search_page_1")
        for link in answer["links"]:
            if link["rel"] == "next":
                del link["body"]
        gateway, _ = answering(httpx.Response(200, json=answer))
        async with gateway:
            with pytest.raises(UpstreamShapeError, match="marker"):
                await search_items(dataset_id, SearchParams(limit=2), gateway=gateway)

    async def test_the_last_page_has_no_token(self, dataset_id: str) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_page_2")))
        async with gateway:
            page = await search_items(dataset_id, SearchParams(limit=2), gateway=gateway)
        assert page.next_page_token is None

    async def test_a_token_from_another_search_is_refused(self, dataset_id: str) -> None:
        """The token carries the hash of the search it belongs to, so a page marker
        cannot be replayed against a different bbox and quietly return the wrong page."""
        gateway, seen = answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            page = await search_items(dataset_id, SearchParams(limit=2), gateway=gateway)
            with pytest.raises(InvalidQuery, match="different search"):
                await search_items(
                    dataset_id,
                    SearchParams(limit=2, bbox=(8.0, 47.0, 12.0, 51.0), page_token=page.next_page_token),
                    gateway=gateway,
                )
        assert len(seen) == 1

    @pytest.mark.parametrize("token", ["not-base64!!", "", "eyJub3QiOiAiYSB0b2tlbiJ9"])
    async def test_a_broken_token_is_refused_in_our_own_words(self, dataset_id: str, token: str) -> None:
        """A broken upstream marker is answered with Elasticsearch internals
        (adr/0005 §3.3). Ours never gets that far: nothing is sent at all."""
        gateway, seen = answering(httpx.Response(200, json=load("search_page_1")))
        async with gateway:
            with pytest.raises(InvalidQuery) as error:
                await search_items(dataset_id, SearchParams(page_token=token), gateway=gateway)
        assert "search_after" not in str(error.value)
        assert seen == []


class TestUpstreamTrouble:
    @pytest.mark.parametrize("status", [400, 404, 429, 503])
    async def test_the_status_code_survives(self, dataset_id: str, status: int) -> None:
        """What pystac_client loses (adr/0005 §3.8) and M1-06 needs to tell apart."""
        gateway, _ = answering(httpx.Response(status, json={"description": "upstream says no"}))
        async with gateway:
            with pytest.raises(UpstreamError) as error:
                await search_items(dataset_id, gateway=gateway)
        assert error.value.status_code == status

    async def test_a_timeout_is_a_timeout_not_an_empty_page(self, dataset_id: str) -> None:
        """Answering "no items" when the source did not answer would be a lie the
        caller cannot see through."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("took too long", request=request)

        async with gateway_for(handler) as gateway:
            with pytest.raises(UpstreamTimeout):
                await search_items(dataset_id, gateway=gateway)

    async def test_an_answer_that_is_not_an_item_collection_is_named_as_such(self, dataset_id: str) -> None:
        gateway, _ = answering(httpx.Response(200, json={"type": "Collection", "id": "not a search result"}))
        async with gateway:
            with pytest.raises(UpstreamShapeError):
                await search_items(dataset_id, gateway=gateway)


class TestSingleItem:
    async def test_an_item_is_fetched_by_id_without_a_search_first(self, dataset_id: str) -> None:
        """adr/0001 Z1: no endpoint may require a search to have happened before it."""
        gateway, seen = answering(httpx.Response(200, json=load("item")))
        async with gateway:
            item = await get_item(dataset_id, "SYNTH_T00AAA_20240601T100000_L2A", gateway=gateway)
        assert seen[0].url.path == (
            "/v1/collections/sentinel-2-c1-l2a/items/SYNTH_T00AAA_20240601T100000_L2A"
        )
        assert seen[0].headers["host"] == "earth-search.aws.element84.com"
        assert item["id"] == "SYNTH_T00AAA_20240601T100000_L2A"

    async def test_a_missing_item_stays_a_404(self, dataset_id: str) -> None:
        gateway, _ = answering(httpx.Response(404, json={"description": "Not Found"}))
        async with gateway:
            with pytest.raises(UpstreamError) as error:
                await get_item(dataset_id, "SYNTH_T00AAA_19700101T000000_L2A", gateway=gateway)
        assert error.value.status_code == 404

    async def test_an_answer_that_is_not_an_item_is_named_as_such(self, dataset_id: str) -> None:
        gateway, _ = answering(httpx.Response(200, json=["not", "an", "item"]))
        async with gateway:
            with pytest.raises(UpstreamShapeError):
                await get_item(dataset_id, "SYNTH_T00AAA_20240601T100000_L2A", gateway=gateway)

    @pytest.mark.parametrize("item_id", ["../../collections", "a b", "item?fields=id", "", "S2A_OK\n"])
    async def test_an_item_id_that_would_leave_its_path_segment_is_refused(
        self, dataset_id: str, item_id: str
    ) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("item")))
        async with gateway:
            with pytest.raises(InvalidQuery, match="URL path"):
                await get_item(dataset_id, item_id, gateway=gateway)
        assert seen == []
