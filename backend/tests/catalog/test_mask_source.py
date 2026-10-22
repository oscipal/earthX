"""The registry's description of a mask layer (plan M4-18 §3.1, adr/0014 §15m)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.datasets import COP_DEM_GLO_30, REGISTRY, SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3
from earthx.catalog.registry import ConfigError, MaskClass, MaskSource

# SentiWiki "S2 Processing", L2A Algorithms, Scene Classification, Table 3 (Otto, 20.10.2026).
SCL_NAMES = [
    "NO_DATA",
    "SATURATED_OR_DEFECTIVE",
    "CAST_SHADOWS",
    "CLOUD_SHADOWS",
    "VEGETATION",
    "NOT_VEGETATED",
    "WATER",
    "UNCLASSIFIED",
    "CLOUD_MEDIUM_PROBABILITY",
    "CLOUD_HIGH_PROBABILITY",
    "THIN_CIRRUS",
    "SNOW or ICE",
]


class TestTheEntries:
    @pytest.mark.parametrize("entry", [SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3], ids=lambda entry: entry.dataset_id)
    def test_both_sentinel_2_entries_describe_the_scene_classification(self, entry) -> None:
        assert entry.capabilities.masking is True
        assert [(c.value, c.label) for c in entry.mask.classes] == list(enumerate(SCL_NAMES))
        assert entry.mask.band == "scl"
        assert entry.mask.suggested == {3, 8, 9, 10}
        assert entry.mask.reference == "https://sentiwiki.copernicus.eu/web/s2-processing"

    def test_the_assets_are_the_ones_an_order_names(self) -> None:
        assert SENTINEL_2_L2A.mask.asset == "scl"
        assert SENTINEL_2_L2A_ZARR3.mask.asset == "SCL_20m:scl"

    def test_the_help_text_says_older_baselines_name_classes_differently(self) -> None:
        for entry in (SENTINEL_2_L2A, SENTINEL_2_L2A_ZARR3):
            assert "Older processing baselines name some classes differently" in entry.mask.note

    def test_the_dem_has_no_layer_and_does_not_mask(self) -> None:
        assert COP_DEM_GLO_30.mask is None and COP_DEM_GLO_30.capabilities.masking is False

    @pytest.mark.parametrize("entry", list(REGISTRY), ids=lambda entry: entry.dataset_id)
    def test_every_entry_switches_normalization_on_itself(self, entry) -> None:
        assert entry.capabilities.normalization is True


class TestTheCollection:
    def test_it_publishes_the_layer_for_the_panel(self) -> None:
        published = to_stac_collection(SENTINEL_2_L2A_ZARR3)["earthx:mask"]
        assert published["asset"] == "SCL_20m:scl" and published["band"] == "scl"
        assert published["classes"][8] == {"value": 8, "label": "CLOUD_MEDIUM_PROBABILITY"}
        assert published["suggested"] == [3, 8, 9, 10]
        assert published["note"] and published["reference"].startswith("https://")

    def test_a_dataset_without_a_layer_publishes_none(self) -> None:
        assert to_stac_collection(COP_DEM_GLO_30)["earthx:mask"] is None

    def test_the_flags_are_published(self) -> None:
        caps = to_stac_collection(SENTINEL_2_L2A)["earthx:capabilities"]
        assert (caps["masking"], caps["normalization"]) == (True, True)


def _layer(**changes) -> MaskSource:
    return replace(SENTINEL_2_L2A.mask, **changes)


class TestConsistency:
    def test_masking_without_a_layer_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="describes no mask layer"):
            replace(SENTINEL_2_L2A, mask=None)

    def test_a_layer_without_masking_is_refused(self) -> None:
        caps = replace(SENTINEL_2_L2A.capabilities, masking=False)
        with pytest.raises(ConfigError, match="masking is off"):
            replace(SENTINEL_2_L2A, capabilities=caps)

    @pytest.mark.parametrize(
        ("changes", "match"),
        [
            ({"band": "red"}, "is not what asset"),
            ({"asset": ""}, "names its asset"),
            ({"note": "  "}, "names its asset"),
            ({"reference": "http://example.invalid/"}, "https"),
            ({"classes": ()}, "ascending"),
            ({"classes": (MaskClass(2, "B"), MaskClass(1, "A"))}, "ascending"),
            ({"classes": (MaskClass(1, "A"), MaskClass(1, "B"))}, "ascending"),
            ({"classes": (MaskClass(-1, "A"),)}, "whole numbers"),
            ({"classes": (MaskClass(65536, "A"),)}, "whole numbers"),
            ({"classes": (MaskClass(1, " "),)}, "has a name"),
            ({"suggested": frozenset({12})}, "among the listed"),
        ],
    )
    def test_a_layer_that_contradicts_itself_is_refused(self, changes, match) -> None:
        with pytest.raises(ConfigError, match=match):
            replace(SENTINEL_2_L2A, mask=_layer(**changes))

    def test_the_zarr_asset_must_end_in_the_band(self) -> None:
        with pytest.raises(ConfigError, match="is not what asset"):
            replace(SENTINEL_2_L2A_ZARR3, mask=replace(SENTINEL_2_L2A_ZARR3.mask, asset="SCL_20m:other"))
