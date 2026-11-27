"""The QGIS style beside every raster file of an export (M5-64, plan ``plans/m5/m5-64-qgis-stil.md``).

QGIS opens ``<name>.qml`` beside ``<name>.tif`` by itself, so each data file of a ZIP gets one that draws it as the app
does: the colormap and range of a band, the stretch of each channel of a colour picture, the classes of a band of classes.

**What decides it.** An order carries at most one drawn look, the layer's (:class:`ExportStyle`, physical values, never
stored in the recipe); every band carries its look from the collection (:attr:`BandMeta.look`) and its classes. The rule
of :func:`file_renderer` picks one renderer per file from them, and where a look has no numbers of its own the file is
measured once (:func:`measured_range`).

**Numbers are physical**: QGIS applies the scale and offset a GeoTIFF states, so a range in the file's stored numbers would
miss its data (measured with QGIS 3.34, plan §2.2). The form is what QGIS 3.34 writes for the category "Symbology"; a
colormap is the tiler's own table of 256 colours, as items of the shader and as the stops of its ramp, never a name of
a ramp of QGIS.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import numpy
from rasterio.enums import Resampling

from earthx.access.band_export import BandMeta
from earthx.access.colormaps import CLASS_TABLES, COLORMAPS
from earthx.catalog.registry import ClassRow, DatasetConfig, Look

__all__ = [
    "QML_SUFFIX",
    "ExportStyle",
    "Gray",
    "Paletted",
    "Pseudocolor",
    "Renderer",
    "Rgb",
    "StyleInvalid",
    "collection_look",
    "file_qml",
    "file_renderer",
    "measured_range",
    "qml_name",
    "qml_text",
    "result_qml",
]

QML_SUFFIX = ".qml"

#: The usual scale of a measure (adr/0035): the 2nd to the 98th percentile.
MEASURED = (2.0, 98.0)
#: The longest side a file is read at to measure it (plan A3).
MEASURE_SIDE = 1024
_MAX_NAME = 200

Range = tuple[float, float]


class StyleInvalid(ValueError):
    """The style of an order is not one this platform draws; the text names no value."""


def _finite_range(value: Any) -> Range:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise StyleInvalid("a range is two numbers")
    low, high = value
    for end in (low, high):
        if isinstance(end, bool) or not isinstance(end, (int, float)) or not math.isfinite(end):
            raise StyleInvalid("a range is two finite numbers")
    if not low < high:
        raise StyleInvalid("the low end of a range is below its high end")
    return float(low), float(high)


def _band_name(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_NAME:
        raise StyleInvalid(f"a band is named by a text of at most {_MAX_NAME} characters")
    return value


@dataclass(frozen=True, slots=True)
class ExportStyle:
    """The look a layer is drawn with as the order carries it: one band with a colormap (``None``: grey) and a range, or a
    colour picture of three bands with a range each (``None``: measured)."""

    band: str | None = None
    colormap: str | None = None
    range: Range | None = None
    rgb: tuple[str, str, str] | None = None
    ranges: tuple[Range, Range, Range] | None = None

    @classmethod
    def from_json(cls, data: Any) -> ExportStyle:
        if isinstance(data, Mapping) and set(data) == {"band", "colormap", "range"}:
            colormap = data["colormap"]
            if colormap is not None and (
                not isinstance(colormap, str) or colormap in CLASS_TABLES or colormap not in COLORMAPS.list()
            ):
                raise StyleInvalid("colormap is null or one of GET /colormaps")
            return cls(band=_band_name(data["band"]), colormap=colormap, range=_finite_range(data["range"]))
        if isinstance(data, Mapping) and set(data) == {"rgb", "ranges"}:
            bands = data["rgb"]
            if not isinstance(bands, (list, tuple)) or len(bands) != 3:
                raise StyleInvalid("rgb names three bands")
            ranges = data["ranges"]
            if ranges is not None and (not isinstance(ranges, (list, tuple)) or len(ranges) != 3):
                raise StyleInvalid("ranges is null or a range per channel")
            red, green, blue = (_band_name(band) for band in bands)
            return cls(
                rgb=(red, green, blue),
                ranges=None if ranges is None else (_finite_range(ranges[0]), _finite_range(ranges[1]), _finite_range(ranges[2])),
            )
        raise StyleInvalid('a style is {"band", "colormap", "range"} or {"rgb", "ranges"}')

    def to_json(self) -> dict[str, Any]:
        if self.rgb is not None:
            return {"rgb": list(self.rgb), "ranges": None if self.ranges is None else [list(r) for r in self.ranges]}
        return {"band": self.band, "colormap": self.colormap, "range": None if self.range is None else list(self.range)}


@dataclass(frozen=True, slots=True)
class Pseudocolor:
    band: int
    colormap: str
    low: float
    high: float


@dataclass(frozen=True, slots=True)
class Gray:
    band: int
    low: float
    high: float


@dataclass(frozen=True, slots=True)
class Rgb:
    bands: tuple[int, int, int]
    ranges: tuple[Range, Range, Range]


@dataclass(frozen=True, slots=True)
class Paletted:
    band: int
    classes: tuple[ClassRow, ...]


Renderer = Pseudocolor | Gray | Rgb | Paletted

#: Measures band ``index`` (from 1) of a file from the ``low`` to the ``high`` percentile, in physical values.
Measure = Callable[[int, float, float], Range]


def collection_look(config: DatasetConfig, band: str) -> Look | None:
    """The look ``band`` has in the collection (M5-60), which a file takes where the order draws it with no other."""
    resolved = config.look_of(band)
    return None if resolved is None else resolved.look


def _usable(low: float, high: float) -> Range:
    """A range QGIS can stretch over: rounded like the registry's physical numbers, and one wide where it has no width."""
    low, high = (float(f"{value:.12g}") for value in (low, high))
    return (low, high) if low < high else (low, low + 1.0)


