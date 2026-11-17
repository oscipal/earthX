"""The tables of data kinds by format and media type, and the shared helpers of every extractor (M5-19 plan §5.2, A7).

Formats come as free text of a catalogue and as URIs of the EU file types (adr/0025 §3); each spelling is a case here.
"""

from __future__ import annotations

import json

import pytest

from earthx.discovery.extract import (
    MAX_GEOMETRY_BYTES,
    data_kind_of,
    geometry_of,
    kind_of,
    localized,
    resource_kind,
)

EU = "http://publications.europa.eu/resource/authority/file-type/"


@pytest.mark.parametrize(
    ("format_", "media_type", "kind"),
    [
        ("GeoTIFF", None, "raster"),
        ("TIFF", None, "raster"),
        ("tif", None, "raster"),
        (f"{EU}GEOTIFF", None, "raster"),
        ("https://publications.europa.eu/resource/authority/file-type/TIFF/", None, "raster"),
        ("JPEG2000", None, "raster"),
        ("NetCDF", None, "raster"),
        (f"{EU}NETCDF", None, "raster"),
        ("HDF5", None, "raster"),
        ("ASCII Grid", None, "raster"),
        (f"{EU}GRID_ASCII", None, "raster"),
        ("ESRI Shapefile", None, "vector"),
        ("SHP", None, "vector"),
        (f"{EU}SHP", None, "vector"),
        ("GeoJSON", None, "vector"),
        ("GML", None, "vector"),
        ("GeoPackage", None, "vector"),
        ("KMZ", None, "vector"),
        ("FlatGeobuf", None, "vector"),
        ("GeoParquet", None, "vector"),
        ("csv", None, "table"),
        (f"{EU}XLSX", None, "table"),
        ("ODS", None, "table"),
        ("WMS", None, "service"),
        ("OGC:WMS", None, "service"),
        (f"{EU}WMS_SRVC", None, "service"),
        ("WFS_SRVC", None, "service"),
        ("WMTS", None, "service"),
        ("OGC API - Features", None, "service"),
        ("ATOM", None, "service"),
        ("PDF", None, "document"),
        ("docx", None, "document"),
        ("HTML", None, "page"),
        (f"{EU}HTML", None, "page"),
        ("ZIP", None, "file"),
        ("JSON", None, "file"),
        (None, "image/tiff; application=geotiff; profile=cloud-optimized", "raster"),
        (None, "application/geo+json", "vector"),
        (None, "text/csv", "table"),
        (None, "text/html; charset=utf-8", "page"),
        (None, "application/pdf", "document"),
        ("image/tiff", None, "raster"),
        ("", "text/html", "page"),
        ("Unknown format", None, None),
        ("Unknown format", "application/x-netcdf", "raster"),
        (None, None, None),
        ("", "", None),
    ],
)
def test_the_kind_of_a_resource_by_each_spelling(format_: str | None, media_type: str | None, kind: str | None) -> None:
    assert resource_kind(format_, media_type) == kind


def test_the_format_wins_over_the_media_type() -> None:
    assert resource_kind("SHP", "application/zip") == "vector"


@pytest.mark.parametrize(
    ("kinds", "expected"),
    [
        (["document", "raster", "service"], "raster"),
        (["table", "vector"], "vector"),
        (["document", "service"], "service"),
        (["page", "document"], "document"),
        (["page", "file", None], "other"),
        ([], "other"),
    ],
)
def test_data_before_service_before_document(kinds: list[str | None], expected: str) -> None:
    assert kind_of(kinds, default="other") == expected


def test_a_page_or_file_media_type_is_no_data_kind_of_a_stac_collection() -> None:
    assert data_kind_of(["text/html", "application/zip"], default="raster") == "raster"
    assert data_kind_of(["application/geo+json"], default="raster") == "vector"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Titel", "Titel"),
        ({"de": "Titel", "en": "Title", "fr": "Titre"}, "Titel"),
        ({"de": " ", "en": "Title", "fr": "Titre"}, "Title"),
        ({"fr": "Titre", "it": "Titolo"}, "Titre"),
        ({"rm": "Titel rumantsch"}, "Titel rumantsch"),
        ('{"de": "Bundesamt", "fr": "Office fédéral"}', "Bundesamt"),
        ("{not json", "{not json"),
        ({"de": None, "en": ""}, None),
        ({"title": "no language"}, None),
        ({}, None),
        (["Titel"], None),
        (42, None),
        (None, None),
    ],
)
def test_a_text_given_per_language_is_read_german_first(value: object, expected: str | None) -> None:
    assert localized(value) == expected


POLYGON = {"type": "Polygon", "coordinates": [[[6.0, 47.0], [9.0, 47.0], [9.0, 48.5], [6.0, 48.5], [6.0, 47.0]]]}


@pytest.mark.parametrize(
    "value",
    [
        POLYGON,
        json.dumps(POLYGON),
        {"type": "Feature", "properties": {"name": "x"}, "geometry": POLYGON},
        {"type": "GeometryCollection", "geometries": [POLYGON, {"type": "Point", "coordinates": [7.0, 47.5]}]},
    ],
)
def test_the_box_of_a_geometry(value: object) -> None:
    found = geometry_of(value)
    assert found is not None and found[0] == (6.0, 47.0, 9.0, 48.5)


def test_only_type_and_checked_coordinates_are_kept() -> None:
    noisy = {**POLYGON, "crs": {"type": "name"}, "bbox": [float("nan")] * 4}
    found = geometry_of(noisy)
    assert found is not None and found[1] == POLYGON


def test_a_third_coordinate_is_dropped() -> None:
    found = geometry_of({"type": "Point", "coordinates": [7.0, 47.0, 500.0]})
    assert found == ((7.0, 47.0, 7.0, 47.0), {"type": "Point", "coordinates": [7.0, 47.0]})


def test_a_large_geometry_keeps_only_its_box() -> None:
    ring = [[6.0 + i * 1e-5, 47.0 + (i % 2) * 1e-5] for i in range(MAX_GEOMETRY_BYTES // 10)]
    found = geometry_of({"type": "LineString", "coordinates": ring})
    assert found is not None and found[1] is None and found[0][0] == 6.0


@pytest.mark.parametrize(
    "value",
    [
        "Schweiz",
        "{broken",
        "[" * 5000,
        {"type": "Polygon"},
        {"type": "Polygon", "coordinates": []},
        {"type": "Point", "coordinates": [200.0, 47.0]},
        {"type": "Point", "coordinates": [7.0, 95.0]},
        {"type": "Point", "coordinates": [float("nan"), 47.0]},
        {"type": "Point", "coordinates": [True, 47.0]},
        {"type": "Point", "coordinates": ["7", "47"]},
        {"type": "Point", "coordinates": [7.0]},
        {"type": "Polygon", "coordinates": [[[[[[6.0, 47.0]]]]]]},
        {"type": "Circle", "coordinates": [7.0, 47.0]},
        {"type": "GeometryCollection", "geometries": [{"type": "GeometryCollection", "geometries": [POLYGON]}]},
        {"type": "FeatureCollection", "features": []},
        [7.0, 47.0],
        None,
    ],
)
def test_no_geometry(value: object) -> None:
    assert geometry_of(value) is None
