"""The AOI crop over a *Zarr* asset, against the synthetic store of M2-09a.

`test_download.py` checks the pipeline with a fake reader: the size cap, the AOI
filter, the notice, and that nothing touches a real filesystem path. What it
cannot check is that the crop works at all for the second format — until M2-10
nothing read a Zarr asset through `build_download_zip`, although
:func:`~earthx.access.download.crop_asset` has accepted one since M2-09a.

Everything here is the real path except the socket: the store is written by the
script of `mini_zarr.py`, served through the reader's own gateway seam, and read
by the same ``open_asset`` the tiler hands to TiTiler. The network guard of
`tests/conftest.py` is active throughout.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import httpx
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform_bounds

from earthx.access import download as dl
from earthx.access.tiles import open_asset
from earthx.catalog.datasets import SENTINEL_2_L2A_ZARR3
from earthx.readers.zarr_reader import ZarrAsset, ZarrAssetError, zarr_asset
from tests.earthx.readers import mini_zarr
from tests.earthx.readers.mini_zarr import BASE_URL, POLICY, from_memory

DATASET = SENTINEL_2_L2A_ZARR3.dataset_id
ITEM = "SYNTH_20260102T100000"

# The registry entry addresses bands as `<group>:<variables>` (ZarrInfo
# .variable_separator), which is the key that ends up as the ZIP member name.
ASSET_KEY = "SR_20m:b04,b02"


@pytest.fixture(scope="module")
def store_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_zarr.build_mini_zarr(tmp_path_factory.mktemp("zarr") / "mini.zarr")


@pytest.fixture
def served(store_root: Path, monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    return mini_zarr.serve_store(store_root, monkeypatch)


def asset(variable: str = "b04,b02", group: str = "r20m") -> ZarrAsset:
    """What the tile path's own resolution hands the crop for this dataset: an
    href naming the *group*, with the variables split off the asset key."""
    return zarr_asset(
        f"{BASE_URL}/{group}",
        POLICY,
        dataset_id=DATASET,
        item_id=ITEM,
        asset=ASSET_KEY,
        crs=mini_zarr.ITEM_CRS,
        resolve=from_memory,
        variable=variable,
    )


def aoi_over(fraction: float = 0.5) -> dict:
    """A polygon in WGS84 over the middle of the store, covering ``fraction`` of it."""
    left, bottom, right, top = mini_zarr.store_bounds()
    inset_x = (right - left) * (1 - fraction) / 2
    inset_y = (top - bottom) * (1 - fraction) / 2
    west, south, east, north = transform_bounds(
        CRS.from_string(mini_zarr.ITEM_CRS),
        CRS.from_epsg(4326),
        left + inset_x,
        bottom + inset_y,
        right - inset_x,
        top - inset_y,
    )
    return {
        "type": "Polygon",
        "coordinates": [
            [[west, south], [east, south], [east, north], [west, north], [west, south]]
        ],
    }


def build(crops: list[dl.AssetCrop], aoi: dict) -> bytes:
    return dl.build_download_zip(
        config=SENTINEL_2_L2A_ZARR3,
        open_reader=open_asset,
        crops=crops,
        aoi_geometry=aoi,
        item_ids=[ITEM],
    )


class TestACropOverTheSecondFormat:
    def test_the_zip_carries_a_readable_cog_and_the_notice(self, served: list[httpx.Request]) -> None:
        zip_bytes = build([dl.AssetCrop(asset=ASSET_KEY, paths=(asset(),))], aoi_over())

        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            names = archive.namelist()
            assert dl.NOTICE_FILENAME in names
            # The cleaned name, because `SR_20m:b04,b02.tif` is not a filename
            # every extractor can write (M2-10 §3.4).
            assert "SR_20m_b04_b02.tif" in names
            with rasterio.open(BytesIO(archive.read("SR_20m_b04_b02.tif"))) as raster:
                assert raster.count > 0
                assert raster.width > 0 and raster.height > 0

    def test_both_variables_of_the_key_reach_the_image(self, served: list[httpx.Request]) -> None:
        """The composite of `ZarrReader._merged` survives the crop, not only the
        tile: two variables give twice the bands one does.

        Checked on the image rather than on the finished COG, and relative to the
        single-variable read rather than as an absolute number — neither the store's
        time axis (this synthetic store carries two acquisitions per group, so one
        variable is already two bands) nor the mask band GDAL writes is this test's
        subject.
        """
        one = dl.crop_asset(open_asset, (asset(variable="b04"),), aoi_over())
        two = dl.crop_asset(open_asset, (asset(variable="b04,b02"),), aoi_over())

        assert two.count == 2 * one.count

    def test_every_byte_came_through_the_gateway(self, served: list[httpx.Request]) -> None:
        """KLAERUNGEN B8, and the reason the store is a `zarr.abc.store.Store` of our
        own: a crop must not become the one read that leaves by another door.

        The `Host` header rather than the URL host: `gateway` connects to the address
        it checked and carries the name in the header (M1-03), so the URL a request
        went out on is an address by design.
        """
        build([dl.AssetCrop(asset=ASSET_KEY, paths=(asset(),))], aoi_over())

        assert served
        assert {request.headers["host"] for request in served} == {mini_zarr.HOST}

    def test_the_notice_names_the_key_the_file_came_from(self, served: list[httpx.Request]) -> None:
        zip_bytes = build([dl.AssetCrop(asset=ASSET_KEY, paths=(asset(),))], aoi_over())

        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            notice = archive.read(dl.NOTICE_FILENAME).decode("utf-8")
        assert ASSET_KEY in notice
        assert "Copernicus Sentinel data" in notice

    def test_a_smaller_aoi_crops_to_fewer_pixels(self, served: list[httpx.Request]) -> None:
        """The AOI is what bounds the read — otherwise "crop" would only mean
        "download the scene and say it was cropped"."""

        def side(fraction: float) -> int:
            zip_bytes = build([dl.AssetCrop(asset=ASSET_KEY, paths=(asset(),))], aoi_over(fraction))
            with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
                with rasterio.open(BytesIO(archive.read("SR_20m_b04_b02.tif"))) as raster:
                    return raster.width

        assert side(0.25) < side(0.9)


class TestWhatTheCropRefuses:
    def test_an_aoi_beside_the_store_is_not_an_empty_image(self, served: list[httpx.Request]) -> None:
        """A crop that touches no data is a refusal the route turns into a 400, not
        a ZIP holding an empty raster nobody asked for.

        This is what M2-10 found by running the crop over the second format for the
        first time: rioxarray raises `NoDataInBounds` where rio-tiler raises
        `TileOutsideBounds`, and only the latter was caught — so the same AOI that
        gives a 400 on a COG gave a 500 on a Zarr asset.
        """
        far_away = {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1], [0.0, 0.0]]],
        }

        with pytest.raises(dl.AoiOutsideItems):
            build([dl.AssetCrop(asset=ASSET_KEY, paths=(asset(),))], far_away)

    def test_a_variable_the_store_does_not_have_is_a_defined_error(
        self, served: list[httpx.Request]
    ) -> None:
        """`ZarrAssetError` is what `api.tiler` answers with a 502: the item named
        something the store does not carry. Never a traceback, and never a band of
        zeros standing in for it."""
        with pytest.raises(ZarrAssetError):
            build([dl.AssetCrop(asset="SR_20m:b99", paths=(asset(variable="b99"),))], aoi_over())

    def test_a_group_the_store_does_not_have_is_a_defined_error(
        self, served: list[httpx.Request]
    ) -> None:
        with pytest.raises(ZarrAssetError):
            build(
                [
                    dl.AssetCrop(
                        asset=f"SR:{mini_zarr.MISSING_GROUP}",
                        paths=(asset(group=mini_zarr.MISSING_GROUP, variable="b04"),),
                    )
                ],
                aoi_over(),
            )
