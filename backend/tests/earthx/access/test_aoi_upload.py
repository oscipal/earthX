"""Parsing and checking an uploaded AOI file (M3-06a), one case per format ×
failure mode from the plan's Abnahme list (docs/plans/m3-06a-aoi-upload-backend.md
§11). Everything here is a synthetic fixture built in the test itself — never a
real AOI or a real shapefile export (`CLAUDE.md`).
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
import shapefile

from earthx.access.aoi_upload import (
    MAX_AOI_POINTS,
    MAX_UPLOAD_BYTES,
    MAX_ZIP_MEMBER_BYTES,
    MAX_ZIP_TOTAL_BYTES,
    AoiTooLarge,
    AoiUploadError,
    parse_aoi_upload,
    parse_geojson,
    parse_kml,
    parse_shapefile_zip,
)

SQUARE = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]]}
FAR_SQUARE = {"type": "Polygon", "coordinates": [[[5.0, 5.0], [5.0, 6.0], [6.0, 6.0], [6.0, 5.0], [5.0, 5.0]]]}
BOWTIE = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [1.0, 1.0], [1.0, 0.0], [0.0, 1.0], [0.0, 0.0]]]}
ANTIMERIDIAN = {
    "type": "Polygon",
    "coordinates": [[[179.0, -1.0], [179.0, 1.0], [-179.0, 1.0], [-179.0, -1.0], [179.0, -1.0]]],
}


def _shapefile_zip(
    rings: list[list[list[float]]],
    *,
    shape_type: int = shapefile.POLYGON,
    prj: str | None = "EPSG:4326",
    with_shx: bool = True,
    with_dbf: bool = True,
) -> bytes:
    """A minimal, synthetic Shapefile bundle as ZIP bytes, entirely via `pyshp`'s
    own `Writer` — never data from a real dataset or export."""
    shp_buf, shx_buf, dbf_buf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    writer = shapefile.Writer(shp=shp_buf, shx=shx_buf, dbf=dbf_buf, shapeType=shape_type)
    writer.field("name", "C")
    for ring in rings:
        if shape_type == shapefile.POLYGON:
            writer.poly([ring])
        else:
            writer.line([ring])
        writer.record("a")
    writer.close()

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as archive:
        archive.writestr("aoi.shp", shp_buf.getvalue())
        if with_shx:
            archive.writestr("aoi.shx", shx_buf.getvalue())
        if with_dbf:
            archive.writestr("aoi.dbf", dbf_buf.getvalue())
        if prj is not None:
            archive.writestr("aoi.prj", prj)
    return zip_buf.getvalue()


_UTM32N_WKT = (
    'PROJCS["WGS_84_UTM_32N",GEOGCS["WGS_84",DATUM["WGS_1984",SPHEROID["WGS_84",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
    'PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",9.0],'
    'PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]'
)


def _utm32n_square_zip() -> bytes:
    """The same square as SQUARE, but projected to EPSG:32632 (UTM 32N) — read back
    through `.prj` it must land close to SQUARE's own corners again. `pyproj` builds
    the projected *input* fixture here (the forward direction); the module under test
    only ever does the reverse, so this is a round trip, not a circular check."""
    import pyproj

    to_utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)
    ring = [list(to_utm.transform(lon, lat)) for lon, lat in SQUARE["coordinates"][0]]
    return _shapefile_zip([ring], prj=_UTM32N_WKT)


# --------------------------------------------------------------------------- GeoJSON


class TestGeoJSON:
    def test_valid_polygon(self) -> None:
        geometry = parse_geojson(json.dumps(SQUARE).encode())
        assert geometry == SQUARE

    def test_feature_wrapper(self) -> None:
        feature = {"type": "Feature", "properties": {}, "geometry": SQUARE}
        assert parse_geojson(json.dumps(feature).encode()) == SQUARE

    def test_malformed_json(self) -> None:
        with pytest.raises(AoiUploadError):
            parse_geojson(b"{not json")

    def test_wrong_geometry_type(self) -> None:
        line = {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]}
        with pytest.raises(AoiUploadError, match="LineString"):
            parse_geojson(json.dumps(line).encode())

    def test_geometry_collection_rejected(self) -> None:
        collection = {"type": "GeometryCollection", "geometries": [SQUARE]}
        with pytest.raises(AoiUploadError, match="GeometryCollection"):
            parse_geojson(json.dumps(collection).encode())

    def test_foreign_crs_rejected(self) -> None:
        geometry = {**SQUARE, "crs": {"type": "name", "properties": {"name": "EPSG:2056"}}}
        with pytest.raises(AoiUploadError, match="crs"):
            parse_geojson(json.dumps(geometry).encode())

    def test_multiple_polygons_are_unioned(self) -> None:
        collection = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {}, "geometry": SQUARE},
                {"type": "Feature", "properties": {}, "geometry": FAR_SQUARE},
            ],
        }
        geometry = parse_geojson(json.dumps(collection).encode())
        assert geometry["type"] == "MultiPolygon"
        assert len(geometry["coordinates"]) == 2

    def test_point_and_polygon_mix_rejected(self) -> None:
        collection = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {}, "geometry": SQUARE},
                {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [0.5, 0.5]}},
            ],
        }
        with pytest.raises(AoiUploadError, match="Point"):
            parse_geojson(json.dumps(collection).encode())

    def test_self_intersecting_polygon_rejected(self) -> None:
        with pytest.raises(AoiUploadError, match="valid"):
            parse_geojson(json.dumps(BOWTIE).encode())

    def test_too_many_points_rejected(self) -> None:
        count = MAX_AOI_POINTS + 10
        ring = [[(i % 1000) * 0.0001, (i // 1000) * 0.0001] for i in range(count)]
        ring.append(ring[0])
        geometry = {"type": "Polygon", "coordinates": [ring]}
        with pytest.raises(AoiUploadError, match=str(MAX_AOI_POINTS)):
            parse_geojson(json.dumps(geometry).encode())

    def test_antimeridian_polygon_passes(self) -> None:
        geometry = parse_geojson(json.dumps(ANTIMERIDIAN).encode())
        assert geometry["type"] == "Polygon"

    def test_no_error_message_contains_a_coordinate(self) -> None:
        line = {"type": "LineString", "coordinates": [[12.345, 67.891], [1.0, 1.0]]}
        with pytest.raises(AoiUploadError) as excinfo:
            parse_geojson(json.dumps(line).encode())
        assert "12.345" not in str(excinfo.value)
        assert "67.891" not in str(excinfo.value)


# ------------------------------------------------------------------------------ KML


KML_POLYGON = """<?xml version="1.0"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>
<Polygon><outerBoundaryIs><LinearRing><coordinates>
0,0,0 0,1,0 1,1,0 1,0,0 0,0,0
</coordinates></LinearRing></outerBoundaryIs></Polygon>
</Placemark></Document></kml>"""

KML_XXE = """<?xml version="1.0"?>
<!DOCTYPE kml [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>
<name>&xxe;</name>
<Polygon><outerBoundaryIs><LinearRing><coordinates>
0,0 0,1 1,1 1,0 0,0
</coordinates></LinearRing></outerBoundaryIs></Polygon>
</Placemark></Document></kml>"""


class TestKML:
    def test_valid_polygon(self) -> None:
        geometry = parse_kml(KML_POLYGON.encode())
        assert geometry == SQUARE

    def test_malformed_xml(self) -> None:
        with pytest.raises(AoiUploadError):
            parse_kml(b"<kml><Document>")

    def test_external_entity_rejected(self) -> None:
        with pytest.raises(AoiUploadError):
            parse_kml(KML_XXE.encode())

    def test_no_geometry_found(self) -> None:
        empty = "<kml><Document><Placemark></Placemark></Document></kml>"
        with pytest.raises(AoiUploadError, match="no usable geometry"):
            parse_kml(empty.encode())

    def test_lines_only_kml_names_lines_in_the_message(self) -> None:
        # M3-06b, Otto's review 26.09.2026: the old generic "no usable geometry
        # found in the file" left a user exporting a route (LineString) guessing;
        # this names what the file actually had.
        route = """<kml><Document>
        <Placemark><LineString><coordinates>0,0 1,1</coordinates></LineString></Placemark>
        </Document></kml>"""
        with pytest.raises(AoiUploadError, match="the file contains only lines"):
            parse_kml(route.encode())

    def test_multiple_placemarks_are_unioned(self) -> None:
        two_polygons = """<kml><Document>
        <Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>
        0,0 0,1 1,1 1,0 0,0
        </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
        <Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>
        5,5 5,6 6,6 6,5 5,5
        </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
        </Document></kml>"""
        geometry = parse_kml(two_polygons.encode())
        assert geometry["type"] == "MultiPolygon"


# ----------------------------------------------------------------------- Shapefile


class TestShapefile:
    def test_valid_polygon(self) -> None:
        zip_bytes = _shapefile_zip([SQUARE["coordinates"][0]])
        geometry = parse_shapefile_zip(zip_bytes)
        assert geometry["type"] == "Polygon"
        (lon0, lat0), *_ = geometry["coordinates"][0]
        assert lon0 == pytest.approx(0.0)
        assert lat0 == pytest.approx(0.0)

    def test_missing_prj_rejected(self) -> None:
        zip_bytes = _shapefile_zip([SQUARE["coordinates"][0]], prj=None)
        with pytest.raises(AoiUploadError, match="prj"):
            parse_shapefile_zip(zip_bytes)

    def test_missing_shp_rejected(self) -> None:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as archive:
            archive.writestr("aoi.prj", "EPSG:4326")
        with pytest.raises(AoiUploadError, match="shp"):
            parse_shapefile_zip(zip_buf.getvalue())

    def test_works_without_shx_and_dbf(self) -> None:
        zip_bytes = _shapefile_zip([SQUARE["coordinates"][0]], with_shx=False, with_dbf=False)
        geometry = parse_shapefile_zip(zip_bytes)
        assert geometry["type"] == "Polygon"

    def test_reprojects_from_prj(self) -> None:
        geometry = parse_shapefile_zip(_utm32n_square_zip())
        assert geometry["type"] == "Polygon"
        for lon, lat in geometry["coordinates"][0]:
            assert -1.0 < lon < 2.0
            assert -1.0 < lat < 2.0

    def test_not_a_zip_rejected(self) -> None:
        with pytest.raises(AoiUploadError, match="ZIP"):
            parse_shapefile_zip(b"not a zip")

    def test_lines_only_shapefile_names_lines_in_the_message(self) -> None:
        # M3-06b, Otto's review 26.09.2026: a shapefile of only line shapes gets a
        # message that says so, not the generic "no usable geometry found".
        zip_bytes = _shapefile_zip([[[0.0, 0.0], [1.0, 1.0]]], shape_type=shapefile.POLYLINE)
        with pytest.raises(AoiUploadError, match="the file contains only lines"):
            parse_shapefile_zip(zip_bytes)

    def test_multipoint_only_shapefile_names_points_in_the_message(self) -> None:
        # A MultiPoint shapefile (one shape, several positions) is a different
        # GeoJSON type than the single `Point` this route accepts (M3-06b).
        shp_buf, shx_buf, dbf_buf = io.BytesIO(), io.BytesIO(), io.BytesIO()
        writer = shapefile.Writer(shp=shp_buf, shx=shx_buf, dbf=dbf_buf, shapeType=shapefile.MULTIPOINT)
        writer.field("name", "C")
        writer.multipoint([[0.0, 0.0], [1.0, 1.0]])
        writer.record("a")
        writer.close()
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as archive:
            archive.writestr("aoi.shp", shp_buf.getvalue())
            archive.writestr("aoi.shx", shx_buf.getvalue())
            archive.writestr("aoi.dbf", dbf_buf.getvalue())
            archive.writestr("aoi.prj", "EPSG:4326")
        with pytest.raises(AoiUploadError, match="the file contains only points"):
            parse_shapefile_zip(zip_buf.getvalue())

    def test_unexpected_zip_entry_rejected(self) -> None:
        zip_bytes = _shapefile_zip([SQUARE["coordinates"][0]])
        archive_in = zipfile.ZipFile(io.BytesIO(zip_bytes))
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as archive_out:
            for name in archive_in.namelist():
                archive_out.writestr(name, archive_in.read(name))
            archive_out.writestr("nested.zip", b"anything")
        with pytest.raises(AoiUploadError, match="unexpected entry"):
            parse_shapefile_zip(zip_buf.getvalue())

    def test_macos_sidecar_files_are_ignored(self) -> None:
        zip_bytes = _shapefile_zip([SQUARE["coordinates"][0]])
        archive_in = zipfile.ZipFile(io.BytesIO(zip_bytes))
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as archive_out:
            for name in archive_in.namelist():
                archive_out.writestr(name, archive_in.read(name))
            archive_out.writestr("__MACOSX/._aoi.shp", b"junk")
        geometry = parse_shapefile_zip(zip_buf.getvalue())
        assert geometry["type"] == "Polygon"

    def test_zip_bomb_rejected(self) -> None:
        # "0" repeated compresses at an extreme ratio; declared as .prj so it is
        # read (and capped) rather than skipped, without needing a nested archive.
        huge = b"0" * (MAX_ZIP_TOTAL_BYTES * 4)
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("aoi.shp", b"\x00" * 100)
            archive.writestr("aoi.prj", huge)
        assert zip_buf.tell() < MAX_ZIP_TOTAL_BYTES  # the bomb itself compresses tiny
        with pytest.raises(AoiTooLarge):
            parse_shapefile_zip(zip_buf.getvalue())

    def test_too_many_zip_members_rejected(self) -> None:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as archive:
            for i in range(15):
                archive.writestr(f"file{i}.prj", "x")
        with pytest.raises(AoiTooLarge):
            parse_shapefile_zip(zip_buf.getvalue())

    def test_member_over_cap_rejected(self) -> None:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("aoi.shp", b"0" * (MAX_ZIP_MEMBER_BYTES + 1))
            archive.writestr("aoi.prj", "EPSG:4326")
        with pytest.raises(AoiTooLarge):
            parse_shapefile_zip(zip_buf.getvalue())


# --------------------------------------------------------------------- dispatch


class TestDispatch:
    def test_unsupported_extension_rejected(self) -> None:
        with pytest.raises(AoiUploadError, match="unsupported file type"):
            parse_aoi_upload("aoi.txt", b"whatever")

    def test_geojson_extension_dispatches(self) -> None:
        assert parse_aoi_upload("aoi.geojson", json.dumps(SQUARE).encode()) == SQUARE
        assert parse_aoi_upload("aoi.json", json.dumps(SQUARE).encode()) == SQUARE

    def test_kml_extension_dispatches(self) -> None:
        assert parse_aoi_upload("aoi.kml", KML_POLYGON.encode()) == SQUARE

    def test_zip_extension_dispatches(self) -> None:
        geometry = parse_aoi_upload("aoi.zip", _shapefile_zip([SQUARE["coordinates"][0]]))
        assert geometry["type"] == "Polygon"

    def test_oversized_upload_rejected(self) -> None:
        with pytest.raises(AoiTooLarge):
            parse_aoi_upload("aoi.geojson", b"0" * (MAX_UPLOAD_BYTES + 1))
