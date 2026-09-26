"""Turn an uploaded AOI file into a checked EPSG:4326 GeoJSON geometry (M3-06a,
docs/plans/m3-06a-aoi-upload-backend.md).

Lives in `access`, not a new module (Otto F2): no module in architekturplan.md 3.1
is named for "parse an uploaded vector file", and `access` already owns AOI handling
for downloads (`download.py`); this file needs neither `readers` nor `catalog`, so
`access`'s own import contract (only those two) stays satisfied unchanged.

Everything here works on bytes the caller already holds in memory
(`api.aoi_upload_route`, §6 of the plan) — nothing opens a file on disk. A ZIP member
is read in capped chunks into a fresh `BytesIO`, never trusting the ZIP's own
(attacker-controlled) declared size.

Three formats in, one geometry out. More than one usable geometry in a file is
combined into a single (multi)polygon when every one of them is polygonal (Otto's
F5 = 2, 26.09.2026, plan §9) and refused otherwise — a point next to a polygon, or
several points, has no honest single answer, so this refuses rather than guesses one
of them away.
"""

from __future__ import annotations

import io
import json
import math
import re
import struct
import zipfile
from collections.abc import Mapping
from typing import Any
from xml.etree.ElementTree import Element, ParseError

import pyproj
import shapefile
from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException
from pyproj.exceptions import CRSError
from shapely.errors import ShapelyError
from shapely.geometry import mapping as shapely_mapping
from shapely.geometry import shape as shapely_shape
from shapely.ops import unary_union


class AoiUploadError(ValueError):
    """The upload is bad in a way that is the caller's fault (a 400)."""


class AoiTooLarge(AoiUploadError):
    """A size cap was exceeded (a 413, not a 400 — plan §10)."""


# docs/plans/m3-06a-aoi-upload-backend.md §8, Otto's F4 (26.09.2026).
# = Starlette's own SpooledTemporaryFile threshold (§6) — kept even though this
# route no longer goes through Starlette's multipart parser (§6 Nachtrag): it is
# still the size below which "definitely never written to disk" needs no borrowed
# guarantee from anyone else's code, only our own chunked read.
MAX_UPLOAD_BYTES = 1_048_576
MAX_ZIP_MEMBERS = 10
MAX_ZIP_MEMBER_BYTES = 20 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 20 * 1024 * 1024
MAX_AOI_POINTS = 20_000

# Point-only AOIs stay useful (plan §9); lines have no established consumer.
ALLOWED_GEOMETRY_TYPES = frozenset({"Point", "Polygon", "MultiPolygon"})
_POLYGONAL_TYPES = frozenset({"Polygon", "MultiPolygon"})
MIN_RING_POINTS = 4

_ZIP_CHUNK_BYTES = 65536
_ZIP_MEMBER_NAME = re.compile(r"^[\w.-]+\.(shp|shx|dbf|prj|cpg)$", re.IGNORECASE)
# RFC 7946: GeoJSON is always CRS84/EPSG:4326. An older export's `crs` member is
# read only far enough to refuse a foreign one, never to switch behaviour on it.
_GEOJSON_CRS_NAMES = frozenset(
    {"urn:ogc:def:crs:OGC::CRS84", "urn:ogc:def:crs:OGC:1.3:CRS84", "EPSG:4326", "urn:ogc:def:crs:EPSG::4326"}
)


def parse_aoi_upload(filename: str, content: bytes) -> dict[str, Any]:
    """Dispatches on `filename`'s extension. `content` is the whole file; the caller
    (`api.aoi_upload_route`) has already capped it before this is ever reached, but
    the cap is checked again here so this function is safe to call on its own, e.g.
    from a test.
    """
    if len(content) > MAX_UPLOAD_BYTES:
        raise AoiTooLarge(f"upload is over the {MAX_UPLOAD_BYTES} byte cap")
    lower = filename.lower()
    if lower.endswith(".geojson") or lower.endswith(".json"):
        return parse_geojson(content)
    if lower.endswith(".kml"):
        return parse_kml(content)
    if lower.endswith(".zip"):
        return parse_shapefile_zip(content)
    raise AoiUploadError(f"unsupported file type: {filename!r} (expected .geojson, .kml or .zip)")


# --------------------------------------------------------------------------- GeoJSON


def parse_geojson(content: bytes) -> dict[str, Any]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AoiUploadError("not valid UTF-8 text") from error
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise AoiUploadError("not valid JSON") from error
    geometries = _geojson_geometries(parsed)
    return _finalise_geometry(_combine_geometries(geometries))


