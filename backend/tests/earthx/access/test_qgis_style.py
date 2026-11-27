"""The QGIS style beside every exported raster file (M5-64): the form against what QGIS itself writes, the rule of the plan
(§4), the style an order carries, the measure and the style of a job's result.

There is no published schema of a ``.qml``; the reference is QGIS. ``tests/fixtures/qgis/<case>.qml`` is what QGIS 3.34.4
wrote back after loading the style this module writes for ``<case>`` (``make_reference.py`` there). Equal elements,
attributes and numbers mean QGIS read every value as written.
"""

from __future__ import annotations

import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from earthx.access.band_export import BandMeta
from earthx.access.colormaps import COLORMAPS
from earthx.access.qgis_style import (
    ExportStyle,
    Gray,
    Paletted,
    Pseudocolor,
    Rgb,
    StyleInvalid,
    file_renderer,
    file_style,
    measured_range,
    qml_text,
    result_style,
    style_file,
)
from earthx.catalog.registry import ClassRow, Look


def file_qml(dataset: Any, bands: list[BandMeta], style: ExportStyle | None, true_color: tuple[str, ...]) -> str:
    styled = file_style(dataset, "exports/x.tif", bands, style, true_color)
    assert styled is not None and styled[0] == "exports/x.qml"
    return styled[1]


def result_qml(properties: Any, style: ExportStyle | None, look_of: Any) -> str | None:
    styled = result_style("folder/result.tif", properties, style, look_of, "qml")
    return None if styled is None else styled[1]


REFERENCE = Path(__file__).resolve().parents[2] / "fixtures" / "qgis"

WORLDCOVER_LIKE = (
    ClassRow(10, "Tree cover", "#006400"),
    ClassRow(20, "Shrubland", "#ffbb22"),
    ClassRow(95, "Mangroves & <salt>", "#00cf75"),
)

CASES = {
    "pseudocolor": Pseudocolor(1, "viridis", 0.02, 0.24),
    "pseudocolor_reversed": Pseudocolor(2, "rdbu_r", -20.0, 30.0),
    "gray": Gray(1, 0.0, 0.3),
    "rgb": Rgb((3, 2, 1), ((0.0, 0.5), (0.0, 0.3), (0.0, 0.25))),
    "paletted": Paletted(1, WORLDCOVER_LIKE),
}


def _value(text: str) -> Any:
    try:
        return round(float(text), 9)
    except ValueError:
        return text


def _canon(element: ET.Element) -> tuple[Any, ...]:
    """An element as a comparable value: attribute order and the spelling of a number do not count."""
    attributes = tuple(sorted((key, _value(value)) for key, value in element.attrib.items()))
    return (element.tag, attributes, _value((element.text or "").strip()), tuple(_canon(child) for child in element))


def _pipe(text: str) -> ET.Element:
    pipe = ET.fromstring(text.split("\n", 1)[1]).find("pipe")
    assert pipe is not None
    return pipe


def _meta(asset: str, *, classes: tuple[ClassRow, ...] | None = None, look: Look | None = None) -> BandMeta:
    return BandMeta(
        asset=asset, name=asset, common_name=None, wavelength_um=None, resolution_m=10.0, data_type="uint16",
        scale=None, offset=None, nodata=0.0, unit=None, categorical=classes is not None, classes=classes, look=look,
    )  # fmt: skip


class Measures:
    """A measure that answers with fixed numbers and remembers what it was asked."""

    def __init__(self) -> None:
        self.asked: list[tuple[int, float, float]] = []

    def __call__(self, band: int, low: float, high: float) -> tuple[float, float]:
        self.asked.append((band, low, high))
        return float(band), float(band) + low / 100 + high / 100


# --- the form ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(CASES))
def test_what_qgis_reads_and_writes_back_is_what_was_written(case: str) -> None:
    reference = (REFERENCE / f"{case}.qml").read_text(encoding="utf-8")
    assert _canon(_pipe(qml_text(CASES[case]))) == _canon(_pipe(reference))


