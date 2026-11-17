"""The composite and step presets of a registry entry and their form (adr/0030 F7, M5-14 plan §3)."""

from __future__ import annotations

import dataclasses
from dataclasses import replace

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.entry_files import to_plain
from earthx.catalog.registry import CompositePreset, ConfigError, DatasetConfig, StepPreset
from earthx.catalog.search_text import search_text
from tests.catalog.entries import (
    BEV_ALS_DGM,
    COP_DEM_GLO_30,
    ESA_WORLDCOVER_2020,
    ESA_WORLDCOVER_2021,
    REGISTRY,
    SENTINEL_1_GRD,
    SENTINEL_2_L2A,
    SWISSALTI3D,
)

FALSE_COLOUR = SENTINEL_2_L2A.composite_presets[0]
HILLSHADE = COP_DEM_GLO_30.step_presets[0]


def _composite(**changes: object) -> DatasetConfig:
    return replace(SENTINEL_2_L2A, composite_presets=(replace(FALSE_COLOUR, **changes),))


def _step(**changes: object) -> DatasetConfig:
    return replace(COP_DEM_GLO_30, step_presets=(replace(HILLSHADE, **changes),))


class TestTheEntries:
    @pytest.mark.parametrize(("entry", "band"), [(COP_DEM_GLO_30, "data"), (SWISSALTI3D, "dtm"), (BEV_ALS_DGM, "dtm")])
    def test_the_elevation_models_offer_hillshade_slope_and_aspect_on_their_heights(self, entry, band) -> None:
        """F2 = 2, F3 = 1: the defaults of ``gdaldem``, slope in degrees."""
        assert [(p.name, p.title) for p in entry.step_presets] == [
            ("hillshade", "Hillshade"),
            ("slope", "Slope"),
            ("aspect", "Aspect"),
        ]
        hillshade, slope, aspect = (dict(p.params) for p in entry.step_presets)
        assert hillshade == {
            "product": "hillshade",
            "bands": [band],
            "method": "horn",
            "azimuth": 315.0,
            "altitude": 45.0,
            "z_factor": 1.0,
            "multidirectional": False,
        }
        assert slope == {"product": "slope", "bands": [band], "method": "horn", "slope_unit": "degrees"}
        assert aspect == {"product": "aspect", "bands": [band], "method": "horn"}
        assert all((p.op, p.op_version) == ("terrain", 1) for p in entry.step_presets)
        # Otto, 17.11.2026: the light of the hillshade and the unit of the slope can be changed under "Quick processing".
        assert [p.adjustable for p in entry.step_presets] == [("azimuth", "altitude"), ("slope_unit",), ()]
        assert entry.composite_presets == ()

    def test_sentinel_2_offers_false_colour_and_swir_with_a_fixed_range_per_channel(self) -> None:
        """F4 = 1 and adr/0030 §5.1."""
        assert [(p.name, p.title, p.channels, p.rescale) for p in SENTINEL_2_L2A.composite_presets] == [
            ("false_colour_ir", "False colour (IR)", ("nir", "red", "green"), ((0.0, 0.5), (0.0, 0.3), (0.0, 0.3))),
            ("swir", "SWIR", ("swir22", "nir08", "red"), ((0.0, 0.4), (0.0, 0.5), (0.0, 0.3))),
        ]
        assert SENTINEL_2_L2A.step_presets == ()

    @pytest.mark.parametrize("entry", [ESA_WORLDCOVER_2020, ESA_WORLDCOVER_2021, SENTINEL_1_GRD])
    def test_the_others_offer_none(self, entry) -> None:
        assert (entry.composite_presets, entry.step_presets) == ((), ())

    @pytest.mark.parametrize("name", ["composite_presets", "step_presets"])
    def test_the_fields_have_no_default(self, name: str) -> None:
        field = next(f for f in dataclasses.fields(DatasetConfig) if f.name == name)
        assert field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING

    def test_the_parameters_of_a_step_preset_cannot_be_changed_afterwards(self) -> None:
        with pytest.raises(TypeError):
            HILLSHADE.params["azimuth"] = 0.0  # type: ignore[index]

    def test_an_entry_reads_back_as_the_plain_data_of_its_file(self) -> None:
        plain = to_plain(COP_DEM_GLO_30)
        assert plain["composite_presets"] == []
        assert plain["step_presets"][0]["params"]["bands"] == ["data"]
        assert to_plain(SENTINEL_2_L2A)["composite_presets"][0]["rescale"] == [[0.0, 0.5], [0.0, 0.3], [0.0, 0.3]]


class TestTheCollection:
    def test_it_publishes_the_composites_red_green_blue(self) -> None:
        published = to_stac_collection(SENTINEL_2_L2A)["earthx:composite_presets"]
        assert published[0] == {
            "name": "false_colour_ir",
            "title": "False colour (IR)",
            "expressions": ["nir", "red", "green"],
            "rescale": [[0.0, 0.5], [0.0, 0.3], [0.0, 0.3]],
            "reference": FALSE_COLOUR.reference,
        }
        assert to_stac_collection(SENTINEL_2_L2A)["earthx:step_presets"] == []

    def test_it_publishes_the_step_with_the_name_of_its_band(self) -> None:
        published = to_stac_collection(COP_DEM_GLO_30)["earthx:step_presets"]
        assert [entry["name"] for entry in published] == ["hillshade", "slope", "aspect"]
        assert published[1] == {
            "name": "slope",
            "title": "Slope",
            "op": "terrain",
            "op_version": 1,
            "params": {"product": "slope", "bands": ["data"], "method": "horn", "slope_unit": "degrees", "name": "slope"},
            "adjustable": ["slope_unit"],
        }
        assert to_stac_collection(COP_DEM_GLO_30)["earthx:composite_presets"] == []

    def test_the_search_text_names_them(self) -> None:
        assert "Hillshade" in search_text(COP_DEM_GLO_30).d
        assert "False colour (IR)" in search_text(SENTINEL_2_L2A).d