def _geojson_geometries(obj: Any) -> list[dict[str, Any]]:
    if not isinstance(obj, Mapping):
        raise AoiUploadError("not a GeoJSON object")
    _check_geojson_crs(obj)
    kind = obj.get("type")
    if kind == "FeatureCollection":
        features = obj.get("features")
        if not isinstance(features, list):
            raise AoiUploadError("FeatureCollection has no features")
        found: list[dict[str, Any]] = []
        for feature in features:
            found.extend(_geojson_geometries_from_feature(feature))
        return found
    if kind == "Feature":
        return _geojson_geometries_from_feature(obj)
    if kind == "GeometryCollection":
        raise AoiUploadError("GeometryCollection is not supported")
    if kind in ALLOWED_GEOMETRY_TYPES:
        return [{"type": kind, "coordinates": obj.get("coordinates")}]
    raise AoiUploadError(f"not a GeoJSON geometry type we support: {kind!r}")


def _geojson_geometries_from_feature(feature: Any) -> list[dict[str, Any]]:
    if not isinstance(feature, Mapping):
        raise AoiUploadError("a feature is not a GeoJSON object")
    _check_geojson_crs(feature)
    geometry = feature.get("geometry")
    if geometry is None:
        return []
    if not isinstance(geometry, Mapping) or geometry.get("type") not in ALLOWED_GEOMETRY_TYPES:
        kind = geometry.get("type") if isinstance(geometry, Mapping) else geometry
        raise AoiUploadError(f"not a GeoJSON geometry type we support: {kind!r}")
    _check_geojson_crs(geometry)
    return [{"type": geometry["type"], "coordinates": geometry.get("coordinates")}]


def _check_geojson_crs(obj: Mapping[str, Any]) -> None:
    crs = obj.get("crs")
    if crs is None:
        return
    name = None
    if isinstance(crs, Mapping):
        properties = crs.get("properties")
        if isinstance(properties, Mapping):
            name = properties.get("name")
    if name not in _GEOJSON_CRS_NAMES:
        raise AoiUploadError(f"unsupported crs {name!r}; GeoJSON must be EPSG:4326/CRS84")


# ------------------------------------------------------------------------------ KML


def parse_kml(content: bytes) -> dict[str, Any]:
    try:
        root = DefusedET.fromstring(content)
    except DefusedXmlException as error:
        raise AoiUploadError("KML contains disallowed XML constructs (external entities/DTD)") from error
    except ParseError as error:
        raise AoiUploadError("not valid XML/KML") from error

    geometries: list[dict[str, Any]] = []
    placemarks = [element for element in root.iter() if _local_name(element.tag) == "Placemark"]
    for placemark in placemarks:
        geometry = _kml_placemark_geometry(placemark)
        if geometry is not None:
            geometries.append(geometry)
    if not placemarks:
        # No <Placemark> at all: fall back to a bare top-level <Polygon>/<Point>,
        # which is unusual but not invalid KML.
        geometry = _kml_placemark_geometry(root)
        if geometry is not None:
            geometries.append(geometry)
    return _finalise_geometry(_combine_geometries(geometries))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_descendant(element: Element, local_name: str) -> Element | None:
    for child in element.iter():
        if _local_name(child.tag) == local_name:
            return child
    return None


def _kml_placemark_geometry(element: Element) -> dict[str, Any] | None:
    polygon = _first_descendant(element, "Polygon")
    if polygon is not None:
        # First <coordinates> found = the outer boundary, same simplification as
        # frontend/src/aoiFile.ts (prototyp-inventar.md F3): inner boundaries are
        # ignored, not read as holes.
        coords_el = _first_descendant(polygon, "coordinates")
        if coords_el is not None and coords_el.text:
            ring = _parse_kml_coordinates(coords_el.text)
            if len(ring) >= 3:
                if ring[0] != ring[-1]:
                    ring = [*ring, ring[0]]
                return {"type": "Polygon", "coordinates": [ring]}
        return None
    point = _first_descendant(element, "Point")
    if point is not None:
        coords_el = _first_descendant(point, "coordinates")
        if coords_el is not None and coords_el.text:
            positions = _parse_kml_coordinates(coords_el.text)
            if positions:
                return {"type": "Point", "coordinates": positions[0]}
        return None
    return None


def _parse_kml_coordinates(text: str) -> list[list[float]]:
    """KML coordinates are always ``lon,lat[,alt]`` (WGS84 by spec) — altitude, if
    present, is dropped here; a malformed token is skipped rather than failing the
    whole file, the same tolerance `frontend/src/aoiFile.ts` already has."""
    positions: list[list[float]] = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        if math.isfinite(lon) and math.isfinite(lat):
            positions.append([lon, lat])
    return positions


