"""The index presets of a registry entry and their form (NM4-14 plan §8.1, §10 points 4 and 5)."""

from __future__ import annotations

import dataclasses
from dataclasses import replace

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A
from earthx.catalog.registry import ConfigError, DatasetConfig, IndexPreset

NDVI = SENTINEL_2_L2A.index_presets[0]


def _with(*presets: IndexPreset) -> DatasetConfig:
    return replace(SENTINEL_2_L2A, index_presets=presets)


def _preset(**changes: object) -> IndexPreset:
    return replace(NDVI, **changes)


class TestTheEntries:
    def test_sentinel_2_offers_the_five_indices_in_the_order_of_the_buttons(self) -> None:
        assert [preset.name for preset in SENTINEL_2_L2A.index_presets] == ["NDVI", "NDWI", "NDSI", "NBR", "EVI"]

    def test_n_is_the_nir_band_b08_not_nir08(self) -> None:
        """Awesome Spectral Indices' `bands.json` maps N to B8 for Sentinel-2; B8A is N2 (plan §7.5)."""
        for preset in SENTINEL_2_L2A.index_presets:
            assert "nir08" not in preset.expression
        assert {"NDVI", "NDWI", "NBR", "EVI"} == {p.name for p in SENTINEL_2_L2A.index_presets if "nir" in p.expression}

    def test_ndwi_is_the_water_index_of_mcfeeters_green_over_nir(self) -> None:
        ndwi = next(preset for preset in SENTINEL_2_L2A.index_presets if preset.name == "NDWI")
        assert ndwi.expression == "(green - nir) / (green + nir)"
        assert "McFeeters" in ndwi.title

    def test_the_dem_offers_none(self) -> None:
        assert COP_DEM_GLO_30.index_presets == ()

    def test_the_field_has_no_default(self) -> None:
        field = next(f for f in dataclasses.fields(DatasetConfig) if f.name == "index_presets")
        assert field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING


class TestTheCollection:
    def test_it_publishes_the_presets_with_rescale_as_the_render_extension_writes_it(self) -> None:
        published = to_stac_collection(SENTINEL_2_L2A)["earthx:index_presets"]
        assert [entry["name"] for entry in published] == ["NDVI", "NDWI", "NDSI", "NBR", "EVI"]
        assert published[0] == {
            "name": "NDVI",
            "title": "Normalized Difference Vegetation Index",
            "expression": "(nir - red) / (nir + red)",
            "rescale": [[-1.0, 1.0]],
            "colormap_name": "rdylgn",
            "formula": "(N - R)/(N + R)",
            "reference": "https://ntrs.nasa.gov/citations/19740022614",
        }

    def test_the_dem_publishes_an_empty_list(self) -> None:
        assert to_stac_collection(COP_DEM_GLO_30)["earthx:index_presets"] == []


class TestTheCheck:
    def test_the_entry_as_it_stands_passes(self) -> None:
        assert _with(*SENTINEL_2_L2A.index_presets) == SENTINEL_2_L2A

    @pytest.mark.parametrize("presets", [NDVI, [NDVI], (NDVI, "NDWI"), ({"name": "NDVI"},)])
    def test_anything_but_a_tuple_of_presets_is_refused(self, presets: object) -> None:
        with pytest.raises(ConfigError, match="index_presets is a tuple of IndexPreset"):
            replace(SENTINEL_2_L2A, index_presets=presets)

    @pytest.mark.parametrize("name", ["", "1NDVI", "_NDVI", "ND VI", "NDVI-2", "N" * 33, None])
    def test_a_name_no_band_math_step_can_add_is_refused(self, name: object) -> None:
        with pytest.raises(ConfigError, match="is not a name a band_math step can add"):
            _with(_preset(name=name))

    @pytest.mark.parametrize("second", ["NDVI", "ndvi", "Ndvi"])
    def test_a_name_twice_is_refused_ignoring_case(self, second: str) -> None:
        with pytest.raises(ConfigError, match="NDVI is named twice|ndvi is named twice|Ndvi is named twice"):
            _with(NDVI, _preset(name=second))

    @pytest.mark.parametrize("name", ["red", "RED", "scl", "visual"])
    def test_the_name_of_a_band_of_the_data_is_refused(self, name: str) -> None:
        with pytest.raises(ConfigError, match="has the name of a band of the data"):
            _with(_preset(name=name))

    def test_an_unknown_band_is_refused_with_its_name(self) -> None:
        with pytest.raises(ConfigError, match="reads swir, which the entry does not know"):
            _with(_preset(expression="(nir - swir) / (nir + swir)"))

    @pytest.mark.parametrize("expression", ["visual - red", "where(scl == 4, nir, red)"])
    def test_an_auxiliary_asset_or_the_mask_layer_is_no_band_to_read(self, expression: str) -> None:
        with pytest.raises(ConfigError, match="which is no band of the data"):
            _with(_preset(expression=expression))

    def test_a_call_is_left_to_band_math_and_its_arguments_are_checked(self) -> None:
        assert _with(_preset(expression="sqrt(nir) - red")).index_presets[0].expression == "sqrt(nir) - red"
        with pytest.raises(ConfigError, match="reads swir"):
            _with(_preset(expression="sqrt(swir) - red"))

    def test_a_number_with_an_exponent_is_no_band(self) -> None:
        assert _with(_preset(expression="nir * 1e2 - red")).index_presets[0].expression == "nir * 1e2 - red"

    def test_an_expression_without_a_band_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="reads no band"):
            _with(_preset(expression="1 + 2"))

    @pytest.mark.parametrize("field", ["title", "expression", "colormap_name", "formula"])
    @pytest.mark.parametrize("value", ["", "  ", " rdylgn", None])
    def test_a_blank_text_is_refused(self, field: str, value: object) -> None:
        with pytest.raises(ConfigError, match=f"has a non-blank {field}"):
            _with(_preset(**{field: value}))

    @pytest.mark.parametrize(
        "rescale", [(1.0, -1.0), (0.0, 0.0), (float("nan"), 1.0), (-1.0, float("inf")), (-1.0,), [-1.0, 1.0], (True, 2)]
    )
    def test_a_rescale_that_is_no_range_is_refused(self, rescale: object) -> None:
        with pytest.raises(ConfigError, match="has a rescale of two finite numbers, the lower first"):
            _with(_preset(rescale=rescale))

    @pytest.mark.parametrize("reference", ["http://ntrs.nasa.gov/citations/19740022614", "doi:10.3133/ofr0211", ""])
    def test_the_source_of_the_formula_is_an_https_address(self, reference: str) -> None:
        with pytest.raises(ConfigError, match="https:// address"):
            _with(_preset(reference=reference))

    def test_presets_need_band_math(self) -> None:
        capabilities = replace(SENTINEL_2_L2A.capabilities, band_math=False)
        with pytest.raises(ConfigError, match="band_math is off"):
            replace(SENTINEL_2_L2A, capabilities=capabilities)
        assert not replace(SENTINEL_2_L2A, capabilities=capabilities, index_presets=()).capabilities.band_math
