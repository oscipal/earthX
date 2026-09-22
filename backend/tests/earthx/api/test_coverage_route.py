"""``GET /coverage/{dataset_id}``: the acceptance criteria of M2-05b, one test each.

Nothing here reaches the network: the gateway's transport and resolver are under
test control, exactly as in ``tests/earthx/adapters/test_earth_search_coverage.py``,
whose fixtures this file reuses rather than inventing new ones. The app is built
without a database (``earthx_cache_pool = None``) — the point of these tests is the
route and its error mapping, not the cache, which M2-05a already covers.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from earthx.api.coverage_route import build_router
from earthx.catalog.datasets import SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.registry import CoverageProvider, DatasetRegistry
from earthx.gateway import Policy
from earthx.gateway.client import Gateway
from tests.earthx.adapters.conftest import answering, gateway_for, load

DATASET = SENTINEL_2_L2A.dataset_id
ZARR3_DATASET = SENTINEL_2_L2A_ZARR3.dataset_id
ZARR3_REGISTRY = DatasetRegistry((SENTINEL_2_L2A_ZARR3,))
ZARR3_HOST = "stac.core.eopf.eodc.eu"
ZARR3_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "eopf_stac"


def ok(name: str) -> httpx.Response:
    return httpx.Response(200, json=load(name))


def ok_zarr3(name: str) -> httpx.Response:
    return httpx.Response(200, json=json.loads((ZARR3_FIXTURES / f"{name}.json").read_text(encoding="utf-8")))


def _public(host: str, port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def zarr3_gateway_for(handler: Callable[[httpx.Request], httpx.Response]) -> Gateway:
    """A gateway allowed against the EOPF STAC API's own host — `conftest`'s
    `gateway_for` is scoped to Earth Search's (M2-09b-3 is the second source this
    route talks to)."""

    async def sleep(seconds: float) -> None:
        return None

    policy = Policy(allowed_hosts=frozenset({ZARR3_HOST}))
    return Gateway(policy, transport=httpx.MockTransport(handler), resolve=_public, sleep=sleep)


def zarr3_answering(*responses: httpx.Response) -> tuple[Gateway, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return zarr3_gateway_for(handler), seen


def client_for(gateway, *, registry: DatasetRegistry | None = None) -> TestClient:
    """The route alone, mounted on a bare app — no lifespan, no database.

    ``TestClient`` is not used as a context manager, the same reasoning as
    ``tests/earthx/api/test_tiler.py``: there is no lifespan here to run.
    """
    app = FastAPI()
    app.include_router(build_router(registry=registry or DatasetRegistry((SENTINEL_2_L2A,))))
    app.state.earthx_gateway = gateway
    app.state.earthx_cache_pool = None
    return TestClient(app)


def get(client: TestClient, dataset_id: str = DATASET, **params: Any) -> httpx.Response:
    params.setdefault("zoom", 5)
    return client.get(f"/coverage/{dataset_id}", params=params)


class TestUnknownDataset:
    def test_answers_404(self) -> None:
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(client_for(gateway), dataset_id="does-not-exist")
        assert response.status_code == 404
        assert not seen


class TestHappyPath:
    def test_the_answer_is_the_compact_wire_shape(self) -> None:
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(client_for(gateway), bbox="5,45,15,55", datetime="2024-01-01T00:00:00Z/2024-12-31T00:00:00Z")

        assert response.status_code == 200
        body = response.json()
        assert body["dataset_id"] == DATASET
        assert body["grid"] == "geotile"
        assert body["counting"] == "centroid"
        assert body["cells"] == [{"k": "8/133/84", "n": 25}, {"k": "8/137/84", "n": 17}]
        assert body["counted"] == 42
        assert body["total_count"] == 42
        assert body["completeness"] == "complete"
        assert body["histogram_interval"] == "month"
        assert body["histogram"][0] == {"t": "2024-01-01T00:00:00Z", "n": 20}
        assert body["extent"] is None
        assert body["from_cache"] is False
        assert len(seen) == 1

    def test_a_zoom_finer_than_the_dataset_cap_is_clamped_not_refused(self) -> None:
        """adr/0004 §5: both caps clamp, they do not reject (M2-05a already proves the
        function; this proves the route actually calls it before building the query).
        """
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(client_for(gateway), zoom=29, bbox="5,45,15,55")
        assert response.status_code == 200
        assert response.json()["level"] == SENTINEL_2_L2A.coverage.max_geotile_level


BROKEN_RING = json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 0]]]})
OFF_GLOBE_RING = json.dumps({"type": "Polygon", "coordinates": [[[0.0, 0.0], [999.0, 0.0], [999.0, 1.0], [0.0, 0.0]]]})


class TestBadInput:
    """Purpose-defeating input, refused with a 400 before anything is sent upstream."""

    @pytest.mark.parametrize(
        "params",
        [
            {"bbox": "5,45,15,55", "intersects": BROKEN_RING},  # two questions, adr/0004 §5
            {"bbox": "5,45,15"},  # wrong number of values
            {"bbox": "5,-95,15,55"},  # latitude outside ±90
            {"intersects": "not json at all"},
            {"intersects": "[1, 2, 3]"},  # not a GeoJSON object
            {"intersects": BROKEN_RING},  # fewer than four positions
            {"intersects": OFF_GLOBE_RING},  # adr/0005 §3.5's lesson, applied to intersects
            {"datetime": "not-a-date"},
            {"max_cloud_cover": 150},  # a percentage, not a fraction
        ],
    )
    def test_answers_400(self, params: dict[str, object]) -> None:
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(client_for(gateway), **params)
        assert response.status_code == 400
        assert not seen

    def test_no_out_of_bounds_coordinate_reaches_the_response(self) -> None:
        response = get(client_for(gateway_for(lambda r: ok("aggregate_complete"))), intersects=OFF_GLOBE_RING)
        assert "999" not in response.text


class TestUpstreamErrors:
    def test_an_upstream_4xx_is_502(self) -> None:
        gateway = gateway_for(lambda request: httpx.Response(400, text="Invalid GeoJSON geometry"))
        response = get(client_for(gateway))
        assert response.status_code == 502
        assert "Invalid GeoJSON" not in response.text

    def test_an_upstream_5xx_is_502(self) -> None:
        gateway = gateway_for(lambda request: httpx.Response(500, text="internal error"))
        response = get(client_for(gateway))
        assert response.status_code == 502

    def test_an_upstream_timeout_is_504(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("no answer", request=request)

        response = get(client_for(gateway_for(handler)))
        assert response.status_code == 504

    def test_a_malformed_upstream_answer_is_502(self) -> None:
        gateway = gateway_for(lambda request: httpx.Response(200, json={"not": "an aggregation"}))
        response = get(client_for(gateway))
        assert response.status_code == 502


class TestUnavailableProvider:
    def test_a_dataset_without_a_way_to_answer_is_501(self) -> None:
        """local-sql is the one way of adr/0004 §5 with no caller yet (plan §8):
        no dataset in M2 has its own items in pgstac."""
        config = replace(SENTINEL_2_L2A, coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL))
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(client_for(gateway, registry=DatasetRegistry((config,))))
        assert response.status_code == 501
        assert not seen


class TestSampleProvider:
    """M2-09b-3: the second way of adr/0004 §5 that this route now dispatches to,
    over ``sentinel-2-l2a-zarr3``'s real registry entry and the EOPF STAC API."""

    def test_the_answer_is_a_declared_sample(self) -> None:
        gateway, seen = zarr3_answering(ok_zarr3("search_page_1"), ok_zarr3("search_empty"))
        # A bbox both to give a spatial filter (so the dataset's own z8 cap applies
        # rather than the coarser world one) and to cover the fixture's two items,
        # which otherwise land in the same z5 cell and defeat this test's point.
        response = get(
            client_for(gateway, registry=ZARR3_REGISTRY), dataset_id=ZARR3_DATASET, zoom=8, bbox="-30,71,-27,72"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["dataset_id"] == ZARR3_DATASET
        assert body["level"] == 8
        assert body["completeness"] == "sample"
        assert body["total_count"] is None
        assert body["footprints_advised"] is False
        assert len(body["cells"]) == 2
        assert len(seen) == 2

    def test_an_unreadable_search_answer_is_502_not_a_crash(self) -> None:
        gateway = zarr3_gateway_for(lambda request: httpx.Response(200, json={"not": "a feature collection"}))
        response = get(client_for(gateway, registry=ZARR3_REGISTRY), dataset_id=ZARR3_DATASET)
        assert response.status_code == 502


class TestSingleCoverageProduct:
    """adr/0004 §5, "Einmal-Produkte": the extent, checked before any provider runs."""

    def _config(self) -> Any:
        return replace(
            SENTINEL_2_L2A,
            capabilities=replace(SENTINEL_2_L2A.capabilities, single_coverage_product=True),
            coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.SAMPLE),
        )

    def test_the_extent_answers_without_asking_upstream(self) -> None:
        config = self._config()
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(client_for(gateway, registry=DatasetRegistry((config,))), dataset_id=config.dataset_id)

        assert response.status_code == 200
        body = response.json()
        assert body["extent"] == list(config.spatial_extent.bbox)
        assert body["completeness"] == "complete"
        assert body["cells"] == []
        assert body["histogram"] == []
        assert not seen


