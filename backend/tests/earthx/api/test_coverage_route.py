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
            {"intersects": '{"type": "Polygon", "coordinates": [[[' + "1" * 5000 + ", 0]]]}"},  # unreadable number
            {"intersects": "[1, 2, 3]"},  # not a GeoJSON object
            {"intersects": BROKEN_RING},  # fewer than four positions
            {"intersects": OFF_GLOBE_RING},  # adr/0005 §3.5's lesson, applied to intersects
            {"datetime": "not-a-date"},
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


def query_of(**filters: Any) -> str:
    return json.dumps(filters)


class TestSearchFilters:
    """DS-02b: ``query`` carries the dataset's search filters, read by the code of ``POST /stac/search``."""

    def test_the_conditions_reach_the_source_in_the_query_extension(self) -> None:
        gateway, seen = answering(ok("aggregate_complete"))
        query = query_of(
            **{
                "eo:cloud_cover": {"gte": 5, "lte": 20},
                "s2:nodata_pixel_percentage": {"lte": 5},
                "platform": {"in": ["sentinel-2b", "sentinel-2a"]},
            }
        )

        response = get(client_for(gateway), bbox="5,45,15,55", query=query)

        assert response.status_code == 200
        assert len(seen) == 1
        assert json.loads(seen[0].url.params["query"]) == {
            "eo:cloud_cover": {"gte": 5.0, "lte": 20.0},
            "s2:nodata_pixel_percentage": {"lte": 5.0},
            "platform": {"in": ["sentinel-2a", "sentinel-2b"]},
        }
        assert response.json()["ignored_filters"] == []

    def test_a_bound_at_the_edge_of_the_range_is_allowed(self) -> None:
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(client_for(gateway), query=query_of(**{"eo:cloud_cover": {"gte": 0, "lte": 100}}))
        assert response.status_code == 200

    def test_no_query_and_an_empty_one_send_no_filter(self) -> None:
        gateway, seen = answering(ok("aggregate_complete"), ok("aggregate_complete"))
        client = client_for(gateway)

        assert get(client).status_code == 200
        assert get(client, query="{}").status_code == 200
        assert all("query" not in request.url.params for request in seen)

    @pytest.mark.parametrize(
        "query",
        [
            query_of(**{"foo:bar": {"gte": 1}}),  # a property the dataset does not offer: the source would answer 0
            query_of(**{"sat:orbit_state": {"in": ["ascending", "descending"]}}),  # DS-04, not Sentinel-2
            query_of(**{"earthx:aoi_cloud_cover": {"lte": 10}}),  # reserved for DS-03
            query_of(datetime={"gte": 1}),  # has its own parameter
            query_of(**{"eo:cloud_cover": {"lt": 20}}),  # an operator outside gte/lte
            query_of(**{"eo:cloud_cover": {"between": [1, 2]}}),  # the source would pass it over
            query_of(**{"eo:cloud_cover": {"in": [10]}}),  # an operator of the other kind
            query_of(**{"eo:cloud_cover": {"lte": "abc"}}),  # the source answers 400 with its internals
            query_of(**{"eo:cloud_cover": {"lte": True}}),
            query_of(**{"eo:cloud_cover": {"lte": 101}}),  # outside the range the filter offers
            query_of(**{"eo:cloud_cover": {"gte": -1}}),
            query_of(**{"eo:cloud_cover": {"gte": 30, "lte": 20}}),
            query_of(**{"eo:cloud_cover": {}}),
            query_of(**{"eo:cloud_cover": 20}),
            query_of(platform={"in": []}),
            query_of(platform={"in": ["sentinel-2z"]}),  # not a value it offers
            query_of(platform={"in": ["sentinel-2a", "sentinel-2a"]}),
            query_of(platform={"in": "sentinel-2a"}),
            query_of(platform={"gte": 1}),
            "[1, 2]",  # not an object
            "20",
            "not json at all",
            "[" * 20000,  # deep enough to exhaust the parser's stack
            '{"eo:cloud_cover": {"lte": ' + "1" * 5000 + "}}",  # a number the parser refuses to read
        ],
    )
    def test_a_filter_the_dataset_does_not_have_is_400_before_anything_is_sent(self, query: str) -> None:
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(client_for(gateway), query=query)
        assert response.status_code == 400
        assert not seen

    def test_a_400_names_no_value_of_the_request(self) -> None:
        gateway, _ = answering(ok("aggregate_complete"))
        client = client_for(gateway)
        bodies = [
            get(client, query=query_of(**{"eo:cloud_cover": {"lte": 98765}})).text,
            get(client, query=query_of(platform={"in": ["secret-satellite"]})).text,
            get(client, query=query_of(**{"Home Address 12": {"gte": 12345}})).text,  # no property, so unnamed
        ]
        for needle, body in zip(("98765", "secret-satellite", "Home Address"), bodies, strict=True):
            assert needle not in body

    def test_a_dataset_without_filters_refuses_any(self) -> None:
        config = replace(SENTINEL_2_L2A, search_filters=())
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(
            client_for(gateway, registry=DatasetRegistry((config,))),
            dataset_id=config.dataset_id,
            query=query_of(**{"eo:cloud_cover": {"lte": 20}}),
        )
        assert response.status_code == 400
        assert not seen

    def test_a_source_error_reaches_neither_the_answer_nor_the_log(self, caplog: pytest.LogCaptureFixture) -> None:
        """C (Otto, 28.10.2026): status and our own text only, even where the source quotes the filter back."""
        # Our own loggers only: the production configuration silences the libraries that log whole URLs
        # (`logging._URL_LOGGING_LIBRARIES`), a bare caplog does not.
        caplog.set_level(logging.DEBUG, logger="earthx")
        gateway = gateway_for(
            lambda request: httpx.Response(
                400, json={"error": "parse_exception: failed to parse [eo:cloud_cover] value [17.25] in shard 3"}
            )
        )

        response = get(client_for(gateway), query=query_of(**{"eo:cloud_cover": {"lte": 17.25}}))

        assert response.status_code == 502
        for needle in ("parse_exception", "shard", "17.25"):
            assert needle not in response.text
            assert needle not in caplog.text

    def test_the_log_names_the_filters_but_no_value(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger="earthx.api.coverage")
        gateway, _ = answering(ok("aggregate_complete"))

        get(
            client_for(gateway),
            bbox="5.123,45.456,15,55",
            query=query_of(**{"eo:cloud_cover": {"lte": 17.25}, "platform": {"in": ["sentinel-2c"]}}),
        )

        record = next(record for record in caplog.records if record.name == "earthx.api.coverage")
        assert record.filters == ["eo:cloud_cover", "platform"]
        for needle in ("17.25", "sentinel-2c", "5.123", "45.456"):
            assert needle not in caplog.text
            assert needle not in str(record.__dict__)

    def test_the_parameter_is_declared_in_the_schema_as_an_optional_string(self) -> None:
        gateway, _ = answering(ok("aggregate_complete"))
        schema = client_for(gateway).app.openapi()
        parameters = {p["name"]: p for p in schema["paths"]["/coverage/{dataset_id}"]["get"]["parameters"]}
        assert "max_cloud_cover" not in parameters
        assert parameters["query"]["required"] is False
        assert parameters["query"]["schema"]["anyOf"][0] == {"type": "string"}


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
            search_filters=(),
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
            search_filters=(),
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


    def test_a_search_filter_on_the_area_way_is_400_before_the_missing_pool_is_503(self) -> None:
        config = self._config()
        gateway, seen = answering(ok("aggregate_complete"))
        response = get(
            client_for(gateway, registry=DatasetRegistry((config,))),
            dataset_id=config.dataset_id,
            query=query_of(**{"eo:cloud_cover": {"lte": 20}}),
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