class TestTheFormOfACompositePreset:
    @pytest.mark.parametrize(
        ("changes", "reason"),
        [
            ({"red": "visual"}, "reads visual, which is no band of the data"),
            ({"red": "scl"}, "reads scl, which is no band of the data"),
            ({"green": "nir99 * 2"}, "reads nir99, which the entry does not know"),
            ({"blue": "2"}, "has a channel that reads no band"),
            ({"blue": " green"}, "non-blank expression"),
            ({"red": "nir", "green": "nir", "blue": "nir"}, "the same in red, green and blue"),
            ({"rescale": ((0.0, 0.5), (0.0, 0.3))}, "a rescale for each of red, green and blue"),
            ({"rescale": ((0.5, 0.0), (0.0, 0.3), (0.0, 0.3))}, "two finite numbers per channel, the lower first"),
            ({"rescale": ((0.0, float("inf")), (0.0, 0.3), (0.0, 0.3))}, "two finite numbers per channel"),
            ({"reference": "http://example.org"}, "https:// address"),
            ({"title": "False colour infrared composite"}, "title of at most 24 characters"),
            ({"title": ""}, "non-blank title"),
        ],
    )
    def test_a_broken_composite_is_refused(self, changes: dict, reason: str) -> None:
        with pytest.raises(ConfigError, match=f"the composite preset false_colour_ir .*{reason}"):
            _composite(**changes)

    @pytest.mark.parametrize("name", ["1st", "a-b", "x" * 31, ""])
    def test_a_name_from_which_no_band_name_follows_is_refused(self, name: str) -> None:
        with pytest.raises(ConfigError, match="name"):
            _composite(name=name)

    def test_a_name_whose_channel_bands_meet_a_band_of_the_data_is_refused(self) -> None:
        entry = replace(SENTINEL_2_L2A, band_units={**SENTINEL_2_L2A.band_units, "fc_r": None})
        with pytest.raises(ConfigError, match="adds a band named like a band of the data"):
            replace(entry, composite_presets=(replace(FALSE_COLOUR, name="fc"),))

    def test_composites_need_band_math(self) -> None:
        capabilities = replace(SENTINEL_2_L2A.capabilities, band_math=False)
        with pytest.raises(ConfigError, match="composite presets fill band_math steps, but band_math is off"):
            replace(SENTINEL_2_L2A, capabilities=capabilities, index_presets=())

    def test_a_list_is_not_a_tuple_of_presets(self) -> None:
        with pytest.raises(ConfigError, match="composite_presets is a tuple of CompositePreset"):
            replace(SENTINEL_2_L2A, composite_presets=[FALSE_COLOUR])
        with pytest.raises(ConfigError, match="composite_presets is a tuple of CompositePreset"):
            replace(SENTINEL_2_L2A, composite_presets=(HILLSHADE,))


class TestTheFormOfAStepPreset:
    @pytest.mark.parametrize(
        ("changes", "reason"),
        [
            ({"op": ""}, "names its operator"),
            ({"op_version": 0}, "a version of its operator from 1"),
            ({"op_version": True}, "a version of its operator from 1"),
            ({"params": ["product"]}, "parameters as a mapping by name"),
            ({"params": {**HILLSHADE.params, "name": "x"}}, "takes the name of its band from the preset"),
            ({"title": "Hillshade from the north west"}, "title of at most 24 characters"),
            ({"adjustable": ["azimuth"]}, "adjustable parameters as a tuple of names"),
            ({"adjustable": ("azimuth", "azimuth")}, "names an adjustable parameter twice"),
            ({"adjustable": ("slope_unit",)}, "makes slope_unit adjustable, which its params do not set"),
            ({"adjustable": ("bands",)}, "keeps the bands it reads fixed"),
        ],
    )
    def test_a_broken_step_preset_is_refused(self, changes: dict, reason: str) -> None:
        with pytest.raises(ConfigError, match=f"the step preset hillshade .*{reason}"):
            _step(**changes)

    def test_a_step_preset_named_like_a_band_of_the_data_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="adds a band named like a band of the data"):
            _step(name="DATA")

    def test_one_name_once_over_index_composite_and_step_presets(self) -> None:
        ndvi = StepPreset(name="NDVI", title="x", op="terrain", op_version=1, params={}, adjustable=())
        with pytest.raises(ConfigError, match="the preset ndvi is named twice"):
            replace(SENTINEL_2_L2A, step_presets=(replace(ndvi, name="ndvi"),))
        with pytest.raises(ConfigError, match="the preset Slope is named twice"):
            replace(COP_DEM_GLO_30, step_presets=(*COP_DEM_GLO_30.step_presets, replace(HILLSHADE, name="Slope")))

    def test_a_tuple_of_another_kind_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="step_presets is a tuple of StepPreset"):
            replace(COP_DEM_GLO_30, step_presets=(FALSE_COLOUR,))


def test_every_released_entry_states_both_fields() -> None:
    for entry in REGISTRY:
        assert isinstance(entry.composite_presets, tuple) and isinstance(entry.step_presets, tuple)
        assert all(isinstance(p, CompositePreset) for p in entry.composite_presets)
