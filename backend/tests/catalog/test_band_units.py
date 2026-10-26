"""The unit per asset in the registry (plan M4-19b §3.2, adr/0014 §15n)."""

from __future__ import annotations

from dataclasses import replace
from fnmatch import fnmatchcase
from types import MappingProxyType

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A
from earthx.catalog.registry import VARIABLE_LIST_SEPARATOR, ConfigError, DatasetConfig, single_asset_keys
from earthx.readers import zarr_reader
from tests.catalog.synthetic_zarr import SYNTHETIC_ZARR, TEST_ENTRIES


class TestTheEntries:
    @pytest.mark.parametrize(
        ("entry", "asset", "unit"),
        [
            (SENTINEL_2_L2A, "red", "1"),
            (SENTINEL_2_L2A, "swir22", "1"),
            (SENTINEL_2_L2A, "scl", None),
            (SENTINEL_2_L2A, "visual", None),
            (SYNTHETIC_ZARR, "SR_10m:b04", "1"),
            (SYNTHETIC_ZARR, "SR_60m:b09", "1"),
            (SYNTHETIC_ZARR, "SCL_20m:scl", None),
            (COP_DEM_GLO_30, "data", "m"),
        ],
    )
    def test_the_units_the_entries_name(self, entry, asset, unit) -> None:
        assert entry.band_unit(asset) == unit

    @pytest.mark.parametrize("asset", ["aot", "wvp", "nothing-of-the-kind"])
    def test_an_asset_the_entry_does_not_list_is_unknown_not_guessed(self, asset) -> None:
        assert SENTINEL_2_L2A.band_unit(asset) is None

    def test_a_group_pattern_is_not_an_exact_key_of_another_group(self) -> None:
        assert SYNTHETIC_ZARR.band_unit("ATM_10m:aot") is None

    @pytest.mark.parametrize("entry", TEST_ENTRIES, ids=lambda entry: entry.dataset_id)
    def test_the_default_render_and_the_mask_each_have_a_key(self, entry) -> None:
        separator = entry.zarr.variable_separator if entry.zarr is not None else None
        wanted = list(entry.default_render.assets) + ([entry.mask.asset] if entry.mask is not None else [])
        for asset in wanted:
            for key in single_asset_keys(asset, separator):
                assert key in entry.band_units or any(fnmatchcase(key, pattern) for pattern in entry.band_units), key


class TestLookup:
    def test_the_exact_key_goes_before_a_pattern(self, valid_config) -> None:
        entry = replace(valid_config, band_units={"red": None, "r*": "1", "green": "1", "blue": "1"})
        assert entry.band_unit("red") is None
        assert entry.band_unit("rededge1") == "1"

    def test_patterns_that_do_not_overlap_may_stand_together(self, valid_config) -> None:
        entry = replace(valid_config, band_units={"r*": "1", "g*": "2", "blue": "1"})
        assert (entry.band_unit("red"), entry.band_unit("green")) == ("1", "2")

    def test_the_mapping_cannot_be_changed_through_the_entry(self, valid_config) -> None:
        assert isinstance(valid_config.band_units, MappingProxyType)
        with pytest.raises(TypeError):
            valid_config.band_units["red"] = "m"  # type: ignore[index]

    def test_the_entry_does_not_share_the_dict_it_was_built_from(self, valid_config) -> None:
        source = {"red": "1", "green": "1", "blue": "1"}
        entry = replace(valid_config, band_units=source)
        source["red"] = "m"
        assert entry.band_unit("red") == "1"


class TestSingleKeys:
    def test_a_cog_key_is_itself(self) -> None:
        assert single_asset_keys("red", None) == ["red"]

    def test_a_zarr_key_is_one_per_variable(self) -> None:
        assert single_asset_keys("SR_10m:b04,b03,b02", ":") == ["SR_10m:b04", "SR_10m:b03", "SR_10m:b02"]

    def test_a_zarr_key_without_a_variable_is_itself(self) -> None:
        assert single_asset_keys("SR_10m", ":") == ["SR_10m"]

    def test_the_list_separator_is_the_readers(self) -> None:
        assert VARIABLE_LIST_SEPARATOR == zarr_reader.VARIABLE_LIST_SEPARATOR


class TestConsistency:
    @pytest.mark.parametrize(
        ("units", "match"),
        [
            ({"red": "1", "green": "1"}, "no entry for 'blue'"),
            ({"": "1", "red": "1", "green": "1", "blue": "1"}, "keyed by an asset"),
            ({" red": "1", "red": "1", "green": "1", "blue": "1"}, "keyed by an asset"),
            ({"red": "", "green": "1", "blue": "1"}, "non-blank text or None"),
            ({"red": "  ", "green": "1", "blue": "1"}, "non-blank text or None"),
            ({"red": " 1", "green": "1", "blue": "1"}, "non-blank text or None"),
            ({"red": 1, "green": "1", "blue": "1"}, "non-blank text or None"),
            ({"red": "m" * 33, "green": "1", "blue": "1"}, "longer than 32"),
            ({}, "no entry for 'red'"),
            ({"r?d": "1", "red": "1", "green": "1", "blue": "1"}, "wildcard other than"),
            ({"r[a-e]d": "1", "red": "1", "green": "1", "blue": "1"}, "wildcard other than"),
            ({"r*": "1", "re*": "1", "green": "1", "blue": "1"}, "overlap"),
        ],
    )
    def test_an_entry_that_contradicts_itself_is_refused(self, valid_config, units, match) -> None:
        with pytest.raises(ConfigError, match=match):
            replace(valid_config, band_units=units)

    def test_the_mask_layer_needs_a_key_too(self) -> None:
        units = {key: unit for key, unit in SENTINEL_2_L2A.band_units.items() if key != "scl"}
        with pytest.raises(ConfigError, match="no entry for 'scl'"):
            replace(SENTINEL_2_L2A, band_units=units)

    def test_every_variable_of_a_zarr_render_needs_a_key(self) -> None:
        with pytest.raises(ConfigError, match="no entry for 'SR_10m:b03'"):
            replace(SYNTHETIC_ZARR, band_units={"SR_10m:b04": "1", "SCL_20m:scl": None})

    def test_an_explicit_none_counts_as_an_entry(self, valid_config) -> None:
        entry = replace(valid_config, band_units={"red": None, "green": None, "blue": None})
        assert entry.band_unit("red") is None

    def test_the_field_has_no_default(self) -> None:
        fields = {name: getattr(SENTINEL_2_L2A, name) for name in SENTINEL_2_L2A.__dataclass_fields__}
        del fields["band_units"]
        with pytest.raises(TypeError, match="band_units"):
            DatasetConfig(**fields)


class TestTheCollection:
    def test_it_publishes_the_units_for_the_panel(self) -> None:
        published = to_stac_collection(SENTINEL_2_L2A)["earthx:band_units"]
        assert published["red"] == "1" and published["scl"] is None

    def test_the_dem_publishes_metres(self) -> None:
        assert to_stac_collection(COP_DEM_GLO_30)["earthx:band_units"] == {"data": "m"}

    def test_the_published_dict_is_a_copy(self) -> None:
        published = to_stac_collection(COP_DEM_GLO_30)["earthx:band_units"]
        published["data"] = "ft"
        assert COP_DEM_GLO_30.band_unit("data") == "m"
