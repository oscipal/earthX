"""Bug A (Otto's review of PR #86, 23.09.2026): "Download failed: the asset
could not be read from the source" for certain items, reproducibly.

Otto's request had two parts. Part 1 (the error mapping) is covered in
``test_download_route.py`` — only a genuine ``RasterioIOError`` may answer
"could not be read from the source"; anything else propagates to
``build_app``'s own ``_rasterio_error`` handler as a 500. Part 2 is this
file: synthetic COGs and a slanted polygon reproducing the edge cases Otto
named, offline (no gateway, no network) —

* the polygon overhangs the asset's edge,
* the polygon touches only the nodata part of an edge scene,
* two items of one mosaic sit in different UTM zones,
* the polygon misses the item even though its STAC bbox let it through,
* a mask matching each asset's own grid when assets differ in native
  resolution (10/20/60 m).

None of these go through ``earthx.readers.cog``'s ``AssetPath``/gateway
machinery — that boundary is exercised elsewhere (``test_download_mask.py``,
``test_cog.py``). Here ``open_reader`` opens a real ``rio_tiler`` ``Reader``
directly against a ``/vsimem/`` path, which is all :func:`~earthx.access.download.crop_asset`
and :func:`~earthx.access.download.crop_asset_to_cog_bytes` ever call through
``open_reader`` anyway.
"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from rio_tiler.io.rasterio import Reader as RioTilerReader
from shapely.geometry import mapping as shapely_mapping
from shapely.geometry import shape as shapely_shape

from earthx.access import download as dl
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.readers.cog import AssetPath

UTM32 = "EPSG:32632"
UTM33 = "EPSG:32633"


def _memcog(data: np.ndarray, *, crs: str, transform: rasterio.Affine, nodata: int | None = 0) -> MemoryFile:
    """A small, real GeoTIFF in GDAL's ``/vsimem/`` filesystem — never a real path."""
    count, height, width = data.shape
    profile: dict[str, Any] = {
        "driver": "GTiff",
        "dtype": data.dtype,
        "count": count,
        "height": height,
        "width": width,
        "crs": crs,
        "transform": transform,
        "tiled": True,
        "blockxsize": 16,
        "blockysize": 16,
    }
    if nodata is not None:
        profile["nodata"] = nodata
    mem = MemoryFile()
    with mem.open(**profile) as dst:
        dst.write(data)
    return mem


def _asset_path(mem: MemoryFile, *, item_id: str = "ITEM1", asset: str = "visual") -> AssetPath:
    return AssetPath(mem.name, dataset_id=SENTINEL_2_L2A.dataset_id, item_id=item_id, asset=asset)


def open_reader(path: AssetPath) -> RioTilerReader:
    return RioTilerReader(str(path))


def _bbox_to_wgs84(crs: str, bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return transform_bounds(crs, "EPSG:4326", *bounds)


def _polygon(bbox: tuple[float, float, float, float]) -> dict:
    west, south, east, north = bbox
    return {
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    }


class TestPolygonOverhangsTheAssetsEdge:
    """"Polygon ragt teilweise über den Rand des Assets": the AOI's own bbox
    extends beyond the dataset — a partial, not a total, miss."""

    def test_a_partially_overhanging_aoi_still_crops_the_part_that_overlaps(self) -> None:
        data = np.full((3, 20, 20), 40, dtype="uint8")
        transform = from_origin(600000, 5700000, 10, 10)
        mem = _memcog(data, crs=UTM32, transform=transform)
        west, south, east, north = _bbox_to_wgs84(UTM32, rasterio.transform.array_bounds(20, 20, transform))
        lon_span = east - west
        # Half inside the dataset, half well beyond its eastern edge.
        aoi = _polygon((west + lon_span * 0.5, south, east + lon_span * 1.0, north))

        zip_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_reader,
            crops=[dl.AssetCrop(asset="visual", paths=(_asset_path(mem),))],
            aoi_geometry=aoi,
            item_ids=["ITEM1"],
        )
        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            with rasterio.io.MemoryFile(archive.read("visual.tif")) as mf, mf.open() as ds:
                assert ds.nodata == 0
                mask = ds.dataset_mask()
                # Some of the crop is real data (the half still over the asset)...
                assert (mask == 255).any()
                # ...and some is legitimately nodata (the half beyond its edge) —
                # neither half crashes or is silently dropped.
                assert (mask == 0).any()


