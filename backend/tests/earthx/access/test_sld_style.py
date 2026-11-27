"""The SLD beside an exported raster file, where "SLD" is chosen as the style file (M5-64 plan §12).

Every SLD is checked against the OGC schema SLD 1.0.0 (with Filter 1.0.0 and GML 2.1.2), which lie unchanged in
``tests/fixtures/ogc-schemas``; XLink and XML come with ``xmlschema``. Nothing is fetched.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from functools import cache
from pathlib import Path

import pytest
import xmlschema

from earthx.access.colormap_tables import ramp_colours
from earthx.access.qgis_style import (
    NO_STYLE,
    STYLE_FORMATS,
    Gray,
    Paletted,
    Pseudocolor,
    Renderer,
    Rgb,
    StyleInvalid,
    check_style_format,
    style_file,
)
from earthx.access.sld_style import SLD_NAMESPACE, sld_text
from earthx.catalog.registry import ClassRow

SCHEMAS = Path(__file__).resolve().parents[2] / "fixtures" / "ogc-schemas"
OGC = "http://schemas.opengis.net/"
#: The schemas of the W3C the OGC ones import, as ``xmlschema`` brings them.
W3C = {"http://www.w3.org/1999/xlink.xsd": ("XLINK", "xlink.xsd"), "http://www.w3.org/2001/xml.xsd": ("XML", "xml.xsd")}
NS = {"sld": SLD_NAMESPACE}

CLASSES = (ClassRow(10, "Tree cover", "#006400"), ClassRow(20, "Shrubland & <dry>", "#ffbb22"), ClassRow(95, "Mangroves", "#00cf75"))
CASES: dict[str, Renderer] = {
    "colormap": Pseudocolor(2, "viridis", 0.02, 0.24),
    "reversed": Pseudocolor(1, "rdbu_r", -20.0, 30.0),
    "grey": Gray(1, 0.0, 0.3),
    "rgb": Rgb((3, 2, 1), ((0.0, 0.5), (0.0, 0.3), (0.0, 0.2))),
    "classes": Paletted(1, CLASSES, 0.0),
    "classes without nodata": Paletted(1, CLASSES, None),
}


@cache
def schema() -> xmlschema.XMLSchema10:
    bundled = Path(xmlschema.__file__).parent / "schemas"

    def local(uri: str) -> str:
        if uri.startswith(OGC):
            return (SCHEMAS / uri.removeprefix(OGC)).as_uri()
        return bundled.joinpath(*W3C[uri]).as_uri() if uri in W3C else uri

    return xmlschema.XMLSchema10(str(SCHEMAS / "sld" / "1.0.0" / "StyledLayerDescriptor.xsd"), uri_mapper=local)


def _symbolizer(text: str) -> ET.Element:
    found = ET.fromstring(text.encode("utf-8")).find(".//sld:RasterSymbolizer", NS)
    assert found is not None
    return found


@pytest.mark.parametrize("case", sorted(CASES))
def test_every_sld_is_valid_against_the_ogc_schema_sld_1_0(case: str) -> None:
    schema().validate(sld_text(CASES[case], "B04_red_10m"), use_location_hints=False)


def test_the_schema_check_catches_what_sld_1_0_does_not_know() -> None:
    """Gegenprobe: the ``type`` of a ColorMap is GeoServer's, not SLD 1.0's (plan §12.1 point 5)."""
    text = sld_text(CASES["classes"], "x").replace("<ColorMap>", '<ColorMap type="values">')
    assert not schema().is_valid(text, use_location_hints=False)


def test_a_colormap_is_the_table_of_the_tiler_from_min_to_max_on_its_band() -> None:
    symbolizer = _symbolizer(sld_text(CASES["colormap"], "x"))
    assert symbolizer.find("sld:ChannelSelection/sld:GrayChannel/sld:SourceChannelName", NS).text == "2"  # type: ignore[union-attr]
    entries = symbolizer.findall("sld:ColorMap/sld:ColorMapEntry", NS)
    expected = ["#{:02x}{:02x}{:02x}".format(*colour[:3]) for colour in ramp_colours("viridis") or []]
    assert [entry.attrib["color"] for entry in entries] == expected
    assert float(entries[0].attrib["quantity"]) == 0.02 and float(entries[-1].attrib["quantity"]) == 0.24
    assert [entry.attrib.get("label") for entry in (entries[0], entries[-1])] == ["0.02", "0.24"]


def test_grey_is_black_at_min_and_white_at_max() -> None:
    entries = _symbolizer(sld_text(CASES["grey"], "x")).findall("sld:ColorMap/sld:ColorMapEntry", NS)
    assert [(e.attrib["color"], float(e.attrib["quantity"])) for e in entries] == [("#000000", 0.0), ("#ffffff", 0.3)]


def test_classes_carry_their_names_and_no_data_is_see_through() -> None:
    entries = _symbolizer(sld_text(CASES["classes"], "x")).findall("sld:ColorMap/sld:ColorMapEntry", NS)
    assert [(e.attrib["quantity"], e.attrib["color"], e.attrib.get("opacity"), e.attrib.get("label")) for e in entries] == [
        ("0.0", "#000000", "0.0", None),
        ("10.0", "#006400", "1.0", "Tree cover"),
        ("20.0", "#ffbb22", "1.0", "Shrubland & <dry>"),
        ("95.0", "#00cf75", "1.0", "Mangroves"),
    ]
    entries = _symbolizer(sld_text(CASES["classes without nodata"], "x")).findall("sld:ColorMap/sld:ColorMapEntry", NS)
    assert len(entries) == 3


def test_a_colour_picture_names_its_bands_and_the_ranges_of_the_app_in_a_comment() -> None:
    text = sld_text(CASES["rgb"], "x")
    selection = _symbolizer(text).find("sld:ChannelSelection", NS)
    assert selection is not None
    channels = [selection.find(f"sld:{tag}", NS) for tag in ("RedChannel", "GreenChannel", "BlueChannel")]
    assert [c.find("sld:SourceChannelName", NS).text for c in channels] == ["3", "2", "1"]  # type: ignore[union-attr]
    assert all(c.find("sld:ContrastEnhancement/sld:Normalize", NS) is not None for c in channels)  # type: ignore[union-attr]
    assert "range in the app: 0 to 0.5" in text and "range in the app: 0 to 0.2" in text


def test_the_layer_is_named_after_its_file() -> None:
    styled = style_file("sld", "exports/group-01/bands_10m.tif", CASES["grey"])
    assert styled is not None and styled[0] == "exports/group-01/bands_10m.sld"
    assert ET.fromstring(styled[1].encode()).find("sld:NamedLayer/sld:Name", NS).text == "bands_10m"  # type: ignore[union-attr]


def test_none_writes_no_style_file() -> None:
    assert style_file(NO_STYLE, "exports/x.tif", CASES["grey"]) is None


@pytest.mark.parametrize("value", STYLE_FORMATS)
def test_the_forms_of_the_style_file_are_taken(value: str) -> None:
    assert check_style_format(value) == value


@pytest.mark.parametrize("value", ["QML", "qgis", "", None, 1, ["sld"], "sld "])
def test_any_other_form_is_refused(value: object) -> None:
    with pytest.raises(StyleInvalid):
        check_style_format(value)
