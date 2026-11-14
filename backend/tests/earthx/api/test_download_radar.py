"""The crop of a dataset placed by GCPs, through the download route: radar geometry, never placed (DS-04d).

Two synthetic slices of one pass (`mini_pass`), read for real through the reader, no network: the route joins them
into one file at the offset of their line times, keeps every pixel of the source, writes the GCPs shifted onto the
window and no CRS, puts the AOI's shape in the mask only (F1 = 2), and names each scene's rows and columns.
"""

from __future__ import annotations

import warnings
import zipfile
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile
from rasterio.transform import GCPTransformer

from earthx.api.tiler import build_app
from earthx.catalog.registry import DatasetRegistry, Georeferencing, LineTimes
from earthx.gateway import check_url
from tests.catalog.entries import SENTINEL_2_L2A
from tests.catalog.synthetic_zarr import without_cloud_share
from tests.earthx.readers import mini_pass
from tests.earthx.readers.mini_zarr import HOST, from_memory

ASSET = "vv"
RADAR = replace(
    without_cloud_share(SENTINEL_2_L2A),
    dataset_id="synthetic-radar",
    source=replace(SENTINEL_2_L2A.source, asset_hosts=(HOST,)),
    georeferencing=Georeferencing.GCP_TPS,
    line_times=LineTimes(first=mini_pass.FIRST_LINE, last=mini_pass.LAST_LINE),
    capabilities=replace(SENTINEL_2_L2A.capabilities, reprojection=False),
)
REGISTRY = DatasetRegistry((RADAR,))


def href(item_id: str) -> str:
    return f"https://{HOST}/products/{item_id}/{ASSET}.tif"


def footprint(index: int) -> dict[str, Any]:
    first, width = index * mini_pass.HEIGHT, mini_pass.WIDTHS[index]
    corners = [(first, 0), (first, width), (first + mini_pass.HEIGHT, width), (first + mini_pass.HEIGHT, 0)]
    ring = [list(mini_pass.position(line, col)) for line, col in corners]
    return {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}


def item(index: int, *, gap_lines: int = 0) -> dict[str, Any]:
    stac = mini_pass.item(index, gap_lines=gap_lines)
    geometry = footprint(index)
    lons, lats = zip(*geometry["coordinates"][0], strict=True)
    # About 10 m pixels, as the item of a real slice says (`sar:pixel_spacing_range`); the size estimate reads it.
    band = {"data_type": "uint16", "nodata": mini_pass.NODATA}
    return {
        **stac,
        "properties": {**stac["properties"], "gsd": 10.0},
        "geometry": geometry,
        "bbox": [min(lons), min(lats), max(lons), max(lats)],
        "assets": {
            ASSET: {"href": href(stac["id"]), "type": "image/tiff; application=geotiff", "raster:bands": [band]}
        },
    }


def area(line0: float, col0: float, line1: float, col1: float) -> dict[str, Any]:
    ring = [list(mini_pass.position(line, col)) for line, col in ((line0, col0), (line0, col1), (line1, col1), (line1, col0))]
    return {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}


#: Across the seam between the two slices (line 64), clear of the narrower slice's right edge.
ACROSS = area(50, 10, 80, 50)


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    directory = tmp_path_factory.mktemp("pass")
    return {
        f"slice-{index}": mini_pass.build_slice(directory / f"slice-{index}.tif", index) for index in range(2)
    }