def test_a_style_is_one_of_the_category_symbology_with_the_doctype_of_qgis() -> None:
    text = qml_text(CASES["gray"])
    assert text.startswith("<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n<qgis ")
    root = ET.fromstring(text.split("\n", 1)[1])
    assert root.attrib == {"styleCategories": "Symbology", "version": "3.34.4"}
    assert root.find("pipe/rasterrenderer/minMaxOrigin/limits").text == "None"  # type: ignore[union-attr]


@pytest.mark.parametrize("name", ["viridis", "viridis_r", "terrain", "rocket", "cfastie_r"])
def test_a_colormap_is_the_table_of_the_tiler_from_min_to_max(name: str) -> None:
    shader = _pipe(qml_text(Pseudocolor(1, name, -5.0, 45.0))).find("rasterrenderer/rastershader/colorrampshader")
    assert shader is not None
    table = COLORMAPS.get(name)
    expected = ["#{:02x}{:02x}{:02x}".format(*table[key][:3]) for key in sorted(table)]
    items = shader.findall("item")
    assert [item.attrib["color"] for item in items] == expected
    assert float(items[0].attrib["value"]) == -5.0
    assert float(items[-1].attrib["value"]) == 45.0
    assert shader.attrib["colorRampType"] == "INTERPOLATED"
    assert shader.attrib["clip"] == "0"
    ramp = {option.attrib["name"]: option.attrib.get("value") for option in shader.findall("colorramp/Option/Option")}
    assert ramp["color1"] == "{},{},{},255".format(*table[min(table)][:3])
    assert ramp["color2"] == "{},{},{},255".format(*table[max(table)][:3])
    assert len(ramp["stops"].split(":")) == len(table) - 2  # type: ignore[union-attr]
    assert shader.find("colorramp").attrib["name"] == "[source]"  # type: ignore[union-attr]


def test_the_tables_of_the_ramps_are_the_ones_the_tiler_draws() -> None:
    """The style reads the ramps without titiler and the registry (``colormap_tables``, plan §12.1); the tiles take
    exactly the same 256 colours for every name of ``GET /colormaps``."""
    from earthx.access.colormap_tables import ramp_colours
    from earthx.access.colormaps import CLASS_TABLES

    names = [name for name in COLORMAPS.list() if name not in CLASS_TABLES]
    assert len(names) > 100
    for name in names:
        table = COLORMAPS.get(name)
        assert ramp_colours(name) == [tuple(int(c) for c in table[key]) for key in sorted(table)], name
    for name in CLASS_TABLES:
        assert ramp_colours(name) is None, "a table of classes is no ramp"
    assert ramp_colours("no_such_map") is None


def test_the_style_loads_neither_titiler_nor_the_registry() -> None:
    import subprocess

    code = (
        "import sys, earthx.access.qgis_style;"
        "bad = [m for m in ('titiler', 'earthx.access.colormaps', 'earthx.catalog.datasets') if m in sys.modules];"
        "print(','.join(bad))"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=REFERENCE.parents[2])
    assert done.stdout.strip() == ""


def test_a_reversed_colormap_runs_the_other_way() -> None:
    def colours(name: str) -> list[str]:
        shader = _pipe(qml_text(Pseudocolor(1, name, 0.0, 1.0))).find("rasterrenderer/rastershader/colorrampshader")
        return [item.attrib["color"] for item in shader.findall("item")]  # type: ignore[union-attr]

    assert colours("magma_r") == list(reversed(colours("magma")))


def test_names_of_classes_are_escaped_and_read_back_as_written() -> None:
    palette = _pipe(qml_text(CASES["paletted"])).find("rasterrenderer/colorPalette")
    entries = [(entry.attrib["value"], entry.attrib["color"], entry.attrib["label"]) for entry in palette]  # type: ignore[union-attr]
    assert entries == [(str(row.value), row.colour, row.name) for row in WORLDCOVER_LIKE]


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("exports/B04_red_10m.tif", "exports/B04_red_10m.qml"),
        ("exports/group-02/bands_20m.tif", "exports/group-02/bands_20m.qml"),
        ("result.tif", "result.qml"),
        ("no_suffix", "no_suffix.qml"),
    ],
)
def test_the_style_is_named_as_qgis_looks_for_it(path: str, name: str) -> None:
    styled = style_file("qml", path, CASES["gray"])
    assert styled is not None and styled[0] == name