def file_renderer(
    bands: Sequence[BandMeta], style: ExportStyle | None, true_color: Sequence[str], measure: Measure
) -> Renderer:
    """The renderer of a file of ``bands`` (in the order of the file), by the rule of the plan (§4), the first that holds:
    the drawn colour picture in this file; the drawn band in this file; a file of one channel of the drawn picture, grey
    in its stretch; the collection's true-colour bands in this file, measured; the first band with its own look."""
    index = {meta.asset: number for number, meta in enumerate(bands, start=1)}
    if style is not None and style.rgb is not None:
        if all(band in index for band in style.rgb):
            numbers = (index[style.rgb[0]], index[style.rgb[1]], index[style.rgb[2]])
            if style.ranges is not None:
                return Rgb(numbers, style.ranges)
            return Rgb(numbers, (_measured(measure, numbers[0]), _measured(measure, numbers[1]), _measured(measure, numbers[2])))
        if len(bands) == 1 and bands[0].asset in style.rgb and bands[0].classes is None:
            channel = style.rgb.index(bands[0].asset)
            return Gray(1, *(style.ranges[channel] if style.ranges is not None else _measured(measure, 1)))
    if style is not None and style.band is not None and style.band in index:
        number = index[style.band]
        meta = bands[number - 1]
        if meta.classes is not None:
            return Paletted(number, meta.classes)
        assert style.range is not None
        if style.colormap is None:
            return Gray(number, *style.range)
        return Pseudocolor(number, style.colormap, *style.range)
    if len(true_color) == 3 and all(band in index for band in true_color):
        numbers = (index[true_color[0]], index[true_color[1]], index[true_color[2]])
        return Rgb(numbers, (_measured(measure, numbers[0]), _measured(measure, numbers[1]), _measured(measure, numbers[2])))
    first = bands[0]
    if first.classes is not None:
        return Paletted(1, first.classes)
    look = first.look
    if look is None:
        return Gray(1, *_measured(measure, 1))
    if look.scale == "fixed":
        assert look.low is not None and look.high is not None
        return Pseudocolor(1, look.colormap, look.low, look.high)
    if look.scale == "percentiles":
        assert look.low is not None and look.high is not None
        return Pseudocolor(1, look.colormap, *_usable(*measure(1, look.low, look.high)))
    return Pseudocolor(1, look.colormap, *_measured(measure, 1))


