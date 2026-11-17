"""The intermediate form of a harvested find (M5-19 plan §5.1) and what every extractor shares.

A find becomes an :class:`Extracted`: only the fields named here, in the language of the source. Whatever else the
source says stays in the raw answer, persons included (``author``, ``maintainer``, contact points, STAC ``contacts``):
they never reach the intermediate form (adr/0033 §5). A find without a spatial statement is kept with
``extent_known = False``; whether and how it is listed is M5-20's (Otto, 17.11.2026, plan §5.3).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from typing import Any

from earthx.catalog.harvest_store import canonical

__all__ = [
    "Distribution",
    "Extracted",
    "Invalid",
    "ShapeError",
    "bbox_of",
    "data_kind_of",
    "extracted_sha256",
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
}
_KIND_ORDER = ("raster", "vector", "table", "service", "document")
MAX_TEXT_CHARS = 20_000


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


def extracted_sha256(extracted: Extracted) -> str:
    return hashlib.sha256(canonical(extracted.to_document())).hexdigest()


def text_of(value: object) -> str | None:
    """A non-blank text, cut to a sane length; anything else is ``None``."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:MAX_TEXT_CHARS]


def bbox_of(value: object) -> tuple[float, float, float, float] | None:
    """West, south, east, north in degrees if ``value`` is such a box (east below west crosses the antimeridian)."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in value):
        return None
    west, south, east, north = (float(v) for v in value)
    if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south <= north <= 90):
        return None
    return west, south, east, north


def data_kind_of(media_types: list[str | None], *, default: str) -> str:
    """The data kind of the media types of a find's data, ``default`` where none is known."""
    kinds = {_MEDIA_KINDS.get((media or "").split(";")[0].strip().lower()) for media in media_types}
    for kind in _KIND_ORDER:
        if kind in kinds:
            return kind
    return default
