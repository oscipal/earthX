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


SQUARE_AOI_10KM = {
    # A ~10 km square near the equator, where a degree is close to 111.3 km —
    # easy to sanity-check by hand, and far from any of `estimate_output_dims`'
    # latitude-dependent branches.
    "type": "Polygon",
    "coordinates": [[[0, 0], [0.0898, 0], [0.0898, 0.0898], [0, 0.0898], [0, 0]]],
}


def item_with(asset: str = "visual", **asset_fields: Any) -> dict[str, Any]:
    """A minimal STAC item carrying only what `plan_outputs` looks at (F1/F2)."""
    return {"id": "ITEM1", "bbox": [-1, -1, 1, 1], "assets": {asset: asset_fields}}


class TestCheckItemCountCap:
    def test_at_the_default_cap_passes(self) -> None:
        dl.check_item_count_cap(dl.MAX_DOWNLOAD_ITEMS)

    def test_one_over_the_cap_is_refused(self) -> None:
        with pytest.raises(dl.AoiTooLarge, match="26 scenes"):
            dl.check_item_count_cap(dl.MAX_DOWNLOAD_ITEMS + 1)

    def test_zero_items_is_refused(self) -> None:
        """The AOI-outside-items case is caught earlier, but the cap must not divide by it."""
        with pytest.raises(dl.AoiTooLarge):
            dl.check_item_count_cap(0)

    def test_a_smaller_cap_can_be_passed_in(self) -> None:
        with pytest.raises(dl.AoiTooLarge):
            dl.check_item_count_cap(5, max_items=4)


class TestAssetGsd:
    def test_the_assets_own_gsd_wins(self) -> None:
        item = item_with(gsd=20, **{"raster:bands": [{"spatial_resolution": 10}]})
        assert dl._asset_gsd(item, "visual") == 20

    def test_raster_bands_spatial_resolution_is_the_fallback(self) -> None:
        item = item_with(**{"raster:bands": [{"spatial_resolution": 10}]})
        assert dl._asset_gsd(item, "visual") == 10

    def test_the_items_own_properties_gsd_is_the_last_resort(self) -> None:
        item = {"id": "i", "bbox": [-1, -1, 1, 1], "assets": {"visual": {}}, "properties": {"gsd": 60}}
        assert dl._asset_gsd(item, "visual") == 60

    @pytest.mark.parametrize("bad_gsd", [0, -10, float("nan"), float("inf"), "ten", None, [10]])
    def test_a_malformed_gsd_is_treated_as_unknown_not_divided_by(self, bad_gsd: object) -> None:
        """Otto's plan-step pass for zweckfremde Nutzung, M3-18: a `0` or negative
        `gsd`, a string, `NaN`/`inf` or the wrong type must never reach a division."""
        item = item_with(gsd=bad_gsd)
        assert dl._asset_gsd(item, "visual") is None

    def test_an_asset_or_item_missing_entirely_is_unknown(self) -> None:
        assert dl._asset_gsd({"id": "i", "bbox": [-1, -1, 1, 1], "assets": {}}, "visual") is None
        assert dl._asset_gsd({"id": "i", "bbox": [-1, -1, 1, 1]}, "visual") is None


class TestAssetBytesPerPixel:
    def test_raster_bands_dtypes_are_summed(self) -> None:
        item = item_with(**{"raster:bands": [{"data_type": "uint8"}] * 3})
        assert dl._asset_bytes_per_pixel(item, "visual") == 3

    def test_bands_is_the_fallback_key_earth_search_and_eopf_both_use(self) -> None:
        item = item_with(asset="red", **{"bands": [{"data_type": "uint16"}]})
        assert dl._asset_bytes_per_pixel(item, "red") == 2

    def test_an_unknown_dtype_string_falls_back_conservatively(self) -> None:
        item = item_with(**{"raster:bands": [{"data_type": "int12-does-not-exist"}]})
        assert dl._asset_bytes_per_pixel(item, "visual") == dl._FALLBACK_BYTES_PER_BAND

    def test_a_zarr_composite_key_is_counted_by_its_own_variables(self) -> None:
        """adr/0007 §12.11: `SR_10m:b04,b03,b02` names three variables in the key
        itself, even where — like every real EOPF item measured (plan §3) — the
        item carries no `raster:bands`/`bands` for it at all."""
        item = {"id": "i", "bbox": [-1, -1, 1, 1], "assets": {"SR_10m:b04,b03,b02": {}}}
        assert dl._asset_bytes_per_pixel(item, "SR_10m:b04,b03,b02") == 3 * dl._FALLBACK_BYTES_PER_BAND

    def test_nothing_at_all_falls_back_to_the_conservative_band_count_too(self) -> None:
        item = {"id": "i", "bbox": [-1, -1, 1, 1], "assets": {"visual": {}}}
        assert dl._asset_bytes_per_pixel(item, "visual") == dl._FALLBACK_BAND_COUNT * dl._FALLBACK_BYTES_PER_BAND