class TestPolygonOnlyTouchesNodata:
    """"Polygon trifft nur den nodata-Teil einer Randszene": the AOI's bbox
    intersects the item, but the pixels it covers are all the source's own
    nodata (e.g. a swath edge) — refused with `AoiOutsideItems` (400), not a
    500 or a silently empty "success"."""

    def test_an_aoi_entirely_over_the_nodata_half_is_refused(self) -> None:
        data = np.full((3, 20, 20), 40, dtype="uint8")
        data[:, :, 10:] = 0  # the eastern half of the scene has no data at all
        transform = from_origin(600000, 5700000, 10, 10)
        mem = _memcog(data, crs=UTM32, transform=transform)
        west, south, east, north = _bbox_to_wgs84(UTM32, rasterio.transform.array_bounds(20, 20, transform))
        lon_mid = (west + east) / 2
        aoi = _polygon((lon_mid + (east - west) * 0.05, south, east - (east - west) * 0.05, north))

        with pytest.raises(dl.AoiOutsideItems):
            dl.build_download_zip(
                config=SENTINEL_2_L2A,
                open_reader=open_reader,
                crops=[dl.AssetCrop(asset="visual", paths=(_asset_path(mem),))],
                aoi_geometry=aoi,
                item_ids=["ITEM1"],
            )


class TestPolygonMissesTheFootprintDespiteTheBbox:
    """"Polygon schneidet das Asset nicht, obwohl der Footprint es tut": the
    same failure as above, but through the naive/mosaic path (`crop_asset`),
    which reads a bbox via `.part()` — unlike `.feature()`, `.part()` never
    raises for a request that turns out to miss the data entirely, it just
    returns an all-masked array. Two items force the mosaic branch."""

    def test_a_two_item_mosaic_whose_aoi_misses_both_is_refused(self) -> None:
        data = np.full((3, 20, 20), 40, dtype="uint8")
        transform = from_origin(600000, 5700000, 10, 10)
        mem1 = _memcog(data, crs=UTM32, transform=transform)
        mem2 = _memcog(data, crs=UTM32, transform=from_origin(600400, 5700000, 10, 10))
        # An AOI nowhere near either item's real extent, in a plausible enough
        # place that a coarse bbox pre-filter upstream of this module could
        # plausibly have let it through (this module does not re-check that).
        aoi = _polygon((-10.0, 50.0, -9.999, 50.001))

        with pytest.raises(dl.AoiOutsideItems):
            dl.build_download_zip(
                config=SENTINEL_2_L2A,
                open_reader=open_reader,
                crops=[
                    dl.AssetCrop(
                        asset="visual",
                        paths=(_asset_path(mem1, item_id="ITEM1"), _asset_path(mem2, item_id="ITEM2")),
                    )
                ],
                aoi_geometry=aoi,
                item_ids=["ITEM1", "ITEM2"],
            )

    def test_a_single_item_naive_read_whose_aoi_misses_it_is_refused(self) -> None:
        """The same gap, minimal: one item, an explicitly coarser resolution
        (`width`/`height` set) so `crop_asset_to_cog_bytes` takes the naive
        path even for a single item (the windowed path only applies natively)."""
        data = np.full((3, 20, 20), 40, dtype="uint8")
        transform = from_origin(600000, 5700000, 10, 10)
        mem = _memcog(data, crs=UTM32, transform=transform)
        aoi = _polygon((-10.0, 50.0, -9.999, 50.001))

        with pytest.raises(dl.AoiOutsideItems):
            dl.crop_asset_to_cog_bytes(
                open_reader, (_asset_path(mem),), aoi, width=5, height=5
            )


class TestMosaicAcrossUtmZones:
    """"Zwei Szenen einer Gruppe in verschiedenen UTM-Zonen": adjacent MGRS
    tiles straddling a zone boundary are a real, if infrequent, mosaic case —
    both items reproject to the same WGS84 output grid regardless of their
    own native CRS (the module docstring: `.part()`'s `dst_crs` defaults to
    the AOI's own, WGS84, never either item's own CRS)."""

    def test_a_mosaic_of_two_utm_zones_merges_without_error(self) -> None:
        data = np.full((3, 20, 20), 77, dtype="uint8")
        transform32 = from_origin(500000, 5700000, 10, 10)  # near the 32/33 boundary
        transform33 = from_origin(500000, 5700000, 10, 10)
        mem32 = _memcog(data, crs=UTM32, transform=transform32)
        mem33 = _memcog(data, crs=UTM33, transform=transform33)

        west32, south32, east32, north32 = _bbox_to_wgs84(UTM32, rasterio.transform.array_bounds(20, 20, transform32))
        west33, south33, east33, north33 = _bbox_to_wgs84(UTM33, rasterio.transform.array_bounds(20, 20, transform33))
        # An AOI over the union of both items' (disjoint, since they are two
        # different projections of "the same" grid square) WGS84 footprints.
        aoi = _polygon(
            (
                min(west32, west33),
                min(south32, south33),
                max(east32, east33),
                max(north32, north33),
            )
        )

        zip_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_reader,
            crops=[
                dl.AssetCrop(
                    asset="visual",
                    paths=(_asset_path(mem32, item_id="ITEM32"), _asset_path(mem33, item_id="ITEM33")),
                )
            ],
            aoi_geometry=aoi,
            item_ids=["ITEM32", "ITEM33"],
        )
        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            with rasterio.io.MemoryFile(archive.read("visual.tif")) as mf, mf.open() as ds:
                assert (ds.dataset_mask() == 255).any()


