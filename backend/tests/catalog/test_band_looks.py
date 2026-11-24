"""The look each band starts with (M5-60): from the source or by hand where an entry writes one, else from the standard
picture, the rule by unit or the default; published per band in the collection."""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from earthx.access.colormaps import COLORMAPS
from earthx.catalog.collection import to_stac_collection
from earthx.catalog.entry_files import EntryFileError, load_entry, to_plain
from earthx.catalog.registry import (
    DEFAULT_LOOK,
    UNIT_LOOKS,
    UNSCALED,
    AssetSelection,
    BandClass,
    BandClasses,
    BandLook,
    BandScaling,
    ClassColours,
    ConfigError,
    DefaultRender,
    Look,
    LookOrigin,
)
from tests.catalog.entries import COP_DEM_GLO_30, REGISTRY


def _looks(entry) -> dict[str, tuple[Look, LookOrigin]]:
    return {key: (resolved.look, resolved.origin) for key in entry.band_units if (resolved := entry.look_of(key))}


def _one_band_standard(
    config, band: str = "red", colormap: str | None = "magma", rescale=((0.0, 50.0),)
) -> DefaultRender:
    return DefaultRender(
        title="One band",
        assets=(band,),
        rescale=rescale,
        colormap_name=colormap,
        expression=None,
        resampling="nearest",
        asset_selection=AssetSelection.ALL,
    )


class TestTheEntries:
    def test_meteoswiss_draws_its_temperatures_like_the_standard_and_humidity_on_its_whole_range(self) -> None:
        looks = _looks(REGISTRY.get("meteoswiss-daily-1km"))
        temperature = (Look("rdbu_r", "fixed", -20.0, 30.0), LookOrigin.STANDARD)
        assert looks["TabsD"] == looks["TminD"] == looks["TmaxD"] == temperature
        assert looks["SrelD"] == (Look("viridis", "fixed", 0.0, 100.0), LookOrigin.UNIT)

    def test_sentinel_2_draws_every_band_in_colour_and_its_probabilities_on_0_to_100(self) -> None:
        looks = _looks(REGISTRY.get("sentinel-2-c1-l2a"))
        for band in ("coastal", "blue", "red", "nir", "swir22", "aot"):
            assert looks[band] == (Look("viridis"), LookOrigin.UNIT)
        assert looks["wvp"] == (DEFAULT_LOOK, LookOrigin.DEFAULT)
        assert looks["cloud"] == looks["snow"] == (Look("viridis", "fixed", 0.0, 100.0), LookOrigin.UNIT)
        assert {"scl", "visual", "preview"}.isdisjoint(looks)

    def test_radar_numbers_stay_grey_on_the_measured_scale(self) -> None:
        looks = _looks(REGISTRY.get("sentinel-1-grd"))
        assert {key: look for key, (look, _) in looks.items()} == {
            band: Look("greys_r") for band in ("vv", "vh", "hh", "hv")
        }

    def test_the_second_height_of_swissalti3d_is_drawn_like_the_first(self) -> None:
        looks = _looks(REGISTRY.get("swissalti3d"))
        assert looks["dtm_2m"] == looks["dtm"] == (Look("terrain", "fixed", 0.0, 5000.0), LookOrigin.STANDARD)

    @pytest.mark.parametrize("entry", REGISTRY, ids=lambda entry: entry.dataset_id)
    def test_no_entry_writes_a_look_and_every_band_with_values_has_one(self, entry) -> None:
        assert dict(entry.band_looks) == {}
        for key in entry.band_units:
            has_one = key not in entry.auxiliary_assets and key not in entry.band_classes
            assert (entry.look_of(key) is not None) is has_one, key

    @pytest.mark.parametrize("entry", REGISTRY, ids=lambda entry: entry.dataset_id)
    def test_the_tiler_knows_every_colormap_of_a_look(self, entry) -> None:
        for look, _ in _looks(entry).values():
            assert look.colormap in COLORMAPS.list()

    def test_the_tiler_knows_every_colormap_of_the_rule(self) -> None:
        for look in (*UNIT_LOOKS.values(), DEFAULT_LOOK):
            assert look.colormap in COLORMAPS.list()


