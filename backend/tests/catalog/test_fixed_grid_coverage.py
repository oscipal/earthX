"""Coverage "fixed grid" (M5-11 plan §5.4): the extent as an area and the days of the window, per month, from the entry.

The route is mounted on a bare app without a database and with a gateway that fails every request: the answer needs
neither.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from earthx.adapters import ADAPTER_SPECS
from earthx.api.coverage_route import build_router
from earthx.catalog.coverage import CoverageProviderMismatch, CoverageQuery, InvalidCoverageQuery
from earthx.catalog.fixed_grid_coverage import fixed_grid_coverage
from earthx.catalog.registry import ConfigError, CoverageProvider, DatasetRegistry, TemporalExtent
from earthx.catalog.search_filters import ValuesCondition
from tests.catalog.entries import METEOSWISS_DAILY_1KM, METEOSWISS_DAILY_PRECIP_1KM, SWISSALTI3D
from tests.earthx.adapters.conftest import answering

TEMPERATURE = METEOSWISS_DAILY_1KM
PRECIPITATION = METEOSWISS_DAILY_PRECIP_1KM


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def ask(config=TEMPERATURE, **fields) -> CoverageQuery:
    return CoverageQuery(dataset_id=config.dataset_id, level=5, **fields)


class TestCount:
    def test_without_a_window_every_day_of_the_extent(self) -> None:
        result = fixed_grid_coverage(ask(), TEMPERATURE)
        assert result.total_count == (datetime(2026, 1, 1) - datetime(1961, 1, 1)).days
        assert result.histogram[0].start == at("1961-01-01") and result.histogram[0].count == 31
        assert result.histogram[-1].start == at("2025-12-01") and result.histogram[-1].count == 31
        assert len(result.histogram) == 65 * 12
        assert result.completeness.value == "complete" and result.cells == () and not result.footprints_advised

    def test_a_window_of_one_calendar_day_meets_one_temperature_day(self) -> None:
        result = fixed_grid_coverage(ask(start=at("2024-07-01"), end=at("2024-07-01T23:59:59")), TEMPERATURE)
        assert result.total_count == 1

    def test_a_calendar_day_meets_two_precipitation_days_from_six_to_six(self) -> None:
        result = fixed_grid_coverage(ask(PRECIPITATION, start=at("2024-07-01"), end=at("2024-07-01T23:59:59")), PRECIPITATION)
        assert result.total_count == 2
        assert fixed_grid_coverage(
            ask(PRECIPITATION, start=at("2024-07-01T06:00"), end=at("2024-07-02T05:59:59")), PRECIPITATION
        ).total_count == 1

    def test_months_are_counted_where_the_days_start(self) -> None:
        result = fixed_grid_coverage(ask(start=at("2024-01-30"), end=at("2024-03-01T12:00")), TEMPERATURE)
        assert [(bucket.start.month, bucket.count) for bucket in result.histogram] == [(1, 2), (2, 29), (3, 1)]
        assert result.total_count == 32

    def test_an_open_end_stops_at_the_extent(self) -> None:
        result = fixed_grid_coverage(ask(start=at("2025-12-30")), TEMPERATURE)
        assert result.total_count == 2

    def test_a_window_outside_the_extent_is_an_empty_area(self) -> None:
        result = fixed_grid_coverage(ask(start=at("2030-01-01"), end=at("2030-12-31")), TEMPERATURE)
        assert result.total_count == 0 and result.histogram == ()
        assert result.area == {"type": "MultiPolygon", "coordinates": []} and result.extent is None
        assert fixed_grid_coverage(ask(end=at("1960-12-31T23:59:59")), TEMPERATURE).total_count == 0


class TestArea:
    def test_without_a_spatial_filter_the_extent(self) -> None:
        result = fixed_grid_coverage(ask(), TEMPERATURE)
        assert result.extent == TEMPERATURE.spatial_extent.bbox
        assert result.area is not None and result.area["type"] == "MultiPolygon" and len(result.area["coordinates"]) == 1

    def test_a_box_crops_the_extent(self) -> None:
        result = fixed_grid_coverage(ask(bbox=(7.0, 46.0, 20.0, 50.0)), TEMPERATURE)
        west, south, east, north = TEMPERATURE.spatial_extent.bbox
        assert result.extent == (7.0, 46.0, east, north)

    def test_a_box_beside_the_grid_has_no_area_and_no_days(self) -> None:
        result = fixed_grid_coverage(ask(bbox=(14.0, 47.0, 15.0, 48.0)), TEMPERATURE)
        assert result.extent is None and result.total_count == 0

    def test_a_box_over_the_antimeridian_is_two_boxes(self) -> None:
        assert fixed_grid_coverage(ask(bbox=(170.0, 40.0, 8.0, 50.0)), TEMPERATURE).extent is not None

    def test_an_area_crops_the_extent(self) -> None:
        ring = [[7.0, 46.0], [8.0, 46.0], [8.0, 47.0], [7.0, 46.0]]
        result = fixed_grid_coverage(ask(intersects={"type": "Polygon", "coordinates": [ring]}), TEMPERATURE)
        assert result.extent == (7.0, 46.0, 8.0, 47.0)

    def test_a_crossing_outline_is_refused(self) -> None:
        bowtie = {"type": "Polygon", "coordinates": [[[7, 46], [8, 47], [8, 46], [7, 47], [7, 46]]]}
        with pytest.raises(InvalidCoverageQuery):
            fixed_grid_coverage(ask(intersects=bowtie), TEMPERATURE)


class TestRefused:
    def test_another_provider(self) -> None:
        with pytest.raises(CoverageProviderMismatch):
            fixed_grid_coverage(ask(SWISSALTI3D), SWISSALTI3D)

    def test_search_filters(self) -> None:
        with pytest.raises(InvalidCoverageQuery):
            fixed_grid_coverage(ask(conditions={"x": ValuesCondition(values=("a",))}), TEMPERATURE)

    @pytest.mark.parametrize(
        "change",
        [
            {"temporal_extent": TemporalExtent(start=at("1961-01-01"), end=None)},
            {"capabilities": replace(TEMPERATURE.capabilities, time_range=False)},
            {"capabilities": replace(TEMPERATURE.capabilities, single_coverage_product=True)},
        ],
        ids=["open-end", "no-time-axis", "one-off-product"],
    )
    def test_an_entry_that_is_no_series_over_one_grid(self, change) -> None:
        with pytest.raises(ConfigError):
            replace(TEMPERATURE, **change)

    def test_a_federated_entry(self) -> None:
        with pytest.raises(ConfigError, match="federated"):
            replace(TEMPERATURE, source=replace(TEMPERATURE.source, item_holding=type(TEMPERATURE.source.item_holding).FEDERATED))


class TestRoute:
    def client(self) -> tuple[TestClient, list[httpx.Request]]:
        gateway, seen = answering(httpx.Response(500))
        app = FastAPI()
        app.include_router(build_router(DatasetRegistry((TEMPERATURE, PRECIPITATION)), ADAPTER_SPECS))
        app.state.earthx_gateway = gateway
        app.state.earthx_cache_pool = None
        return TestClient(app), seen

    def test_answered_without_a_database_or_a_request(self) -> None:
        client, seen = self.client()
        response = client.get(
            f"/coverage/{TEMPERATURE.dataset_id}", params={"zoom": 5, "datetime": "2024-07-01T00:00:00Z/2024-07-31T23:59:59Z"}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total_count"] == 31 and body["histogram"] == [{"t": "2024-07-01T00:00:00Z", "n": 31}]
        assert body["area"]["type"] == "MultiPolygon" and body["extent"] == list(TEMPERATURE.spatial_extent.bbox)
        assert body["footprints_advised"] is False and body["cells"] == []
        assert seen == []

    def test_an_area_is_posted_and_cropped(self) -> None:
        client, _ = self.client()
        ring = [[7.0, 46.0], [8.0, 46.0], [8.0, 47.0], [7.0, 47.0], [7.0, 46.0]]
        response = client.post(
            f"/coverage/{PRECIPITATION.dataset_id}", json={"zoom": 7, "intersects": {"type": "Polygon", "coordinates": [ring]}}
        )
        assert response.status_code == 200, response.text
        assert response.json()["extent"] == [7.0, 46.0, 8.0, 47.0]

    def test_a_crossing_outline_is_400(self) -> None:
        client, _ = self.client()
        bowtie = {"type": "Polygon", "coordinates": [[[7, 46], [8, 47], [8, 46], [7, 47], [7, 46]]]}
        response = client.post(f"/coverage/{TEMPERATURE.dataset_id}", json={"zoom": 5, "intersects": bowtie})
        assert response.status_code == 400

    def test_a_search_filter_is_400(self) -> None:
        client, _ = self.client()
        response = client.get(f"/coverage/{TEMPERATURE.dataset_id}", params={"zoom": 5, "query": '{"x": {"eq": 1}}'})
        assert response.status_code == 400

    def test_the_provider_is_one_the_entries_may_name(self) -> None:
        assert TEMPERATURE.coverage.provider is CoverageProvider.FIXED_GRID
