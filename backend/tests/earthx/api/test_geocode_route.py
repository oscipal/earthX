"""``POST /geocode`` (M3-07a): the route's own job — wiring, error mapping, and
never a search text or a result name in a log line. What `geocode()` itself does
with a hit (outline simplification, the cache, the rate slot) is already covered by
``tests/earthx/adapters/test_nominatim.py``; the fakes here stand in for Postgres
so this file never needs a real database.
"""

from __future__ import annotations

import logging

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import earthx.api.geocode_route as geocode_route_module
from earthx.api.geocode_route import router
from tests.earthx.adapters.conftest import NOMINATIM_HOST, NOMINATIM_POLICY, answering, gateway_for, load_nominatim

BASE_URL = f"https://{NOMINATIM_HOST}"
USER_AGENT = "EarthX-test/0.0 (+https://example.invalid)"


class FakeCache:
    def __init__(self) -> None:
        self.store: dict = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value, *, ttl_s: float) -> None:
        self.store[key] = value


class FakeRateSlot:
    def __init__(self, *, delay_s: float = 0.0, raises: Exception | None = None) -> None:
        self.delay_s = delay_s
        self.raises = raises

    async def reserve(self, name: str) -> float:
        if self.raises is not None:
            raise self.raises
        return self.delay_s

    async def push_back(self, name: str, *, seconds: float) -> None:
        return None


class _FakeConnectionCM:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


class FakePool:
    def connection(self):
        return _FakeConnectionCM()


def build_client(
    *,
    gateway=None,
    pool: FakePool | None = ...,
    cache: FakeCache | None = None,
    rate_slot: FakeRateSlot | None = None,
    geocoder_url: str | None = BASE_URL,
    user_agent: str = USER_AGENT,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    pool = FakePool() if pool is ... else pool
    cache = cache if cache is not None else FakeCache()
    rate_slot = rate_slot if rate_slot is not None else FakeRateSlot()
    monkeypatch.setattr(geocode_route_module, "PostgresGeocodeCache", lambda conn: cache)
    monkeypatch.setattr(geocode_route_module, "PostgresRateSlot", lambda conn: rate_slot)

    app = FastAPI()
    app.include_router(router)
    app.state.earthx_geocoder_gateway = gateway
    app.state.earthx_cache_pool = pool
    if geocoder_url is not None:
        app.state.earthx_geocoder_url = geocoder_url
        app.state.earthx_geocoder_user_agent = user_agent
    return TestClient(app)


def gateway_answering(*responses: httpx.Response):
    return answering(*responses, policy=NOMINATIM_POLICY)


def test_a_hit_comes_back_with_attribution(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _ = gateway_answering(httpx.Response(200, json=load_nominatim("search_hit_with_outline")))
    client = build_client(gateway=gateway, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": "Musterstadt"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["attribution"] == "© OpenStreetMap contributors"


def test_no_gateway_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    client = build_client(gateway=None, geocoder_url=None, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": "Berlin"})
    assert response.status_code == 503


def test_no_cache_pool_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _ = gateway_answering(httpx.Response(200, json=load_nominatim("search_empty")))
    client = build_client(gateway=gateway, pool=None, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": "Berlin"})
    assert response.status_code == 503


def test_empty_text_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, seen = gateway_answering(httpx.Response(200, json=load_nominatim("search_empty")))
    client = build_client(gateway=gateway, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": "   "})
    assert response.status_code == 422
    assert seen == []


def test_201_characters_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _ = gateway_answering(httpx.Response(200, json=load_nominatim("search_empty")))
    client = build_client(gateway=gateway, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": "a" * 201})
    assert response.status_code == 422


def test_a_control_character_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _ = gateway_answering(httpx.Response(200, json=load_nominatim("search_empty")))
    client = build_client(gateway=gateway, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": "Berlin\x07"})
    assert response.status_code == 422


def test_missing_field_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _ = gateway_answering(httpx.Response(200, json=load_nominatim("search_empty")))
    client = build_client(gateway=gateway, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={})
    assert response.status_code == 422


def test_wrong_type_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _ = gateway_answering(httpx.Response(200, json=load_nominatim("search_empty")))
    client = build_client(gateway=gateway, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": 123})
    assert response.status_code == 422


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _ = gateway_answering(httpx.Response(200, json=load_nominatim("search_empty")))
    client = build_client(gateway=gateway, monkeypatch=monkeypatch)
    response = client.get("/geocode", params={"q": "Berlin"})
    assert response.status_code == 405


def test_a_slot_past_the_wait_budget_is_503_with_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, seen = gateway_answering(httpx.Response(200, json=load_nominatim("search_empty")))
    client = build_client(gateway=gateway, rate_slot=FakeRateSlot(delay_s=5.0), monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": "Berlin"})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert seen == []


def test_a_429_is_503_with_a_fixed_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, seen = gateway_answering(httpx.Response(429))
    client = build_client(gateway=gateway, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": "Berlin"})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"
    assert len(seen) == 1


def test_a_503_from_the_source_is_502(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _ = gateway_answering(httpx.Response(503))
    client = build_client(gateway=gateway, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": "Berlin"})
    assert response.status_code == 502


def test_a_403_from_the_source_is_502(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _ = gateway_answering(httpx.Response(403))
    client = build_client(gateway=gateway, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": "Berlin"})
    assert response.status_code == 502


def test_a_timeout_is_504(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow")

    gateway = gateway_for(handler, policy=NOMINATIM_POLICY)
    client = build_client(gateway=gateway, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": "Berlin"})
    assert response.status_code == 504


def test_a_malformed_answer_is_502(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, _ = gateway_answering(httpx.Response(200, json=load_nominatim("search_malformed_not_list")))
    client = build_client(gateway=gateway, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": "Berlin"})
    assert response.status_code == 502


def test_the_rate_slot_being_unreachable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, seen = gateway_answering(httpx.Response(200, json=load_nominatim("search_empty")))
    broken = FakeRateSlot(raises=psycopg.OperationalError("connection refused"))
    client = build_client(gateway=gateway, rate_slot=broken, monkeypatch=monkeypatch)
    response = client.post("/geocode", json={"q": "Berlin"})
    assert response.status_code == 503
    assert seen == []


def test_no_search_text_or_result_name_reaches_the_log(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    secret_query = "Geheimburg-Gasse-12345"
    gateway, _ = gateway_answering(httpx.Response(200, json=load_nominatim("search_hit_with_outline")))
    client = build_client(gateway=gateway, monkeypatch=monkeypatch)
    caplog.set_level(logging.DEBUG)
    # M3-16 (earthx/logging.py): httpx's own "HTTP Request: ..." line carries the
    # full URL, query string included — `configure_logging()` raises it to WARNING
    # in every real process; this test does the same two lines without touching
    # the root logger's handlers, which `caplog` needs for itself.
    caplog.set_level(logging.WARNING, logger="httpx")
    caplog.set_level(logging.WARNING, logger="httpx2")
    response = client.post("/geocode", json={"q": secret_query})
    assert response.status_code == 200
    for record in caplog.records:
        assert secret_query not in record.getMessage()
        assert secret_query not in str(record.__dict__)


def test_a_cache_hit_answers_without_a_new_gateway_request(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, seen = gateway_answering(httpx.Response(200, json=load_nominatim("search_hit_with_outline")))
    cache = FakeCache()
    client = build_client(gateway=gateway, cache=cache, monkeypatch=monkeypatch)
    client.post("/geocode", json={"q": "Musterstadt"})
    client.post("/geocode", json={"q": "Musterstadt"})
    assert len(seen) == 1