class TestMaskMatchesEachAssetsOwnResolution:
    """"Maske bei Bändern mit unterschiedlicher Auflösung (10/20/60 m)": two
    assets of one item, native 10 m and native 20 m, in the same request —
    each asset's own mask file has to match *that asset's* grid, not the
    other one's."""

    def test_two_assets_at_different_native_resolutions_each_get_their_own_grid(self) -> None:
        transform_10m = from_origin(600000, 5700000, 10, 10)
        transform_20m = from_origin(600000, 5700000, 20, 20)
        mem_10m = _memcog(np.full((3, 40, 40), 30, dtype="uint8"), crs=UTM32, transform=transform_10m)
        mem_20m = _memcog(np.full((1, 20, 20), 60, dtype="uint8"), crs=UTM32, transform=transform_20m)
        west, south, east, north = _bbox_to_wgs84(UTM32, rasterio.transform.array_bounds(40, 40, transform_10m))
        aoi = _polygon((west, south, east, north))

        zip_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_reader,
            crops=[
                dl.AssetCrop(asset="visual", paths=(_asset_path(mem_10m, asset="visual"),)),
                dl.AssetCrop(asset="scl", paths=(_asset_path(mem_20m, asset="scl"),)),
            ],
            aoi_geometry=aoi,
            item_ids=["ITEM1"],
        )
        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            with rasterio.io.MemoryFile(archive.read("visual.tif")) as mf, mf.open() as visual_ds:
                visual_shape = visual_ds.shape
            with rasterio.io.MemoryFile(archive.read("visual_mask.tif")) as mf, mf.open() as visual_mask_ds:
                assert visual_mask_ds.shape == visual_shape
            with rasterio.io.MemoryFile(archive.read("scl.tif")) as mf, mf.open() as scl_ds:
                scl_shape = scl_ds.shape
            with rasterio.io.MemoryFile(archive.read("scl_mask.tif")) as mf, mf.open() as scl_mask_ds:
                assert scl_mask_ds.shape == scl_shape
            # The two assets really do have different native resolutions here —
            # otherwise this test would not distinguish "each asset gets its own
            # grid" from "one grid happens to fit both".
            assert visual_shape != scl_shape


