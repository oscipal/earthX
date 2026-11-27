"""M5-64: the QGIS style beside every exported raster (plan ``m5-64-qgis-stil.md``).

QGIS has no schema of its styles; the reference is what QGIS 3.34 writes itself (``tests/fixtures/qgis/``, written by
``scripts/write-qgis-reference-styles.py`` from the same inputs). Ours must be the same document: the same elements in
the same order, the same attributes, the same values (numbers as numbers). Where QGIS is installed, it also loads each
style and draws it; CI has no QGIS and skips that part.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from earthx.access.colormap_tables import ramp_colours
from earthx.access.colormaps import COLORMAPS
from earthx.access.qgis_style import (
    MASK_STYLE,
    ExportStyles,
    RgbLook,
    Stats,
    collection_styles,
    dataset_style,
    file_style,
    measure_band,
    paletted_style,
    parse_order_look,
    pseudocolor_style,
    rgb_style,
    style_name,
)
from earthx.catalog.registry import ClassRow, Look
from tests.catalog.entries import COP_DEM_GLO_30, SENTINEL_2_L2A

REFERENCES = Path(__file__).resolve().parents[2] / "fixtures" / "qgis"
CLASSES = (ClassRow(10, "Tree cover", "#006400"), ClassRow(20, "Shrub & <land>", "#FFBB22"))


def _number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def _same_value(ours: str, theirs: str) -> bool:
    a, b = _number(ours), _number(theirs)
    if a is not None and b is not None:
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    return ours == theirs


def _differences(ours: ET.Element, theirs: ET.Element, path: str = "") -> list[str]:
    """Where two styles differ: element, attribute set, value, text, number of children; attribute order is free."""
    here = f"{path}/{theirs.tag}"
    if ours.tag != theirs.tag:
        return [f"{here}: element {ours.tag}"]
    found = []
    if set(ours.attrib) != set(theirs.attrib):
        found.append(f"{here}: attributes {sorted(set(ours.attrib) ^ set(theirs.attrib))}")
    found += [
        f"{here}@{key}: {ours.attrib[key][:60]!r} for {theirs.attrib[key][:60]!r}"
        for key in set(ours.attrib) & set(theirs.attrib)
        if not _same_value(ours.attrib[key], theirs.attrib[key])
    ]
    if not _same_value((ours.text or "").strip(), (theirs.text or "").strip()):
        found.append(f"{here}: text {ours.text!r}")
    if len(ours) != len(theirs):
        found.append(f"{here}: {len(ours)} children for {len(theirs)}")
    for mine, other in zip(ours, theirs, strict=False):
        found += _differences(mine, other, here)
    return found


OURS = {
    "pseudocolor": lambda: pseudocolor_style(1, ramp_colours("viridis") or [], 0.0, 0.3),
    "rgb": lambda: rgb_style((1, 2, 3), [(0.0, 0.25), (0.01, 0.26), (0.02, 0.27)]),
    "paletted": lambda: paletted_style(1, [(row.value, row.colour, row.name, 255) for row in CLASSES]),
}


class TestTheReferenceOfQgis:
    @pytest.mark.parametrize("kind", sorted(OURS))
    def test_ours_is_the_document_qgis_writes(self, kind: str) -> None:
        theirs = ET.parse(REFERENCES / f"{kind}.qml").getroot()
        assert _differences(ET.fromstring(OURS[kind]()), theirs) == []

    def test_the_reference_was_written_with_the_ramp_the_tiles_draw(self) -> None:
        written = json.loads((REFERENCES / "viridis.json").read_text(encoding="utf-8"))
        assert [tuple(colour) for colour in written] == ramp_colours("viridis")

    @pytest.mark.parametrize("kind", sorted(OURS))
    def test_a_style_starts_as_qgis_reads_it_and_has_no_time_in_it(self, kind: str) -> None:
        text = OURS[kind]()
        assert text.startswith("<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n<qgis styleCategories=\"Symbology\"")
        assert text == OURS[kind]()  # the same bytes each time: crop and job agree, the ETag of a ZIP holds


class TestTheRamps:
    @pytest.mark.parametrize("name", ["viridis", "rdbu_r", "greys_r", "terrain", "blues", "rocket", "mako_r", "cfastie_r", "rdylgn"])
    def test_every_ramp_is_the_table_the_tiles_draw(self, name: str) -> None:
        table = COLORMAPS.get(name)
        assert ramp_colours(name) == [tuple(int(c) for c in table[key]) for key in sorted(table)]

    def test_a_ramp_has_256_stops_from_the_low_to_the_high_end(self) -> None:
        root = ET.fromstring(pseudocolor_style(2, ramp_colours("rdbu_r") or [], -20.0, 30.0))
        items = root.findall(".//colorrampshader/item")
        assert len(items) == 256 and root.find(".//rasterrenderer").get("band") == "2"
        assert (float(items[0].get("value")), float(items[-1].get("value"))) == (-20.0, 30.0)
        assert items[0].get("color") == "#{:02x}{:02x}{:02x}".format(*ramp_colours("rdbu_r")[0][:3])
        assert root.find(".//colorrampshader").get("clip") == "0"  # outside the range the end colours, as the tiles

    def test_an_unknown_ramp_has_no_table(self) -> None:
        assert ramp_colours("no-such-ramp") is None


class TestTheLookOfAnOrder:
    def test_bands_and_rgb_are_read_with_physical_numbers(self) -> None:
        looks, rgb = parse_order_look(
            {"bands": {"red": {"colormap": "viridis", "low": 0, "high": 0.3}},
             "rgb": {"bands": ["swir22", "nir08", "red"], "ranges": [[0, 0.4], [0, 0.5], [0, 0.3]]}}
        )  # fmt: skip
        assert looks == {"red": Look("viridis", "fixed", 0.0, 0.3)}
        assert rgb == RgbLook(("swir22", "nir08", "red"), ((0.0, 0.4), (0.0, 0.5), (0.0, 0.3)))

    @pytest.mark.parametrize(
        "look",
        [
            [],
            "viridis",
            {"bands": {"red": {"colormap": "no-such-ramp", "low": 0, "high": 1}}},
            {"bands": {"red": {"colormap": "viridis", "low": 1, "high": 1}}},
            {"bands": {"red": {"colormap": "viridis", "low": 2, "high": 1}}},
            {"bands": {"red": {"colormap": "viridis", "low": float("nan"), "high": 1}}},
            {"bands": {"red": {"colormap": "viridis", "low": "0", "high": 1}}},
            {"bands": {"red": {"colormap": "viridis", "low": True, "high": 2}}},
            {"bands": {"red": {"colormap": "viridis", "low": 0}}},
            {"bands": {"red": {"colormap": "viridis", "low": 0, "high": 1, "scale": "measured"}}},
            {"bands": {"": {"colormap": "viridis", "low": 0, "high": 1}}},
            {"bands": {f"b{i}": {"colormap": "viridis", "low": 0, "high": 1} for i in range(65)}},
            {"bands": [], "extra": 1},
            {"rgb": {"bands": ["a", "b"], "ranges": [[0, 1], [0, 1]]}},
            {"rgb": {"bands": ["a", "b", "c"], "ranges": [[0, 1], [0, 1], [1, 0]]}},
            {"rgb": {"bands": ["a", "b", "c"], "ranges": [[0, 1], [0, 1], [0, 1]], "colormap": "viridis"}},
        ],
    )
    def test_a_look_that_is_no_look_is_refused(self, look: object) -> None:
        with pytest.raises(ValueError):
            parse_order_look(look)

    def test_the_order_goes_over_the_collection_and_the_standard_picture_gives_its_stretch(self) -> None:
        styles = collection_styles(SENTINEL_2_L2A, ["red", "visual"], {"bands": {"red": {"colormap": "magma", "low": 0, "high": 0.2}}})
        assert styles.looks["red"] == Look("magma", "fixed", 0.0, 0.2)
        assert styles.looks["visual"] == Look("gray", "fixed", 0.0, 255.0)
        assert styles.true_color == tuple(SENTINEL_2_L2A.true_color)

    def test_without_a_look_each_band_takes_the_look_of_the_collection(self) -> None:
        styles = collection_styles(COP_DEM_GLO_30, ["data"])
        assert styles.looks["data"] == COP_DEM_GLO_30.look_of("data").look  # type: ignore[union-attr]

    def test_the_styles_travel_as_json_and_back(self) -> None:
        styles = ExportStyles(
            {"red": Look("viridis"), "nir": Look("magma", "fixed", 0.0, 0.5)},
            RgbLook(("a", "b", "c"), ((0.0, 1.0), (0.0, 2.0), (0.0, 3.0))),
            ("red", "green", "blue"),
        )
        assert ExportStyles.from_json(json.loads(json.dumps(styles.to_json()))) == styles

    @pytest.mark.parametrize("data", [[], {"looks": []}, {"looks": {"a": {"scale": "measured"}}}, {"rgb": {"bands": ["a"]}}])
    def test_styles_of_the_wrong_form_are_refused(self, data: object) -> None:
        with pytest.raises(ValueError):
            ExportStyles.from_json(data)  # type: ignore[arg-type]


def _kind(style: str) -> str:
    return ET.fromstring(style).find(".//rasterrenderer").get("type")  # type: ignore[union-attr]


STATS = Stats(p2=0.1, p98=0.9, minimum=0.0, maximum=1.0)


def _style(keys: list[str], styles: ExportStyles, classes: list | None = None) -> str:
    return file_style(len(keys), keys, classes or [None] * len(keys), styles, lambda index: STATS)


class TestWhatEachFileGets:
    def test_three_bands_of_one_asset_are_true_colour(self) -> None:
        root = ET.fromstring(_style(["visual"] * 3, ExportStyles({"visual": Look("gray", "fixed", 0.0, 255.0)})))
        assert root.find(".//rasterrenderer").get("type") == "multibandcolor"
        assert [float(e.text) for e in root.iter("maxValue")] == [255.0] * 3

    def test_the_rgb_of_the_look_where_its_three_bands_are_in_the_file(self) -> None:
        rgb = RgbLook(("c", "b", "a"), ((0.0, 0.3), (0.0, 0.4), (0.0, 0.5)))
        root = ET.fromstring(_style(["a", "b", "c", "d"], ExportStyles(rgb=rgb)))
        renderer = root.find(".//rasterrenderer")
        assert (renderer.get("redBand"), renderer.get("greenBand"), renderer.get("blueBand")) == ("3", "2", "1")
        assert [float(e.text) for e in root.iter("maxValue")] == [0.3, 0.4, 0.5]

    def test_a_band_of_classes_is_its_palette_with_names_and_colours(self) -> None:
        root = ET.fromstring(_style(["map"], ExportStyles(), [CLASSES]))
        entries = [(e.get("value"), e.get("color"), e.get("label")) for e in root.iter("paletteEntry")]
        assert entries == [("10", "#006400", "Tree cover"), ("20", "#ffbb22", "Shrub & <land>")]

    def test_the_band_the_look_names_in_a_file_of_several(self) -> None:
        root = ET.fromstring(_style(["a", "b", "c"], ExportStyles({"b": Look("magma", "fixed", 1.0, 2.0)})))
        renderer = root.find(".//rasterrenderer")
        assert (renderer.get("type"), renderer.get("band"), renderer.get("classificationMax")) == ("singlebandpseudocolor", "2", "2")

    def test_true_colour_where_no_look_names_a_band_and_its_three_bands_are_there(self) -> None:
        styles = ExportStyles(true_color=("red", "green", "blue"))
        renderer = ET.fromstring(_style(["blue", "green", "red", "nir"], styles)).find(".//rasterrenderer")
        assert (renderer.get("type"), renderer.get("redBand"), renderer.get("blueBand")) == ("multibandcolor", "3", "1")

    def test_else_band_one_in_viridis_on_the_usual_scale_of_the_measure(self) -> None:
        root = ET.fromstring(_style(["a", "b"], ExportStyles()))
        shader = root.find(".//colorrampshader")
        assert (float(shader.get("minimumValue")), float(shader.get("maximumValue"))) == (0.1, 0.9)
        assert root.find(".//item").get("color") == "#440154"  # viridis

    def test_percentiles_0_100_take_the_minimum_and_the_maximum(self) -> None:
        shader = ET.fromstring(_style(["a"], ExportStyles({"a": Look("greys_r", "percentiles", 0.0, 100.0)}))).find(".//colorrampshader")
        assert (float(shader.get("minimumValue")), float(shader.get("maximumValue"))) == (0.0, 1.0)

    def test_a_band_with_one_value_still_has_two_ends(self) -> None:
        flat = Stats(5.0, 5.0, 5.0, 5.0)
        shader = ET.fromstring(file_style(1, ["a"], [None], ExportStyles(), lambda index: flat)).find(".//colorrampshader")
        assert float(shader.get("minimumValue")) < 5.0 < float(shader.get("maximumValue"))

    def test_a_band_without_any_valid_pixel_is_drawn_from_0_to_1(self) -> None:
        shader = ET.fromstring(file_style(1, ["a"], [None], ExportStyles(), lambda index: None)).find(".//colorrampshader")
        assert (float(shader.get("minimumValue")), float(shader.get("maximumValue"))) == (0.0, 1.0)

    def test_a_file_whose_bands_are_not_named_once_each_is_refused(self) -> None:
        with pytest.raises(ValueError):
            file_style(2, ["a"], [None], ExportStyles(), lambda index: STATS)

    def test_the_mask_is_inside_white_and_outside_not_drawn(self) -> None:
        entries = [(e.get("value"), e.get("alpha"), e.get("label")) for e in ET.fromstring(MASK_STYLE).iter("paletteEntry")]
        assert entries == [("0", "0", "Outside AOI"), ("1", "255", "Inside AOI")]

    @pytest.mark.parametrize(("raster", "style"), [("B04_red_10m.tif", "B04_red_10m.qml"), ("result.tif", "result.qml"), ("x_mask.tif", "x_mask.qml")])
    def test_the_style_has_the_name_of_its_file(self, raster: str, style: str) -> None:
        assert style_name(raster) == style


def _scaled_file(values: numpy.ndarray, *, nodata: int = 0) -> MemoryFile:
    memory = MemoryFile()
    profile = {"driver": "GTiff", "dtype": "uint16", "count": 1, "width": values.shape[1], "height": values.shape[0],
               "crs": "EPSG:32632", "transform": from_origin(500000, 5200000, 10, 10), "nodata": nodata}  # fmt: skip
    with memory.open(**profile) as dataset:
        dataset.write(values, 1)
        dataset.scales, dataset.offsets = (0.0001,), (-0.1,)
    return memory


class TestMeasuringAFile:
    def test_the_measure_is_physical_and_leaves_out_what_has_no_data(self) -> None:
        values = numpy.arange(1000, 1100, dtype="uint16").reshape(10, 10)
        values[0, :5] = 0
        with _scaled_file(values) as memory, memory.open() as dataset:
            stats = measure_band(dataset, 1)
        assert stats is not None
        assert stats.minimum == pytest.approx(0.0005) and stats.maximum == pytest.approx(0.0099)

    def test_a_file_without_a_valid_pixel_has_no_measure(self) -> None:
        with _scaled_file(numpy.zeros((4, 4), dtype="uint16")) as memory, memory.open() as dataset:
            assert measure_band(dataset, 1) is None

    def test_a_large_file_is_read_at_most_1024_pixels_a_side(self, tmp_path: Path) -> None:
        path = tmp_path / "large.tif"
        profile = {"driver": "GTiff", "dtype": "uint8", "count": 1, "width": 3000, "height": 100, "crs": "EPSG:32632",
                   "transform": from_origin(0, 0, 1, 1)}  # fmt: skip
        with rasterio.open(path, "w", **profile) as dataset:
            dataset.write(numpy.tile(numpy.arange(3000) % 200, (100, 1)).astype("uint8"), 1)
        reads: list[tuple[int, int]] = []
        with rasterio.open(path) as dataset:
            original = dataset.read

            def spy(*args, **kwargs):
                reads.append(kwargs["out_shape"])
                return original(*args, **kwargs)

            dataset.read = spy  # type: ignore[method-assign]
            dataset_style(dataset, ["a"], [None], ExportStyles())
        assert reads and max(reads[0]) <= 1024


#: The system Python with QGIS (``python3-qgis``), where there is one; CI has none.
QGIS_PYTHON = next((path for path in ("/usr/bin/python3.12", "/usr/bin/python3") if shutil.which(path)), None)


def _qgis_available() -> bool:
    if QGIS_PYTHON is None:
        return False
    probe = subprocess.run([QGIS_PYTHON, "-c", "import qgis.core"], capture_output=True, check=False)
    return probe.returncode == 0


@pytest.mark.skipif(not _qgis_available(), reason="QGIS is not installed (CI); the reference files stand in for it")
def test_qgis_loads_and_draws_every_kind_of_style(tmp_path: Path) -> None:
    """With QGIS itself: each style loads, its renderer has our numbers, and it draws the expected colour at a pixel."""
    with rasterio.open(tmp_path / "scaled.tif", "w", **{
        "driver": "GTiff", "dtype": "uint16", "count": 1, "width": 4, "height": 4, "crs": "EPSG:32632",
        "transform": from_origin(500000, 5200000, 10, 10), "nodata": 0,
    }) as dataset:  # fmt: skip
        dataset.write(numpy.full((4, 4), 2500, dtype="uint16"), 1)  # 0.15 after scale and offset: the middle of 0..0.3
        dataset.scales, dataset.offsets = (0.0001,), (-0.1,)
    (tmp_path / "scaled.qml").write_text(OURS["pseudocolor"](), encoding="utf-8")
    script = textwrap.dedent(
        f"""
        import os
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from qgis.core import QgsApplication, QgsRasterLayer, QgsMapSettings, QgsMapRendererSequentialJob
        from qgis.PyQt.QtCore import QSize
        app = QgsApplication([], False); app.initQgis()
        layer = QgsRasterLayer({str(tmp_path / "scaled.tif")!r}, "x")  # loads scaled.qml beside it by itself
        shader = layer.renderer().shader().rasterShaderFunction()
        settings = QgsMapSettings(); settings.setLayers([layer]); settings.setExtent(layer.extent())
        settings.setOutputSize(QSize(4, 4)); settings.setDestinationCrs(layer.crs())
        job = QgsMapRendererSequentialJob(settings); job.start(); job.waitForFinished()
        print(layer.renderer().type(), shader.minimumValue(), shader.maximumValue(), hex(job.renderedImage().pixel(1, 1)))
        """
    )
    done = subprocess.run([QGIS_PYTHON, "-c", script], capture_output=True, text=True, check=True, timeout=120)
    kind, low, high, colour = done.stdout.split()[-4:]
    middle = ramp_colours("viridis")[128]
    assert (kind, float(low), float(high)) == ("singlebandpseudocolor", 0.0, 0.3)
    drawn = [int(colour[4:6], 16), int(colour[6:8], 16), int(colour[8:10], 16)]
    assert all(abs(a - b) <= 2 for a, b in zip(drawn, middle[:3], strict=True)), (drawn, middle)