def _measured(measure: Measure, band: int) -> Range:
    return _usable(*measure(band, *MEASURED))


def measured_range(dataset: Any, band: int, low: float, high: float) -> Range:
    """The ``low`` and ``high`` percentile of band ``band`` of an open dataset, in physical values (its own scale and
    offset, as QGIS applies them), read at most :data:`MEASURE_SIDE` pixels wide (from its overviews where it has them).
    A band without a valid value gives 0 to 1 (plan A3)."""
    factor = max(1, math.ceil(max(dataset.width, dataset.height) / MEASURE_SIDE))
    shape = (max(1, dataset.height // factor), max(1, dataset.width // factor))
    data = dataset.read(band, out_shape=shape, masked=True, resampling=Resampling.nearest)
    values = numpy.ma.compressed(data).astype(numpy.float64)
    values = values[numpy.isfinite(values)]
    if values.size == 0:
        return 0.0, 1.0
    ends = numpy.percentile(values, [low, high]) * dataset.scales[band - 1] + dataset.offsets[band - 1]
    return _usable(float(ends.min()), float(ends.max()))


def file_qml(dataset: Any, bands: Sequence[BandMeta], style: ExportStyle | None, true_color: Sequence[str]) -> str:
    """The ``.qml`` of a written file, open as ``dataset``, of ``bands`` in its order (:func:`file_renderer`)."""
    return qml_text(
        file_renderer(bands, style, true_color, lambda band, low, high: measured_range(dataset, band, low, high))
    )


def _result_band(band: Mapping[str, Any], look_of: Callable[[str], Look | None]) -> BandMeta:
    name = str(band.get("name", ""))
    stac = band.get("classification:classes")
    classes = None
    if isinstance(stac, list) and stac:
        classes = tuple(
            ClassRow(int(row["value"]), str(row.get("title") or row.get("name")), f"#{str(row['color_hint']).lower()}")
            for row in stac
        )
    return BandMeta(
        asset=name, name=name, common_name=None, wavelength_um=None, resolution_m=None, data_type=None, scale=None,
        offset=None, nodata=None, unit=None, categorical=classes is not None, classes=classes,
        look=look_of(name) if band.get("earthx:source_values") is True else None,
    )  # fmt: skip


def _statistics_range(statistics: Any, low: float, high: float) -> Range:
    """The ends a result's statistics hold for ``low`` and ``high``: its minimum and maximum for 0 and 100, else its 2nd
    and 98th percentile, the only ones it keeps; 0 to 1 where it has none."""
    stats = statistics if isinstance(statistics, Mapping) else {}
    keys = ("minimum", "maximum") if (low, high) == (0.0, 100.0) else ("percentile_2", "percentile_98")
    ends = [stats.get(key) for key in keys]
    if not all(isinstance(end, (int, float)) and not isinstance(end, bool) and math.isfinite(end) for end in ends):
        return 0.0, 1.0
    return _usable(float(ends[0]), float(ends[1]))  # type: ignore[arg-type]


def result_qml(properties: Any, style: ExportStyle | None, look_of: Callable[[str], Look | None]) -> str | None:
    """``result.qml`` of a job's result from its STAC ``properties`` (F6): the layer's ``style`` where it names bands of
    the result (a style of one band always applies to a result of one band); else classes in their colours, a band with the source's values in its look (``look_of``), any other grey
    from the 2nd to the 98th percentile of its statistics. ``None`` for a result whose properties list no bands."""
    bands = properties.get("bands") if isinstance(properties, Mapping) else None
    if not isinstance(bands, list) or not bands or not all(isinstance(band, Mapping) for band in bands):
        return None
    try:
        metas = [_result_band(band, look_of) for band in bands]
    except (KeyError, TypeError, ValueError):
        return None

    def measure(index: int, low: float, high: float) -> Range:
        return _statistics_range(bands[index - 1].get("statistics"), low, high)

    if style is not None and style.band is not None and len(metas) == 1:
        # A layer of a result of one band draws that band, whatever the layer calls it.
        style = replace(style, band=metas[0].asset)

    return qml_text(file_renderer(metas, style, (), measure))


def qml_name(path: str) -> str:
    """``<name>.qml`` beside ``<name>.tif``: the name QGIS looks for when it opens the file."""
    stem, dot, _ = path.rpartition(".")
    return (stem if dot else path) + QML_SUFFIX


# --- the file ---------------------------------------------------------------------------------------------------------

#: The version of QGIS the form was checked against (plan A7).
QGIS_VERSION = "3.34.4"
_DOCTYPE = "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"
_STEPS = 255


def _number(value: float) -> str:
    return repr(float(value))


def _rgba(colour: Sequence[int]) -> str:
    return f"{colour[0]},{colour[1]},{colour[2]},255"


def _hex(colour: Sequence[int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*colour[:3])


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attributes: str) -> ET.Element:
    element = ET.SubElement(parent, tag, attributes)
    if text is not None:
        element.text = text
    return element


def _option_map(
    parent: ET.Element, tag: str, options: Sequence[tuple[str, str | None, str | None]], **attributes: str
) -> None:
    outer = _sub(_sub(parent, tag, **attributes), "Option", type="Map")
    for name, value, kind in options:
        attributes = {"value": value, "name": name, "type": kind}
        _sub(outer, "Option", **{key: text for key, text in attributes.items() if text is not None})


def _min_max_origin(renderer: ET.Element) -> None:
    origin = _sub(renderer, "minMaxOrigin")
    for tag, text in (
        ("limits", "None"), ("extent", "WholeRaster"), ("statAccuracy", "Estimated"),
        ("cumulativeCutLower", "0.02"), ("cumulativeCutUpper", "0.98"), ("stdDevFactor", "2"),
    ):  # fmt: skip
        _sub(origin, tag, text)


def _legend(parent: ET.Element) -> None:
    legend = _sub(
        parent, "rampLegendSettings",
        useContinuousLegend="1", suffix="", orientation="2", prefix="", maximumLabel="", direction="0", minimumLabel="",
    )  # fmt: skip
    _option_map(
        legend,
        "numericFormat",
        [
            ("decimal_separator", None, "invalid"), ("decimals", "6", "int"), ("rounding_type", "0", "int"),
            ("show_plus", "false", "bool"), ("show_thousand_separator", "true", "bool"),
            ("show_trailing_zeros", "false", "bool"), ("thousand_separator", None, "invalid"),
        ],
        id="basic",
    )  # fmt: skip


def _stretch(parent: ET.Element, tag: str, low: float, high: float) -> None:
    element = _sub(parent, tag)
    _sub(element, "minValue", _number(low))
    _sub(element, "maxValue", _number(high))
    _sub(element, "algorithm", "StretchToMinimumMaximum")


def _colormap_colours(name: str) -> list[tuple[int, ...]]:
    table = COLORMAPS.get(name)
    return [tuple(table[key]) for key in sorted(table)]


def _pseudocolor(pipe: ET.Element, spec: Pseudocolor) -> None:
    renderer = _sub(
        pipe, "rasterrenderer",
        classificationMin=_number(spec.low), nodataColor="", band=str(spec.band), alphaBand="-1", opacity="1",
        classificationMax=_number(spec.high), type="singlebandpseudocolor",
    )  # fmt: skip
    _min_max_origin(renderer)
    shader = _sub(
        _sub(renderer, "rastershader"), "colorrampshader",
        clip="0", minimumValue=_number(spec.low), maximumValue=_number(spec.high), classificationMode="1",
        labelPrecision="6", colorRampType="INTERPOLATED",
    )  # fmt: skip
    colours = _colormap_colours(spec.colormap)
    last = len(colours) - 1
    stops = ":".join(f"{i / last:.6g};{_rgba(colours[i])};rgb;ccw" for i in range(1, last))
    ramp = _sub(shader, "colorramp", name="[source]", type="gradient")
    options = _sub(ramp, "Option", type="Map")
    for name, value in (
        ("color1", _rgba(colours[0])), ("color2", _rgba(colours[last])), ("direction", "ccw"), ("discrete", "0"),
        ("rampType", "gradient"), ("spec", "rgb"), ("stops", stops),
    ):  # fmt: skip
        _sub(options, "Option", value=value, name=name, type="QString")
    for i, colour in enumerate(colours):
        value = spec.low + (spec.high - spec.low) * i / last
        _sub(shader, "item", value=_number(value), color=_hex(colour), alpha="255", label=f"{value:.6g}")
    _legend(shader)


def _gray(pipe: ET.Element, spec: Gray) -> None:
    renderer = _sub(
        pipe, "rasterrenderer",
        nodataColor="", alphaBand="-1", opacity="1", grayBand=str(spec.band), gradient="BlackToWhite",
        type="singlebandgray",
    )  # fmt: skip
    _min_max_origin(renderer)
    _stretch(renderer, "contrastEnhancement", spec.low, spec.high)
    _legend(renderer)


def _rgb(pipe: ET.Element, spec: Rgb) -> None:
    red, green, blue = spec.bands
    renderer = _sub(
        pipe, "rasterrenderer",
        nodataColor="", redBand=str(red), alphaBand="-1", opacity="1", blueBand=str(blue), type="multibandcolor",
        greenBand=str(green),
    )  # fmt: skip
    _min_max_origin(renderer)
    for tag, (low, high) in zip(
        ("redContrastEnhancement", "greenContrastEnhancement", "blueContrastEnhancement"), spec.ranges, strict=True
    ):
        _stretch(renderer, tag, low, high)


def _paletted(pipe: ET.Element, spec: Paletted) -> None:
    renderer = _sub(
        pipe, "rasterrenderer", nodataColor="", band=str(spec.band), alphaBand="-1", opacity="1", type="paletted"
    )
    _min_max_origin(renderer)
    palette = _sub(renderer, "colorPalette")
    for row in spec.classes:
        _sub(palette, "paletteEntry", value=str(row.value), color=row.colour, alpha="255", label=row.name)


_WRITERS: dict[type, Callable[[ET.Element, Any], None]] = {
    Pseudocolor: _pseudocolor, Gray: _gray, Rgb: _rgb, Paletted: _paletted,
}  # fmt: skip


def qml_text(renderer: Renderer) -> str:
    """The ``.qml`` that draws a file with ``renderer``, in the form QGIS 3.34 writes the category "Symbology"."""
    root = ET.Element("qgis", {"styleCategories": "Symbology", "version": QGIS_VERSION})
    _option_map(
        root,
        "pipe-data-defined-properties",
        [("name", "", "QString"), ("properties", None, None), ("type", "collection", "QString")],
    )
    pipe = _sub(root, "pipe")
    _sub(
        _sub(pipe, "provider"), "resampling",
        zoomedOutResamplingMethod="nearestNeighbour", maxOversampling="2", enabled="false",
        zoomedInResamplingMethod="nearestNeighbour",
    )  # fmt: skip
    _WRITERS[type(renderer)](pipe, renderer)
    _sub(pipe, "brightnesscontrast", contrast="0", gamma="1", brightness="0")
    _sub(
        pipe, "huesaturation",
        colorizeGreen="128", colorizeRed="255", saturation="0", colorizeStrength="100", grayscaleMode="0",
        colorizeOn="0", colorizeBlue="128", invertColors="0",
    )  # fmt: skip
    _sub(pipe, "rasterresampler", maxOversampling="2")
    _sub(pipe, "resamplingStage", "resamplingFilter")
    _sub(root, "blendMode", "0")
    ET.indent(root, space="  ")
    return _DOCTYPE + ET.tostring(root, encoding="unicode") + "\n"
