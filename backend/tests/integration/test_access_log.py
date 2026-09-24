"""M3-16: the running `api` app never puts a query string in its access log.

`plans/m3-02-konformitaetsbericht.md` K-01/K-02: `GET /stac/search?...bbox=...`
and `GET /coverage/{id}?...bbox=...` both go through `earthx.api.main.app`, the
same app `RequestIdMiddleware` is now wired into (`api/main.py`). This tests the
*app*, not the middleware in isolation — `backend/tests/test_logging.py` already
covers the middleware and `summarize_geometry` on their own.

Real Postgres/pgstac, mocked Earth Search transport — the same split
`test_api_federating.py` uses one file over.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

from earthx.api.main import app
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.load import main as load_catalog
from earthx.gateway import Gateway, Policy
from tests.earthx.adapters.conftest import load as load_earth_search_fixture

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "earth_search"
HOST = "earth-search.aws.element84.com"
POLICY = Policy(allowed_hosts=frozenset({HOST}))
DATASET_ID = SENTINEL_2_L2A.dataset_id

# A distinctive, high-precision pair — the same shape `test_logging.py` uses. If it
# (or its repr) turns up anywhere in the rendered access-log line, the redaction failed.
_EXACT_LON = "13.377476"
_EXACT_LAT = "52.516275"
BBOX = f"{_EXACT_LON},{_EXACT_LAT},14.0,53.0"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def require_catalog_loaded(require_postgres_env: None) -> None:
    code = load_catalog()
    assert code == 0


@asynccontextmanager
async def _client(handler: Callable[[httpx.Request], httpx.Response]) -> AsyncIterator[httpx.AsyncClient]:
    async def sleep(seconds: float) -> None:
        return None

    async with app.router.lifespan_context(app):
        app.state.earthx_gateway = Gateway(
            POLICY, transport=httpx.MockTransport(handler), resolve=lambda host, port: ("93.184.216.34",), sleep=sleep
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


def _assert_clean_access_log(lines: list[str], *, method: str) -> None:
    """No coordinate, no query string at all, and the fields K-01/K-02 ask for."""
    assert lines, "expected RequestIdMiddleware to write at least one access-log line"
    for line in lines:
        assert _EXACT_LON not in line
        assert _EXACT_LAT not in line
        assert "?" not in line  # the whole query string is gone, not just bbox/intersects
        payload = json.loads(line)
        assert payload["request_id"]
        assert payload["method"] == method
        assert isinstance(payload["status"], int)
        assert isinstance(payload["duration_ms"], int | float)
        assert "bbox" not in payload["path"]


class TestSearchAccessLog:
    async def test_a_bbox_search_leaves_no_coordinate_or_query_string_in_the_access_log(
        self, require_catalog_loaded: None, access_log_lines: list[str]
    ) -> None:
        handler = lambda request: httpx.Response(200, json=load_fixture("search_empty"))  # noqa: E731
        async with _client(handler) as client:
            response = await client.get("/stac/search", params={"collections": DATASET_ID, "bbox": BBOX})
        assert response.status_code == 200
        _assert_clean_access_log(access_log_lines, method="GET")


class TestCoverageAccessLog:
    async def test_a_bbox_coverage_query_leaves_no_coordinate_or_query_string_in_the_access_log(
        self, require_catalog_loaded: None, access_log_lines: list[str]
    ) -> None:
        handler = lambda request: httpx.Response(200, json=load_earth_search_fixture("aggregate_complete"))  # noqa: E731
        async with _client(handler) as client:
            response = await client.get(f"/coverage/{DATASET_ID}", params={"zoom": 5, "bbox": BBOX})
        assert response.status_code == 200
        _assert_clean_access_log(access_log_lines, method="GET")
