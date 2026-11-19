"""The intermediate form of a harvested find (M5-19 plan §5.1) and what every extractor shares.

A find becomes an :class:`Extracted`: only the fields named here, in the language of the source. Whatever else the
source says stays in the raw answer, persons included (``author``, ``maintainer``, contact points, STAC ``contacts``):
they never reach the intermediate form (adr/0033 §5). A find without a spatial statement is kept with
``extent_known = False``; whether and how it is listed is M5-20's (Otto, 17.11.2026, plan §5.3).

The data kind of a find comes from the formats and media types of its files and services (plan §5.2): the tables here
take the free text of a catalogue (``GeoTIFF``, ``ESRI Shapefile``) and the URIs of the EU file types alike.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Any

from earthx.catalog import categories as _categories
from earthx.catalog import listed as _listed
from earthx.catalog.categories import CATEGORIES_FILE
from earthx.catalog.harvest_store import canonical
from earthx.catalog.listed import CATALOG_TAGS_FILE
from earthx.catalog.sources import CkanFilter, SourceConfig, SourceProtocol

__all__ = [
    "Distribution",
    "Extracted",
    "FILE_KINDS",
    "LANGUAGES",
    "Invalid",
    "ShapeError",
    "bbox_of",
    "changed_fields",
    "comparable",
    "data_kind_of",
    "extracted_sha256",
    "extractor_version",
    "geometry_of",
    "kind_of",
    "localized",
    "resource_kind",
    "text_of",
]

#: Data kinds by media type, without parameters (adr/0033 §5; plan §5.2). Data before service before document.
_MEDIA_KINDS = {
    "image/tiff": "raster",
    "image/jp2": "raster",
    "application/x-netcdf": "raster",
    "application/netcdf": "raster",
    "application/x-hdf": "raster",
    "application/x-hdf5": "raster",
    "application/vnd+zarr": "raster",
    "application/vnd.zarr": "raster",
    "application/geo+json": "vector",
    "application/vnd.apache.parquet": "vector",
    "application/x-parquet": "vector",
    "application/flatgeobuf": "vector",
    "application/geopackage+sqlite3": "vector",
    "application/gml+xml": "vector",
    "application/vnd.google-earth.kml+xml": "vector",
    "text/csv": "table",
    "application/vnd.ms-excel": "table",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "table",
    "application/vnd.oasis.opendocument.spreadsheet": "table",
    "application/pdf": "document",
    "application/msword": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "application/vnd.ogc.wms_xml": "service",
    "application/vnd.ogc.wfs_xml": "service",
    "application/atom+xml": "service",
    "text/html": "page",
    "application/xhtml+xml": "page",
    "application/zip": "file",
    "application/json": "file",
    "application/xml": "file",
    "text/plain": "file",
}
#: Formats as catalogues write them, after :func:`_format_token` (upper case, letters and digits only; the last part of
#: an EU file type URI). ``page`` is a page for people, ``file`` a file of no known data kind (an archive, JSON, XML).
_FORMAT_KINDS = {
    **dict.fromkeys(
        "TIFF TIF GEOTIFF COG JPEG2000 JP2 NETCDF NC HDF HDF4 HDF5 ZARR ASCIIGRID AAIGRID GRIDASCII".split(), "raster"
    ),
    **dict.fromkeys(
        "SHP SHAPE SHAPEFILE ESRISHAPEFILE GEOJSON GML GPKG GEOPACKAGE KML KMZ FLATGEOBUF FGB GEOPARQUET".split(),
        "vector",
    ),
    **dict.fromkeys("CSV XLSX XLS ODS".split(), "table"),
    **dict.fromkeys(
        "WMS WMTS WFS WCS WMSSRVC WMTSSRVC WFSSRVC WCSSRVC OGCWMS OGCWMTS OGCWFS OGCWCS OGCAPI OGCAPIFEATURES"
        " OGCAPITILES OGCAPIMAPS OGCAPICOVERAGES OGCAPIRECORDS ATOM ATOMFEED".split(),
        "service",
    ),
    **dict.fromkeys("PDF DOC DOCX".split(), "document"),
    **dict.fromkeys("HTML HTM XHTML WEBPAGE".split(), "page"),
    **dict.fromkeys("ZIP GZ TAR 7Z JSON XML TXT LAS LAZ".split(), "file"),
}
_KIND_ORDER = ("raster", "vector", "table", "service", "document")
#: Kinds of a resource that is a file to load (plan §5.2: ``delivery`` is ``download`` where one is).
FILE_KINDS = frozenset({"raster", "vector", "table", "document", "file"})
MAX_TEXT_CHARS = 20_000
#: The largest geometry kept in the intermediate form, as canonical JSON (plan §5.1); a larger one leaves its box.
MAX_GEOMETRY_BYTES = 64 * 1024
_GEOMETRY_TYPES = frozenset(
    {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "GeometryCollection"}
)
#: The order a text given in several languages is read in (plan A7): the search knows German and English (adr/0026).
LANGUAGES = ("de", "en", "fr", "it")
_LANGUAGE_KEY = re.compile(r"[a-z]{2}(?:[-_][A-Za-z]{2})?")


class ShapeError(Exception):
    """A listing the harvest cannot read: the run ends ``failed`` with ``shape``; the text names no address."""


class Invalid(Exception):
    """A find that cannot become an intermediate form; ``reason`` is a code of migration 024."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Distribution:
    """A file, service or page the source names; stored, never asked (adr/0025 K4, Verify is M5-20)."""

    href: str
    #: The format as the source writes it (CKAN ``format``); STAC assets have only a media type.
    format: str | None
    media_type: str | None
    title: str | None
    roles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Extracted:
    source_key: str
    title: str
    description: str
    publisher: str | None
    doi: str | None
    #: Every licence statement as the source writes it, for the rule of M5-20 (adr/0033 §6).
    licence_statements: tuple[str, ...]
    bbox: tuple[float, float, float, float] | None
    #: The GeoJSON geometry where the source gives one of at most :data:`MAX_GEOMETRY_BYTES`.
    geometry: dict[str, Any] | None
    spatial_text: str | None
    extent_known: bool
    temporal: tuple[str | None, str | None] | None
    data_kind: str
    delivery: str | None
    account: str | None
    category: str
    keywords: tuple[str, ...]
    #: The link "Source" (plan §6) and its rank; ``landing_url`` is the page of the dataset, for the sample of M5-20.
    source_url: str
    source_rank: int
    landing_url: str | None
    distributions: tuple[Distribution, ...]

    def to_document(self) -> dict[str, Any]:
        return asdict(self)


