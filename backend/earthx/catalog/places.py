"""Place names for the search text, derived from the extent of a dataset (adr/0026 §4.1, F8; M5-22 plan F4).

``backend/catalog/places.json`` holds the countries of Natural Earth at 1:50m (public domain) with their English and
German name, their continent and a coarse outline; ``scripts/write-place-outlines.py`` writes it from a release named
in the file, with its checksum. :func:`place_terms` turns a bounding box into words:

* a country whose area lies at least half inside the box gives its English and German name; so does a continent;
* a box over nearly the whole earth (every continent but Antarctica at least half inside) gives only ``global``,
  ``worldwide``, ``weltweit`` instead, since naming every country would say nothing.

Areas are geodesic (WGS 84 ellipsoid), so a box far from the equator is not overweighted.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pyproj import Geod
from shapely.errors import ShapelyError
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry

import earthx
from earthx.catalog.registry import ConfigError

PLACES_FILE = Path(earthx.__file__).resolve().parents[1] / "catalog" / "places.json"

#: The share of a country's or a continent's area that has to lie in the box (F4).
SHARE = 0.5
GLOBAL_TERMS = ("global", "worldwide", "weltweit")
#: Not inhabited enough to decide whether a dataset is global: a box that stops at 60° S is still global.
NOT_FOR_GLOBAL = "Antarctica"

_GEOD = Geod(ellps="WGS84")
_KEYS = frozenset({"source", "release", "file", "sha256", "script", "tolerance_deg", "continents", "countries"})
_COUNTRY_KEYS = frozenset({"code", "en", "de", "continent", "outline"})


@dataclass(frozen=True, slots=True)
class Country:
    code: str
    en: str
    de: str
    continent: str | None
    outline: BaseGeometry
    #: Geodesic area of the outline in m².
    area: float


@dataclass(frozen=True, slots=True)
class Places:
    countries: tuple[Country, ...]
    #: English name of each continent to its German name.
    continents: Mapping[str, str]


def _area(geometry: BaseGeometry) -> float:
    return abs(_GEOD.geometry_area_perimeter(geometry)[0])


def _text(raw: Mapping[str, object], key: str, where: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ConfigError(f"{where}: '{key}' is a non-empty text without surrounding spaces")
    return value


def load_places(path: Path = PLACES_FILE) -> Places:
    """The places in ``path``, checked; :class:`ConfigError` names the file, the country and what is wrong."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ConfigError(f"{path.name}: cannot be read ({type(error).__name__})") from None
    if not isinstance(data, dict) or set(data) != _KEYS:
        raise ConfigError(f"{path.name}: has exactly the keys {', '.join(sorted(_KEYS))}")
    continents = data["continents"]
    if not isinstance(continents, dict) or not continents:
        raise ConfigError(f"{path.name}: 'continents' maps each English name to the German one")
    for name in continents:
        _text(continents, name, f"{path.name}, continent {name}")
    if not isinstance(data["countries"], list) or not data["countries"]:
        raise ConfigError(f"{path.name}: 'countries' is a non-empty list")
    countries = tuple(_country(raw, continents, path.name) for raw in data["countries"])
    codes = [country.code for country in countries]
    if len(set(codes)) != len(codes):
        raise ConfigError(f"{path.name}: a country code appears twice")
    return Places(countries, dict(continents))


def _country(raw: object, continents: Mapping[str, str], file: str) -> Country:
    if not isinstance(raw, dict) or set(raw) != _COUNTRY_KEYS:
        raise ConfigError(f"{file}: each country has exactly the keys {', '.join(sorted(_COUNTRY_KEYS))}")
    code = _text(raw, "code", f"{file}, a country")
    where = f"{file}, country {code}"
    continent = raw["continent"]
    if continent is not None and continent not in continents:
        raise ConfigError(f"{where}: the continent is one of 'continents' or null")
    try:
        outline = shape(raw["outline"])
    except (ShapelyError, AttributeError, KeyError, TypeError, ValueError):
        raise ConfigError(f"{where}: the outline is no GeoJSON geometry") from None
    if outline.geom_type not in ("Polygon", "MultiPolygon") or not outline.is_valid:
        raise ConfigError(f"{where}: the outline is a valid polygon or multipolygon")
    area = _area(outline)
    if area <= 0:
        raise ConfigError(f"{where}: the outline has no area")
    return Country(code, _text(raw, "en", where), _text(raw, "de", where), continent, outline, area)


@cache
def places() -> Places:
    """The places of this process, read once."""
    return load_places()


def place_terms(bbox: Sequence[float], known: Places | None = None) -> tuple[str, ...]:
    """The place names of the box ``west, south, east, north`` in degrees, English before German, each once."""
    known = places() if known is None else known
    area = box(*bbox)
    in_box: dict[str, float] = {}
    of_continent: dict[str, float] = {}
    in_continent: dict[str, float] = {}
    for country in known.countries:
        inside = _area(country.outline.intersection(area)) if country.outline.intersects(area) else 0.0
        in_box[country.code] = inside / country.area
        if country.continent is not None:
            of_continent[country.continent] = of_continent.get(country.continent, 0.0) + country.area
            in_continent[country.continent] = in_continent.get(country.continent, 0.0) + inside
    continents = [name for name in sorted(of_continent) if in_continent[name] / of_continent[name] >= SHARE]
    if {name for name in of_continent if name != NOT_FOR_GLOBAL} <= set(continents):
        return GLOBAL_TERMS
    terms: list[str] = []
    for country in sorted(known.countries, key=lambda c: c.en):
        if in_box[country.code] >= SHARE:
            terms += [country.en, country.de]
    for name in continents:
        terms += [name, known.continents[name]]
    return tuple(dict.fromkeys(terms))
