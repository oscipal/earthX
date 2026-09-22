"""The AOI-crop-to-ZIP pipeline of M2-06, without a network and without GDAL reads.

Every reader call here is a fake: what these tests check is the arithmetic
(the size cap, the AOI filter), the geometry validation, the notice text and
that nothing the module writes ever reaches a real filesystem path — not
whether rio-tiler can read a COG over HTTP, which `test_cog.py` and
`test_tiler.py` already cover for the tile path this module shares an
:class:`~earthx.readers.cog.AssetPath` with.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from typing import Any

import numpy as np
import pytest
import rasterio
from rio_tiler.errors import PointOutsideBounds
from rio_tiler.models import ImageData

from earthx.access import download as dl
from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import LicenseInfo, LicenseTier
from earthx.readers.cog import AssetPath

GOOD_AOI = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}


def path(item_id: str = "ITEM1", asset: str = "visual") -> AssetPath:
    return AssetPath(
        f"/vsicurl/https://assets.example.invalid/{item_id}/{asset}.tif",
        dataset_id="test-dataset",
        item_id=item_id,
        asset=asset,
    )


class FakeReader:
    """A reader that never touches a network — ``feature()`` returns a small array."""

    calls: list[AssetPath] = []

    def __init__(self, src_path: AssetPath) -> None:
        self.src_path = src_path

    def __enter__(self) -> "FakeReader":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def feature(self, geometry: dict[str, Any], max_size: int | None = None) -> ImageData:
        FakeReader.calls.append(self.src_path)
        data = (np.random.default_rng(0).random((3, 16, 16)) * 255).astype("uint8")
        return ImageData(data, crs="EPSG:4326", bounds=(0, 0, 1, 1))


class OutsideReader(FakeReader):
    """Every read raises: the bbox prefilter passed but the footprint does not."""

    def feature(self, geometry: dict[str, Any], max_size: int | None = None) -> ImageData:
        raise PointOutsideBounds("outside")


@pytest.fixture(autouse=True)
def _reset_calls() -> None:
    FakeReader.calls = []


class TestParseAoiGeometry:
    def test_a_valid_polygon_is_accepted(self) -> None:
        geom = dl.parse_aoi_geometry(GOOD_AOI)
        assert geom.geom_type == "Polygon"

    def test_a_valid_multipolygon_is_accepted(self) -> None:
        multi = {"type": "MultiPolygon", "coordinates": [GOOD_AOI["coordinates"]]}
        geom = dl.parse_aoi_geometry(multi)
        assert geom.geom_type == "MultiPolygon"

    @pytest.mark.parametrize(
        "geometry",
        [
            {"type": "Point", "coordinates": [0, 0]},
            {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]},  # bowtie
            {"type": "Polygon", "coordinates": []},
            {"not": "geojson"},
            {"type": "Polygon", "coordinates": [[[0, 0]]]},
            "not even a mapping",
            None,
        ],
    )
    def test_a_malformed_or_wrong_typed_geometry_is_refused(self, geometry: object) -> None:
        with pytest.raises(dl.InvalidAoi):
            dl.parse_aoi_geometry(geometry)  # type: ignore[arg-type]


class TestFilterItemsIntersectingAoi:
    def test_keeps_only_the_items_whose_bbox_touches_the_aoi(self) -> None:
        aoi = dl.parse_aoi_geometry(GOOD_AOI)
        inside = {"id": "in", "bbox": [0.2, 0.2, 0.8, 0.8]}
        outside = {"id": "out", "bbox": [10, 10, 11, 11]}
        assert dl.filter_items_intersecting_aoi([inside, outside], aoi) == [inside]

    def test_an_item_without_a_usable_bbox_is_dropped_rather_than_guessed_at(self) -> None:
        aoi = dl.parse_aoi_geometry(GOOD_AOI)
        assert dl.filter_items_intersecting_aoi([{"id": "no-bbox"}], aoi) == []

    def test_no_match_is_an_empty_list_not_an_error(self) -> None:
        aoi = dl.parse_aoi_geometry(GOOD_AOI)
        assert dl.filter_items_intersecting_aoi([], aoi) == []


class TestCheckSizeCap:
    def test_a_single_item_and_asset_at_the_default_cap_passes(self) -> None:
        dl.check_size_cap(item_count=1, asset_count=1)

    def test_many_items_times_many_assets_is_refused_before_any_read(self) -> None:
        with pytest.raises(dl.AoiTooLarge):
            dl.check_size_cap(item_count=22, asset_count=13)

    def test_zero_items_is_refused(self) -> None:
        """The AOI-outside-items case is caught earlier, but the cap must not divide by it."""
        with pytest.raises(dl.AoiTooLarge):
            dl.check_size_cap(item_count=0, asset_count=1)

    def test_a_smaller_cap_can_be_passed_in(self) -> None:
        with pytest.raises(dl.AoiTooLarge):
            dl.check_size_cap(item_count=1, asset_count=1, max_side=64, max_bytes=100)


class TestCropAsset:
    def test_a_single_asset_reads_once(self) -> None:
        image = dl.crop_asset(FakeReader, [path()], GOOD_AOI)
        assert image.count == 3
        assert FakeReader.calls == [path()]

    def test_several_items_mosaic_and_the_first_valid_pixel_wins(self) -> None:
        image = dl.crop_asset(FakeReader, [path("ITEM1"), path("ITEM2")], GOOD_AOI)
        assert image.count == 3
        assert len(FakeReader.calls) == 2

    def test_a_single_item_outside_the_footprint_is_reported_as_aoi_outside_items(self) -> None:
        with pytest.raises(dl.AoiOutsideItems):
            dl.crop_asset(OutsideReader, [path()], GOOD_AOI)

    def test_every_candidate_outside_the_footprint_is_aoi_outside_items_even_mosaicked(self) -> None:
        with pytest.raises(dl.AoiOutsideItems):
            dl.crop_asset(OutsideReader, [path("ITEM1"), path("ITEM2")], GOOD_AOI)


class TestBuildNoticeText:
    def test_carries_attribution_and_the_full_terms_notice(self) -> None:
        """Otto, 22.09.2026: the platform offers no language choice, only English."""
        text = dl.build_notice_text(SENTINEL_2_L2A, item_ids=["ITEM1"])
        assert "Contains modified Copernicus Sentinel data" in text
        notice_en = SENTINEL_2_L2A.license.terms.notice["en"].format(
            terms_url=SENTINEL_2_L2A.license.terms.url
        )
        assert notice_en in text
        assert SENTINEL_2_L2A.license.terms.url in text
        assert "ITEM1" in text

    def test_a_dataset_without_terms_still_gets_a_notice_with_its_attribution(self) -> None:
        config = _dataset_without_terms()
        text = dl.build_notice_text(config, item_ids=["ITEM1"])
        assert config.title in text
        assert "ITEM1" in text


def _dataset_without_terms():
    from dataclasses import replace

    return replace(
        SENTINEL_2_L2A,
        license=LicenseInfo(
            spdx_id="CC0-1.0",
            name="CC0",
            url="https://creativecommons.org/publicdomain/zero/1.0/",
            commercial_use=True,
            distribution=True,
            derivatives=True,
            share_alike=False,
            attribution_required=False,
            tier=LicenseTier.PROCESSING,
            attribution_modified=None,
            attribution_unmodified=None,
            terms=None,
        ),
    )


class TestBuildDownloadZip:
    def test_the_zip_carries_one_cog_per_asset_and_the_notice_file(self) -> None:
        crops = [
            dl.AssetCrop(asset="visual", paths=(path(asset="visual"),)),
            dl.AssetCrop(asset="red", paths=(path(asset="red"),)),
        ]
        zip_bytes = dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=FakeReader,
            crops=crops,
            aoi_geometry=GOOD_AOI,
            item_ids=["ITEM1"],
        )
        with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
            names = set(archive.namelist())
            assert names == {"visual.tif", "red.tif", dl.NOTICE_FILENAME}
            notice = archive.read(dl.NOTICE_FILENAME).decode("utf-8")
            assert "Contains modified Copernicus Sentinel data" in notice
            # Each entry is a real, openable COG — not just bytes with a .tif name.
            # ImageData.to_raster adds a mask as a fourth, alpha band when the
            # source carries no explicit nodata value (rio-tiler's own default).
            with rasterio.io.MemoryFile(archive.read("visual.tif")) as memfile, memfile.open() as ds:
                assert ds.count == 4
                assert ds.profile["driver"] == "GTiff"

    def test_nothing_is_ever_written_outside_gdals_in_memory_filesystem(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D3: nichts wird auf Platte geschrieben. Every write-mode open must be `/vsimem/`."""
        real_open = rasterio.open
        write_paths: list[str] = []

        def guarded_open(path_arg, mode: str = "r", **kwargs: object):
            if "w" in mode:
                write_paths.append(str(path_arg))
                assert str(path_arg).startswith("/vsimem/"), f"wrote to a real path: {path_arg!r}"
            return real_open(path_arg, mode, **kwargs)

        monkeypatch.setattr(rasterio, "open", guarded_open)

        crops = [dl.AssetCrop(asset="visual", paths=(path(),))]
        dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=FakeReader,
            crops=crops,
            aoi_geometry=GOOD_AOI,
            item_ids=["ITEM1"],
        )
        assert write_paths, "the test did not actually exercise a write path"
