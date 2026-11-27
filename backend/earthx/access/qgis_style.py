"""The QGIS style beside every raster file of an export (M5-64, plan ``m5-64-qgis-stil.md``).

A file ``<name>.tif`` gets ``<name>.qml``; QGIS loads it when it opens the file (measured with QGIS 3.34). The style
draws the file as the app draws it:

* one band of measured values: ``singlebandpseudocolor`` with the ramp the tiles draw, as 256 stops, between the
  minimum and maximum of the look;
* three bands of one picture (true colour) or of an RGB look: ``multibandcolor`` with a stretch per channel;
* one band of classes: ``paletted`` with value, colour and name of each class (the list of the colour table, M5-62).

QGIS applies the ``scale``/``offset`` of a GeoTIFF when it reads it (measured), so every range is physical, as the
looks of the registry and of the app are. The files are text, written in one fixed form without a time, so that the
synchronous crop and the job write the same bytes. Nothing here reads a registry or a network: the caller hands in the
looks (``ExportStyles``), the worker core included.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from xml.sax.saxutils import quoteattr

import numpy

from earthx.access.colormap_tables import ramp_colours
from earthx.catalog.registry import ClassRow, DatasetConfig, Look

__all__ = [
    "MASK_STYLE",
    "QGIS_VERSION",
    "STYLE_SUFFIX",
    "ExportStyles",
    "RgbLook",
    "Stats",
    "collection_styles",
    "dataset_style",
    "file_style",
    "measure_band",
    "parse_order_look",
    "style_name",
]

#: The version the form of the files was taken from (QGIS writes it in every style; others read it).
QGIS_VERSION = "3.34.4-Prizren"

STYLE_SUFFIX = ".qml"

#: The ramp of a band without any look, as the registry's last rule (``DEFAULT_LOOK``).
DEFAULT_COLORMAP = "viridis"

#: The longest side read to measure a file: the measure of a range, not of the data (M5-60 §11).
MEASURE_SIDE = 1024

#: The bands a look may name: more than any file holds, few enough for a short order.
MAX_LOOK_BANDS = 64


def style_name(raster: str) -> str:
    """The name of the style of the raster file ``raster``: the same name with ``.qml`` (QGIS loads no other)."""
    stem = raster[:-4] if raster.lower().endswith(".tif") else raster
    return f"{stem}{STYLE_SUFFIX}"


# --- the looks an export is drawn with -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RgbLook:
    """Three bands on red, green and blue, each stretched between its own two physical values."""

    bands: tuple[str, str, str]
    ranges: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]


@dataclass(frozen=True, slots=True)
class ExportStyles:
    """What the styles of one export are drawn with: a look per band (asset key or band name) and at most one RGB.

    The caller merges what the user sees (the order's look, ``fixed`` with its numbers) over the looks of the
    collection or the operator. ``true_color`` names the bands a file of several bands is shown in true colour with
    when no look names one of them (plan F2).
    """

    looks: Mapping[str, Look] = field(default_factory=dict)
    rgb: RgbLook | None = None
    true_color: tuple[str, str, str] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "looks": {key: look.annotation() for key, look in sorted(self.looks.items())},
            "rgb": None if self.rgb is None else {"bands": list(self.rgb.bands), "ranges": [list(r) for r in self.rgb.ranges]},
            "true_color": None if self.true_color is None else list(self.true_color),
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> ExportStyles:
        """The styles from :meth:`to_json`; anything of the wrong form is a :class:`ValueError`."""
        if not isinstance(data, Mapping):
            raise ValueError("the styles are an object")
        looks = data.get("looks", {})
        if not isinstance(looks, Mapping):
            raise ValueError("looks is an object")
        parsed = {str(key): _look_of_json(value) for key, value in looks.items()}
        rgb = data.get("rgb")
        true_color = data.get("true_color")
        return cls(
            looks=parsed,
            rgb=None if rgb is None else _rgb_of_json(rgb),
            true_color=None if true_color is None else _three_names(true_color, "true_color"),
        )


def _look_of_json(value: Any) -> Look:
    if not isinstance(value, Mapping):
        raise ValueError("a look is an object")
    try:
        return Look(
            colormap=str(value["colormap"]),
            scale=value.get("scale", "fixed"),
            low=_number_or_none(value.get("low")),
            high=_number_or_none(value.get("high")),
        )
    except (KeyError, TypeError) as error:
        raise ValueError(f"a look is not complete: {error}") from None


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("a bound of a look is a finite number")
    return float(value)


def _three_names(value: Any, what: str) -> tuple[str, str, str]:
    if not (isinstance(value, (list, tuple)) and len(value) == 3 and all(isinstance(v, str) and v for v in value)):
        raise ValueError(f"{what} names three bands")
    return (value[0], value[1], value[2])


def _range(value: Any) -> tuple[float, float]:
    if not (isinstance(value, (list, tuple)) and len(value) == 2):
        raise ValueError("a range is two numbers")
    low, high = _number_or_none(value[0]), _number_or_none(value[1])
    if low is None or high is None or not low < high:
        raise ValueError("a range has a low end below its high end")
    return (low, high)


def _rgb_of_json(value: Any) -> RgbLook:
    if not isinstance(value, Mapping):
        raise ValueError("rgb is an object")
    bands = _three_names(value.get("bands"), "rgb")
    ranges = value.get("ranges")
    if not (isinstance(ranges, (list, tuple)) and len(ranges) == 3):
        raise ValueError("rgb has three ranges")
    return RgbLook(bands, (_range(ranges[0]), _range(ranges[1]), _range(ranges[2])))


def parse_order_look(value: Any) -> tuple[dict[str, Look], RgbLook | None]:
    """The look of an order, as the app sends what it draws (M5-64 plan §4.4), or a :class:`ValueError`.

    ``{"bands": {key: {"colormap", "low", "high"}}, "rgb": {"bands": [r, g, b], "ranges": [[lo, hi] × 3]}}``, every
    number physical, every colormap one the tiles know. Only ``fixed`` ranges come from the app: it always has numbers.
    """
    if not isinstance(value, Mapping) or set(value) - {"bands", "rgb"}:
        raise ValueError("a look holds bands and rgb, nothing else")
    bands = value.get("bands", {})
    if not isinstance(bands, Mapping) or len(bands) > MAX_LOOK_BANDS:
        raise ValueError(f"the bands of a look are an object of at most {MAX_LOOK_BANDS}")
    looks: dict[str, Look] = {}
    for key, band in bands.items():
        if not isinstance(key, str) or not key or not isinstance(band, Mapping) or set(band) - {"colormap", "low", "high"}:
            raise ValueError("a band of a look has a colormap, a low and a high end")
        colormap = band.get("colormap")
        if not isinstance(colormap, str) or ramp_colours(colormap) is None:
            raise ValueError("the colormap of a look is one the tiles know")
        low, high = _range([band.get("low"), band.get("high")])
        looks[key] = Look(colormap=colormap, scale="fixed", low=low, high=high)
    rgb = value.get("rgb")
    if rgb is not None and isinstance(rgb, Mapping) and set(rgb) - {"bands", "ranges"}:
        raise ValueError("rgb holds bands and ranges, nothing else")
    return looks, None if rgb is None else _rgb_of_json(rgb)


#: The colormap of a picture the tiles draw without one: the plain grey ramp of the tiler (black to white).
GREY = "gray"


def collection_styles(config: DatasetConfig, keys: Sequence[str], look: Any = None) -> ExportStyles:
    """The styles of an export of ``config``: the order's ``look`` (what the user sees, :func:`parse_order_look`) over
    the look of each band in the collection (``look_of``), and the stretch of the standard picture for its asset.

    A :class:`ValueError` for a look the order cannot carry. A key of the look that names no band of the export is kept:
    a file without that band never meets it (plan A2).
    """
    looks: dict[str, Look] = {}
    for key in keys:
        resolved = config.look_of(key)
        if resolved is not None:
            looks[key] = resolved.look
    render = config.default_render
    if (
        render is not None
        and render.expression is None
        and render.rescale
        and len(render.assets) == 1
        and render.assets[0] in keys
        and render.assets[0] not in config.band_classes
    ):
        asset = render.assets[0]
        scaling = config.scaling_of(asset)
        low, high = (scaling.physical(value) for value in render.rescale[0])
        looks.setdefault(asset, Look(render.colormap_name or GREY, "fixed", *_spread(low, high)))
    rgb = None
    if look is not None:
        ordered, rgb = parse_order_look(look)
        looks.update(ordered)
    true_color = tuple(config.true_color) if len(config.true_color) == 3 else None
    return ExportStyles(looks, rgb, true_color)  # type: ignore[arg-type]


# --- measuring a file -------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Stats:
    """What a look without numbers takes from the data: the 2nd and 98th percentile, the minimum and the maximum."""

    p2: float
    p98: float
    minimum: float
    maximum: float


def measure_band(dataset: Any, band: int) -> Stats | None:
    """The physical statistics of band ``band`` (1-based) of an open file, from one read of at most 1024 px a side.

    The valid pixels only (the file's own mask), scaled with the band's ``scale``/``offset`` as QGIS reads them.
    ``None`` where the band has no valid pixel.
    """
    width, height = dataset.width, dataset.height
    factor = max(1, math.ceil(max(width, height) / MEASURE_SIDE))
    shape = (max(1, height // factor), max(1, width // factor))
    data = dataset.read(band, out_shape=shape, masked=True)
    values = numpy.ma.compressed(data).astype("float64")
    values = values[numpy.isfinite(values)]
    if values.size == 0:
        return None
    scale = (dataset.scales or [1.0] * dataset.count)[band - 1] or 1.0
    offset = (dataset.offsets or [0.0] * dataset.count)[band - 1] or 0.0
    values = values * scale + offset
    p2, p98 = numpy.percentile(values, [2, 98])
    return Stats(float(p2), float(p98), float(values.min()), float(values.max()))


def range_of(look: Look, measure: Callable[[], Stats | None]) -> tuple[float, float]:
    """The two ends a look draws between: its numbers where it has them, else the measure (as ``displayLook.lookRange``)."""
    if look.scale == "fixed" and look.low is not None and look.high is not None:
        return _spread(look.low, look.high)
    stats = measure()
    if stats is None:
        return (0.0, 1.0)
    if look.scale == "percentiles" and (look.low, look.high) == (0, 100):
        return _spread(stats.minimum, stats.maximum)
    return _spread(stats.p2, stats.p98)


def _spread(low: float, high: float) -> tuple[float, float]:
    """A range with two different ends: a constant band (one pixel, a flat area) is drawn in its middle colour."""
    if high > low:
        return (low, high)
    pad = max(abs(low) * 1e-6, 1e-9)
    return (low - pad, high + pad)


# --- the three kinds of style --------------------------------------------------------------------------------------


def _number(value: float) -> str:
    """A number as QGIS reads it back: the shortest text that is the same double, never in an exponent of ``e+``."""
    text = repr(float(value))
    return "0" if text in ("0.0", "-0.0") else text.removesuffix(".0")


def _hex(colour: Sequence[int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*colour[:3])


_HEAD = (
    "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"
    f'<qgis styleCategories="Symbology" version="{QGIS_VERSION}">\n'
    "  <pipe-data-defined-properties>\n"
    '    <Option type="Map">\n'
    '      <Option type="QString" name="name" value=""/>\n'
    '      <Option name="properties"/>\n'
    '      <Option type="QString" name="type" value="collection"/>\n'
    "    </Option>\n"
    "  </pipe-data-defined-properties>\n"
    "  <pipe>\n"
    "    <provider>\n"
    '      <resampling enabled="false" maxOversampling="2" zoomedInResamplingMethod="nearestNeighbour" '
    'zoomedOutResamplingMethod="nearestNeighbour"/>\n'
    "    </provider>\n"
)

_MIN_MAX_ORIGIN = (
    "      <minMaxOrigin>\n"
    "        <limits>None</limits>\n"
    "        <extent>WholeRaster</extent>\n"
    "        <statAccuracy>Estimated</statAccuracy>\n"
    "        <cumulativeCutLower>0.02</cumulativeCutLower>\n"
    "        <cumulativeCutUpper>0.98</cumulativeCutUpper>\n"
    "        <stdDevFactor>2</stdDevFactor>\n"
    "      </minMaxOrigin>\n"
)

_TAIL = (
    '    <brightnesscontrast brightness="0" contrast="0" gamma="1"/>\n'
    '    <huesaturation colorizeBlue="128" colorizeGreen="128" colorizeOn="0" colorizeRed="255" colorizeStrength="100" '
    'grayscaleMode="0" invertColors="0" saturation="0"/>\n'
    '    <rasterresampler maxOversampling="2"/>\n'
    "    <resamplingStage>resamplingFilter</resamplingStage>\n"
    "  </pipe>\n"
    "  <blendMode>0</blendMode>\n"
    "</qgis>\n"
)


def pseudocolor_style(band: int, colours: Sequence[Sequence[int]], low: float, high: float) -> str:
    """One band through a colour ramp: every colour of the table a stop, evenly from ``low`` to ``high``.

    ``clip="0"``: values outside the range take the end colours, as the tiles draw them.
    """
    count = len(colours)
    values = [low + (high - low) * i / (count - 1) for i in range(count)]
    rgba = [f"{c[0]},{c[1]},{c[2]},255" for c in colours]
    stops = ":".join(f"{i / (count - 1):.6g};{rgba[i]};rgb;ccw" for i in range(1, count - 1))
    items = "".join(
        f'          <item alpha="255" color="{_hex(colours[i])}" label="{value:.6g}" value="{_number(value)}"/>\n'
        for i, value in enumerate(values)
    )
    return (
        _HEAD
        + f'    <rasterrenderer alphaBand="-1" band="{band}" classificationMax="{_number(high)}" '
        f'classificationMin="{_number(low)}" nodataColor="" opacity="1" type="singlebandpseudocolor">\n'
        + _MIN_MAX_ORIGIN
        + "      <rastershader>\n"
        f'        <colorrampshader classificationMode="1" clip="0" colorRampType="INTERPOLATED" labelPrecision="6" '
        f'maximumValue="{_number(high)}" minimumValue="{_number(low)}">\n'
        '          <colorramp name="[source]" type="gradient">\n'
        '            <Option type="Map">\n'
        f'              <Option type="QString" name="color1" value="{rgba[0]}"/>\n'
        f'              <Option type="QString" name="color2" value="{rgba[-1]}"/>\n'
        '              <Option type="QString" name="direction" value="ccw"/>\n'
        '              <Option type="QString" name="discrete" value="0"/>\n'
        '              <Option type="QString" name="rampType" value="gradient"/>\n'
        '              <Option type="QString" name="spec" value="rgb"/>\n'
        f'              <Option type="QString" name="stops" value="{stops}"/>\n'
        "            </Option>\n"
        "          </colorramp>\n"
        + items
        + '          <rampLegendSettings direction="0" maximumLabel="" minimumLabel="" orientation="2" prefix="" '
        'suffix="" useContinuousLegend="1">\n'
        '            <numericFormat id="basic">\n'
        '              <Option type="Map">\n'
        '                <Option type="invalid" name="decimal_separator"/>\n'
        '                <Option type="int" name="decimals" value="6"/>\n'
        '                <Option type="int" name="rounding_type" value="0"/>\n'
        '                <Option type="bool" name="show_plus" value="false"/>\n'
        '                <Option type="bool" name="show_thousand_separator" value="true"/>\n'
        '                <Option type="bool" name="show_trailing_zeros" value="false"/>\n'
        '                <Option type="invalid" name="thousand_separator"/>\n'
        '              </Option>\n'
        '            </numericFormat>\n'
        '          </rampLegendSettings>\n'
        "        </colorrampshader>\n"
        "      </rastershader>\n"
        "    </rasterrenderer>\n"
        + _TAIL
    )


def rgb_style(bands: tuple[int, int, int], ranges: Sequence[tuple[float, float]]) -> str:
    """Three bands on red, green and blue, each stretched linearly between its two values."""
    enhancements = "".join(
        f"      <{colour}ContrastEnhancement>\n"
        f"        <minValue>{_number(low)}</minValue>\n"
        f"        <maxValue>{_number(high)}</maxValue>\n"
        "        <algorithm>StretchToMinimumMaximum</algorithm>\n"
        f"      </{colour}ContrastEnhancement>\n"
        for colour, (low, high) in zip(("red", "green", "blue"), ranges, strict=True)
    )
    return (
        _HEAD
        + f'    <rasterrenderer alphaBand="-1" blueBand="{bands[2]}" greenBand="{bands[1]}" nodataColor="" opacity="1" '
        f'redBand="{bands[0]}" type="multibandcolor">\n'
        + _MIN_MAX_ORIGIN
        + enhancements
        + "    </rasterrenderer>\n"
        + _TAIL
    )


def paletted_style(band: int, entries: Sequence[tuple[float, str, str, int]]) -> str:
    """One band of classes: each ``(value, #rrggbb, name, alpha)`` an entry of the palette; a value without one is not drawn."""
    palette = "".join(
        f'        <paletteEntry alpha="{alpha}" color="{colour.lower()}" label={quoteattr(name)} value="{_number(value)}"/>\n'
        for value, colour, name, alpha in entries
    )
    return (
        _HEAD
        + f'    <rasterrenderer alphaBand="-1" band="{band}" nodataColor="" opacity="1" type="paletted">\n'
        + _MIN_MAX_ORIGIN
        + "      <colorPalette>\n"
        + palette
        + "      </colorPalette>\n"
        "    </rasterrenderer>\n"
        + _TAIL
    )


#: The style of every mask file (plan F7): inside the AOI white, outside not drawn.
MASK_STYLE = paletted_style(1, [(0, "#000000", "Outside AOI", 0), (1, "#ffffff", "Inside AOI", 255)])


def class_style(band: int, classes: Sequence[ClassRow]) -> str:
    """The palette of a band of classes, from the same list as the colour table of the file (M5-62)."""
    return paletted_style(band, [(row.value, row.colour, row.name, 255) for row in classes])


# --- the style of one file -----------------------------------------------------------------------------------------


def file_style(
    count: int,
    keys: Sequence[str],
    classes: Sequence[Sequence[ClassRow] | None],
    styles: ExportStyles,
    measure: Callable[[int], Stats | None],
) -> str:
    """The style of a raster file of ``count`` bands whose band ``i`` (0-based) is the band or asset ``keys[i]``.

    ``classes[i]`` are the classes of band ``i`` where its values are classes; ``measure(i)`` gives the statistics of
    band ``i`` for a look without numbers (called only then). In this order (plan §4.2, F2): three bands of one asset
    (true colour) on R/G/B; the three bands of the RGB look where all are in the file; a band of classes alone; the
    band the look names, else true colour where its three bands are in the file, else band 1.
    """
    if len(keys) != count or len(classes) != count:
        raise ValueError("a file style names every band of the file once")

    def measured(index: int) -> Callable[[], Stats | None]:
        return lambda: measure(index)

    def looked(index: int) -> Look:
        return styles.looks.get(keys[index]) or Look(DEFAULT_COLORMAP)

    if count == 3 and len(set(keys)) == 1:
        return rgb_style((1, 2, 3), [range_of(looked(0), measured(i)) for i in range(3)])
    if styles.rgb is not None and all(name in keys for name in styles.rgb.bands):
        places = tuple(keys.index(name) + 1 for name in styles.rgb.bands)
        return rgb_style(places, styles.rgb.ranges)  # type: ignore[arg-type]
    if count == 1 and classes[0]:
        return class_style(1, classes[0])
    named = next((i for i, key in enumerate(keys) if key in styles.looks and not classes[i]), None)
    if named is None and styles.true_color is not None and all(name in keys for name in styles.true_color):
        places = [keys.index(name) for name in styles.true_color]
        ranges = [range_of(Look(DEFAULT_COLORMAP), measured(place)) for place in places]
        return rgb_style((places[0] + 1, places[1] + 1, places[2] + 1), ranges)
    index = 0 if named is None else named
    if classes[index]:
        return class_style(index + 1, classes[index])
    look = looked(index)
    colours = ramp_colours(look.colormap) or ramp_colours(DEFAULT_COLORMAP)
    assert colours is not None
    low, high = range_of(look, measured(index))
    return pseudocolor_style(index + 1, colours, low, high)


def dataset_style(
    dataset: Any, keys: Sequence[str], classes: Sequence[Sequence[ClassRow] | None], styles: ExportStyles
) -> str:
    """The style of an open raster file, measured on the file itself where a look has no numbers (plan F5)."""
    return file_style(dataset.count, keys, classes, styles, lambda index: measure_band(dataset, index + 1))