class TestEstimateOutputDims:
    def test_a_10km_square_at_10m_is_about_1000px_and_never_exceeds_the_real_read(self) -> None:
        """rio-tiler's own `feature(max_size=...)` against a real synthetic COG on the
        same ground, to make "never underestimate" (module docstring) a comparison,
        not a claim: this function must never come out smaller than what a real read
        of the same AOI produces (plan §5 "Ausgabeschätzung")."""
        height, width = dl.estimate_output_dims(dl.parse_aoi_geometry(SQUARE_AOI_10KM), gsd=10.0)
        assert 900 <= height <= 1100
        assert 900 <= width <= 1100

    def test_the_long_side_is_clipped_to_max_side_the_short_side_keeps_the_ratio(self) -> None:
        aoi = dl.parse_aoi_geometry(
            {"type": "Polygon", "coordinates": [[[0, 0], [0.2, 0], [0.2, 0.1], [0, 0.1], [0, 0]]]}
        )
        height, width = dl.estimate_output_dims(aoi, gsd=10.0, max_side=256)
        assert width == 256
        assert height < width

    def test_a_finer_gsd_never_produces_fewer_pixels_up_to_the_cap(self) -> None:
        aoi = dl.parse_aoi_geometry(SQUARE_AOI_10KM)
        coarse = dl.estimate_output_dims(aoi, gsd=100.0)
        fine = dl.estimate_output_dims(aoi, gsd=10.0)
        assert fine[0] >= coarse[0]
        assert fine[1] >= coarse[1]

    def test_an_aoi_straddling_the_equator_still_never_underestimates(self) -> None:
        """The widest possible metres/degree of longitude (`cos(0)`) is used
        whenever the AOI's own latitude could be as low as the equator — including
        when it straddles it, not only when it sits on one side (F1)."""
        aoi = dl.parse_aoi_geometry(
            {"type": "Polygon", "coordinates": [[[0, -0.05], [0.05, -0.05], [0.05, 0.05], [0, 0.05], [0, -0.05]]]}
        )
        height, width = dl.estimate_output_dims(aoi, gsd=10.0)
        assert width >= 500  # 0.05 deg * 111_320 m/deg / 10 m ~ 557 px