# --- the style of an order --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        {"band": "red", "colormap": "viridis", "range": [0.02, 0.24]},
        {"band": "dtm", "colormap": None, "range": [-3, 1200]},
        {"rgb": ["nir", "red", "green"], "ranges": [[0, 0.5], [0, 0.3], [0, 0.3]]},
        {"rgb": ["red", "green", "blue"], "ranges": None},
    ],
)
def test_a_style_reads_and_writes_the_same(data: dict[str, Any]) -> None:
    style = ExportStyle.from_json(data)
    assert ExportStyle.from_json(json.loads(json.dumps(style.to_json()))) == style


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        "viridis",
        {},
        {"band": "red", "colormap": "viridis"},
        {"band": "red", "colormap": "viridis", "range": [0, 1], "extra": 1},
        {"band": "", "colormap": "viridis", "range": [0, 1]},
        {"band": "x" * 201, "colormap": "viridis", "range": [0, 1]},
        {"band": 4, "colormap": "viridis", "range": [0, 1]},
        {"band": "red", "colormap": "no_such_map", "range": [0, 1]},
        {"band": "red", "colormap": 7, "range": [0, 1]},
        {"band": "red", "colormap": "viridis", "range": [1, 0]},
        {"band": "red", "colormap": "viridis", "range": [1, 1]},
        {"band": "red", "colormap": "viridis", "range": [0, math.nan]},
        {"band": "red", "colormap": "viridis", "range": [-math.inf, 1]},
        {"band": "red", "colormap": "viridis", "range": [0, 1, 2]},
        {"band": "red", "colormap": "viridis", "range": [True, 2]},
        {"band": "red", "colormap": "viridis", "range": ["0", "1"]},
        {"band": "red", "colormap": "viridis", "range": None},
        {"rgb": ["red", "green"], "ranges": None},
        {"rgb": "red,green,blue", "ranges": None},
        {"rgb": ["red", "green", None], "ranges": None},
        {"rgb": ["red", "green", "blue"], "ranges": [[0, 1], [0, 1]]},
        {"rgb": ["red", "green", "blue"], "ranges": [[0, 1], [0, 1], [2, 1]]},
        {"rgb": ["red", "green", "blue"]},
    ],
)
def test_a_style_this_platform_does_not_draw_is_refused(data: Any) -> None:
    with pytest.raises(StyleInvalid):
        ExportStyle.from_json(data)


def test_a_table_of_classes_is_no_colormap_of_a_style() -> None:
    from earthx.access.colormaps import CLASS_TABLES

    assert CLASS_TABLES, "the registry has a standard picture of classes"
    with pytest.raises(StyleInvalid):
        ExportStyle.from_json({"band": "map", "colormap": CLASS_TABLES[0], "range": [0, 1]})


# --- the rule (plan §4) -----------------------------------------------------------------------------------------------

RED, GREEN, BLUE, NIR = (_meta(name) for name in ("red", "green", "blue", "nir"))
TRUE_COLOR = ("red", "green", "blue")


def test_1_the_drawn_colour_picture_takes_the_numbers_of_its_bands_in_this_file() -> None:
    style = ExportStyle(rgb=("nir", "red", "green"), ranges=((0, 0.5), (0, 0.3), (0, 0.2)))
    renderer = file_renderer([BLUE, GREEN, RED, NIR], style, TRUE_COLOR, Measures())
    assert renderer == Rgb((4, 3, 2), ((0, 0.5), (0, 0.3), (0, 0.2)))