class TestTheOrder:
    def test_a_unit_of_the_rule_takes_its_look(self, valid_config) -> None:
        entry = replace(valid_config, band_units={**valid_config.band_units, "red": "%"})
        resolved = entry.look_of("red")
        assert (resolved.look, resolved.origin) == (Look("viridis", "fixed", 0.0, 100.0), LookOrigin.UNIT)

    @pytest.mark.parametrize("unit", ["cm", "W m-2", None])
    def test_any_other_unit_takes_the_default(self, valid_config, unit) -> None:
        entry = replace(valid_config, band_units={**valid_config.band_units, "red": unit})
        resolved = entry.look_of("red")
        assert (resolved.look, resolved.origin) == (DEFAULT_LOOK, LookOrigin.DEFAULT)

    def test_the_standard_picture_of_one_band_gives_its_look_to_every_band_of_its_unit(self, valid_config) -> None:
        entry = replace(valid_config, default_render=_one_band_standard(valid_config))
        for band in ("red", "green", "blue"):
            resolved = entry.look_of(band)
            assert (resolved.look, resolved.origin) == (Look("magma", "fixed", 0.0, 50.0), LookOrigin.STANDARD)

    def test_a_band_of_another_unit_than_the_standard_takes_the_rule(self, valid_config) -> None:
        entry = replace(
            valid_config,
            default_render=_one_band_standard(valid_config),
            band_units={**valid_config.band_units, "blue": "%"},
        )
        assert entry.look_of("blue").origin is LookOrigin.UNIT

    def test_a_band_of_no_known_unit_does_not_share_the_look_of_a_standard_of_no_known_unit(self, valid_config) -> None:
        entry = replace(
            valid_config,
            default_render=_one_band_standard(valid_config),
            band_units={"red": None, "green": None, "blue": "1"},
        )
        assert entry.look_of("red").origin is LookOrigin.STANDARD
        assert entry.look_of("green").origin is LookOrigin.DEFAULT

    @pytest.mark.parametrize(
        "render",
        [
            {"colormap": None},
            {"rescale": None},
            {"rescale": ((0.0, 1.0), (0.0, 2.0))},
        ],
        ids=["no colormap", "no range", "a range per channel"],
    )
    def test_a_standard_without_colormap_and_one_range_gives_no_look(self, valid_config, render) -> None:
        entry = replace(valid_config, default_render=_one_band_standard(valid_config, **render))
        assert entry.look_of("green").origin is LookOrigin.UNIT

    def test_a_standard_of_three_bands_gives_no_look(self, valid_config) -> None:
        assert valid_config.look_of("red").origin is LookOrigin.UNIT

    def test_a_look_from_the_source_wins_over_the_standard_and_takes_the_colormap_of_the_rule(
        self, valid_config
    ) -> None:
        entry = replace(
            valid_config,
            default_render=_one_band_standard(valid_config),
            band_looks={"green": BandLook(LookOrigin.STAC, "fixed", 0.0, 0.4)},
        )
        resolved = entry.look_of("green")
        assert (resolved.look, resolved.origin) == (Look("viridis", "fixed", 0.0, 0.4), LookOrigin.STAC)

    def test_a_look_from_the_source_keeps_a_colormap_it_names(self, valid_config) -> None:
        entry = replace(valid_config, band_looks={"green": BandLook(LookOrigin.STAC, "fixed", 0.0, 0.4, "greens")})
        assert entry.look_of("green").look == Look("greens", "fixed", 0.0, 0.4)

    def test_a_look_by_hand_is_taken_as_written(self, valid_config) -> None:
        entry = replace(
            valid_config, band_looks={"red": BandLook(LookOrigin.MANUAL, "percentiles", 0.0, 100.0, "reds")}
        )
        resolved = entry.look_of("red")
        assert (resolved.look, resolved.origin) == (Look("reds", "percentiles", 0.0, 100.0), LookOrigin.MANUAL)

    def test_no_look_for_a_band_of_classes_an_auxiliary_asset_or_an_unknown_band(self, valid_config) -> None:
        entry = replace(
            valid_config,
            band_units={**valid_config.band_units, "red": None, "thumb": None},
            band_descriptions={**valid_config.band_descriptions, "red": "Classes"},
            band_classes={"red": BandClasses(ClassColours.PALETTE, None, (BandClass(1, "Water"),))},
            auxiliary_assets=("thumb",),
        )
        assert entry.look_of("red") is None
        assert entry.look_of("thumb") is None
        assert entry.look_of("nir") is None