class TestNoAoiReachesAnswerOrLog:
    """plans/m2-05-coverage.md §3.5, §6.6: the source's body stays out of both."""

    def test_no_coordinate_from_the_request_appears_in_the_response_or_the_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING, logger="earthx.api.coverage")
        gateway = gateway_for(
            lambda request: httpx.Response(
                500, text="invalid number of points in LinearRing at (5.123, 45.456) - must be >= [4]"
            )
        )
        area = {
            "type": "Polygon",
            "coordinates": [[[5.123, 45.456], [6.0, 45.0], [6.0, 46.0], [5.123, 45.456]]],
        }
        response = get(client_for(gateway), intersects=json.dumps(area))

        assert response.status_code == 502
        for needle in ("5.123", "45.456"):
            assert needle not in response.text
            assert needle not in caplog.text


class TestSchema:
    def test_no_endpoint_declares_a_free_url_parameter(self) -> None:
        gateway, _ = answering(ok("aggregate_complete"))
        client = client_for(gateway)
        schema = client.app.openapi()
        parameters = {
            (parameter["in"], parameter["name"])
            for operations in schema["paths"].values()
            for operation in operations.values()
            if isinstance(operation, dict)
            for parameter in operation.get("parameters", [])
        }
        assert ("query", "url") not in parameters
