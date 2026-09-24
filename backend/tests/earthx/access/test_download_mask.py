"""The AOI mask a download's crop carries (F3, M3-18; redefined 23.09.2026, M3-18 §3).

``test_download.py`` checks the data/mask split against a fake reader that
ignores the AOI geometry entirely — useful for the size cap and the ZIP shape,
useless for the mask itself, which is only ever computed from a real geometry
against a real raster grid (``rasterize``). This file reads the real synthetic
COG of ``mini_cog.py`` through the real ``open_asset``/``CogReader`` path — the
socket swapped out, everything else real — the same pattern
`test_download_zarr.py` uses for the second format.

**Mask instead of nodata (Otto, 23.09.2026, M3-18 §3).** The data file
(``visual.tif``) is always the full bounding box, at the source's own
validity, whatever the polygon's shape — nothing here masks a pixel for lying
outside the AOI. The polygon itself lives in the companion mask file
(``visual_mask.tif``): ``1`` inside, ``0`` outside, same grid as the data.
"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.warp import transform_bounds

from earthx.access import download as dl
from earthx.access.tiles import open_asset
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.readers.cog import asset_path
from tests.earthx.readers import mini_cog
from tests.earthx.readers.mini_cog import ASSET_URL, ORIGIN_X, ORIGIN_Y, RESOLUTION, SIZE
from tests.earthx.readers.mini_zarr import ITEM_CRS, POLICY, from_memory

ITEM = "SYNTH_20260924T000000"


@pytest.fixture(scope="module")
def cog_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_cog.build_mini_cog(tmp_path_factory.mktemp("cog") / "mini.tif")


@pytest.fixture
def served(cog_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return mini_cog.serve_cog(cog_path, monkeypatch)


def _to_wgs84(x: float, y: float) -> tuple[float, float]:
    west, south, east, north = transform_bounds(CRS.from_string(ITEM_CRS), CRS.from_epsg(4326), x, y, x, y)
    return (west + east) / 2, (south + north) / 2


def _diamond_aoi() -> dict:
    """A rotated square inscribed in the middle third of the COG's own extent.

    Deliberately not axis-aligned: a rectangle in the item's own grid cannot
    tell "the cutline mask is real" apart from "the AOI's own bounding box is
    real" (both give the same pixels), which is exactly the distinction this
    module's mask has to get right (F3, plan §5 "schräges Polygon").
    """
    span = SIZE * RESOLUTION
    cx, cy = ORIGIN_X + span / 2, ORIGIN_Y - span / 2
    radius = span / 4
    corners_utm = [(cx, cy - radius), (cx + radius, cy), (cx, cy + radius), (cx - radius, cy)]
    ring = [_to_wgs84(x, y) for x, y in corners_utm]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def _rectangle_aoi(fraction: float = 0.6) -> dict:
    """A plain axis-aligned rectangle over the middle ``fraction`` of the COG."""
    span = SIZE * RESOLUTION
    inset = span * (1 - fraction) / 2
    west, south = _to_wgs84(ORIGIN_X + inset, ORIGIN_Y - span + inset)
    east, north = _to_wgs84(ORIGIN_X + span - inset, ORIGIN_Y - inset)
    return {
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    }


def _asset():
    return asset_path(ASSET_URL, POLICY, dataset_id=SENTINEL_2_L2A.dataset_id, item_id=ITEM, asset="visual", resolve=from_memory)


def _open_zip_member(zip_bytes: bytes, name: str) -> rasterio.io.DatasetReader:
    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        member = archive.read(name)
    memfile = MemoryFile(member)
    return memfile.open()


class TestTheAoiMaskOnARealCog:
    def test_a_slanted_polygon_leaves_the_data_file_untouched(self, served: list[str]) -> None:
        """Otto, 23.09.2026 (M3-18 §3): the data file is a plain bounding-box crop —
        every pixel keeps its source value and validity, whatever the polygon's
        shape. The polygon itself is checked separately, on the mask file, below."""
        zip_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_asset,
            crops=[dl.AssetCrop(asset="visual", paths=(_asset(),))],
            aoi_geometry=_diamond_aoi(),
            item_ids=[ITEM],
        )
        with _open_zip_member(zip_bytes, "visual.tif") as raster:
            # No alpha band (plan §2 "Maske, >= 2 Items") — still a GDAL-internal
            # mask band, but reflecting only the source's own validity now.
            assert raster.count == 3
            data = raster.read()

            # mini_cog.py never writes the reserved nodata value (1..255 only), and
            # the diamond no longer clips anything here — every pixel in the whole
            # bounding box is valid and keeps its original value.
            assert (raster.dataset_mask() == 255).all()
            assert (data != 0).all()

            # No `nodata` tag at all (F3, M3-18): the mask above is what a reader
            # must trust, and cog_translate's `add_mask=True` measurably cannot
            # carry a `nodata` tag on the same call without corrupting the file
            # (module docstring of `_masked_array_to_cog_bytes`).
            assert raster.nodata is None

    def test_a_slanted_polygon_s_mask_file_marks_outside_and_inside(self, served: list[str]) -> None:
        zip_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_asset,
            crops=[dl.AssetCrop(asset="visual", paths=(_asset(),))],
            aoi_geometry=_diamond_aoi(),
            item_ids=[ITEM],
        )
        with _open_zip_member(zip_bytes, "visual.tif") as raster, _open_zip_member(
            zip_bytes, "visual_mask.tif"
        ) as mask_raster:
            assert mask_raster.count == 1
            assert mask_raster.dtypes[0] == "uint8"
            # Same grid as the data file — a consumer can index the two together.
            assert mask_raster.shape == raster.shape
            assert mask_raster.transform == raster.transform

            mask = mask_raster.read(1)
            corner = mask[0, 0]
            centre = mask[mask.shape[0] // 2, mask.shape[1] // 2]
            assert corner == 0, "the diamond's own corner must be outside the mask"
            assert centre == 1, "the diamond's centre must be inside the mask"
            assert set(mask.flatten().tolist()) <= {0, 1}

    def test_a_rectangle_aoi_still_gets_a_mask_file_for_uniformity(
        self, served: list[str]
    ) -> None:
        """Plan §11: a rectangle in WGS84 lon/lat is not necessarily aligned with
        the source's own (possibly rotated) pixel grid, so a mask file ships even
        here — checked, not assumed to be all `1`."""
        zip_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_asset,
            crops=[dl.AssetCrop(asset="visual", paths=(_asset(),))],
            aoi_geometry=_rectangle_aoi(),
            item_ids=[ITEM],
        )
        with _open_zip_member(zip_bytes, "visual.tif") as raster:
            assert raster.count == 3
            # The data file is never cropped to the polygon (M3-18 §3) — every
            # pixel of the bounding box stays valid, rectangle or not.
            assert (raster.dataset_mask() == 255).all()
        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            assert "visual_mask.tif" in archive.namelist()
        with _open_zip_member(zip_bytes, "visual_mask.tif") as mask_raster:
            mask = mask_raster.read(1)
            assert set(mask.flatten().tolist()) <= {0, 1}
            assert (mask == 1).any()

    def test_the_aoi_geojson_carries_the_requested_geometry(self, served: list[str]) -> None:
        aoi_geometry = _diamond_aoi()
        zip_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_asset,
            crops=[dl.AssetCrop(asset="visual", paths=(_asset(),))],
            aoi_geometry=aoi_geometry,
            item_ids=[ITEM],
        )
        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            # Round-tripped through JSON on both sides: the ring's points are
            # plain tuples until they cross that boundary, lists afterwards.
            assert json.loads(archive.read(dl.AOI_FILENAME).decode("utf-8")) == json.loads(json.dumps(aoi_geometry))


class TestWindowedReadMatchesTheWholeArrayRead:
    """F10a/F10b (M3-18 §10): the windowed native-resolution path
    (:func:`_write_native_windowed_cog`, used automatically by
    :func:`crop_asset_to_cog_bytes` for a single COG item) must produce the
    same crop as the older whole-array path it replaces for that case — same
    grid, same mask, and (up to nearest-neighbor edge noise on a slanted
    cutline) the same pixel values."""

    def _naive_cog_bytes(self, served: list[str], aoi_geometry: dict) -> bytes:
        image = dl.crop_asset(open_asset, (_asset(),), aoi_geometry)
        return dl._masked_array_to_cog_bytes(image.array, image.transform, image.crs)

    def test_a_rectangle_aoi_is_pixel_identical(self, served: list[str]) -> None:
        aoi_geometry = _rectangle_aoi()
        windowed_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_asset,
            crops=[dl.AssetCrop(asset="visual", paths=(_asset(),))],
            aoi_geometry=aoi_geometry,
            item_ids=[ITEM],
        )
        naive_bytes = self._naive_cog_bytes(served, aoi_geometry)
        with (
            _open_zip_member(windowed_bytes, "visual.tif") as windowed,
            MemoryFile(naive_bytes).open() as naive,
        ):
            assert windowed.shape == naive.shape
            assert windowed.transform == naive.transform
            assert (windowed.dataset_mask() == naive.dataset_mask()).all()
            assert (windowed.read() == naive.read()).all()

    def test_a_slanted_aoi_masks_agree_and_values_are_near_identical(self, served: list[str]) -> None:
        import numpy as np

        aoi_geometry = _diamond_aoi()
        windowed_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_asset,
            crops=[dl.AssetCrop(asset="visual", paths=(_asset(),))],
            aoi_geometry=aoi_geometry,
            item_ids=[ITEM],
        )
        naive_bytes = self._naive_cog_bytes(served, aoi_geometry)
        with (
            _open_zip_member(windowed_bytes, "visual.tif") as windowed,
            MemoryFile(naive_bytes).open() as naive,
        ):
            assert windowed.shape == naive.shape
            # Exact mask agreement: the cutline rasterisation is the same
            # `rasterize(..., all_touched=True)` call either way.
            assert (windowed.dataset_mask() == naive.dataset_mask()).all()
            # Values may differ by nearest-neighbor edge noise right at the
            # cutline (plan §10, "windowed transform misalignment") — never by
            # more than one full band step, and never on average.
            diff = np.abs(windowed.read().astype(int) - naive.read().astype(int))
            assert diff.mean() < 1.0