#: Lists of the intermediate form whose order says nothing: compared and hashed sorted (Otto, 19.11.2026).
_UNORDERED = ("keywords", "licence_statements", "distributions")
#: How a field name of a source may appear in a report; any other is named as such, never quoted.
_FIELD_NAME = re.compile(r"[A-Za-z0-9_:.-]{1,40}")


def comparable(document: Any) -> Any:
    """An intermediate form as JSON values (tuples become lists), with its unordered lists sorted: two forms that
    differ only in the order of keywords, licence statements or distributions compare equal."""
    if document is None:
        return None
    plain = json.loads(canonical(document))
    if isinstance(plain, dict):
        for field in _UNORDERED:
            if isinstance(plain.get(field), list):
                plain[field] = sorted(plain[field], key=lambda item: canonical(item))
    return plain


def extracted_sha256(extracted: Extracted) -> str:
    return hashlib.sha256(canonical(comparable(extracted.to_document()))).hexdigest()


def _name(field: object) -> str:
    return field if isinstance(field, str) and _FIELD_NAME.fullmatch(field) else "(anderes Feld)"


def changed_fields(old: Any, new: Any) -> list[str]:
    """The names of the top-level fields in which two documents differ, for a report: a list that only changed its
    order is ``<name> (Reihenfolge)``, one of another length ``<name> (Anzahl)``, a list of objects of the same length
    names the fields of its items that differ (``resources.url``). Names only, never values."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        return [] if old == new else ["(ganzes Dokument)"]
    names: list[str] = []
    for field in sorted(set(old) | set(new), key=str):
        before, after = old.get(field), new.get(field)
        if before == after:
            continue
        name = _name(field)
        if isinstance(before, list) and isinstance(after, list):
            if len(before) != len(after):
                names.append(f"{name} (Anzahl)")
                continue
            if sorted(canonical(item) for item in before) == sorted(canonical(item) for item in after):
                names.append(f"{name} (Reihenfolge)")
                continue
            if all(isinstance(item, dict) for item in (*before, *after)):
                inner = {
                    _name(key)
                    for a, b in zip(before, after, strict=True)
                    for key in set(a) | set(b)
                    if a.get(key) != b.get(key)
                }
                names += [f"{name}.{key}" for key in sorted(inner)]
                continue
        names.append(name)
    return names


@cache
def _code_fingerprint(protocol: SourceProtocol) -> bytes:
    """Everything the intermediate form of a find depends on besides the find and its source's settings: the code of
    the protocol's extractor, of this module and of the link rule, and the tables of categories and catalogue tags."""
    here = Path(__file__)
    paths = (
        here.with_name({SourceProtocol.STAC_API: "stac.py", SourceProtocol.CKAN: "ckan.py"}[protocol]),
        here,
        here.with_name("links.py"),
        Path(_categories.__file__),
        Path(_listed.__file__),
        CATEGORIES_FILE,
        CATALOG_TAGS_FILE,
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.digest()


def extractor_version(source: SourceConfig) -> str:
    """The version a find's state is derived with: a fingerprint of the extractor and of the source's settings that
    shape a find (its catalogue page, and for CKAN its publisher field and the extras of its page).

    A find with a kept raw answer is judged again when it changes, also if the answer itself did not (Otto,
    17.11.2026); a changed ``catalog_page`` changes the link "Source" of every find, so it counts too.
    """
    digest = hashlib.sha256(_code_fingerprint(source.protocol))
    digest.update((source.catalog_page or "").encode())
    if isinstance(source.filter, CkanFilter):
        digest.update(b"\0" + source.filter.publisher_field.encode())
        digest.update(b"\0" + "\0".join(source.filter.page_extras).encode())
    return digest.hexdigest()[:16]


def text_of(value: object) -> str | None:
    """A non-blank text, cut to a sane length, without NUL and lone surrogates (Postgres takes neither in ``jsonb``);
    anything else is ``None``."""
    if not isinstance(value, str):
        return None
    text = "".join(c for c in value[: MAX_TEXT_CHARS * 2] if c != "\x00" and not "\ud800" <= c <= "\udfff").strip()
    return text[:MAX_TEXT_CHARS] or None


def bbox_of(value: object) -> tuple[float, float, float, float] | None:
    """West, south, east, north in degrees if ``value`` is such a box (east below west crosses the antimeridian)."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
        return None
    try:
        west, south, east, north = (float(v) for v in value)
    except OverflowError:
        # An integer of a foreign answer too large for a float.
        return None
    if not all(math.isfinite(v) for v in (west, south, east, north)):
        return None
    if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south <= north <= 90):
        return None
    return west, south, east, north


def localized(value: object) -> str | None:
    """A text, or the first non-blank one of a text given per language (``{"de": …, "fr": …}``) in the order of
    :data:`LANGUAGES`, then of the language codes (plan A7). A text that is such a mapping written as JSON counts as one
    (the organisations of opendata.swiss [S])."""
    if isinstance(value, str) and value.lstrip().startswith("{"):
        try:
            value = json.loads(value)
        except (ValueError, RecursionError):
            return text_of(value)
    if not isinstance(value, dict):
        return text_of(value)
    if not value or not all(isinstance(key, str) and _LANGUAGE_KEY.fullmatch(key) for key in value):
        return None
    order = [*LANGUAGES, *sorted(key for key in value if key not in LANGUAGES)]
    return next((text for key in order if (text := text_of(value.get(key))) is not None), None)


def _format_token(value: str) -> str:
    if "://" in value:
        value = value.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def resource_kind(format_: str | None, media_type: str | None) -> str | None:
    """What a file, service or page of a find is by its format, else by its media type: a data kind of
    :data:`_KIND_ORDER`, ``page``, ``file``, or ``None`` where neither is known."""
    for value in (format_, media_type):
        if not value:
            continue
        media = value.split(";")[0].strip().lower()
        if "/" in media and "://" not in media and media in _MEDIA_KINDS:
            return _MEDIA_KINDS[media]
        kind = _FORMAT_KINDS.get(_format_token(value))
        if kind is not None:
            return kind
    return None


def kind_of(kinds: Iterable[str | None], *, default: str) -> str:
    """The data kind of a find from what its resources are: data before service before document."""
    found = set(kinds)
    return next((kind for kind in _KIND_ORDER if kind in found), default)


def data_kind_of(media_types: list[str | None], *, default: str) -> str:
    """The data kind of the media types of a find's data, ``default`` where none is known."""
    return kind_of(
        (
            kind if (kind := _MEDIA_KINDS.get((media or "").split(";")[0].strip().lower())) in _KIND_ORDER else None
            for media in media_types
        ),
        default=default,
    )


def _coordinates(value: object, depth: int, points: list[tuple[float, float]]) -> list[Any]:
    """The coordinates of a geometry rebuilt from checked positions (longitude and latitude only), and every position
    added to ``points``; :class:`ValueError` where they are no nesting of positions on the globe."""
    if depth > 3 or not isinstance(value, list) or not value:
        raise ValueError("no coordinates")
    if not isinstance(value[0], list):
        box = bbox_of([*value[:2], *value[:2]]) if len(value) in (2, 3) else None
        if box is None:
            raise ValueError("no position on the globe")
        points.append((box[0], box[1]))
        return [box[0], box[1]]
    return [_coordinates(item, depth + 1, points) for item in value]


def _clean_geometry(value: object, points: list[tuple[float, float]], depth: int = 0) -> dict[str, Any]:
    """Only the type and the checked coordinates of a geometry (or of a feature's), nothing else the source wrote."""
    if isinstance(value, dict) and value.get("type") == "Feature" and not depth:
        value = value.get("geometry")
    if not isinstance(value, dict) or not isinstance(value.get("type"), str) or value["type"] not in _GEOMETRY_TYPES:
        raise ValueError("no geometry")
    if value["type"] == "GeometryCollection":
        members = value.get("geometries")
        if depth or not isinstance(members, list) or not members:
            raise ValueError("no geometry collection")
        return {"type": value["type"], "geometries": [_clean_geometry(m, points, depth + 1) for m in members]}
    return {"type": value["type"], "coordinates": _coordinates(value.get("coordinates"), 0, points)}


def geometry_of(value: object) -> tuple[tuple[float, float, float, float], dict[str, Any] | None] | None:
    """The box of a GeoJSON geometry (or a feature, or the JSON text of either), with the geometry itself where it is
    small enough to keep; ``None`` where ``value`` is no geometry with positions on the globe."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, RecursionError):
            return None
    points: list[tuple[float, float]] = []
    try:
        geometry = _clean_geometry(value, points)
    except ValueError:
        return None
    longitudes, latitudes = [p[0] for p in points], [p[1] for p in points]
    box = (min(longitudes), min(latitudes), max(longitudes), max(latitudes))
    kept = geometry if len(canonical(geometry)) <= MAX_GEOMETRY_BYTES else None
    return box, kept
