"""T-B: the place-search adapter against synthetic, recorded-looking answers.

Fixtures are invented places and coordinates (`backend/tests/fixtures/nominatim/`),
never a copy of real OSM data — CLAUDE.md and `docs/plans/m3-07a-ortssuche-backend.md`
§11. Everything goes through the gateway with a mock transport and a fake resolver,
same as the other adapter tests.
"""

from __future__ import annotations

import httpx
import pytest

from earthx.adapters.nominatim import (
    ATTRIBUTION,
    RateLimited,
    UpstreamShapeError,
    geocode,
    normalize_query_text,
)
from earthx.gateway import UpstreamError, UpstreamTimeout
from earthx.gateway.client import Gateway

from .conftest import NOMINATIM_HOST, NOMINATIM_POLICY
from .conftest import _public as _resolve
from .conftest import answering as _answering
from .conftest import load_nominatim as load

pytestmark = pytest.mark.anyio

BASE_URL = f"https://{NOMINATIM_HOST}"


def answering(*responses: httpx.Response) -> tuple[Gateway, list[httpx.Request]]:
    return _answering(*responses, policy=NOMINATIM_POLICY)


class FakeRateSlot:
    """Always free at once, unless told otherwise — the rate slot's own storage is
    tested against real Postgres in `tests/integration/test_geocode_cache.py`."""

    def __init__(self, delay_s: float = 0.0) -> None:
        self.delay_s = delay_s
        self.reserved: list[str] = []
        self.pushed_back: list[tuple[str, float]] = []

    async def reserve(self, name: str) -> float:
        self.reserved.append(name)
        return self.delay_s

    async def push_back(self, name: str, *, seconds: float) -> None:
        self.pushed_back.append((name, seconds))


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self.sets = 0

    async def get(self, key: str) -> dict | None:
        return self.store.get(key)

    async def set(self, key: str, value: dict, *, ttl_s: float) -> None:
        self.sets += 1
        self.store[key] = value


class BrokenCache:
    async def get(self, key: str) -> dict | None:
        raise RuntimeError("cache is down")

    async def set(self, key: str, value: dict, *, ttl_s: float) -> None:
        raise RuntimeError("cache is down")


async def _geocode(text: str, *, gateway: Gateway, cache=None, rate_slot=None):
    return await geocode(
        text,
        gateway=gateway,
        base_url=BASE_URL,
        user_agent="EarthX-test/0.0 (+https://example.invalid)",
        cache=cache,
        rate_slot=rate_slot or FakeRateSlot(),
    )


class TestNormalizeQueryText:
    def test_leading_and_trailing_whitespace_is_trimmed(self) -> None:
        assert normalize_query_text("  Berlin  ") == "Berlin"

    def test_internal_whitespace_runs_collapse_to_one_space(self) -> None:
        assert normalize_query_text("Bad\t\nHomburg") == "Bad Homburg"

    def test_empty_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            normalize_query_text("")

    def test_only_whitespace_is_rejected_as_empty_not_as_control_characters(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            normalize_query_text("   \t \n ")

    def test_a_control_character_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="control"):
            normalize_query_text("Berlin\x07")

    def test_201_characters_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="200"):
            normalize_query_text("a" * 201)

    def test_exactly_200_characters_is_accepted(self) -> None:
        assert normalize_query_text("a" * 200) == "a" * 200


