"""The AOI mask a download's crop carries (F3, M3-18, Otto 24.09.2026).

``test_download.py`` checks ``_image_to_cog_bytes`` against a fake reader that
ignores the AOI geometry entirely — useful for the size cap and the ZIP shape,
useless for the mask itself, which rio-tiler only ever computes from a real
geometry against a real raster grid (``Reader.feature``'s own cutline
rasterisation). This file reads the real synthetic COG of ``mini_cog.py``
through the real ``open_asset``/``CogReader`` path — the socket swapped out,
everything else real — the same pattern `test_download_zarr.py` uses for the
second format.
"""

from __future__ import annotations

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
    import zipfile
    from io import BytesIO

    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        member = archive.read(name)
    memfile = MemoryFile(member)
    return memfile.open()


class TestTheAoiMaskOnARealCog:
    def test_a_slanted_polygon_masks_outside_and_keeps_inside(self, served: list[str]) -> None:
        zip_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_asset,
            crops=[dl.AssetCrop(asset="visual", paths=(_asset(),))],
            aoi_geometry=_diamond_aoi(),
            item_ids=[ITEM],
        )
        with _open_zip_member(zip_bytes, "visual.tif") as raster:
            # No alpha band, whatever the AOI shape — the mask is a GDAL-internal
            # band, never a fourth data band (plan §2 "Maske, >= 2 Items").
            assert raster.count == 3
            mask = raster.dataset_mask()
            data = raster.read()

            corner_mask = mask[0, 0]
            center_mask = mask[mask.shape[0] // 2, mask.shape[1] // 2]
            assert corner_mask == 0, "the diamond's own corner must be outside the mask"
            assert center_mask == 255, "the diamond's centre must be inside the mask"

            # F3: a masked pixel is written as plain 0, not a leftover source value.
            assert (data[:, 0, 0] == 0).all()
            # And the mask, not a coincidence with the fill value, is what a reader
            # must trust: an interior pixel is real data, so it is virtually never 0
            # on all three bands (mini_cog.py reserves 0 and only ever writes 1..255).
            assert not (data[:, mask.shape[0] // 2, mask.shape[1] // 2] == 0).all()

            # No `nodata` tag at all (F3, M3-18): the mask above is what a reader
            # must trust, and cog_translate's `add_mask=True` measurably cannot
            # carry a `nodata` tag on the same call without corrupting the file
            # (module docstring of `_image_to_cog_bytes`).
            assert raster.nodata is None

    def test_a_rectangle_aoi_is_unchanged_no_pixel_is_masked_by_the_cutline(
        self, served: list[str]
    ) -> None:
        zip_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_asset,
            crops=[dl.AssetCrop(asset="visual", paths=(_asset(),))],
            aoi_geometry=_rectangle_aoi(),
            item_ids=[ITEM],
        )
        with _open_zip_member(zip_bytes, "visual.tif") as raster:
            assert raster.count == 3
            # mini_cog.py never writes the reserved nodata value (1..255 only), so a
            # plain rectangle AOI must come back with every pixel inside the mask —
            # exactly the M2-06 behaviour this task must not change (plan §5).
            assert (raster.dataset_mask() == 255).all()