def client_for(
    files: dict[str, Path],
    items: dict[str, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    registry: DatasetRegistry = REGISTRY,
) -> TestClient:
    by_url = {href(item_id): files[item_id] for item_id in items}

    def vsicurl_path(checked: object) -> str:
        return str(by_url[getattr(checked, "url", str(checked))])

    monkeypatch.setattr("earthx.readers.cog.vsicurl_path", vsicurl_path)
    monkeypatch.setattr(
        "earthx.readers.cog.check_url", lambda url, policy, **_: check_url(url, policy, resolve=from_memory)
    )

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        return items[item_id]

    @asynccontextmanager
    async def lifespan(app):
        app.state.earthx_item_source = item_source
        yield

    app = build_app(registry, lifespan=lifespan)
    app.state.earthx_resolver = from_memory
    return TestClient(app)


@pytest.fixture
def joined(files: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with client_for(files, {"slice-0": item(0), "slice-1": item(1)}, monkeypatch) as client:
        yield client


def download(client: TestClient, **body: Any) -> Any:
    payload = {"groups": [["slice-0", "slice-1"]], "assets": [ASSET], "aoi": ACROSS, **body}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        return client.post(f"/collections/{RADAR.dataset_id}/download", json=payload)


def members(response: Any) -> dict[str, bytes]:
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def data_and_mask(files: dict[str, bytes]) -> tuple[str, str]:
    (data,) = [name for name in files if name.endswith(".tif") and "mask" not in name]
    (mask,) = [name for name in files if name.endswith(".tif") and "mask" in name]
    return data, mask


def test_the_crop_is_one_file_in_radar_geometry_without_a_crs(joined: TestClient) -> None:
    response = download(joined)
    assert response.status_code == 200, response.text
    files = members(response)
    data, mask = data_and_mask(files)
    with MemoryFile(files[data]) as memory, memory.open() as dataset:
        assert dataset.crs is None
        assert dataset.transform.is_identity
        gcps, gcp_crs = dataset.gcps
        assert gcp_crs == mini_pass.GCP_CRS
        # Every GCP of both slices, the second's shifted by the height of the first.
        assert len(gcps) == 2 * len(mini_pass.gcps(0, mini_pass.WIDTHS[0]))
        values = dataset.read(1)
    lines, cols = numpy.vectorize(mini_pass.value_at)(values)
    # One row of the file is one line of the pass, one column one column: nothing warped, nothing flipped.
    assert (numpy.diff(lines, axis=0) == 1).all() and (numpy.diff(cols, axis=1) == 1).all()
    assert lines.min() < mini_pass.HEIGHT <= lines.max()
    with MemoryFile(files[mask]) as memory, memory.open() as dataset:
        assert dataset.crs is None and len(dataset.gcps[0]) == len(gcps)
        inside = dataset.read(1)
    assert set(numpy.unique(inside)) <= {0, 1} and inside.any()


def test_the_gcps_of_the_file_place_it_where_the_source_lies(joined: TestClient) -> None:
    files = members(download(joined))
    data, _ = data_and_mask(files)
    with MemoryFile(files[data]) as memory, memory.open() as dataset:
        transformer = GCPTransformer(dataset.gcps[0], tps=True)
        row, col = dataset.height // 2, dataset.width // 2
        line, column = mini_pass.value_at(dataset.read(1)[row, col])
        lon, lat = transformer.xy(row + 0.5, col + 0.5, offset="ul")
    expected = mini_pass.position(line + 0.5, column + 0.5)
    assert abs(lon - expected[0]) < 2 * mini_pass.STEP_LON and abs(lat - expected[1]) < 2 * mini_pass.STEP_LAT


def test_the_data_keep_every_value_outside_the_shape(joined: TestClient) -> None:
    triangle = {
        "type": "Polygon",
        "coordinates": [[list(mini_pass.position(*corner)) for corner in ((50, 10), (50, 50), (80, 10), (50, 10))]],
    }
    files = members(download(joined, aoi=triangle))
    data, mask = data_and_mask(files)
    with MemoryFile(files[data]) as data_memory, data_memory.open() as values:
        with MemoryFile(files[mask]) as mask_memory, mask_memory.open() as shape:
            outside = shape.read(1) == 0
            assert outside.any()
            assert (values.read(1)[outside] != mini_pass.NODATA).all()


def test_the_notice_names_the_grid_and_each_scenes_window(joined: TestClient) -> None:
    files = members(download(joined))
    notice = files["ATTRIBUTION.txt"].decode("utf-8")
    assert "Grid: radar geometry of the source scenes, not map-projected" in notice
    assert "Scene slice-0: rows " in notice and "Scene slice-1: rows 0-" in notice
    assert "Resolution: native" not in notice


def test_a_missing_slice_splits_the_pass_into_two_groups(files: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    items = {"slice-0": item(0), "slice-1": item(1, gap_lines=mini_pass.HEIGHT)}
    with client_for(files, items, monkeypatch) as client:
        response = download(client)
    assert response.status_code == 200, response.text
    names = members(response)
    assert any("group-01/" in name for name in names) and any("group-02/" in name for name in names)
    notice = names["ATTRIBUTION.txt"].decode("utf-8")
    assert "Not joined into one file: a slice of the pass is missing." in notice
    assert "Group 1: Scene slice-0" in notice and "Group 2: Scene slice-1" in notice


def test_another_common_resolution_is_refused_before_anything_is_read(joined: TestClient) -> None:
    response = download(joined, form="multi_band", common_resolution=20.0)
    assert response.status_code == 422
    assert "radar geometry" in response.json()["detail"]


def test_an_aoi_beside_the_pass_is_refused(joined: TestClient) -> None:
    response = download(joined, aoi=area(400, 400, 420, 420))
    assert response.status_code == 400


def test_a_file_with_gcps_where_the_registry_names_a_geotransform_is_not_read(
    files: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = replace(RADAR, georeferencing=Georeferencing.GEOTRANSFORM, line_times=None)
    items = {"slice-0": item(0), "slice-1": item(1)}
    with client_for(files, items, monkeypatch, DatasetRegistry((plain,))) as client:
        payload = {"groups": [["slice-0", "slice-1"]], "assets": [ASSET], "aoi": ACROSS}
        response = client.post(f"/collections/{plain.dataset_id}/download", json=payload)
    assert response.status_code == 502
    with rasterio.open(files["slice-0"]) as dataset:
        assert dataset.crs is None