def test_1_a_drawn_colour_picture_without_ranges_is_measured_per_channel() -> None:
    measures = Measures()
    renderer = file_renderer([RED, GREEN, NIR], ExportStyle(rgb=("nir", "red", "green"), ranges=None), (), measures)
    assert renderer == Rgb((3, 1, 2), ((3.0, 4.0), (1.0, 2.0), (2.0, 3.0)))
    assert measures.asked == [(3, 2.0, 98.0), (1, 2.0, 98.0), (2, 2.0, 98.0)]


def test_2_the_drawn_band_in_this_file_takes_its_colormap_and_range() -> None:
    style = ExportStyle(band="nir", colormap="magma", range=(0.1, 0.4))
    measures = Measures()
    assert file_renderer([RED, NIR], style, (), measures) == Pseudocolor(2, "magma", 0.1, 0.4)
    assert measures.asked == []


def test_2_the_drawn_band_without_a_colormap_is_grey() -> None:
    assert file_renderer([NIR], ExportStyle(band="nir", colormap=None, range=(0.1, 0.4)), (), Measures()) == Gray(1, 0.1, 0.4)


def test_2_a_drawn_band_of_classes_keeps_its_classes() -> None:
    scl = _meta("scl", classes=WORLDCOVER_LIKE)
    style = ExportStyle(band="scl", colormap="viridis", range=(0, 11))
    assert file_renderer([RED, scl], style, (), Measures()) == Paletted(2, WORLDCOVER_LIKE, 0.0)


def test_3_a_file_of_one_channel_of_the_drawn_picture_is_grey_in_its_stretch() -> None:
    style = ExportStyle(rgb=("nir", "red", "green"), ranges=((0, 0.5), (0, 0.3), (0, 0.2)))
    assert file_renderer([RED], style, TRUE_COLOR, Measures()) == Gray(1, 0, 0.3)
    measures = Measures()
    assert file_renderer([NIR], ExportStyle(rgb=("nir", "red", "green"), ranges=None), (), measures) == Gray(1, 1.0, 2.0)
    assert measures.asked == [(1, 2.0, 98.0)]


def test_4_the_true_colour_bands_of_the_collection_in_one_file_are_a_measured_colour_picture() -> None:
    measures = Measures()
    renderer = file_renderer([BLUE, GREEN, RED, NIR], ExportStyle(band="swir16", colormap="viridis", range=(0, 1)), TRUE_COLOR, measures)
    assert renderer == Rgb((3, 2, 1), ((3.0, 4.0), (2.0, 3.0), (1.0, 2.0)))


def test_4_needs_all_three_true_colour_bands() -> None:
    renderer = file_renderer([RED, GREEN, NIR], None, TRUE_COLOR, Measures())
    assert isinstance(renderer, Gray)


def test_5_the_first_band_takes_its_fixed_look_without_a_measure() -> None:
    cloud = _meta("cloud", look=Look("viridis", "fixed", 0.0, 100.0))
    measures = Measures()
    assert file_renderer([cloud, RED], None, (), measures) == Pseudocolor(1, "viridis", 0.0, 100.0)
    assert measures.asked == []


def test_5_a_measured_look_is_measured_from_the_2nd_to_the_98th_percentile() -> None:
    measures = Measures()
    renderer = file_renderer([_meta("red", look=Look("viridis"))], None, (), measures)
    assert renderer == Pseudocolor(1, "viridis", 1.0, 2.0)
    assert measures.asked == [(1, 2.0, 98.0)]


def test_5_a_look_in_percentiles_is_measured_at_its_own() -> None:
    measures = Measures()
    renderer = file_renderer([_meta("dem", look=Look("terrain", "percentiles", 0.0, 100.0))], None, (), measures)
    assert renderer == Pseudocolor(1, "terrain", 1.0, 2.0)
    assert measures.asked == [(1, 0.0, 100.0)]


def test_5_a_band_of_classes_is_paletted_and_one_without_look_grey() -> None:
    assert file_renderer([_meta("map", classes=WORLDCOVER_LIKE)], None, (), Measures()) == Paletted(1, WORLDCOVER_LIKE, 0.0)
    assert file_renderer([RED], None, (), Measures()) == Gray(1, 1.0, 2.0)


