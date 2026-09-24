"""The read tools against synthetic answers of the public STAC API, without a network."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from earthx.chatbot import tools as tools_module
from earthx.chatbot.tools import TOOL_SPECS, CatalogTools, UnknownCollection, call_tool
from earthx.chatbot.validation import InvalidArgument
from earthx.gateway import Gateway, Policy

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
HOST = "stac.example.invalid"
ROOT = f"https://{HOST}/stac"
POLICY = Policy(allowed_hosts=frozenset({HOST}))


def fixture(*parts: str) -> Any:
    return json.loads((FIXTURES.joinpath(*parts)).read_text(encoding="utf-8"))


def public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


async def no_sleep(_: float) -> None:
    return None


def catalogue(request: httpx.Request) -> httpx.Response:
    """The synthetic API: two pages of collections, one detail, and the item search."""
    path, token = request.url.path, request.url.params.get("token")
    if request.method == "GET" and path == "/stac/collections":
        page = "collections_page_2.json" if token == "page2" else "collections_page_1.json"
        return httpx.Response(200, json=fixture("chatbot", page))
    if request.method == "GET" and path == "/stac/collections/synth-optical-l2a":
        return httpx.Response(200, json=fixture("chatbot", "collection_detail.json"))
    if request.method == "POST" and path == "/stac/search":
        return httpx.Response(200, json=fixture("earth_search", "search_page_1.json"))
    return httpx.Response(404, json={"code": "NotFoundError", "description": "not found"})


def build(
    handler: Callable[[httpx.Request], httpx.Response] = catalogue, **limits: Any
) -> tuple[CatalogTools, Gateway]:
    policy = Policy(allowed_hosts=frozenset({HOST}), **limits) if limits else POLICY
    gateway = Gateway(policy, transport=httpx.MockTransport(handler), resolve=public, sleep=no_sleep)
    return CatalogTools(gateway, ROOT + "/"), gateway


def answering(status: int = 200, **kwargs: Any) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(status, **kwargs)


# search_collections


async def test_search_follows_the_next_link_and_matches_every_word() -> None:
    tools, gateway = build()
    async with gateway:
        result = await tools.search_collections("synthetic radar")
    assert [c["id"] for c in result["collections"]] == ["synth-radar-alps"]
    assert result["total_matches"] == 1
    assert result["catalogue_complete"] is True


async def test_search_reads_keywords_and_providers_too() -> None:
    tools, gateway = build()
    async with gateway:
        by_keyword = await tools.search_collections("dem")
        by_provider = await tools.search_collections("space agency")
    assert [c["id"] for c in by_keyword["collections"]] == ["synth-injection"]
    assert [c["id"] for c in by_provider["collections"]] == ["synth-optical-l2a"]


async def test_search_without_words_lists_the_whole_catalogue_up_to_the_limit() -> None:
    tools, gateway = build()
    async with gateway:
        result = await tools.search_collections(limit=2)
    assert len(result["collections"]) == 2
    assert result["total_matches"] == 3


async def test_search_drops_collections_outside_the_box_and_the_interval() -> None:
    tools, gateway = build()
    async with gateway:
        in_alps_2020 = await tools.search_collections(bbox=[8, 46, 9, 47], datetime="2020-06-01/2020-06-30")
        in_alps_2024 = await tools.search_collections(bbox=[8, 46, 9, 47], datetime="2024-06-01/2024-06-30")
        in_brazil = await tools.search_collections(bbox=[-50, -10, -49, -9])
    assert {c["id"] for c in in_alps_2020["collections"]} == {"synth-optical-l2a", "synth-radar-alps"}
    assert {c["id"] for c in in_alps_2024["collections"]} == {"synth-optical-l2a"}
    assert {c["id"] for c in in_brazil["collections"]} == {"synth-optical-l2a", "synth-injection"}


async def test_search_says_when_it_stopped_before_the_last_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools_module, "MAX_COLLECTION_PAGES", 1)
    tools, gateway = build()
    async with gateway:
        result = await tools.search_collections()
    assert result["catalogue_complete"] is False
    assert result["total_matches"] == 2


async def test_a_next_link_to_another_host_is_refused_by_the_gateway() -> None:
    def elsewhere(request: httpx.Request) -> httpx.Response:
        page = fixture("chatbot", "collections_page_1.json")
        page["links"][1]["href"] = "https://attacker.example.invalid/collections"
        return httpx.Response(200, json=page)

    tools, gateway = build(elsewhere)
    async with gateway:
        result = await call_tool(tools, "search_collections", {})
    assert result == {"error": "the catalogue could not be reached or refused the request"}


async def test_an_instruction_in_a_description_stays_data_in_the_result() -> None:
    tools, gateway = build()
    async with gateway:
        result = await tools.search_collections("elevation")
    [hit] = result["collections"]
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in hit["description"]
    assert set(hit) == {"id", "title", "description", "license", "bbox", "interval"}


async def test_a_long_description_is_cut_in_the_search_result() -> None:
    def long_text(request: httpx.Request) -> httpx.Response:
        page = fixture("chatbot", "collections_page_2.json")
        page["collections"][0]["description"] = "word " * 1000
        return httpx.Response(200, json=page)

    tools, gateway = build(long_text)
    async with gateway:
        result = await tools.search_collections("word")
    assert len(result["collections"][0]["description"]) <= 300


# get_collection


async def test_get_collection_returns_the_chosen_fields_and_leaves_the_source_out() -> None:
    tools, gateway = build()
    async with gateway:
        detail = await tools.get_collection("synth-optical-l2a")
    assert detail["license"] == "CC-BY-4.0"
    assert detail["bbox"] == [-180.0, -56.0, 180.0, 84.0]
    assert detail["interval"] == ["2017-03-28T00:00:00Z", None]
    assert detail["earthx:license_flags"]["attribution_required"] is True
    assert detail["providers"] == ["Synthetic Space Agency"]
    assert "earthx:source" not in detail
    assert "upstream.example.invalid" not in json.dumps(detail)


async def test_an_oversized_earthx_field_is_dropped_whole() -> None:
    def bloated(request: httpx.Request) -> httpx.Response:
        body = fixture("chatbot", "collection_detail.json")
        body["earthx:capabilities"] = {f"flag_{i}": "x" * 100 for i in range(100)}
        return httpx.Response(200, json=body)

    tools, gateway = build(bloated)
    async with gateway:
        detail = await tools.get_collection("synth-optical-l2a")
    assert "earthx:capabilities" not in detail
    assert "earthx:license_flags" in detail


async def test_an_unknown_collection_is_named_as_such() -> None:
    tools, gateway = build()
    async with gateway:
        with pytest.raises(UnknownCollection):
            await tools.get_collection("does-not-exist")
        result = await call_tool(tools, "get_collection", {"collection_id": "does-not-exist"})
    assert result == {"error": "no collection with id 'does-not-exist'"}


async def test_a_collection_id_with_a_path_never_reaches_the_api() -> None:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return catalogue(request)

    tools, gateway = build(record)
    async with gateway:
        with pytest.raises(InvalidArgument):
            await tools.get_collection("../search")
    assert seen == []


# check_availability


async def test_availability_sends_one_bounded_search_and_reads_the_total() -> None:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return catalogue(request)

    tools, gateway = build(record)
    async with gateway:
        result = await tools.check_availability("sentinel-2-c1-l2a", [9, 48, 10, 49], "2024-06-01/2024-06-30")
    assert json.loads(seen[0].content) == {
        "collections": ["sentinel-2-c1-l2a"],
        "bbox": [9.0, 48.0, 10.0, 49.0],
        "datetime": "2024-06-01T00:00:00Z/2024-06-30T23:59:59.999999Z",
        "limit": tools_module.AVAILABILITY_SAMPLE,
    }
    assert result == {
        "collection_id": "sentinel-2-c1-l2a",
        "count": 3,
        "count_is_exact": True,
        "sample_size": 2,
        "earliest_in_sample": "2024-06-01T10:00:00Z",
        "latest_in_sample": "2024-06-02T10:00:00Z",
    }


async def test_availability_without_a_total_but_with_a_next_page_is_a_lower_bound() -> None:
    page = fixture("earth_search", "search_no_count.json")
    page["links"] = [{"rel": "next", "href": f"{ROOT}/search", "method": "POST", "body": {"token": "next:2"}}]
    tools, gateway = build(answering(json=page))
    async with gateway:
        result = await tools.check_availability("sentinel-2-c1-l2a", [9, 48, 10, 49], "2024-06-01/2024-06-30")
    assert result["count_is_exact"] is False
    assert result["count"] == result["sample_size"]


async def test_availability_without_a_total_and_without_a_next_page_counts_the_page() -> None:
    tools, gateway = build(answering(json=fixture("earth_search", "search_no_count.json")))
    async with gateway:
        result = await tools.check_availability("sentinel-2-c1-l2a", [9, 48, 10, 49], "2024-06-01/2024-06-30")
    assert result["count_is_exact"] is True
    assert result["count"] == result["sample_size"]


async def test_availability_with_nothing_found_is_an_exact_zero() -> None:
    tools, gateway = build(answering(json=fixture("earth_search", "search_empty.json")))
    async with gateway:
        result = await tools.check_availability("sentinel-2-c1-l2a", [9, 48, 10, 49], "2024-06-01")
    assert result["count"] == 0
    assert result["count_is_exact"] is True
    assert result["earliest_in_sample"] is None


async def test_availability_needs_both_box_and_time() -> None:
    tools, gateway = build()
    async with gateway:
        with pytest.raises(InvalidArgument):
            await tools.check_availability("sentinel-2-c1-l2a", None, "2024-06-01")
        result = await call_tool(tools, "check_availability", {"collection_id": "x", "bbox": [9, 48, 10, 49]})
    assert result == {"error": "check_availability needs argument(s) datetime"}


# call_tool: what a model might get wrong, and what the API might answer


@pytest.mark.parametrize(
    ("name", "arguments", "error"),
    [
        ("start_job", {}, "unknown tool; available: check_availability, get_collection, search_collections"),
        (None, {}, "unknown tool; available: check_availability, get_collection, search_collections"),
        ("get_collection", ["synth-optical-l2a"], "arguments must be an object"),
        ("get_collection", {"collection_id": "x", "token": "t"}, "get_collection takes no argument(s) token"),
        ("get_collection", {}, "get_collection needs argument(s) collection_id"),
        ("search_collections", {"bbox": [10, 48, 9, 49]}, None),
        ("search_collections", {"limit": "all"}, "limit must be a whole number"),
    ],
)
async def test_call_tool_answers_every_wrong_call_with_an_error(
    name: object, arguments: object, error: str | None
) -> None:
    tools, gateway = build()
    async with gateway:
        result = await call_tool(tools, name, arguments)
    assert set(result) == {"error"}
    if error is not None:
        assert result["error"] == error


@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (answering(500, text="boom"), "the catalogue answered 500"),
        (answering(content=b"{not json"), "the catalogue answered with something that is not valid STAC JSON"),
        (answering(json=["a", "list"]), "the catalogue answered with something that is not valid STAC JSON"),
        (answering(content=b"x" * 5000), "the catalogue could not be reached or refused the request"),
    ],
)
async def test_call_tool_turns_a_broken_api_answer_into_an_error(handler: Callable, error: str) -> None:
    tools, gateway = build(handler, max_response_bytes=4096)
    async with gateway:
        result = await call_tool(tools, "get_collection", {"collection_id": "synth-optical-l2a"})
    assert result == {"error": error}


async def test_call_tool_reports_a_timeout_after_the_gateway_gave_up() -> None:
    attempts: list[httpx.Request] = []

    def slow(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        raise httpx.ReadTimeout("slow", request=request)

    tools, gateway = build(slow)
    async with gateway:
        result = await call_tool(tools, "search_collections", {"query": "radar"})
    assert result == {"error": "the catalogue could not be reached or refused the request"}
    assert len(attempts) == 3


def test_every_spec_names_a_tool_and_forbids_unknown_arguments() -> None:
    for spec in TOOL_SPECS:
        assert callable(getattr(CatalogTools, spec["name"]))
        assert spec["input_schema"]["additionalProperties"] is False