class TestTheScaling:
    """M5-60 F8 and A8 (Otto, 24.11.2026): the range of the standard picture is in the stored numbers its tiles draw, a
    look in the unit of the band."""

    REFLECTANCE = BandScaling(0.0001, -0.1)

    def _first_present(self, rescale) -> DefaultRender:
        return DefaultRender(
            title="Co-polarisation",
            assets=("red", "green"),
            rescale=rescale,
            colormap_name="magma",
            expression=None,
            resampling="nearest",
            asset_selection=AssetSelection.FIRST_PRESENT,
        )

    def test_sentinel_2_names_the_scaling_of_its_source(self) -> None:
        entry = REGISTRY.get("sentinel-2-c1-l2a")
        for band in ("coastal", "red", "nir08", "swir22"):
            assert entry.scaling_of(band) == self.REFLECTANCE
        assert entry.scaling_of("aot") == entry.scaling_of("wvp") == BandScaling(0.001, 0.0)
        for band in ("cloud", "snow", "scl"):
            assert entry.scaling_of(band) == UNSCALED

    def test_a_band_without_scaling_is_stored_in_its_unit(self, valid_config) -> None:
        assert valid_config.scaling_of("red") == UNSCALED

    def test_the_standard_range_of_a_scaled_band_is_turned_into_its_unit(self, valid_config) -> None:
        entry = replace(
            valid_config,
            default_render=_one_band_standard(valid_config, rescale=((1000.0, 4000.0),)),
            band_scaling={"red": self.REFLECTANCE},
        )
        for band in ("red", "green", "blue"):
            resolved = entry.look_of(band)
            assert (resolved.look, resolved.origin) == (Look("magma", "fixed", 0.0, 0.3), LookOrigin.STANDARD)
        published = {band["name"]: band for band in to_stac_collection(entry)["earthx:bands"]}
        assert published["green"]["earthx:look"] == {"colormap": "magma", "scale": "fixed", "low": 0.0, "high": 0.3}

    def test_the_first_present_of_several_assets_gives_its_look_where_their_scaled_ranges_agree(self, valid_config) -> None:
        entry = replace(
            valid_config,
            default_render=self._first_present(((1000.0, 4000.0), (0.0, 0.3))),
            band_scaling={"red": self.REFLECTANCE},
        )
        assert entry.look_of("blue").look == Look("magma", "fixed", 0.0, 0.3)

    def test_scaled_ranges_that_differ_stop_the_entry(self, valid_config) -> None:
        with pytest.raises(ConfigError, match=r"differ once scaled \(red 0 to 0.3, green 0 to 3000\).*set band_looks for blue, green, red"):
            replace(
                valid_config,
                default_render=self._first_present(((1000.0, 4000.0), (1000.0, 4000.0))),
                band_scaling={"red": self.REFLECTANCE, "green": BandScaling(1.0, -1000.0)},
            )

    def test_looks_of_their_own_let_the_entry_load(self, valid_config) -> None:
        own = BandLook(LookOrigin.STAC, "fixed", 0.0, 0.3)
        entry = replace(
            valid_config,
            default_render=self._first_present(((1000.0, 4000.0), (1000.0, 4000.0))),
            band_scaling={"red": self.REFLECTANCE},
            band_looks={"red": own, "green": own, "blue": own},
        )
        assert {entry.look_of(band).origin for band in ("red", "green", "blue")} == {LookOrigin.STAC}

    def test_a_missing_look_of_its_own_still_stops_the_entry(self, valid_config) -> None:
        own = BandLook(LookOrigin.STAC, "fixed", 0.0, 0.3)
        with pytest.raises(ConfigError, match="set band_looks for blue$"):
            replace(
                valid_config,
                default_render=self._first_present(((1000.0, 4000.0), (1000.0, 4000.0))),
                band_scaling={"red": self.REFLECTANCE},
                band_looks={"red": own, "green": own},
            )

    @pytest.mark.parametrize(
        ("scaling", "match"),
        [
            ({"nir": BandScaling(0.0001, -0.1)}, "no band of band_units"),
            ({"red": BandScaling(0.0, 0.0)}, "scale above 0"),
            ({"red": BandScaling(-0.0001, 0.0)}, "scale above 0"),
            ({"red": BandScaling(math.nan, 0.0)}, "finite scale"),
            ({"red": BandScaling(0.0001, math.inf)}, "finite offset"),
        ],
        ids=["unknown band", "zero", "negative", "nan", "infinite offset"],
    )
    def test_a_wrong_scaling_is_refused(self, valid_config, scaling, match) -> None:
        with pytest.raises(ConfigError, match=match):
            replace(valid_config, band_scaling=scaling)

    def test_a_band_of_classes_has_no_scaling(self, valid_config) -> None:
        with pytest.raises(ConfigError, match="no band of band_units"):
            replace(
                valid_config,
                band_units={**valid_config.band_units, "red": None},
                band_classes={"red": BandClasses(ClassColours.PALETTE, None, (BandClass(1, "Water"),))},
                band_scaling={"red": BandScaling(2.0, 0.0)},
            )

    def test_a_scaling_is_read_strictly_from_the_file(self, tmp_path: Path) -> None:
        data = to_plain(COP_DEM_GLO_30)
        data["band_scaling"] = {"data": {"scale": 0.5, "offset": -10}}
        path = tmp_path / f"{COP_DEM_GLO_30.dataset_id}.yaml"
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        assert load_entry(path).scaling_of("data") == BandScaling(0.5, -10.0)
        data["band_scaling"] = {"data": {"scale": "0.5", "offset": 0}}
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        with pytest.raises(EntryFileError):
            load_entry(path)


