"""NM4-75: the rules of ``access.band_export`` that need no raster: names, plans, conversions, the table of the dialog."""

from __future__ import annotations

from typing import Any

import pytest

from earthx.access.band_export import (
    BandMeta,
    BandsFile,
    ExportPlanError,
    band_count,
    band_meta,
    band_meta_of_items,
    band_table,
    bands_text,
    is_geotiff,
    plan_files,
    resampling_for,
)

TIFF = "image/tiff; application=geotiff; profile=cloud-optimized"


def asset(name: str | None, gsd: float | None, *, wavelength: float | None = None, bands: int = 1, type_: str = TIFF) -> dict[str, Any]:
    entry: dict[str, Any] = {"type": type_, "raster:bands": [{"data_type": "uint16", "nodata": 0}] * bands}
    if gsd is not None:
        entry["gsd"] = gsd
    if name is not None:
        entry["eo:bands"] = [{"name": name, **({"center_wavelength": wavelength} if wavelength else {})}]
    return entry


def meta(key: str, res: float | None, *, categorical: bool = False, name: str | None = None) -> BandMeta:
    return band_meta({"assets": {key: asset(name or key.upper(), res)}}, key, categorical=categorical)


class TestTheNamesOfTheFiles:
    def test_a_file_is_named_by_its_name_common_name_and_resolution(self) -> None:
        item = {"assets": {"red": {**asset("B04", 10), "eo:bands": [{"name": "B04", "common_name": "red"}]}}}
        plan = plan_files("per_band", [band_meta(item, "red")])[0]
        assert (plan.name, plan.mask_name) == ("B04_red_10m.tif", "B04_red_10m_mask.tif")

    def test_a_common_name_equal_to_the_name_is_said_once_and_a_missing_resolution_is_left_out(self) -> None:
        item = {"assets": {"red": {**asset("red", None), "eo:bands": [{"name": "red", "common_name": "RED"}]}}}
        assert plan_files("per_band", [band_meta(item, "red")])[0].name == "red.tif"

    def test_two_bands_with_one_name_are_told_apart_by_their_asset(self) -> None:
        names = [p.name for p in plan_files("per_band", [meta("a", 10, name="X"), meta("b", 10, name="X")])]
        assert names == ["X_10m_a.tif", "X_10m_b.tif"]

    @pytest.mark.parametrize("name", ["../escape", "a b:c", "::", "ü"])
    def test_nothing_that_is_not_a_filename_reaches_the_archive(self, name: str) -> None:
        file = plan_files("per_band", [meta("k", 10, name=name)])[0].name
        assert "/" not in file and ":" not in file and " " not in file and not file.startswith(".")
        assert file.endswith("_10m.tif") or file == "10m.tif" or file.endswith(".tif")


class TestThePlans:
    def test_one_file_per_resolution_in_order_of_the_finest_first(self) -> None:
        plans = plan_files("per_resolution", [meta("a", 60), meta("b", 10), meta("c", 20), meta("d", 10)])
        assert [(p.name, p.assets) for p in plans] == [
            ("bands_10m.tif", ("b", "d")), ("bands_20m.tif", ("c",)), ("bands_60m.tif", ("a",)),
        ]  # fmt: skip

    def test_sizes_that_differ_in_the_last_digits_are_one_resolution(self) -> None:
        assert len(plan_files("per_resolution", [meta("a", 10.0), meta("b", 10.0000000001)])) == 1

    def test_bands_without_a_pixel_size_share_one_file(self) -> None:
        assert [p.name for p in plan_files("per_resolution", [meta("a", None), meta("b", None)])] == ["bands.tif"]

    def test_one_multi_band_file_holds_all_in_the_order_asked(self) -> None:
        plan = plan_files("multi_band", [meta("b", 20), meta("a", 10)], 20.0)
        assert [(p.name, p.assets, p.resolution_m) for p in plan] == [("bands_20m.tif", ("b", "a"), 20.0)]

    @pytest.mark.parametrize(
        ("form", "bands", "common", "message"),
        [
            ("per_band", [], None, "at least one"),
            ("per_band", [("a", 10), ("a", 10)], None, "twice"),
            ("multi_band", [("a", 10)], None, "common resolution"),
            ("multi_band", [("a", None)], 20.0, "known pixel size"),
            ("multi_band", [("a", 10)], float("nan"), "positive"),
            ("per_resolution", [("a", 10)], 10.0, "common resolution"),
            ("nothing", [("a", 10)], None, "form is one of"),
        ],
    )
    def test_what_is_no_plan_is_refused(self, form: str, bands: list[tuple[str, float | None]], common: float | None, message: str) -> None:
        with pytest.raises(ExportPlanError, match=message):
            plan_files(form, [meta(key, res) for key, res in bands], common)


