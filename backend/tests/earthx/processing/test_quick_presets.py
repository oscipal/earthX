"""The composite and step presets against the steps they fill, when ``api`` is built (adr/0030 F7, M5-14 plan §3.2).

What a dataset cannot do never becomes a button: a preset its operator, its flags or the tiler would refuse stops the start.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.catalog.registry import DatasetRegistry
from earthx.processing.operators.base import Looks
from earthx.processing.operators.registry import REGISTRY as OPERATORS
from earthx.processing.operators.terrain import TERRAIN
from earthx.processing.quick_presets import QuickPresetMismatch, check_quick_presets
from tests.catalog.entries import COP_DEM_GLO_30, REGISTRY, SENTINEL_2_L2A

HILLSHADE = COP_DEM_GLO_30.step_presets[0]
FALSE_COLOUR = SENTINEL_2_L2A.composite_presets[0]


def _dem_with(**changes: object) -> DatasetRegistry:
    return DatasetRegistry((replace(COP_DEM_GLO_30, step_presets=(replace(HILLSHADE, **changes),)),))


def test_the_registry_of_the_platform_passes() -> None:
    check_quick_presets(REGISTRY)


class TestAStepPreset:
    @pytest.mark.parametrize(
        ("changes", "reason"),
        [
            ({"op": "hillshade"}, "names hillshade version 1, which the panel does not offer"),
            ({"op_version": 2}, "names terrain version 2, which the panel does not offer"),
            ({"op": "reproject", "op_version": 3}, "reproject does not run as a tile"),
            ({"op": "normalize", "op_version": 2}, "names normalize version 2, which the panel does not offer|adds no named band"),
            ({"params": {**HILLSHADE.params, "azimuth": 400.0}}, "has parameters terrain refuses: azimuth"),
            ({"params": {**HILLSHADE.params, "colour": "red"}}, "has parameters terrain refuses: colour"),
            ({"params": {"product": "slope", "bands": ["data"]}, "adjustable": ()}, "slope needs slope_unit"),
            ({"params": {**HILLSHADE.params, "bands": ["elevation"]}}, "reads elevation, which is no band of the data"),
            ({"params": {**HILLSHADE.params, "colour": "red"}, "adjustable": ("colour",)}, "makes colour adjustable, which terrain does not take"),
        ],
    )
    def test_a_preset_the_operator_refuses_stops_the_start(self, changes: dict, reason: str) -> None:
        with pytest.raises(QuickPresetMismatch, match=f"cop-dem-glo-30: the step preset hillshade .*({reason})"):
            check_quick_presets(_dem_with(**changes))

    def test_a_preset_on_a_dataset_without_the_flag_stops_the_start(self) -> None:
        """Hillshade on Sentinel-2: `terrain` is off there, so the button would be refused; it may not be one."""
        entry = replace(SENTINEL_2_L2A, step_presets=(replace(HILLSHADE, params={**HILLSHADE.params, "bands": ["red"]}),))
        with pytest.raises(QuickPresetMismatch, match="sentinel-2-c1-l2a does not allow terrain"):
            check_quick_presets(DatasetRegistry((entry,)))

    def test_a_preset_of_an_operator_without_a_look_stops_the_start(self) -> None:
        plain = replace(TERRAIN, looks=None)
        operators = OPERATORS.__class__([*(op for key, op in OPERATORS.items() if key != ("terrain", 1)), plain])
        with pytest.raises(QuickPresetMismatch, match="has no look of terrain to be drawn with"):
            check_quick_presets(_dem_with(), operators)

    def test_a_look_the_tiler_cannot_paint_stops_the_start(self) -> None:
        looks = Looks(param="product", by_value={**TERRAIN.looks.by_value, "hillshade": replace(TERRAIN.looks.by_value["hillshade"], colormap="sunset_unicorn")})
        operators = OPERATORS.__class__([*(op for key, op in OPERATORS.items() if key != ("terrain", 1)), replace(TERRAIN, looks=looks)])
        with pytest.raises(QuickPresetMismatch, match="colormap 'sunset_unicorn', which the tiler does not know"):
            check_quick_presets(_dem_with(), operators)


class TestACompositePreset:
    @pytest.mark.parametrize(
        ("changes", "reason"),
        [
            ({"red": "log(nir)"}, "the functions are"),
            ({"green": "(red"}, "not a valid expression"),
            ({"blue": "green if red else nir"}, "IfExp is not allowed"),
        ],
    )
    def test_a_channel_band_math_would_refuse_stops_the_start(self, changes: dict, reason: str) -> None:
        entry = replace(SENTINEL_2_L2A)
        object.__setattr__(entry, "composite_presets", (replace(FALSE_COLOUR, **changes),))
        with pytest.raises(QuickPresetMismatch, match=f"the composite preset .*({reason})"):
            check_quick_presets(DatasetRegistry((entry,)))

    def test_the_bands_band_math_reads_are_matched_once_more(self) -> None:
        entry = replace(SENTINEL_2_L2A)
        object.__setattr__(entry, "composite_presets", (replace(FALSE_COLOUR, red="visual"),))
        with pytest.raises(QuickPresetMismatch, match="reads visual, which is no band of the data"):
            check_quick_presets(DatasetRegistry((entry,)))


def test_every_problem_is_named_not_only_the_first() -> None:
    entry = replace(COP_DEM_GLO_30, step_presets=(replace(HILLSHADE, op_version=9), replace(HILLSHADE, name="shade", op="nothing")))
    with pytest.raises(QuickPresetMismatch) as raised:
        check_quick_presets(DatasetRegistry((entry,)))
    assert "hillshade" in str(raised.value) and "shade names nothing" in str(raised.value)


def test_the_angles_of_the_light_say_their_unit_in_the_description() -> None:
    """"Quick processing" offers an angle as a dial or a slider in degrees from the schema alone (M5-14, Otto, 17.11.2026)."""
    schema = TERRAIN.params.model_json_schema()["properties"]
    assert schema["azimuth"]["x-earthx-unit"] == "deg"
    assert schema["altitude"]["x-earthx-unit"] == "deg"
    assert "x-earthx-unit" not in schema["z_factor"]
