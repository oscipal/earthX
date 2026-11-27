"""M5-64: the QGIS style of a raster job's result, drawn as the app draws the result (plan §4.3, F3)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import pytest

from earthx.api.result_styles import result_style
from earthx.processing.operators import REGISTRY as OPERATORS
from tests.catalog.entries import COP_DEM_GLO_30, SENTINEL_2_L2A

STATS = {"minimum": -0.2, "maximum": 0.8, "percentile_2": -0.1, "percentile_98": 0.7}


def band(name: str, **extra: Any) -> dict[str, Any]:
    return {"name": name, "data_type": "float32", "nodata": "nan", "statistics": STATS, **extra}


def renderer(style: str | None) -> ET.Element:
    assert style is not None
    found = ET.fromstring(style).find(".//rasterrenderer")
    assert found is not None
    return found


def ends(style: str | None) -> tuple[float, float]:
    assert style is not None
    shader = ET.fromstring(style).find(".//colorrampshader")
    assert shader is not None
    return float(shader.get("minimumValue", "nan")), float(shader.get("maximumValue", "nan"))


def first_colour(style: str | None) -> str:
    assert style is not None
    return ET.fromstring(style).find(".//colorrampshader/item").get("color")  # type: ignore[union-attr]


BAND_MATH = {"steps": [{"op": "band_math", "op_version": 2, "params": {"expression": "(nir - red) / (nir + red)", "name": "NDVI"}}]}


class TestWhereTheLookComesFrom:
    def test_the_look_of_the_download_comes_first(self) -> None:
        look = {"bands": {"NDVI": {"colormap": "magma", "low": 0.1, "high": 0.6}}}
        style = result_style({"bands": [band("NDVI")]}, BAND_MATH, config=SENTINEL_2_L2A, operators=OPERATORS, look=look)
        assert ends(style) == (0.1, 0.6)

    def test_a_result_of_one_band_takes_the_one_look_of_the_download_whatever_its_name(self) -> None:
        look = {"bands": {"band": {"colormap": "magma", "low": 0.2, "high": 0.4}}}
        style = result_style({"bands": [band("NDVI")]}, BAND_MATH, config=SENTINEL_2_L2A, operators=OPERATORS, look=look)
        assert ends(style) == (0.2, 0.4)

    def test_an_index_takes_the_look_of_its_preset(self) -> None:
        style = result_style({"bands": [band("NDVI")]}, BAND_MATH, config=SENTINEL_2_L2A, operators=OPERATORS)
        assert ends(style) == (-1.0, 1.0)
        assert first_colour(style) == "#a50026"  # rdylgn

    def test_a_band_with_the_values_of_the_source_takes_its_look_in_the_collection(self) -> None:
        properties = {"bands": [band("data", **{"earthx:source_values": True})]}
        style = result_style(properties, {"steps": []}, config=COP_DEM_GLO_30, operators=OPERATORS)
        assert ends(style) == (0.0, 5000.0)  # terrain, fixed

    def test_a_product_of_an_operator_takes_the_look_of_the_operator(self) -> None:
        recipe = {"steps": [{"op": "terrain", "op_version": 1, "params": {"product": "hillshade"}}]}
        style = result_style({"bands": [band("hillshade")]}, recipe, config=COP_DEM_GLO_30, operators=OPERATORS)
        assert ends(style) == (-0.2, 0.8)  # percentiles 0/100: the minimum and the maximum of the result
        assert first_colour(style) == "#000000"  # greys_r: dark to light (adr/0035)

    def test_anything_else_is_viridis_on_the_usual_scale_of_the_statistics(self) -> None:
        style = result_style({"bands": [band("x")]}, {"steps": []}, config=None, operators=OPERATORS)
        assert ends(style) == (-0.1, 0.7) and first_colour(style) == "#440154"

    def test_a_band_of_classes_is_its_palette(self) -> None:
        classes = [{"value": 10, "name": "tree_cover", "title": "Tree cover", "color_hint": "006400"}]
        style = result_style({"bands": [band("map", **{"classification:classes": classes})]}, {"steps": []}, config=None, operators=OPERATORS)
        entry = ET.fromstring(style or "").find(".//paletteEntry")
        assert renderer(style).get("type") == "paletted" and entry is not None
        assert (entry.get("value"), entry.get("color"), entry.get("label")) == ("10", "#006400", "Tree cover")

    def test_three_bands_of_the_rgb_look_are_true_colour(self) -> None:
        look = {"rgb": {"bands": ["red", "green", "blue"], "ranges": [[0, 0.3], [0, 0.3], [0, 0.3]]}}
        bands = [band(name, **{"earthx:source_values": True}) for name in ("blue", "green", "red")]
        found = renderer(result_style({"bands": bands}, {"steps": []}, config=SENTINEL_2_L2A, operators=OPERATORS, look=look))
        assert (found.get("type"), found.get("redBand"), found.get("blueBand")) == ("multibandcolor", "3", "1")


class TestWhatIsRefused:
    def test_a_result_that_names_no_bands_gets_no_style(self) -> None:
        assert result_style({}, {"steps": []}, config=None, operators=OPERATORS) is None

    @pytest.mark.parametrize("look", [[], {"bands": {"x": {"colormap": "nope", "low": 0, "high": 1}}}, {"other": 1}])
    def test_a_look_that_is_no_look_is_refused(self, look: object) -> None:
        with pytest.raises(ValueError):
            result_style({"bands": [band("x")]}, {"steps": []}, config=None, operators=OPERATORS, look=look)
        with pytest.raises(ValueError):
            result_style({}, {"steps": []}, config=None, operators=OPERATORS, look=look)

    def test_a_step_the_registry_does_not_know_is_no_look(self) -> None:
        recipe = {"steps": [{"op": "no-such-op", "op_version": 9, "params": {}}]}
        assert ends(result_style({"bands": [band("x")]}, recipe, config=None, operators=OPERATORS)) == (-0.1, 0.7)
