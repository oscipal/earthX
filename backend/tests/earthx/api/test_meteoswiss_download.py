"""The download of a MeteoSwiss day with four quantities, over the real routes of the tiler (M5-11, Otto's browser check).

A synthetic archive with an annual file per quantity, materialized for real; the item goes to ``POST /bands`` and
``POST /download`` of the app. The quantities are read through their chunk references, each into a file of its own.
"""

from __future__ import annotations

import asyncio
import io
import zipfile
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from earthx.api.tiler import build_app
from earthx.discovery import meteoswiss_grid
from tests.catalog.entries import METEOSWISS_DAILY_1KM, registry_of
from tests.catalog.synthetic_chain import aoi_wgs84
from tests.earthx.discovery import mini_archive
from tests.earthx.processing import sources
from tests.earthx.readers import mini_netcdf

QUANTITIES = ["TabsD", "TminD", "TmaxD", "SrelD"]


@pytest.fixture
def day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, dict[str, Any]]]:
    sources.serve({}, monkeypatch)
    body = mini_archive.annual_file(tmp_path, 2024, days=[0])
    archive = mini_archive.Archive({mini_archive.name(q, "ch01r", 2024): body for q in QUANTITIES})
    mini_netcdf.Source(body).serve_readers(monkeypatch)
    config = mini_archive.entry(METEOSWISS_DAILY_1KM)

    async def materialize() -> dict[str, Any]:
        async with archive.gateway() as gateway:
            outcome = await meteoswiss_grid.materialize_items(
                config, gateway=gateway, known_version=None, today=mini_archive.TODAY
            )
        return outcome.items[0]

    item = asyncio.run(materialize())

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return item

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = item_source
        yield

    app = build_app(registry_of(config), lifespan=lifespan)
    app.state.earthx_resolver = mini_netcdf.from_memory
    with TestClient(app) as client:
        yield client, item


def download(client: TestClient, item: dict[str, Any], assets: list[str], **layout: Any) -> Any:
    body = {"groups": [[item["id"]]], "assets": assets, "aoi": aoi_wgs84(tuple(item["bbox"])), **layout}
    return client.post(f"/collections/{METEOSWISS_DAILY_1KM.dataset_id}/download", json=body)


def test_the_dialog_is_offered_the_four_quantities_each_in_a_file_of_its_own(day) -> None:
    client, item = day
    answer = client.post(f"/collections/{METEOSWISS_DAILY_1KM.dataset_id}/bands", json={"items": [item["id"]]})
    assert answer.status_code == 200, answer.text
    rows = {row["asset"]: row for row in answer.json()["bands"]}
    assert sorted(rows) == sorted(QUANTITIES)
    assert all(row["preselected"] and row["stackable"] is False for row in rows.values())
    assert (rows["TminD"]["unit"], rows["SrelD"]["unit"], rows["TabsD"]["resolution_m"]) == ("°C", "%", 1000.0)


def test_the_four_quantities_land_in_four_files(day) -> None:
    client, item = day
    response = download(client, item, QUANTITIES, form="per_band")
    assert response.status_code == 200, response.text
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert [name for name in names if name.endswith("_1000m.tif")] == [f"exports/{q}_1000m.tif" for q in QUANTITIES]
    assert "exports/BANDS.txt" in names


def test_a_quantity_not_ticked_stays_out(day) -> None:
    client, item = day
    names = zipfile.ZipFile(io.BytesIO(download(client, item, ["TminD", "SrelD"], form="per_band").content)).namelist()
    assert [name for name in names if name.endswith("_1000m.tif")] == ["exports/TminD_1000m.tif", "exports/SrelD_1000m.tif"]


@pytest.mark.parametrize("layout", [{"form": "per_resolution"}, {"form": "multi_band", "common_resolution": 1000.0}])
def test_a_stacked_file_is_refused_in_words(day, layout: dict[str, Any]) -> None:
    """The stacked forms read GeoTIFFs; the dialog never asks for them for these bands (`stackable`)."""
    client, item = day
    response = download(client, item, QUANTITIES, **layout)
    assert response.status_code == 422
    assert "no raster to read" in response.json()["detail"]