class TestTheChecks:
    @pytest.mark.parametrize(
        ("looks", "match"),
        [
            ({"nir": BandLook(LookOrigin.STAC, "measured")}, "no band of band_units"),
            ({"r*": BandLook(LookOrigin.STAC, "measured")}, "no band of band_units"),
            ({"red": BandLook(LookOrigin.UNIT, "measured")}, "comes from the source"),
            ({"red": BandLook(LookOrigin.STANDARD, "measured")}, "comes from the source"),
            ({"red": BandLook(LookOrigin.MANUAL, "measured")}, "names its colormap"),
            ({"red": BandLook(LookOrigin.STAC, "measured", colormap=" ")}, "names a colormap or none"),
            ({"red": BandLook(LookOrigin.STAC, "fixed", 1.0, 1.0)}, "no complete look"),
            ({"red": BandLook(LookOrigin.STAC, "fixed", 0.0)}, "no complete look"),
            ({"red": BandLook(LookOrigin.STAC, "measured", 0.0, 1.0)}, "no complete look"),
            ({"red": BandLook(LookOrigin.STAC, "fixed", 0.0, math.inf)}, "finite numbers"),
            ({"red": BandLook(LookOrigin.STAC, "fixed", math.nan, 1.0)}, "finite numbers"),
            ({"red": BandLook(LookOrigin.STAC, "percentiles", -1.0, 100.0)}, "no complete look"),
            ({"red": BandLook(LookOrigin.STAC, "percentiles", 5.0, 95.0)}, "0 to 100 or 2 to 98"),
        ],
        ids=[
            "unknown band",
            "pattern",
            "unit written",
            "standard written",
            "by hand without colormap",
            "blank colormap",
            "empty range",
            "one end",
            "measured with ends",
            "infinite end",
            "nan end",
            "percentiles below 0",
            "percentiles the measure does not know",
        ],
    )
    def test_a_wrong_look_is_refused(self, valid_config, looks, match) -> None:
        with pytest.raises(ConfigError, match=match):
            replace(valid_config, band_looks=looks)

    def test_a_band_of_classes_takes_no_look(self, valid_config) -> None:
        with pytest.raises(ConfigError, match="no band of band_units"):
            replace(
                valid_config,
                band_units={**valid_config.band_units, "red": None},
                band_classes={"red": BandClasses(ClassColours.PALETTE, None, (BandClass(1, "Water"),))},
                band_looks={"red": BandLook(LookOrigin.STAC, "measured")},
            )

    def test_an_auxiliary_asset_takes_no_look(self, valid_config) -> None:
        with pytest.raises(ConfigError, match="no band of band_units"):
            replace(
                valid_config,
                band_units={**valid_config.band_units, "thumb": None},
                auxiliary_assets=("thumb",),
                band_looks={"thumb": BandLook(LookOrigin.STAC, "measured")},
            )