class TestGeocode:
    async def test_a_hit_with_an_outline_under_the_cap_is_not_simplified(self) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_hit_with_outline")))
        async with gateway:
            response = await _geocode("Musterstadt", gateway=gateway)
        assert len(response.results) == 1
        result = response.results[0]
        assert result.outline is not None
        assert result.outline_simplified is False
        assert result.bbox == (8.38, 48.98, 8.42, 49.02)  # west, south, east, north
        assert response.from_cache is False

    async def test_an_outline_over_the_cap_is_simplified_under_it(self) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_hit_over_outline_cap")))
        async with gateway:
            response = await _geocode("Weitland", gateway=gateway)
        result = response.results[0]
        assert result.outline_simplified is True
        assert result.outline is not None

    async def test_a_point_hit_has_a_box_but_no_outline(self) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_point_hit")))
        async with gateway:
            response = await _geocode("Musterbahnhof", gateway=gateway)
        result = response.results[0]
        assert result.outline is None
        assert result.outline_simplified is False
        assert result.bbox is not None

    async def test_a_line_hit_has_a_box_but_no_outline(self) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_line_hit")))
        async with gateway:
            response = await _geocode("Musterstraße", gateway=gateway)
        assert response.results[0].outline is None

    async def test_no_hit_is_an_empty_list_not_an_error(self) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            response = await _geocode("qwxzyvkplm", gateway=gateway)
        assert response.results == ()

    async def test_a_body_that_is_not_a_list_is_an_upstream_shape_error(self) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_malformed_not_list")))
        async with gateway:
            with pytest.raises(UpstreamShapeError):
                await _geocode("anything", gateway=gateway)

    async def test_a_body_that_is_not_json_is_an_upstream_shape_error(self) -> None:
        gateway, _ = answering(httpx.Response(200, content=b"not json"))
        async with gateway:
            with pytest.raises(UpstreamShapeError):
                await _geocode("anything", gateway=gateway)

    async def test_hits_with_an_unusable_box_are_dropped_not_the_whole_answer(self) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_bad_bbox")))
        async with gateway:
            response = await _geocode("Kaputtbox", gateway=gateway)
        assert len(response.results) == 1
        assert response.results[0].display_name == "Gute Box, Beispielland"

    async def test_a_self_intersecting_outline_is_repaired_by_make_valid(self) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_invalid_polygon")))
        async with gateway:
            response = await _geocode("Schleifenland", gateway=gateway)
        assert response.results[0].outline is not None
        assert response.results[0].outline["type"] == "MultiPolygon"

    async def test_an_empty_name_falls_back_to_display_name(self) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_hit_missing_name")))
        async with gateway:
            response = await _geocode("Namenlos", gateway=gateway)
        assert response.results[0].name == "Namenlos, Beispielland"

    async def test_the_request_carries_our_user_agent_and_fixed_parameters(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await geocode(
                "Berlin",
                gateway=gateway,
                base_url=BASE_URL,
                user_agent="EarthX-test/0.0 (+https://example.invalid)",
                cache=None,
                rate_slot=FakeRateSlot(),
            )
        request = seen[0]
        assert request.url.path == "/search"
        assert request.headers["user-agent"] == "EarthX-test/0.0 (+https://example.invalid)"
        query = dict(httpx.QueryParams(request.url.query))
        assert query["q"] == "Berlin"
        assert query["format"] == "jsonv2"
        assert query["polygon_geojson"] == "1"
        assert query["limit"] == "5"
        assert query["accept-language"] == "en"

    async def test_attribution_is_always_present(self) -> None:
        gateway, _ = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            response = await _geocode("qwxzyvkplm", gateway=gateway)
        payload = response.to_payload()
        assert payload["attribution"] == ATTRIBUTION
        assert payload["results"] == []

    async def test_invalid_query_never_reaches_the_gateway(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            with pytest.raises(ValueError):
                await _geocode("   ", gateway=gateway)
        assert seen == []

    async def test_a_cache_hit_never_reaches_the_gateway_or_the_rate_slot(self) -> None:
        cache = FakeCache()
        rate_slot = FakeRateSlot()
        gateway, seen = answering(httpx.Response(200, json=load("search_hit_with_outline")))
        async with gateway:
            first = await _geocode("Musterstadt", gateway=gateway, cache=cache, rate_slot=rate_slot)
            second = await _geocode("Musterstadt", gateway=gateway, cache=cache, rate_slot=rate_slot)
        assert first.from_cache is False
        assert second.from_cache is True
        assert len(seen) == 1
        assert rate_slot.reserved == ["nominatim"]

    async def test_a_cache_hit_is_case_insensitive(self) -> None:
        cache = FakeCache()
        gateway, seen = answering(httpx.Response(200, json=load("search_hit_with_outline")))
        async with gateway:
            await _geocode("musterstadt", gateway=gateway, cache=cache)
            await _geocode("MUSTERSTADT", gateway=gateway, cache=cache)
        assert len(seen) == 1

    async def test_a_broken_cache_read_falls_back_to_the_source(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            response = await _geocode("Berlin", gateway=gateway, cache=BrokenCache())
        assert response.from_cache is False
        assert len(seen) == 1

    async def test_a_slot_farther_out_than_the_wait_budget_is_rate_limited(self) -> None:
        gateway, seen = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            with pytest.raises(RateLimited) as raised:
                await _geocode("Berlin", gateway=gateway, rate_slot=FakeRateSlot(delay_s=5.0))
        assert raised.value.retry_after_s == 5.0
        assert seen == []

    async def test_a_429_pushes_the_slot_back_and_is_rate_limited_not_upstream_error(self) -> None:
        gateway, seen = answering(httpx.Response(429))
        rate_slot = FakeRateSlot()
        async with gateway:
            with pytest.raises(RateLimited):
                await _geocode("Berlin", gateway=gateway, rate_slot=rate_slot)
        assert len(seen) == 1  # never repeated — no retry budget for this request
        assert rate_slot.pushed_back == [("nominatim", 30.0)]

    async def test_the_source_is_asked_exactly_once_even_on_a_503(self) -> None:
        gateway, seen = answering(httpx.Response(503))
        async with gateway:
            with pytest.raises(UpstreamError):
                await _geocode("Berlin", gateway=gateway)
        assert len(seen) == 1

    async def test_the_source_is_asked_exactly_once_on_a_timeout(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("too slow")

        async def sleep(seconds: float) -> None:
            return None

        gateway = Gateway(NOMINATIM_POLICY, transport=httpx.MockTransport(handler), resolve=_resolve, sleep=sleep)
        async with gateway:
            with pytest.raises(UpstreamTimeout):
                await _geocode("Berlin", gateway=gateway)

    async def test_a_403_is_an_upstream_error_not_rate_limited(self) -> None:
        gateway, seen = answering(httpx.Response(403))
        async with gateway:
            with pytest.raises(UpstreamError) as raised:
                await _geocode("Berlin", gateway=gateway)
        assert raised.value.status_code == 403
        assert len(seen) == 1

    async def test_a_result_is_cached_and_an_empty_answer_too(self) -> None:
        cache = FakeCache()
        gateway, _ = answering(httpx.Response(200, json=load("search_empty")))
        async with gateway:
            await _geocode("qwxzyvkplm", gateway=gateway, cache=cache)
        assert cache.sets == 1