def test_0_an_asset_of_three_bands_is_its_own_colour_picture() -> None:
    visual = _meta("visual")
    measures = Measures()
    assert file_renderer([visual], None, TRUE_COLOR, measures, band_count=3, byte=True) == Rgb(
        (1, 2, 3), ((0.0, 255.0), (0.0, 255.0), (0.0, 255.0))
    )
    assert measures.asked == []
    renderer = file_renderer([visual], None, (), measures, band_count=3)
    assert renderer == Rgb((1, 2, 3), ((1.0, 2.0), (2.0, 3.0), (3.0, 4.0))), "not bytes: each channel measured"
    assert file_renderer([visual], None, (), Measures(), band_count=1) == Gray(1, 1.0, 2.0), "one band: the rule as before"


def test_the_style_of_a_written_visual_file_is_rgb_0_to_255() -> None:
    memory = MemoryFile()
    with memory.open(
        driver="GTiff", dtype="uint8", count=3, width=4, height=4, crs="EPSG:32632",
        transform=from_origin(500000, 5200000, 10, 10), nodata=0,
    ) as dataset:  # fmt: skip
        dataset.write(numpy.full((3, 4, 4), 7, dtype="uint8"))
    with memory, memory.open() as dataset:
        text = file_qml(dataset, [_meta("visual")], None, TRUE_COLOR)
    renderer = _pipe(text).find("rasterrenderer")
    assert renderer is not None and renderer.attrib["type"] == "multibandcolor"
    assert [renderer.attrib[f"{c}Band"] for c in ("red", "green", "blue")] == ["1", "2", "3"]
    assert [e.text for e in renderer.iter("maxValue")] == ["255.0"] * 3


def test_a_drawn_band_in_no_file_leaves_the_files_their_own_looks() -> None:
    cloud = _meta("cloud", look=Look("viridis", "fixed", 0.0, 100.0))
    style = ExportStyle(band="red", colormap="magma", range=(0.0, 0.3))
    assert file_renderer([cloud], style, (), Measures()) == Pseudocolor(1, "viridis", 0.0, 100.0)


def test_a_measure_without_width_is_made_one_wide_and_rounded() -> None:
    def flat(band: int, low: float, high: float) -> tuple[float, float]:
        return 0.30000000000000004, 0.30000000000000004

    assert file_renderer([RED], None, (), flat) == Gray(1, 0.3, 1.3)


# --- the measure of a written file ------------------------------------------------------------------------------------


def _tiff(data: numpy.ndarray, *, nodata: float, scale: float = 1.0, offset: float = 0.0) -> MemoryFile:
    memory = MemoryFile()
    with memory.open(
        driver="GTiff", dtype=data.dtype.name, count=1, width=data.shape[1], height=data.shape[0], crs="EPSG:32632",
        transform=from_origin(500000, 5200000, 10, 10), nodata=nodata,
    ) as dataset:  # fmt: skip
        dataset.write(data, 1)
        dataset.scales = (scale,)
        dataset.offsets = (offset,)
    return memory


def test_the_measure_is_in_physical_values_and_leaves_out_nodata() -> None:
    data = numpy.arange(1, 10001, dtype="uint16").reshape(100, 100)
    data[:10] = 0
    with _tiff(data, nodata=0, scale=0.0001, offset=-0.1) as memory, memory.open() as dataset:
        low, high = measured_range(dataset, 1, 2.0, 98.0)
    valid = numpy.arange(1001, 10001, dtype="float64")
    expected = numpy.percentile(valid, [2.0, 98.0]) * 0.0001 - 0.1
    assert low == pytest.approx(expected[0], abs=1e-12)
    assert high == pytest.approx(expected[1], abs=1e-12)


def test_a_large_file_is_measured_from_a_smaller_read() -> None:
    data = numpy.ones((3000, 2500), dtype="uint8")
    data[:, 1250:] = 200
    with _tiff(data, nodata=0) as memory, memory.open() as dataset:
        calls: list[Any] = []
        read = dataset.read

        def spy(*args: Any, **kwargs: Any) -> Any:
            calls.append(kwargs.get("out_shape"))
            return read(*args, **kwargs)

        dataset.read = spy  # type: ignore[method-assign]
        assert measured_range(dataset, 1, 0.0, 100.0) == (1.0, 200.0)
    assert calls == [(1000, 833)]