# ----------------------------------------------------------------------- Shapefile


def parse_shapefile_zip(content: bytes) -> dict[str, Any]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as error:
        raise AoiUploadError("not a valid ZIP file") from error

    members = _extract_shapefile_members(archive)
    if "shp" not in members:
        raise AoiUploadError("the ZIP has no .shp file")
    if "prj" not in members:
        raise AoiUploadError("the ZIP has no .prj file; the coordinate system is not guessed")

    prj_text = members["prj"].getvalue().decode("ascii", errors="replace")
    try:
        crs = pyproj.CRS.from_user_input(prj_text)
    except CRSError as error:
        raise AoiUploadError("the .prj file's coordinate system could not be read") from error
    transformer = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    for name in ("shp", "shx", "dbf"):
        if name in members:
            members[name].seek(0)
    try:
        reader = shapefile.Reader(shp=members["shp"], shx=members.get("shx"), dbf=members.get("dbf"))
        shapes = reader.shapes()
    except (shapefile.ShapefileException, struct.error, IndexError) as error:
        raise AoiUploadError("not a valid shapefile") from error

    geometries: list[dict[str, Any]] = []
    for shape in shapes:
        geometry = _shapefile_geometry(shape, transformer)
        if geometry is not None:
            geometries.append(geometry)
    return _finalise_geometry(_combine_geometries(geometries))


def _basename(name: str) -> str:
    return name.rsplit("/", 1)[-1]


def _extract_shapefile_members(archive: zipfile.ZipFile) -> dict[str, io.BytesIO]:
    """Reads the ZIP's members into per-extension `BytesIO` buffers, never trusting
    `ZipInfo.file_size` — every member is read in chunks with a running total,
    aborting as soon as either cap in the plan (§8) is exceeded, regardless of what
    the ZIP's own header claims."""
    infos = archive.infolist()
    if len(infos) > MAX_ZIP_MEMBERS:
        raise AoiTooLarge(f"the ZIP has more than {MAX_ZIP_MEMBERS} entries")

    members: dict[str, io.BytesIO] = {}
    total = 0
    for info in infos:
        name = info.filename
        if name.startswith("__MACOSX/") or _basename(name).startswith("._"):
            continue  # macOS Finder "AppleDouble" sidecar files: common, harmless.
        if "/" in name or "\\" in name or not _ZIP_MEMBER_NAME.match(name):
            raise AoiUploadError(f"the ZIP has an unexpected entry: {name!r}")
        extension = name.rsplit(".", 1)[-1].lower()
        if extension == "cpg":
            continue  # not read; only geometry is used, never attributes.

        buffer = io.BytesIO()
        member_total = 0
        with archive.open(info, "r") as source:
            while True:
                chunk = source.read(_ZIP_CHUNK_BYTES)
                if not chunk:
                    break
                member_total += len(chunk)
                total += len(chunk)
                if member_total > MAX_ZIP_MEMBER_BYTES:
                    raise AoiTooLarge(f"{name} is over the {MAX_ZIP_MEMBER_BYTES} byte decompressed cap")
                if total > MAX_ZIP_TOTAL_BYTES:
                    raise AoiTooLarge(f"the ZIP's decompressed contents are over the {MAX_ZIP_TOTAL_BYTES} byte cap")
                buffer.write(chunk)
        buffer.seek(0)
        members[extension] = buffer
    return members


def _shapefile_geometry(shape: Any, transformer: pyproj.Transformer) -> dict[str, Any] | None:
    geo = shape.__geo_interface__
    kind = geo.get("type")
    if kind not in ALLOWED_GEOMETRY_TYPES:
        return None
    coordinates = _transform_coordinates(_to_lists(geo.get("coordinates")), transformer)
    return {"type": kind, "coordinates": coordinates}


def _transform_coordinates(coordinates: Any, transformer: pyproj.Transformer) -> Any:
    if isinstance(coordinates, list) and coordinates and all(_is_number(v) for v in coordinates):
        lon, lat = transformer.transform(coordinates[0], coordinates[1])
        return [lon, lat]
    if isinstance(coordinates, list) and coordinates:
        return [_transform_coordinates(item, transformer) for item in coordinates]
    raise AoiUploadError("geometry has malformed coordinates")


def _to_lists(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_to_lists(item) for item in value]
    return value


# ------------------------------------------------------------------ shared checks


