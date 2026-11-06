"""ESA WorldCover, direct from its AWS bucket (M5-07, `adr/0023` §6.1, §8.3).

A materializer like :mod:`earthx.adapters.cop_dem_bucket`, on the same terms: the
bucket has no catalogue and no search API, so this module turns its own tile grid
into STAC items, once, for the one-off command in `discovery`. Its `AdapterSpec`
offers `materialize` and nothing else.

One adapter serves both entries. ``source.source_collection_id`` names the state as
the bucket lays it out, ``<version>/<year>`` (``v100/2020``, ``v200/2021``); the files
of a state lie under ``<version>/<year>/map/`` as
``ESA_WorldCover_10m_<year>_<version>_<tile>_Map.tif`` (M5-07 plan §2, measured).

What this module refuses to trust (the lesson of `adr/0009` §11):

* **The grid.** ``esa_worldcover_grid.geojson`` names every 3° tile by its south-west
  corner (``ll_tile``). A name that does not fit, or a polygon that is not the cell its
  name gives, fails the whole run (M5-07 plan F3).
* **That every tile has a file.** The listing of ``<prefix>/map/`` is checked against
  the grid; more than 1 % missing aborts the run, as for the DEM.

Everything goes through ``gateway`` (KLAERUNGEN B8): the grid, the listing, nothing
else. No asset is opened.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException

from earthx.adapters.cop_dem_bucket import COG_MEDIA_TYPE, MAX_NOT_LOADABLE_FRACTION, MaterializeOutcome
from earthx.adapters.errors import NotMaterialized, UnsupportedSource, UpstreamShapeError
from earthx.catalog.registry import DatasetConfig, ItemHolding
from earthx.gateway import Gateway

GRID_PATH = "/esa_worldcover_grid.geojson"

# AWS's own maximum per listing page; three pages cover one state (2651 files, measured 06.11.2026).
LISTING_PAGE_SIZE = 1000

# The edge of one tile of the grid, in degrees (`readme.html` of the bucket: "3x3 degree tiles").
TILE_DEGREES = 3

# Nominal resolution: 1/12 000° per pixel, "10m" in the product's name (`adr/0023` §6.1).
GSD_METRES = 10.0

_STATE_RE = re.compile(r"^(?P<version>v\d{3})/(?P<year>\d{4})$")
_TILE_RE = re.compile(r"^(?P<ns>[NS])(?P<lat>\d{2})(?P<ew>[EW])(?P<lon>\d{3})$")


def _state(config: DatasetConfig) -> tuple[str, str]:
    """``(version, year)`` from ``source_collection_id``; anything else is a registry error."""
    match = _STATE_RE.match(config.source.source_collection_id)
    if match is None:
        raise UnsupportedSource(
            f"{config.dataset_id}: source_collection_id {config.source.source_collection_id!r} is not <version>/<year>"
        )
    return match["version"], match["year"]


def _cell(tile: str) -> tuple[float, float, float, float]:
    """The nominal 3° cell whose south-west corner the tile name gives."""
    match = _TILE_RE.match(tile)
    if match is None:
        raise UpstreamShapeError(f"grid tile name does not match the WorldCover pattern: {tile!r}")
    lat, lon = int(match["lat"]), int(match["lon"])
    south = float(lat if match["ns"] == "N" else -lat)
    west = float(lon if match["ew"] == "E" else -lon)
    if not -90 <= south <= 90 - TILE_DEGREES or not -180 <= west <= 180 - TILE_DEGREES:
        raise UpstreamShapeError(f"grid tile {tile!r} lies outside the globe")
    return (west, south, west + TILE_DEGREES, south + TILE_DEGREES)


def _parse_grid(raw: bytes) -> dict[str, tuple[float, float, float, float]]:
    """Every tile of the grid, mapped to its cell, after checking that its polygon is that cell."""
    try:
        grid = json.loads(raw)
        features = grid["features"]
    except (ValueError, TypeError, KeyError) as error:
        raise UpstreamShapeError(f"the WorldCover grid is no GeoJSON feature collection: {error}") from error
    if not isinstance(features, list) or not features:
        raise UpstreamShapeError("the WorldCover grid has no features")
    tiles: dict[str, tuple[float, float, float, float]] = {}
    for feature in features:
        try:
            tile = feature["properties"]["ll_tile"]
            ring = feature["geometry"]["coordinates"][0]
            xs = [float(x) for x, _y in ring]
            ys = [float(y) for _x, y in ring]
        except (TypeError, KeyError, IndexError, ValueError) as error:
            raise UpstreamShapeError(f"a WorldCover grid feature has no ll_tile or polygon: {error}") from error
        if not isinstance(tile, str):
            raise UpstreamShapeError(f"a WorldCover grid feature names its tile {tile!r}")
        cell = _cell(tile)
        if (min(xs), min(ys), max(xs), max(ys)) != cell:
            raise UpstreamShapeError(f"the polygon of grid tile {tile} is not the cell its name gives")
        if tile in tiles:
            raise UpstreamShapeError(f"grid tile {tile} appears twice")
        tiles[tile] = cell
    return tiles


def _parse_listing_page(raw: bytes) -> tuple[list[str], str | None]:
    """The object keys of one ``ListObjectsV2`` page, and its continuation token."""
    try:
        root = DefusedET.fromstring(raw)
    except (ParseError, DefusedXmlException) as error:
        raise UpstreamShapeError(f"bucket listing is not valid XML: {error}") from error
    keys: list[str] = []
    token: str | None = None
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "Key" and element.text:
            keys.append(element.text)
        elif tag == "NextContinuationToken" and element.text:
            token = element.text
    return keys, token


async def _list_map_keys(config: DatasetConfig, prefix: str, *, gateway: Gateway) -> set[str]:
    """Every key under ``<prefix>/map/``."""
    keys: list[str] = []
    token: str | None = None
    while True:
        params = {"list-type": "2", "prefix": f"{prefix}/map/", "max-keys": str(LISTING_PAGE_SIZE)}
        if token is not None:
            params["continuation-token"] = token
        response = await gateway.get(f"{config.source.endpoint}/", params=params)
        page, token = _parse_listing_page(response.content)
        keys.extend(page)
        if token is None:
            return set(keys)


def _stac_instant(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _item(stem: str, key: str, cell: tuple[float, float, float, float], *, config: DatasetConfig) -> dict[str, Any]:
    """One STAC item for one tile: the map alone (``inputquality`` is not part of M5-07, plan §4.2)."""
    west, south, east, north = cell
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": stem,
        "collection": config.dataset_id,
        "bbox": [west, south, east, north],
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {
            # One map for the whole year, not an acquisition: the period of the entry, the same for every tile.
            "datetime": None,
            "start_datetime": _stac_instant(config.temporal_extent.start),
            "end_datetime": _stac_instant(config.temporal_extent.end),
            "gsd": GSD_METRES,
            "proj:code": "EPSG:4326",
        },
        "assets": {"map": {"href": f"{config.source.endpoint}/{key}", "type": COG_MEDIA_TYPE, "roles": ["data"]}},
        "links": [],
    }


async def materialize_items(
    config: DatasetConfig,
    *,
    gateway: Gateway,
    known_version: str | None,
) -> MaterializeOutcome:
    """Build every item of one WorldCover state, or report "unchanged" against the ETag of the grid."""
    if config.source.item_holding is not ItemHolding.MATERIALIZED:
        raise NotMaterialized(
            f"{config.dataset_id} is not materialized; adapters.materialize_items does not build its items"
        )
    if config.temporal_extent.end is None:
        raise UnsupportedSource(f"{config.dataset_id}: temporal_extent has no end; a WorldCover item needs one")
    version, year = _state(config)

    headers = {"if-none-match": known_version} if known_version else None
    response = await gateway.get(f"{config.source.endpoint}{GRID_PATH}", headers=headers)
    if response.status_code == 304:
        return MaterializeOutcome(
            status="unchanged",
            source_version=known_version or "",
            listed=0,
            in_bucket=0,
            missing=0,
            withheld=0,
            unknown=0,
            items=(),
        )
    new_version = response.headers.get("etag", "")
    if not new_version:
        raise UpstreamShapeError("the WorldCover grid answered without an ETag; a later run could not compare")
    tiles = _parse_grid(response.content)

    prefix = f"{version}/{year}"
    keys = await _list_map_keys(config, prefix, gateway=gateway)
    if not keys:
        raise UpstreamShapeError(f"the bucket lists no file under {prefix}/map/")

    def key_of(tile: str) -> str:
        return f"{prefix}/map/ESA_WorldCover_10m_{year}_{version}_{tile}_Map.tif"

    missing = {tile for tile in tiles if key_of(tile) not in keys}
    unknown = keys - {key_of(tile) for tile in tiles}
    if len(missing) / len(tiles) > MAX_NOT_LOADABLE_FRACTION:
        raise UpstreamShapeError(
            f"{len(missing)} of {len(tiles)} grid tiles have no file under {prefix}/map/ — "
            "over the 1% abort threshold (M5-07 plan §4.2)"
        )

    items = tuple(
        _item(f"ESA_WorldCover_10m_{year}_{version}_{tile}", key_of(tile), cell, config=config)
        for tile, cell in tiles.items()
        if tile not in missing
    )
    return MaterializeOutcome(
        status="loaded",
        source_version=new_version,
        listed=len(tiles),
        in_bucket=len(keys),
        missing=len(missing),
        withheld=0,
        unknown=len(unknown),
        items=items,
    )
