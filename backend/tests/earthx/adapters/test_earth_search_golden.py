"""M5-08: Earth Search stays bit for bit what it was when the STAC adapter became one module (plan §4.7, R4).

The golden file ``tests/fixtures/earth_search/golden_requests.json`` was written by this module against the
code *before* ``adapters/stac_api.py`` existed. It holds, for a matrix of searches, item fetches and coverage
queries: every request as it left the gateway (method, URL, headers, body as text), every cache write (key,
value, lifetime) and every answer (items, count, our own page token). A test on fields would not notice a
reordered key in a JSON body; this compares the bytes.

Everything goes through the dispatch in ``earthx.adapters``, never a source module, so this file itself does
not change when the modules behind the dispatch do. To write the file anew (only on purpose, and never in the
same commit as a change to the adapter)::

    cd backend && python -m tests.earthx.adapters.test_earth_search_golden
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anyio
import httpx
import pytest

from earthx.adapters import ADAPTER_SPECS, CacheValue, SearchParams, coverage, get_item, search_items
from earthx.catalog.coverage import CoverageQuery
from earthx.catalog.search_filters import RangeCondition, ValuesCondition
from tests.catalog.entries import SENTINEL_2_L2A

from .conftest import FIXTURES, gateway_for, load

GOLDEN = FIXTURES / "golden_requests.json"

CLOSED = (datetime(2024, 6, 1, tzinfo=timezone.utc), datetime(2024, 6, 30, 23, 59, 59, tzinfo=timezone.utc))
POLYGON = {
    "type": "Polygon",
    "coordinates": [[[10.5, 49.5], [10.6, 49.5], [10.6, 49.6], [10.5, 49.6], [10.5, 49.5]]],
}
CONDITIONS = {
    "eo:cloud_cover": RangeCondition(minimum=None, maximum=20.0),
    "s2:nodata_pixel_percentage": RangeCondition(minimum=0.0, maximum=5.0),
    "platform": ValuesCondition(values=("sentinel-2a", "sentinel-2c")),
}


class RecordingCache:
    """An in-memory cache that keeps every write in the order it came."""

    def __init__(self) -> None:
        self.values: dict[str, CacheValue] = {}
        self.writes: list[dict[str, Any]] = []

    async def get(self, key: str) -> CacheValue | None:
        return self.values.get(key)

    async def set(self, key: str, value: CacheValue, *, ttl_s: float, dataset_id: str) -> None:
        self.values[key] = value
        self.writes.append({"key": key, "value": value, "ttl_s": ttl_s, "dataset_id": dataset_id})


def _request(request: httpx.Request) -> dict[str, Any]:
    return {
        "method": request.method,
        "url": str(request.url),
        "headers": sorted([name, value] for name, value in request.headers.items()),
        "body": request.content.decode("utf-8"),
    }


def _page(page: Any) -> dict[str, Any]:
    return {
        "items": list(page.items),
        "matched": page.matched,
        "next_page_token": page.next_page_token,
        "from_cache": page.from_cache,
    }


Step = Callable[[Any, RecordingCache, list[Any]], Awaitable[Any]]


async def _run(answers: list[str], steps: list[Step]) -> dict[str, Any]:
    """Run ``steps`` against one gateway answering with the named fixtures in order."""
    seen: list[httpx.Request] = []
    queue = [load(name) for name in answers]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=queue.pop(0))

    cache = RecordingCache()
    results: list[Any] = []
    async with gateway_for(handler) as gateway:
        for step in steps:
            results.append(await step(gateway, cache, results))
    return {"requests": [_request(request) for request in seen], "cache_writes": cache.writes, "results": results}


def _search(params: Callable[[list[Any]], SearchParams]) -> Step:
    async def step(gateway: Any, cache: RecordingCache, results: list[Any]) -> Any:
        page = await search_items(SENTINEL_2_L2A, params(results), adapters=ADAPTER_SPECS, gateway=gateway, cache=cache)
        return _page(page)

    return step


def _item(item_id: str) -> Step:
    async def step(gateway: Any, cache: RecordingCache, results: list[Any]) -> Any:
        return await get_item(SENTINEL_2_L2A, item_id, adapters=ADAPTER_SPECS, gateway=gateway, cache=cache)

    return step


def _coverage(query: CoverageQuery) -> Step:
    async def step(gateway: Any, cache: RecordingCache, results: list[Any]) -> Any:
        result = await coverage(query, SENTINEL_2_L2A, adapters=ADAPTER_SPECS, gateway=gateway, cache=cache)
        return json.loads(json.dumps(asdict(result), default=str))

    return step


def _cases() -> dict[str, tuple[list[str], list[Step]]]:
    dataset_id = SENTINEL_2_L2A.dataset_id
    return {
        "plain search, the next page, then the first page again from the cache": (
            ["search_page_1", "search_page_2"],
            [
                _search(lambda results: SearchParams(limit=2)),
                _search(lambda results: SearchParams(limit=2, page_token=results[0]["next_page_token"])),
                _search(lambda results: SearchParams(limit=2)),
            ],
        ),
        "bbox and a closed window": (
            ["search_real_shape"],
            [_search(lambda results: SearchParams(bbox=(10.5, 49.5, 10.51, 49.51), start=CLOSED[0], end=CLOSED[1]))],
        ),
        "an open end": (["search_empty"], [_search(lambda results: SearchParams(start=CLOSED[0]))]),
        "intersects": (["search_empty"], [_search(lambda results: SearchParams(intersects=POLYGON, limit=5))]),
        "ids without a count": (
            ["search_no_count"],
            [_search(lambda results: SearchParams(ids=("SYNTH_B", "SYNTH_A", "SYNTH_B")))],
        ),
        "conditions": (["search_empty"], [_search(lambda results: SearchParams(conditions=CONDITIONS))]),
        "everything at once": (
            ["search_empty"],
            [
                _search(
                    lambda results: SearchParams(
                        intersects=POLYGON,
                        ids=("SYNTH_A",),
                        start=CLOSED[0],
                        end=CLOSED[1],
                        limit=5,
                        conditions=CONDITIONS,
                    )
                )
            ],
        ),
        "an item, then the same item from the cache": (
            ["item"],
            [_item("SYNTH_T00AAA_20240601T100000_L2A"), _item("SYNTH_T00AAA_20240601T100000_L2A")],
        ),
        "an item with band assets": (["item_asset_hosts"], [_item("SYNTH_T00AAA_20240601T100000_L2A")]),
        "coverage over the whole extent": (["aggregate_complete"], [_coverage(CoverageQuery(dataset_id, level=8))]),
        "coverage with area, window and conditions": (
            ["aggregate_truncated"],
            [
                _coverage(
                    CoverageQuery(
                        dataset_id,
                        level=8,
                        bbox=(5.0, 45.0, 15.0, 55.0),
                        start=CLOSED[0],
                        end=CLOSED[1],
                        conditions=CONDITIONS,
                    )
                )
            ],
        ),
    }


async def capture() -> dict[str, Any]:
    return {name: await _run(answers, steps) for name, (answers, steps) in _cases().items()}


def _golden() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


@pytest.mark.anyio
@pytest.mark.parametrize("case", sorted(_cases()))
async def test_earth_search_is_what_it_was(case: str) -> None:
    answers, steps = _cases()[case]
    assert await _run(answers, steps) == _golden()[case]


def test_the_golden_file_has_exactly_the_cases_of_this_module() -> None:
    assert sorted(_golden()) == sorted(_cases())


def _write(path: Path) -> None:
    path.write_text(json.dumps(anyio.run(capture), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    _write(GOLDEN)