class TestPlanOutputsAndCheckOutputSizeCap:
    def test_a_small_known_asset_plans_well_under_the_cap(self) -> None:
        item = item_with(gsd=10, **{"raster:bands": [{"data_type": "uint8"}] * 3})
        aoi = dl.parse_aoi_geometry(SQUARE_AOI_10KM)
        planned = dl.plan_outputs([item], ["visual"], aoi)
        assert len(planned) == 1
        assert planned[0].total_bytes < dl.MAX_TOTAL_OUTPUT_BYTES
        dl.check_output_size_cap(planned)  # must not raise

    def test_an_asset_with_no_size_metadata_at_all_falls_back_to_the_worst_case(self) -> None:
        item = {"id": "i", "bbox": [-1, -1, 1, 1], "assets": {"thumbnail": {}}}
        aoi = dl.parse_aoi_geometry(SQUARE_AOI_10KM)
        planned = dl.plan_outputs([item], ["thumbnail"], aoi)
        assert planned[0].width == dl.MAX_OUTPUT_SIDE_PX
        assert planned[0].height == dl.MAX_OUTPUT_SIDE_PX
        assert planned[0].bytes_per_pixel == dl._FALLBACK_BAND_COUNT * dl._FALLBACK_BYTES_PER_BAND

    def test_the_finest_gsd_among_several_items_is_used(self) -> None:
        """A mosaic is still one file (module docstring) — the size that matters is
        the most pixels any contributing item could produce, not their sum."""
        fine = item_with(gsd=10, **{"raster:bands": [{"data_type": "uint8"}]})
        coarse = {**item_with(gsd=60, **{"raster:bands": [{"data_type": "uint8"}]}), "id": "ITEM2"}
        aoi = dl.parse_aoi_geometry(SQUARE_AOI_10KM)
        only_coarse = dl.plan_outputs([coarse], ["visual"], aoi)[0]
        both = dl.plan_outputs([fine, coarse], ["visual"], aoi)[0]
        assert both.total_bytes == dl.plan_outputs([fine], ["visual"], aoi)[0].total_bytes
        assert both.total_bytes >= only_coarse.total_bytes

    def test_a_request_that_would_exceed_the_cap_is_refused_with_a_readable_message(self) -> None:
        import re

        item = {"id": "i", "bbox": [-1, -1, 1, 1], "assets": {"a": {}, "b": {}, "c": {}}}
        aoi = dl.parse_aoi_geometry(SQUARE_AOI_10KM)
        planned = dl.plan_outputs([item], ["a", "b", "c"], aoi)
        with pytest.raises(dl.AoiTooLarge) as excinfo:
            dl.check_output_size_cap(planned)
        message = str(excinfo.value)
        assert "MB" in message
        # A rounded MB figure, never a raw byte count (five digits or more) and no
        # AOI coordinate — the same requirement the route test asserts on the log.
        assert not re.search(r"\d{5,}", message)

    def test_no_planned_output_is_refused(self) -> None:
        with pytest.raises(dl.AoiTooLarge):
            dl.check_output_size_cap([])


class HalfMaskedReader(FakeReader):
    """The right half of the array is masked, as if the source had no data
    there — used with :class:`FillingReader` to prove a second item is only
    read when the first does not finish filling the AOI (F4, M3-18)."""

    calls: list[AssetPath] = []

    def feature(self, geometry: dict[str, Any], max_size: int | None = None) -> ImageData:
        HalfMaskedReader.calls.append(self.src_path)
        data = np.full((3, 16, 16), 10, dtype="uint8")
        mask = np.zeros((3, 16, 16), dtype=bool)
        mask[:, :, 8:] = True
        return ImageData(np.ma.MaskedArray(data, mask=mask), crs="EPSG:4326", bounds=(0, 0, 1, 1))


class FillingReader(FakeReader):
    calls: list[AssetPath] = []

    def feature(self, geometry: dict[str, Any], max_size: int | None = None) -> ImageData:
        FillingReader.calls.append(self.src_path)
        data = np.full((3, 16, 16), 20, dtype="uint8")
        return ImageData(data, crs="EPSG:4326", bounds=(0, 0, 1, 1))


def _dispatch(readers: dict[str, type]):
    """A single ``open_reader`` that opens item ``X``'s path with ``readers[X]``."""

    def open_reader(src_path: AssetPath) -> FakeReader:
        return readers[src_path.item_id](src_path)

    return open_reader