class TestTheFile:
    def _write(self, tmp_path: Path, data: dict) -> Path:
        path = tmp_path / f"{COP_DEM_GLO_30.dataset_id}.yaml"
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return path

    def test_a_look_of_the_source_is_read_from_the_file_and_written_back(self, tmp_path: Path) -> None:
        data = to_plain(COP_DEM_GLO_30)
        data["band_looks"] = {"data": {"origin": "stac", "scale": "fixed", "low": -100, "high": 4000.5}}
        entry = load_entry(self._write(tmp_path, data))
        assert entry.look_of("data").look == Look("terrain", "fixed", -100.0, 4000.5)
        assert to_plain(entry)["band_looks"] == {
            "data": {"origin": "stac", "scale": "fixed", "low": -100, "high": 4000.5}
        }

    @pytest.mark.parametrize(
        "look",
        [
            {"origin": "guess", "scale": "measured"},
            {"origin": "stac", "scale": "stretched"},
            {"origin": "stac", "scale": "measured", "gamma": 2},
            {"origin": "stac", "scale": "fixed", "low": "0", "high": 1},
        ],
        ids=["unknown origin", "unknown scale", "unknown field", "a number as text"],
    )
    def test_a_look_is_read_strictly(self, tmp_path: Path, look: dict) -> None:
        data = to_plain(COP_DEM_GLO_30)
        data["band_looks"] = {"data": look}
        with pytest.raises(EntryFileError):
            load_entry(self._write(tmp_path, data))


class TestTheCollection:
    def test_every_band_with_values_publishes_its_look_and_where_it_came_from(self) -> None:
        bands = {
            band["name"]: band for band in to_stac_collection(REGISTRY.get("meteoswiss-daily-1km"))["earthx:bands"]
        }
        assert bands["SrelD"]["earthx:look"] == {"colormap": "viridis", "scale": "fixed", "low": 0.0, "high": 100.0}
        assert bands["SrelD"]["earthx:look_origin"] == "unit"
        assert bands["TminD"]["earthx:look_origin"] == "standard"

    def test_a_measured_look_has_no_ends(self) -> None:
        bands = {band["name"]: band for band in to_stac_collection(REGISTRY.get("sentinel-2-c1-l2a"))["earthx:bands"]}
        assert bands["red"]["earthx:look"] == {"colormap": "viridis", "scale": "measured"}

    def test_a_band_of_classes_publishes_no_look(self) -> None:
        bands = {band["name"]: band for band in to_stac_collection(REGISTRY.get("sentinel-2-c1-l2a"))["earthx:bands"]}
        assert "earthx:look" not in bands["scl"] and "earthx:look_origin" not in bands["scl"]
        assert "classification:classes" in bands["scl"]
