"""The description of each band in the registry (M5-59): a few words for the table of the Data catalogue."""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.registry import MAX_BAND_DESCRIPTION_CHARS, ConfigError
from tests.catalog.entries import REGISTRY
from tests.catalog.synthetic_zarr import TEST_ENTRIES

ENTRIES = [*REGISTRY, *TEST_ENTRIES]
BANDS = {"red": "1", "green": "1", "blue": "1"}


def _assets(entry) -> list[str]:
    return [key for key in entry.band_units if key not in entry.auxiliary_assets]


class TestTheEntries:
    @pytest.mark.parametrize("entry", ENTRIES, ids=lambda entry: entry.dataset_id)
    def test_every_band_has_a_short_description(self, entry) -> None:
        for key in _assets(entry):
            assert 0 < len(entry.band_descriptions[key]) <= MAX_BAND_DESCRIPTION_CHARS, key

    @pytest.mark.parametrize("entry", REGISTRY, ids=lambda entry: entry.dataset_id)
    def test_the_collection_publishes_them_by_the_keys_of_the_units(self, entry) -> None:
        published = to_stac_collection(entry)["earthx:band_descriptions"]
        assert published == dict(entry.band_descriptions)
        assert set(published) <= set(to_stac_collection(entry)["earthx:band_units"])

    def test_the_red_edge_band_reads_like_the_example(self) -> None:
        sentinel = next(entry for entry in REGISTRY if entry.dataset_id == "sentinel-2-c1-l2a")
        assert sentinel.band_descriptions["rededge1"] == "Red edge 1"


class TestWhatTheEntryRefuses:
    def test_a_band_without_a_description(self, valid_config) -> None:
        with pytest.raises(ConfigError, match="no entry for 'blue'"):
            replace(valid_config, band_descriptions={"red": "Red", "green": "Green"})

    def test_no_description_at_all(self, valid_config) -> None:
        with pytest.raises(ConfigError, match="band_descriptions has no entry"):
            replace(valid_config, band_descriptions={})

    def test_a_description_of_something_that_is_no_band(self, valid_config) -> None:
        with pytest.raises(ConfigError, match="names 'nir'"):
            replace(valid_config, band_descriptions={**valid_config.band_descriptions, "nir": "Near infrared"})

    @pytest.mark.parametrize("text", ["", "   ", " Red", "Red ", "Red\nband", "x" * (MAX_BAND_DESCRIPTION_CHARS + 1), None, 7])
    def test_a_description_that_is_no_short_one_line_text(self, valid_config, text) -> None:
        with pytest.raises(ConfigError, match="description of 'red'"):
            replace(valid_config, band_descriptions={**valid_config.band_descriptions, "red": text})

    def test_the_longest_allowed_text_passes(self, valid_config) -> None:
        text = "x" * MAX_BAND_DESCRIPTION_CHARS
        assert replace(valid_config, band_descriptions={**valid_config.band_descriptions, "red": text}).band_descriptions["red"] == text

    def test_an_auxiliary_asset_needs_none(self, valid_config) -> None:
        entry = replace(valid_config, band_units={**BANDS, "visual": None}, auxiliary_assets=("visual",))
        assert "visual" not in entry.band_descriptions

    def test_a_group_pattern_is_described_by_the_pattern(self) -> None:
        zarr = next(entry for entry in TEST_ENTRIES if "SR_*" in entry.band_units)
        assert zarr.band_descriptions["SR_*"]
        with pytest.raises(ConfigError, match="no entry for 'SR_\\*'"):
            replace(zarr, band_descriptions={"SCL_20m:scl": "Scene classification"})

    def test_the_description_is_read_only(self, valid_config) -> None:
        with pytest.raises(TypeError):
            valid_config.band_descriptions["red"] = "Other"  # type: ignore[index]