def _combine_geometries(geometries: list[dict[str, Any]]) -> dict[str, Any]:
    """Otto's F5 = 2 (26.09.2026, plan §9): more than one usable geometry is merged
    into a single (multi)polygon when every one of them is polygonal, and refused
    otherwise — a point next to a polygon, or several points, has no single
    unambiguous merged AOI."""
    if not geometries:
        raise AoiUploadError("no usable geometry found in the file")
    if len(geometries) == 1:
        return geometries[0]
    kinds = {g.get("type") for g in geometries}
    if not kinds <= _POLYGONAL_TYPES:
        raise AoiUploadError(
            f"the file has {len(geometries)} features; multiple features are only combined "
            f"when every one is a polygon (found {sorted(k for k in kinds if k)})"
        )
    try:
        shapes = [shapely_shape(g) for g in geometries]
        merged = unary_union(shapes)
    except (ShapelyError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise AoiUploadError("could not combine the file's polygons") from error
    return shapely_mapping(merged)


def _finalise_geometry(geometry: Any) -> dict[str, Any]:
    if not isinstance(geometry, Mapping) or "type" not in geometry:
        raise AoiUploadError("not a usable geometry")
    kind = geometry.get("type")
    if kind not in ALLOWED_GEOMETRY_TYPES:
        raise AoiUploadError(f"geometry type {kind!r} is not supported (allowed: Point, Polygon, MultiPolygon)")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, (list, tuple)) or not coordinates:
        raise AoiUploadError("geometry has no coordinates")
    coordinates = _drop_z(_to_lists(coordinates))

    points = _check_positions(coordinates)
    if points > MAX_AOI_POINTS:
        raise AoiUploadError(f"geometry has more than {MAX_AOI_POINTS} positions")

    if kind in _POLYGONAL_TYPES:
        for ring in _rings_of(kind, coordinates):
            if len(ring) < MIN_RING_POINTS or ring[0] != ring[-1]:
                raise AoiUploadError("a ring is not closed or has too few positions")
        _check_polygon_validity({"type": kind, "coordinates": coordinates})

    return {"type": kind, "coordinates": coordinates}


def _drop_z(coordinates: Any) -> Any:
    if isinstance(coordinates, list) and coordinates and all(_is_number(v) for v in coordinates):
        return coordinates[:2]
    if isinstance(coordinates, list) and coordinates:
        return [_drop_z(item) for item in coordinates]
    raise AoiUploadError("geometry has malformed coordinates")


def _check_positions(coordinates: Any) -> int:
    """Walks a (possibly nested) coordinates array; returns the number of positions.
    No message anywhere in this module names a coordinate (plan §10) — only counts
    and rule names ever surface."""
    if isinstance(coordinates, list) and coordinates and all(_is_number(v) for v in coordinates):
        if len(coordinates) < 2:
            raise AoiUploadError("a position has fewer than two numbers")
        longitude, latitude = coordinates[0], coordinates[1]
        if not -180.0 <= float(longitude) <= 180.0:
            raise AoiUploadError("a longitude is outside +/-180")
        if not -90.0 <= float(latitude) <= 90.0:
            raise AoiUploadError("a latitude is outside +/-90")
        return 1
    if not isinstance(coordinates, list) or not coordinates:
        raise AoiUploadError("geometry has no coordinates")
    return sum(_check_positions(item) for item in coordinates)


def _rings_of(kind: str, coordinates: list[Any]) -> list[list[Any]]:
    if kind == "Polygon":
        return [ring for ring in coordinates if isinstance(ring, list)]
    return [ring for polygon in coordinates if isinstance(polygon, list) for ring in polygon if isinstance(ring, list)]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _check_polygon_validity(geometry: Mapping[str, Any]) -> None:
    """Refuses a polygon whose rings self-intersect or otherwise fail the OGC
    simple-feature rules (same technique as `adapters.federated_search`'s check for
    `intersects`, M3-08 — independently written here, since `access` may not import
    `adapters`, plan §2)."""
    try:
        shape = shapely_shape(geometry)
    except (ShapelyError, ValueError, TypeError, KeyError, AttributeError):
        raise AoiUploadError("not a usable polygon geometry") from None
    if not shape.is_valid:
        raise AoiUploadError("polygon is not valid (rings must not self-intersect)")


__all__ = [
    "MAX_AOI_POINTS",
    "MAX_UPLOAD_BYTES",
    "MAX_ZIP_MEMBER_BYTES",
    "MAX_ZIP_MEMBERS",
    "MAX_ZIP_TOTAL_BYTES",
    "AoiTooLarge",
    "AoiUploadError",
    "parse_aoi_upload",
    "parse_geojson",
    "parse_kml",
    "parse_shapefile_zip",
]
