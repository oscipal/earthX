"""The tile route over a NetCDF item read through its chunk references (adr/0029 A2, F7; M5-11 plan §4.3, §4.4).

The whole tiler as `build_app` makes it, with a synthetic entry stored as ``netcdf-refs`` and its item served from
memory; the file comes from the fake source of `mini_netcdf.py`. Checked: a tile is drawn from one chunk request, the
process keeps the chunk for the next tile, and a file replaced since its references were made is a ``502`` with
the fixed title, never an old or new picture.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from rasterio.warp import transform_bounds
from rio_tiler.constants import WEB_MERCATOR_TMS, WGS84_CRS

from earthx.api.tiler import build_app
from earthx.catalog.registry import DataFormat, DatasetRegistry
from earthx.discovery.netcdf_refs import reference_file, step_references
from earthx.readers.reference_store import _CACHE, TILER_CHUNK_CACHE_BYTES, configure_chunk_cache
from tests.catalog.entries import COP_DEM_GLO_30
from tests.earthx.readers import mini_netcdf
from tests.earthx.readers.mini_netcdf import HOST, URL, Source, from_memory

DATASET = "synthetic-netcdf"
ITEM = "synthetic-netcdf-20240103"
CONFIG = replace(
    COP_DEM_GLO_30,
    dataset_id=DATASET,
    format=DataFormat.NETCDF_REFS,
    source=replace(COP_DEM_GLO_30.source, asset_hosts=(HOST,)),
)


@pytest.fixture(autouse=True)
def no_cache_after() -> Iterator[None]:
    yield
    configure_chunk_cache(0)


@pytest.fixture
def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Source]:
    source = Source(mini_netcdf.build(tmp_path / "file.nc").read_bytes())

    async def references() -> Any:
        async with source.gateway() as gateway:
            return await reference_file(gateway, URL, mini_netcdf.VARIABLE)

    item = {
        "type": "Feature",
        "id": ITEM,
        "properties": {"datetime": "2024-01-03T00:00:00Z", "proj:code": "EPSG:2056"},
        "assets": {"TabsD": {"href": URL, "earthx:refs": step_references(asyncio.run(references()), 2)}},
    }
    source.seen.clear()
    source.serve_readers(monkeypatch)

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return item

    app = build_app(DatasetRegistry((CONFIG,)))
    app.state.earthx_item_source = item_source
    app.state.earthx_cache_pool = None
    app.state.earthx_resolver = from_memory
    return TestClient(app), source


def tile_path() -> str:
    west, south, east, north = transform_bounds(
        "EPSG:2056", WGS84_CRS, mini_netcdf.WEST, mini_netcdf.SOUTH, mini_netcdf.WEST + 37_000, mini_netcdf.SOUTH + 24_000
    )
    tile = WEB_MERCATOR_TMS.tile((west + east) / 2, (south + north) / 2, 9)
    return f"/collections/{DATASET}/items/{ITEM}/tiles/WebMercatorQuad/{tile.z}/{tile.x}/{tile.y}?asset=TabsD&rescale=-10,30"


def test_the_tiler_keeps_chunks(served: tuple[TestClient, Source]) -> None:
    assert _CACHE.max_bytes == TILER_CHUNK_CACHE_BYTES


def test_a_tile_from_one_chunk_request_then_from_the_cache(served: tuple[TestClient, Source]) -> None:
    client, source = served
    for _ in range(2):
        response = client.get(tile_path())
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("image/")
    assert len(source.seen) == 1
    assert source.seen[0].headers["if-match"] == source.etag


def test_a_replaced_file_is_a_502_with_its_title(served: tuple[TestClient, Source], tmp_path: Path) -> None:
    client, source = served
    source.replace(mini_netcdf.build(tmp_path / "new.nc", mini_netcdf.values(seed=9)).read_bytes())
    response = client.get(tile_path())
    assert response.status_code == 502
    assert "updated this file" in response.json()["detail"]
    assert URL not in response.text


def test_a_source_that_ignores_the_range_is_a_502(served: tuple[TestClient, Source]) -> None:
    client, source = served
    source.ignore_range = True
    response = client.get(tile_path())
    assert response.status_code == 502
    assert URL not in response.text