def test_a_band_without_values_and_a_constant_band_have_a_range_still() -> None:
    with _tiff(numpy.zeros((8, 8), dtype="uint8"), nodata=0) as memory, memory.open() as dataset:
        assert measured_range(dataset, 1, 2.0, 98.0) == (0.0, 1.0)
    with _tiff(numpy.full((8, 8), numpy.nan, dtype="float32"), nodata=math.nan) as memory, memory.open() as dataset:
        assert measured_range(dataset, 1, 2.0, 98.0) == (0.0, 1.0)
    with _tiff(numpy.full((8, 8), 7, dtype="uint8"), nodata=0) as memory, memory.open() as dataset:
        assert measured_range(dataset, 1, 2.0, 98.0) == (7.0, 8.0)


def test_the_style_of_a_written_file_measures_it_where_the_look_asks() -> None:
    data = numpy.arange(1, 101, dtype="uint16").reshape(10, 10)
    with _tiff(data, nodata=0, scale=0.01) as memory, memory.open() as dataset:
        text = file_qml(dataset, [_meta("red", look=Look("viridis", "percentiles", 0.0, 100.0))], None, ())
    renderer = _pipe(text).find("rasterrenderer")
    assert renderer is not None
    assert (float(renderer.attrib["classificationMin"]), float(renderer.attrib["classificationMax"])) == (0.01, 1.0)


# --- the style of a job's result --------------------------------------------------------------------------------------

STATISTICS = {"minimum": -0.5, "maximum": 0.9, "percentile_2": -0.1, "percentile_98": 0.8}


def _renderer(text: str | None) -> ET.Element:
    assert text is not None
    renderer = _pipe(text).find("rasterrenderer")
    assert renderer is not None
    return renderer


def test_a_result_without_style_is_grey_from_its_statistics() -> None:
    renderer = _renderer(result_qml({"bands": [{"name": "ndvi", "statistics": STATISTICS}]}, None, lambda band: None))
    assert renderer.attrib["type"] == "singlebandgray"
    assert renderer.find("contrastEnhancement/minValue").text == "-0.1"  # type: ignore[union-attr]
    assert renderer.find("contrastEnhancement/maxValue").text == "0.8"  # type: ignore[union-attr]


def test_a_result_takes_the_style_of_its_layer() -> None:
    bands = {"bands": [{"name": "ndvi", "statistics": STATISTICS}]}
    renderer = _renderer(result_qml(bands, ExportStyle(band="ndvi", colormap="rdylgn", range=(-0.2, 0.9)), lambda band: None))
    assert (renderer.attrib["type"], renderer.attrib["classificationMin"], renderer.attrib["classificationMax"]) == (
        "singlebandpseudocolor", "-0.2", "0.9",
    )  # fmt: skip


def test_a_style_of_one_band_draws_a_result_of_one_band_whatever_its_name() -> None:
    bands = {"bands": [{"name": "band_1", "statistics": STATISTICS}]}
    renderer = _renderer(result_qml(bands, ExportStyle(band="ndvi", colormap="rdylgn", range=(-0.2, 0.9)), lambda b: None))
    assert renderer.attrib["type"] == "singlebandpseudocolor"
    two = {"bands": [{"name": "a", "statistics": STATISTICS}, {"name": "b", "statistics": STATISTICS}]}
    renderer = _renderer(result_qml(two, ExportStyle(band="ndvi", colormap="rdylgn", range=(-0.2, 0.9)), lambda b: None))
    assert renderer.attrib["type"] == "singlebandgray", "of several bands only the one it names"