class TestCropAsset:
    def test_a_single_asset_reads_once(self) -> None:
        image = dl.crop_asset(FakeReader, [path()], GOOD_AOI)
        assert image.count == 3
        assert FakeReader.calls == [path()]

    def test_a_second_item_is_never_opened_once_the_first_fills_the_aoi(self) -> None:
        """F4 (M3-18): ``threads=1`` reads items one at a time and stops as soon as
        the mosaic is done — measured (plan §3) to be what keeps memory flat
        regardless of how many items a request names."""
        image = dl.crop_asset(FakeReader, [path("ITEM1"), path("ITEM2")], GOOD_AOI)
        assert image.count == 3
        assert len(FakeReader.calls) == 1

    def test_a_second_item_is_read_when_the_first_does_not_fill_the_aoi(self) -> None:
        HalfMaskedReader.calls, FillingReader.calls = [], []
        readers = {"ITEM1": HalfMaskedReader, "ITEM2": FillingReader}
        image = dl.crop_asset(_dispatch(readers), [path("ITEM1"), path("ITEM2")], GOOD_AOI)

        assert HalfMaskedReader.calls == [path("ITEM1")]
        assert FillingReader.calls == [path("ITEM2")]
        # First valid pixel wins (adr/0006 §3.5): item 1's own data survives on its
        # unmasked left half, item 2 only fills the right half item 1 left empty.
        assert (image.array[:, :, 0] == 10).all()
        assert (image.array[:, :, 15] == 20).all()

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
            # No alpha band regardless of the source having no nodata (F3, M3-18):
            # the AOI mask travels as a GDAL-internal mask band instead, the same
            # band count whether one item or a mosaic produced it.
            with rasterio.io.MemoryFile(archive.read("visual.tif")) as memfile, memfile.open() as ds:
                assert ds.count == 3
                assert ds.profile["driver"] == "GTiff"
                # FakeReader.feature never masks anything, so every pixel is valid.
                assert (ds.dataset_mask() == 255).all()

    def test_nothing_is_ever_written_outside_gdals_in_memory_filesystem(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D3: nichts wird auf Platte geschrieben. Every ``MemoryFile`` this module
        opens must carry rio-tiler's own ``/vsimem/`` virtual filesystem name —
        the actual guarantee behind "nothing touches a real path", checked directly
        rather than through ``rasterio.open`` (``MemoryFile.open()`` never calls it,
        so patching it there would silently stop testing anything, plan §5)."""
        real_memory_file = dl.MemoryFile
        created_names: list[str] = []

        def tracked_memory_file(*args: object, **kwargs: object):
            memory_file = real_memory_file(*args, **kwargs)
            created_names.append(memory_file.name)
            return memory_file

        monkeypatch.setattr(dl, "MemoryFile", tracked_memory_file)

        crops = [dl.AssetCrop(asset="visual", paths=(path(),))]
        dl.build_download_zip(
            config=SENTINEL_2_L2A,
            open_reader=FakeReader,
            crops=crops,
            aoi_geometry=GOOD_AOI,
            item_ids=["ITEM1"],
        )
        assert created_names, "the test did not actually exercise a write path"
        assert all(name.startswith("/vsimem/") for name in created_names)


class TestTheNameACropGetsInsideTheZip:
    """M2-10: the asset key travels into the archive, and for a Zarr dataset it is
    not a plain word — ``SR_10m:b04,b03,b02`` names the group the item advertises
    plus the variables to composite (adr/0007 §12.11). A ``:`` is not a legal
    filename on Windows, so the archive would fail to extract or be silently
    renamed where it matters least: on the user's disk."""

    def test_a_plain_asset_key_is_left_alone(self) -> None:
        assert dl.crop_filename("visual") == "visual.tif"

    def test_a_zarr_group_key_loses_its_separators(self) -> None:
        assert dl.crop_filename("SR_10m:b04,b03,b02") == "SR_10m_b04_b03_b02.tif"

    @pytest.mark.parametrize(
        ("asset", "expected"),
        [
            ("a/b", "a_b.tif"),  # a path separator would open a directory in the ZIP
            ("../escape", "escape.tif"),  # ... and this one would leave it entirely
            ("b04  b03", "b04_b03.tif"),  # a run collapses, it does not repeat
            ("::::", "asset.tif"),  # nothing left over is still a nameable file
            ("", "asset.tif"),
        ],
    )
    def test_nothing_outside_a_plain_name_survives(self, asset: str, expected: str) -> None:
        assert dl.crop_filename(asset) == expected

    def test_two_different_keys_can_clean_to_the_same_name(self) -> None:
        """A known, unresolved collision, pinned so that whoever hits it sees it here
        first: `b04:b03` and `b04,b03` are different asset keys and become the same
        file, which a ZIP allows and no user could untangle.

        Deduplicating the request (`api.tiler.download_crop`) removes the case that
        can actually happen — the same key asked for twice — but not this one. It
        needs two keys that differ only in a character the cleaning removes, and no
        registry entry in M2 carries such a pair.
        """
        assert dl.crop_filename("b04:b03") == dl.crop_filename("b04,b03")

    def test_the_notice_names_the_key_the_cleaned_file_came_from(self) -> None:
        notice = dl.build_notice_text(
            SENTINEL_2_L2A, item_ids=["ITEM1"], assets=["SR_10m:b04,b03,b02"]
        )
        assert "SR_10m:b04,b03,b02" in notice
        assert "SR_10m_b04_b03_b02.tif" in notice

    def test_a_crop_without_named_assets_keeps_the_notice_as_it_was(self) -> None:
        assert "Assets:" not in dl.build_notice_text(SENTINEL_2_L2A, item_ids=["ITEM1"])