class TestCropExtentIsTheGroupsOwnFootprintNotTheWholeAoi:
    """Otto's precising message, 23.09.2026 ("Präzisierung zur Maske"), M3-18
    §13: the data file and its mask are sized to the bounding box of
    (AOI ∩ union of the group's own item footprints), never the AOI's own
    (possibly much larger) bounding box — while ``aoi.geojson`` always still
    carries the original, un-clipped AOI regardless."""

    def test_a_scene_covering_only_part_of_the_aoi_crops_no_further_than_the_scene(self) -> None:
        data = np.full((3, 20, 20), 40, dtype="uint8")
        transform = from_origin(600000, 5700000, 10, 10)
        mem = _memcog(data, crs=UTM32, transform=transform)
        footprint_bbox = _bbox_to_wgs84(UTM32, rasterio.transform.array_bounds(20, 20, transform))
        west, south, east, north = footprint_bbox
        lon_span = east - west
        # The AOI reaches well past the item's real footprint to the east — a
        # user-drawn area that only one scene of the group actually covers.
        aoi = _polygon((west, south, east + lon_span * 2, north))
        item = {"id": "ITEM1", "geometry": _polygon(footprint_bbox)}

        region = dl.compute_crop_region([item], shapely_shape(aoi))
        zip_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_reader,
            crops=[dl.AssetCrop(asset="visual", paths=(_asset_path(mem),))],
            aoi_geometry=aoi,
            region_geometry=shapely_mapping(region),
            item_ids=["ITEM1"],
        )
        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            with rasterio.io.MemoryFile(archive.read("visual.tif")) as mf, mf.open() as ds:
                out_west, out_south, out_east, out_north = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)
            with rasterio.io.MemoryFile(archive.read("visual_mask.tif")) as mf, mf.open() as mask_ds:
                mask_west, mask_south, mask_east, mask_north = transform_bounds(
                    mask_ds.crs, "EPSG:4326", *mask_ds.bounds
                )

            # Both the data file and the mask end at the scene's own eastern
            # edge, not the AOI's own (much further east) bounding box.
            assert out_east == pytest.approx(east, abs=1e-3)
            assert out_east < aoi.get("coordinates")[0][2][0] - lon_span * 0.5
            assert mask_east == pytest.approx(east, abs=1e-3)

            # ...yet the AOI written into the ZIP is still the whole, original
            # area the user drew, unclipped by what the scene actually covers.
            written_aoi = json.loads(archive.read("aoi.geojson"))
            assert written_aoi == aoi

    def test_two_scenes_of_one_group_crop_to_the_union_of_both_footprints(self) -> None:
        data = np.full((3, 20, 20), 40, dtype="uint8")
        transform1 = from_origin(600000, 5700000, 10, 10)
        transform2 = from_origin(600300, 5700000, 10, 10)  # adjacent, to the east
        mem1 = _memcog(data, crs=UTM32, transform=transform1)
        mem2 = _memcog(data, crs=UTM32, transform=transform2)
        fp1 = _bbox_to_wgs84(UTM32, rasterio.transform.array_bounds(20, 20, transform1))
        fp2 = _bbox_to_wgs84(UTM32, rasterio.transform.array_bounds(20, 20, transform2))
        union_west, union_south = min(fp1[0], fp2[0]), min(fp1[1], fp2[1])
        union_east, union_north = max(fp1[2], fp2[2]), max(fp1[3], fp2[3])
        # An AOI clearly larger than the union of both footprints in every
        # direction — the group's own extent is what should bound the crop,
        # not this margin.
        margin = (union_north - union_south) * 0.5
        aoi = _polygon(
            (union_west - margin, union_south - margin, union_east + margin, union_north + margin)
        )
        items = [
            {"id": "ITEM1", "geometry": _polygon(fp1)},
            {"id": "ITEM2", "geometry": _polygon(fp2)},
        ]

        region = dl.compute_crop_region(items, shapely_shape(aoi))
        zip_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_reader,
            crops=[
                dl.AssetCrop(
                    asset="visual",
                    paths=(_asset_path(mem1, item_id="ITEM1"), _asset_path(mem2, item_id="ITEM2")),
                )
            ],
            aoi_geometry=aoi,
            region_geometry=shapely_mapping(region),
            item_ids=["ITEM1", "ITEM2"],
        )
        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            with rasterio.io.MemoryFile(archive.read("visual.tif")) as mf, mf.open() as ds:
                out_bounds = transform_bounds(ds.crs, "EPSG:4326", *ds.bounds)

            # The extent is the union of both scenes' own footprints, well
            # short of the AOI's own (much larger, margin-padded) bounding box.
            assert out_bounds[0] == pytest.approx(union_west, abs=1e-3)
            assert out_bounds[2] == pytest.approx(union_east, abs=1e-3)
            assert out_bounds[0] > aoi.get("coordinates")[0][0][0] + margin * 0.5

            written_aoi = json.loads(archive.read("aoi.geojson"))
            assert written_aoi == aoi

    def test_geojson_in_the_zip_is_always_the_original_aoi_even_when_narrowed(self) -> None:
        """A group that fully covers the AOI still ships ``aoi.geojson`` as the
        AOI exactly as drawn — the same file the narrowing tests above already
        check, isolated here as its own case per Otto's list (M3-18 §13)."""
        data = np.full((3, 20, 20), 40, dtype="uint8")
        transform = from_origin(600000, 5700000, 10, 10)
        mem = _memcog(data, crs=UTM32, transform=transform)
        footprint_bbox = _bbox_to_wgs84(UTM32, rasterio.transform.array_bounds(20, 20, transform))
        aoi = _polygon(footprint_bbox)
        item = {"id": "ITEM1", "geometry": _polygon(footprint_bbox)}

        region = dl.compute_crop_region([item], shapely_shape(aoi))
        zip_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=open_reader,
            crops=[dl.AssetCrop(asset="visual", paths=(_asset_path(mem),))],
            aoi_geometry=aoi,
            region_geometry=shapely_mapping(region),
            item_ids=["ITEM1"],
        )
        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            written_aoi = json.loads(archive.read("aoi.geojson"))
            assert written_aoi == aoi