def test_a_result_band_of_classes_is_paletted_from_its_item() -> None:
    classes = [
        {"value": 10, "name": "tree_cover", "title": "Tree cover", "color_hint": "006400"},
        {"value": 20, "name": "shrubland", "title": "Shrubland", "color_hint": "FFBB22"},
    ]
    renderer = _renderer(result_qml({"bands": [{"name": "map", "classification:classes": classes}]}, None, lambda b: None))
    assert [(e.attrib["value"], e.attrib["color"], e.attrib["label"]) for e in renderer.find("colorPalette")] == [  # type: ignore[union-attr]
        ("10", "#006400", "Tree cover"), ("20", "#ffbb22", "Shrubland"),
    ]  # fmt: skip


def test_a_result_band_with_the_values_of_the_source_takes_its_look() -> None:
    looks = {"cloud": Look("viridis", "fixed", 0.0, 100.0), "red": Look("viridis")}
    properties = {
        "bands": [
            {"name": "cloud", "earthx:source_values": True, "statistics": STATISTICS},
            {"name": "red", "earthx:source_values": True, "statistics": STATISTICS},
        ]
    }
    renderer = _renderer(result_qml(properties, None, looks.get))
    assert (renderer.attrib["classificationMin"], renderer.attrib["classificationMax"]) == ("0.0", "100.0")
    one = {"bands": properties["bands"][1:]}
    renderer = _renderer(result_qml(one, None, looks.get))
    assert (renderer.attrib["classificationMin"], renderer.attrib["classificationMax"]) == ("-0.1", "0.8")


def test_a_result_band_that_changed_takes_no_look_of_the_source() -> None:
    properties = {"bands": [{"name": "cloud", "statistics": STATISTICS}]}
    renderer = _renderer(result_qml(properties, None, {"cloud": Look("viridis", "fixed", 0.0, 100.0)}.get))
    assert renderer.attrib["type"] == "singlebandgray"


@pytest.mark.parametrize(
    "properties",
    [None, {}, {"bands": []}, {"bands": "ndvi"}, {"bands": [7]}, {"bands": [{"name": "map", "classification:classes": [{}]}]}],
)
def test_a_result_that_names_no_bands_has_no_style(properties: Any) -> None:
    assert result_qml(properties, None, lambda band: None) is None


def test_a_result_without_statistics_is_grey_from_0_to_1() -> None:
    renderer = _renderer(result_qml({"bands": [{"name": "x", "statistics": {"percentile_2": "a"}}]}, None, lambda b: None))
    assert renderer.find("contrastEnhancement/minValue").text == "0.0"  # type: ignore[union-attr]


# --- the look a band carries ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("look", [None, Look("viridis"), Look("terrain", "fixed", 0.0, 5000.0), Look("magma", "percentiles", 2, 98)])
def test_the_look_of_a_band_travels_with_the_order(look: Look | None) -> None:
    meta = _meta("red", look=look)
    data = json.loads(json.dumps(meta.to_json()))
    assert ("look" in data) == (look is not None)
    assert BandMeta.from_json(data) == meta


@pytest.mark.parametrize(
    "look",
    [
        "viridis",
        {"colormap": "viridis"},
        {"colormap": "viridis", "scale": "stretched"},
        {"colormap": 1, "scale": "measured"},
        {"colormap": "viridis", "scale": "fixed", "low": 1.0},
        {"colormap": "viridis", "scale": "fixed", "low": 2.0, "high": 1.0},
        {"colormap": "viridis", "scale": "fixed", "low": "0", "high": 1.0},
        {"colormap": "viridis", "scale": "fixed", "low": 0.0, "high": math.inf},
        {"colormap": "viridis", "scale": "measured", "extra": 1},
    ],
)
def test_a_look_that_is_none_is_refused(look: Any) -> None:
    data = {**_meta("red").to_json(), "look": look}
    with pytest.raises(ValueError):
        BandMeta.from_json(data)


def write_cases(directory: str) -> None:
    """The styles of :data:`CASES` into ``directory``, for ``fixtures/qgis/make_reference.py``."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    for case, renderer in CASES.items():
        (target / f"{case}.qml").write_text(qml_text(renderer), encoding="utf-8")


if __name__ == "__main__":
    write_cases(sys.argv[1])