class TestTheConversion:
    @pytest.mark.parametrize(
        ("categorical", "source", "target", "method"),
        [
            (False, 10, 10, "none"),
            (False, 10.0000001, 10, "none"),
            (False, 20, 10, "nearest"),  # finer: the values stay
            (True, 20, 10, "nearest"),
            (False, 10, 20, "average"),  # coarser: a measurement is averaged
            (True, 20, 60, "mode"),  # ... a class is not
        ],
    )
    def test_by_direction_and_kind(self, categorical: bool, source: float, target: float, method: str) -> None:
        assert resampling_for(meta("a", source, categorical=categorical), target) == method

    def test_nothing_is_converted_without_a_target_or_a_known_size(self) -> None:
        assert resampling_for(meta("a", 10), None) == "none"
        assert resampling_for(meta("a", None), 20) == "none"


class TestWhatIsRead:
    def test_a_band_of_the_wrong_type_in_the_json_is_refused_not_carried_on(self) -> None:
        good = meta("a", 10).to_json()
        assert BandMeta.from_json(good) == meta("a", 10)
        for field, value in {"resolution_m": "10", "categorical": "x", "asset": 3, "scale": True, "nodata": float("inf")}.items():
            with pytest.raises(ValueError):
                BandMeta.from_json({**good, field: value})
        with pytest.raises(KeyError):
            BandMeta.from_json({k: v for k, v in good.items() if k != "unit"})

    def test_band_count_reads_what_the_item_says_and_nothing_more(self) -> None:
        item = {"assets": {"one": asset("A", 10), "three": asset("B", 10, bands=3), "none": {"type": TIFF}}}
        assert (band_count(item, "one"), band_count(item, "three"), band_count(item, "none"), band_count(item, "gone")) == (1, 3, None, None)

    def test_a_geotiff_that_is_no_thumbnail(self) -> None:
        assert is_geotiff(asset("A", 10))
        assert not is_geotiff({"type": TIFF, "roles": ["thumbnail"]})
        assert not is_geotiff({"type": "image/jpeg"})
        assert not is_geotiff("image/tiff")


class TestTheTableOfTheDialog:
    def table(self, assets: dict[str, dict[str, Any]], **kw: Any) -> list[tuple[str, bool]]:
        result = band_table([{"assets": assets}], auxiliary=kw.get("auxiliary", ()), mask_asset=kw.get("mask"), unit_of=lambda a: None)
        return [(m.asset, ticked) for m, ticked in result]

    def test_spectral_bands_and_the_mask_layer_start_ticked_the_others_do_not(self) -> None:
        assets = {"red": asset("B04", 10, wavelength=0.66), "aot": asset("AOT", 10), "scl": asset("SCL", 20), "visual": asset(None, 10), "thumb": {"type": "image/jpeg"}}
        assert self.table(assets, auxiliary=["visual"], mask="scl") == [("red", True), ("aot", False), ("scl", True)]

    def test_a_dataset_with_no_spectral_band_starts_with_every_band_ticked(self) -> None:
        assert self.table({"data": asset("data", 30)}) == [("data", True)]
        assert self.table({"a": asset("a", 30), "b": asset("b", 30)}) == [("a", True), ("b", True)]

    def test_no_scene_no_table(self) -> None:
        assert band_table([], auxiliary=(), mask_asset=None, unit_of=lambda a: None) == []

    def test_the_finest_size_over_the_scenes_is_the_size_of_the_band(self) -> None:
        first = {"assets": {"red": asset("B04", 20)}}
        second = {"assets": {"red": asset("B04", 10)}}
        assert band_meta_of_items([first, second], "red").resolution_m == 10.0
        assert band_meta_of_items([first, {"assets": {}}], "red").resolution_m == 20.0
        assert band_meta_of_items([{"assets": {}}], "red").resolution_m is None  # asked for what no item has: a bare band


def test_bands_txt_writes_a_dash_for_what_the_item_does_not_say_and_the_default_scale() -> None:
    text = bands_text(
        title="T", form="per_band",
        files=[BandsFile("exports/x.tif", [band_meta({"assets": {"a": {"type": TIFF}}}, "a")], ["none"], [None])],
    )  # fmt: skip
    assert text.splitlines()[-1] == "1 | a | - | - | - | - | none | - | 1 | 0 | - | -"
