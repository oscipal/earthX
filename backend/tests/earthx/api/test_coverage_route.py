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
from dataclasses import replace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from earthx.adapters import ADAPTER_SPECS
from earthx.api.coverage_route import build_router
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import CoverageProvider, DatasetRegistry, ItemHolding
from tests.earthx.adapters.conftest import answering, gateway_for, load

DATASET = SENTINEL_2_L2A.dataset_id


def ok(name: str) -> httpx.Response:
    return httpx.Response(200, json=load(name))


def client_for(gateway, *, registry: DatasetRegistry | None = None) -> TestClient:
    """The route alone, mounted on a bare app — no lifespan, no database.

    ``TestClient`` is not used as a context manager, the same reasoning as
    ``tests/earthx/api/test_tiler.py``: there is no lifespan here to run.
    """
    app = FastAPI()
    app.include_router(build_router(registry or DatasetRegistry((SENTINEL_2_L2A,)), ADAPTER_SPECS))
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
        config = replace(
            SENTINEL_2_L2A,
            coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
            # local-sql is only a valid combination on a materialized entry
            # (M3-11a K-05) — this route's 501 is about no caller existing yet,
            # not about the combination itself being invalid.
            source=replace(SENTINEL_2_L2A.source, item_holding=ItemHolding.MATERIALIZED),
        )
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(client_for(gateway, registry=DatasetRegistry((config,))))
        assert response.status_code == 501
        assert not seen


class TestAreaPathWithoutADatabase:
    """M3-11c: `local-sql` + `single_coverage_product` is the area way, answered
    from a materialized dataset's own items in pgstac — the one way this route
    cannot answer without the process's real database pool.
    """

    def _config(self) -> Any:
        return replace(
            SENTINEL_2_L2A,
            capabilities=replace(SENTINEL_2_L2A.capabilities, single_coverage_product=True),
            coverage=replace(SENTINEL_2_L2A.coverage, provider=CoverageProvider.LOCAL_SQL),
            source=replace(SENTINEL_2_L2A.source, item_holding=ItemHolding.MATERIALIZED),
        )

    def test_without_a_pool_the_answer_is_503_not_the_global_extent(self) -> None:
        config = self._config()
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(client_for(gateway, registry=DatasetRegistry((config,))), dataset_id=config.dataset_id)

        assert response.status_code == 503
        assert not seen

    def test_a_broken_intersects_polygon_is_400_before_any_database_read(self) -> None:
        """`local_coverage._check_intersects_is_valid`'s own, stricter check: a
        self-intersecting polygon is refused before this ever asks for a pool —
        the ``503`` above must never mask a `400` the request itself deserves."""
        config = self._config()
        area = json.dumps(
            {"type": "Polygon", "coordinates": [[[0.0, 0.0], [2.0, 2.0], [2.0, 0.0], [0.0, 2.0], [0.0, 0.0]]]}
        )
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(
            client_for(gateway, registry=DatasetRegistry((config,))), dataset_id=config.dataset_id, intersects=area
        )

        assert response.status_code == 400
        assert not seen


class TestIgnoredFilters:
    """Otto, 26.09.2026 (M3-11c): a filter a dataset structurally cannot honour is
    dropped and named, not silently applied — for any provider, not only the area
    way (`ignored_filters`).
    """

    def test_a_dataset_without_a_time_axis_ignores_the_datetime_filter(self) -> None:
        config = replace(SENTINEL_2_L2A, capabilities=replace(SENTINEL_2_L2A.capabilities, time_range=False))
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(
            client_for(gateway, registry=DatasetRegistry((config,))),
            dataset_id=config.dataset_id,
            datetime="2024-01-01T00:00:00Z/2024-12-31T00:00:00Z",
        )

        assert response.status_code == 200
        assert response.json()["ignored_filters"] == ["datetime"]
        assert len(seen) == 1

    def test_a_dataset_with_a_time_axis_keeps_the_datetime_filter(self) -> None:
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(client_for(gateway), datetime="2024-01-01T00:00:00Z/2024-12-31T00:00:00Z")

        assert response.status_code == 200
        assert response.json()["ignored_filters"] == []


class TestNoAoiReachesAnswerOrLog:
    """plans/m2/m2-05-coverage.md §3.5, §6.6: the source's body stays out of both."""

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
