"""The OGC SLD 1.0 beside an exported raster file, where a person chooses "SLD" as the style file (M5-64 plan §12).

The same renderer as the QGIS style (:mod:`earthx.access.qgis_style`), written as a ``RasterSymbolizer`` that is valid
against the schema of SLD 1.0.0 (plan §12.2, F8):

- a colormap: the band as ``GrayChannel`` and the tiler's 256 colours as a ``ColorMap`` from min to max (a ramp, what
  readers make of a ``ColorMap`` without more);
- grey: a ``ColorMap`` from black at min to white at max, which is the stretch exactly;
- classes: one ``ColorMapEntry`` per class with its name as ``label``, the value of no data see-through;
- a colour picture: the three bands as ``Red``/``Green``/``BlueChannel``, each with ``Normalize``. SLD 1.0 has no
  numbers for the stretch of a channel, so a reader stretches each to the values of the file; the ranges of the app
  stand beside them as a comment.

QGIS 3.34 does not load an SLD for a raster layer (measured, plan §12.1): this file is for servers and other tools.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from typing import TYPE_CHECKING

from earthx.access.colormap_tables import ramp_colours

if TYPE_CHECKING:
    from earthx.access.qgis_style import Gray, Paletted, Pseudocolor, Renderer, Rgb

__all__ = ["SLD_NAMESPACE", "sld_text"]

SLD_NAMESPACE = "http://www.opengis.net/sld"
_XSI = "http://www.w3.org/2001/XMLSchema-instance"
_SCHEMA = "http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd"


def _number(value: float) -> str:
    return repr(float(value))


def _hex(colour: Sequence[int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*colour[:3])


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attributes: str) -> ET.Element:
    element = ET.SubElement(parent, tag, attributes)
    if text is not None:
        element.text = text
    return element


def _gray_channel(symbolizer: ET.Element, band: int) -> None:
    _sub(_sub(_sub(symbolizer, "ChannelSelection"), "GrayChannel"), "SourceChannelName", str(band))


def _entry(colour_map: ET.Element, colour: str, quantity: float, *, opacity: float | None = None, label: str | None = None) -> None:
    attributes = {"color": colour, "quantity": _number(quantity)}
    if opacity is not None:
        attributes["opacity"] = _number(opacity)
    if label is not None:
        attributes["label"] = label
    _sub(colour_map, "ColorMapEntry", **attributes)


def _pseudocolor(symbolizer: ET.Element, spec: Pseudocolor) -> None:
    _gray_channel(symbolizer, spec.band)
    colours = ramp_colours(spec.colormap)
    assert colours is not None
    last = len(colours) - 1
    colour_map = _sub(symbolizer, "ColorMap")
    for i, colour in enumerate(colours):
        value = spec.low + (spec.high - spec.low) * i / last
        _entry(colour_map, _hex(colour), value, label=f"{value:.6g}" if i in (0, last) else None)


def _gray(symbolizer: ET.Element, spec: Gray) -> None:
    _gray_channel(symbolizer, spec.band)
    colour_map = _sub(symbolizer, "ColorMap")
    _entry(colour_map, "#000000", spec.low, label=f"{spec.low:.6g}")
    _entry(colour_map, "#ffffff", spec.high, label=f"{spec.high:.6g}")


def _paletted(symbolizer: ET.Element, spec: Paletted) -> None:
    _gray_channel(symbolizer, spec.band)
    colour_map = _sub(symbolizer, "ColorMap")
    entries = [(float(row.value), row.colour, 1.0, row.name) for row in spec.classes]
    if spec.nodata is not None and math.isfinite(spec.nodata) and spec.nodata not in {value for value, *_ in entries}:
        entries.append((spec.nodata, "#000000", 0.0, None))
    for value, colour, opacity, label in sorted(entries, key=lambda entry: entry[0]):
        _entry(colour_map, colour, value, opacity=opacity, label=label)


def _rgb(symbolizer: ET.Element, spec: Rgb) -> None:
    selection = _sub(symbolizer, "ChannelSelection")
    for tag, band, (low, high) in zip(("RedChannel", "GreenChannel", "BlueChannel"), spec.bands, spec.ranges, strict=True):
        channel = _sub(selection, tag)
        _sub(channel, "SourceChannelName", str(band))
        _sub(_sub(channel, "ContrastEnhancement"), "Normalize")
        channel.insert(0, ET.Comment(f" range in the app: {low:.6g} to {high:.6g}; SLD 1.0 stretches to the file "))


def sld_text(renderer: Renderer, name: str) -> str:
    """The SLD 1.0 of a file named ``name`` drawn with ``renderer``."""
    from earthx.access.qgis_style import Gray, Paletted, Pseudocolor, Rgb

    ET.register_namespace("", SLD_NAMESPACE)
    ET.register_namespace("xsi", _XSI)
    root = ET.Element(
        f"{{{SLD_NAMESPACE}}}StyledLayerDescriptor",
        {"version": "1.0.0", f"{{{_XSI}}}schemaLocation": f"{SLD_NAMESPACE} {_SCHEMA}"},
    )
    layer = _sub(root, f"{{{SLD_NAMESPACE}}}NamedLayer")
    _sub(layer, f"{{{SLD_NAMESPACE}}}Name", name)
    style = _sub(layer, f"{{{SLD_NAMESPACE}}}UserStyle")
    _sub(style, f"{{{SLD_NAMESPACE}}}Title", name)
    rule = _sub(_sub(style, f"{{{SLD_NAMESPACE}}}FeatureTypeStyle"), f"{{{SLD_NAMESPACE}}}Rule")
    symbolizer = _sub(rule, f"{{{SLD_NAMESPACE}}}RasterSymbolizer")
    if isinstance(renderer, Pseudocolor):
        _pseudocolor(symbolizer, renderer)
    elif isinstance(renderer, Gray):
        _gray(symbolizer, renderer)
    elif isinstance(renderer, Paletted):
        _paletted(symbolizer, renderer)
    elif isinstance(renderer, Rgb):
        _rgb(symbolizer, renderer)
    for element in symbolizer.iter():
        if isinstance(element.tag, str) and not element.tag.startswith("{"):
            element.tag = f"{{{SLD_NAMESPACE}}}{element.tag}"
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
