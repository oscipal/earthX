"""BEV ALS-DGM 1 m from the INSPIRE ATOM service of the BEV (M5-09, `adr/0023` §4.2, §8.3).

A materializer like :mod:`earthx.adapters.esa_worldcover_bucket`: the source has no catalogue API, so this module turns
its ATOM feeds into STAC items, once, for the one-off command in `discovery`. Its `AdapterSpec` offers `materialize`
and nothing else. A general ATOM adapter waits for the next ATOM source (`adr/0011` F6) or the harvest (M5-21).

The service feed lists one entry per model, tile and reference date ("Stichtag"), each pointing to a dataset feed that
holds exactly one file (Otto's probe runs, M5-09 plan §2.4). ``source.source_collection_id`` names the model as the
titles do (``ALS DTM``). Only the newest reference date is loaded (M5-09 F1); every date is a full state of Austria.

What this module refuses to trust:

* **The titles.** An entry that is neither a tile of the known form nor one of the series entries counts as unknown.
* **The polygon of the feed.** It lies up to 0.07° off the 50 km cell the tile name gives (plan §2.4); the footprint
  is that cell, transformed from EPSG:3035 (Otto, 16.11.2026).
* **The file link.** One ``image/tiff`` link per dataset feed, on an asset host, under the path of its model, date and
  tile; anything else makes the tile not loadable. More than 1 % not loadable aborts the run, as for DEM and WorldCover.
* **A newer date than the entry.** A newest date outside the entry's period fails the run: the entry is followed up in
  review first, so Git stays the one truth for what is loaded (plan A2).

The feeds carry neither ETag nor Last-Modified (plan §2.4), so the version of a run is a hash of what the service feed
says about the tiles of the chosen date. An equal hash is "unchanged" after one request. Everything goes through
``gateway`` (KLAERUNGEN B8); no file is opened.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timezone
from typing import Any
from xml.etree.ElementTree import Element, ParseError

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException
from pyproj import Transformer

from earthx.adapters.cop_dem_bucket import COG_MEDIA_TYPE, MAX_NOT_LOADABLE_FRACTION, MaterializeOutcome
from earthx.adapters.errors import NotMaterialized, UnsupportedSource, UpstreamShapeError
from earthx.catalog.registry import DatasetConfig, ItemHolding
from earthx.gateway import Gateway, host_of
from earthx.gateway.errors import UpstreamError

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "inspire_dls": "http://inspire.ec.europa.eu/schemas/inspire_dls/1.0",
}

#: The one asset of an item, as the entry's ``default_render`` and ``band_units`` name it.
ASSET_KEY = "dtm"
#: The edge of one tile of the INSPIRE grid the names give, in metres of EPSG:3035.
CELL_METRES = 50_000
#: Nominal resolution of the files (all 55 headers, plan §2.4).
GSD_METRES = 1.0
CRS = "EPSG:3035"
#: Points per edge of a cell before it is transformed, so the curved edges in WGS 84 stay inside the footprint's error.
EDGE_POINTS = 16

_MODEL = re.compile(r"^ALS (?P<model>DTM|DSM)$")
_TILE_TITLE = re.compile(
    r"^ALS (?P<model>DTM|DSM) (?P<tile>CRS3035RES50000mN(?P<north>\d{7})E(?P<east>\d{7})) Höhenraster 1m Stichtag "
    r"(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})$"
)
_TILE = re.compile(r"^CRS3035RES50000mN(?P<north>\d{7})E(?P<east>\d{7})$")
_SERIES_TITLE = re.compile(r"^Serie ALS (DTM|DSM) Höhenraster 1m Stichtag \d{2}\.\d{2}\.\d{4}$")
# The whole address of a file: https, no port, query or fragment, the path of its model, date and tile (plan §2.4).
_FILE_URL = re.compile(
    r"^https://[A-Za-z0-9.-]+/download/ALS/(?P<model>DTM|DSM)/(?P<date>\d{8})/"
    r"ALS_(?P=model)_(?P<tile>CRS3035RES50000mN\d{7}E\d{7})\.tif$"
)
_DOI = re.compile(
    r"^https://doi\.org/(?P<doi>10\.\d{4,9}/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"
)

_TO_WGS84 = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)


def _model(config: DatasetConfig) -> str:
    """``DTM`` or ``DSM`` from ``source_collection_id``; anything else is a registry error."""
    match = _MODEL.match(config.source.source_collection_id)
    if match is None:
        raise UnsupportedSource(
            f"{config.dataset_id}: source_collection_id {config.source.source_collection_id!r} is not 'ALS DTM' or "
            "'ALS DSM'"
        )
    return match["model"]


def _parse(raw: bytes, what: str) -> Element:
    try:
        return DefusedET.fromstring(raw)
    except (ParseError, DefusedXmlException) as error:
        raise UpstreamShapeError(f"the {what} is not valid XML: {error}") from error


def _link(entry: Element, media_type: str) -> list[str]:
    """The ``href`` of every alternate link of this media type."""
    return [
        link.get("href", "")
        for link in entry.findall("atom:link", NS)
        if link.get("rel", "alternate") == "alternate" and link.get("type", "") == media_type
    ]


def _text(entry: Element, path: str) -> str:
    return (entry.findtext(path, "", NS) or "").strip()


def cell_footprint(north: int, east: int) -> tuple[list[float], dict[str, Any]]:
    """``bbox`` and ``geometry`` in WGS 84 of the cell whose lower left corner the tile name gives."""
    steps = [i * CELL_METRES / EDGE_POINTS for i in range(EDGE_POINTS)]
    ring_xy = (
        [(east + s, north) for s in steps]
        + [(east + CELL_METRES, north + s) for s in steps]
        + [(east + CELL_METRES - s, north + CELL_METRES) for s in steps]
        + [(east, north + CELL_METRES - s) for s in steps]
    )
    lons, lats = _TO_WGS84.transform([x for x, _ in ring_xy], [y for _, y in ring_xy])
    ring = [[round(lon, 7), round(lat, 7)] for lon, lat in zip(lons, lats, strict=True)]
    ring.append(ring[0])
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return [min(xs), min(ys), max(xs), max(ys)], {"type": "Polygon", "coordinates": [ring]}


def _version(tiles: dict[str, tuple[date, Element]]) -> str:
    """A hash of what the service feed says about the chosen tiles: name, date, ``updated``, feed link, DOI."""
    lines = sorted(
        "\t".join(
            (
                tile,
                day.isoformat(),
                _text(entry, "atom:updated"),
                ",".join(_link(entry, "application/atom+xml")),
                _text(entry, "inspire_dls:spatial_dataset_identifier_code"),
            )
        )
        for tile, (day, entry) in tiles.items()
    )
    return "sha256:" + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _inside(bbox: list[float], extent: tuple[float, float, float, float]) -> bool:
    west, south, east, north = extent
    centre_x, centre_y = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return west <= centre_x <= east and south <= centre_y <= north


def tile_item(config: DatasetConfig, *, tile: str, day: date, href: str, doi: str) -> dict[str, Any]:
    """The STAC item of one tile of one reference date, as a run writes it."""
    match = _TILE.match(tile)
    if match is None:
        raise UpstreamShapeError(f"tile name {tile!r} is not of the 50 km grid in EPSG:3035")
    bbox, geometry = cell_footprint(int(match["north"]), int(match["east"]))
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": f"ALS_{_model(config)}_{day.strftime('%Y%m%d')}_{tile}",
        "collection": config.dataset_id,
        "bbox": bbox,
        "geometry": geometry,
        "properties": {
            # The reference date: the state of the data on that day, not the day of a survey (plan §2.1).
            "datetime": f"{day.isoformat()}T00:00:00Z",
            "gsd": GSD_METRES,
            "proj:code": CRS,
            "sci:doi": doi,
        },
        "assets": {ASSET_KEY: {"href": href, "type": COG_MEDIA_TYPE, "roles": ["data"]}},
        "links": [],
    }


def tiles_by_date(raw: bytes, model: str) -> tuple[dict[date, dict[str, Element]], int]:
    """The service feed's entries of ``model``, by reference date and tile, and the count of entries of unknown form.

    Series entries and entries of the other model are passed over; a title of another form, or a date that is no day,
    counts as unknown. A tile listed twice for one date, or no tile of the model at all, fails the run.
    """
    service = _parse(raw, "service feed")
    by_date: dict[date, dict[str, Element]] = {}
    unknown = 0
    for entry in service.findall("atom:entry", NS):
        title = _text(entry, "atom:title")
        match = _TILE_TITLE.match(title)
        if match is None:
            if _SERIES_TITLE.match(title) is None:
                unknown += 1
            continue
        if match["model"] != model:
            continue
        try:
            day = date(int(match["year"]), int(match["month"]), int(match["day"]))
        except ValueError:
            unknown += 1
            continue
        tiles = by_date.setdefault(day, {})
        if match["tile"] in tiles:
            raise UpstreamShapeError(f"the service feed lists tile {match['tile']} of {day} twice")
        tiles[match["tile"]] = entry
    if not by_date:
        raise UpstreamShapeError(f"the service feed lists no tile of ALS {model}")
    return by_date, unknown


def dataset_feed_of(entry: Element) -> str | None:
    """The one dataset feed a tile's entry links, or ``None``."""
    feeds = _link(entry, "application/atom+xml")
    return feeds[0] if len(feeds) == 1 else None


def doi_of(entry: Element) -> str | None:
    """The DOI of a tile, from the identifier of its entry (``https://doi.org/10.48677/<uuid>``), or ``None``."""
    match = _DOI.match(_text(entry, "inspire_dls:spatial_dataset_identifier_code"))
    return match["doi"] if match else None


def file_of(raw: bytes, *, model: str, tile: str, day: date, asset_hosts: tuple[str, ...]) -> str | None:
    """The one file of a dataset feed, or ``None`` if the feed does not hold exactly the file it should."""
    entries = _parse(raw, "dataset feed").findall("atom:entry", NS)
    if len(entries) != 1:
        return None
    hrefs = _link(entries[0], "image/tiff")
    if len(hrefs) != 1:
        return None
    match = _FILE_URL.match(hrefs[0])
    if (
        match is None
        or host_of(hrefs[0]) not in asset_hosts
        or match["model"] != model
        or match["tile"] != tile
        or match["date"] != day.strftime("%Y%m%d")
    ):
        return None
    return hrefs[0]


async def materialize_items(
    config: DatasetConfig,
    *,
    gateway: Gateway,
    known_version: str | None,
    expected_items: int | None = None,
) -> MaterializeOutcome:
    """Build an item for every tile of the newest reference date, or report "unchanged" against the hash."""
    if config.source.item_holding is not ItemHolding.MATERIALIZED:
        raise NotMaterialized(
            f"{config.dataset_id} is not materialized; adapters.materialize_items does not build its items"
        )
    model = _model(config)
    if config.temporal_extent.end is None:
        raise UnsupportedSource(f"{config.dataset_id}: temporal_extent has no end; the newest date is checked there")

    by_date, unknown = tiles_by_date((await gateway.get(config.source.endpoint)).content, model)

    newest = max(by_date)
    start, end = config.temporal_extent.start, config.temporal_extent.end
    if not start.astimezone(timezone.utc).date() <= newest <= end.astimezone(timezone.utc).date():
        raise UnsupportedSource(
            f"{config.dataset_id}: the newest reference date {newest} lies outside temporal_extent; follow the entry "
            "up before loading (M5-09 plan A2)"
        )
    chosen = by_date[newest]
    withheld = sum(len(tiles) for day, tiles in by_date.items() if day != newest)
    version = _version({tile: (newest, entry) for tile, entry in chosen.items()})
    if version == known_version:
        return MaterializeOutcome(
            status="unchanged",
            source_version=version,
            listed=0,
            in_bucket=0,
            missing=0,
            withheld=0,
            unknown=0,
            items=(),
        )

    items: list[dict[str, Any]] = []
    missing = 0
    for tile, entry in sorted(chosen.items()):
        doi = doi_of(entry)
        feed = dataset_feed_of(entry)
        if doi is None or feed is None:
            unknown += 1
            continue
        try:
            response = await gateway.get(feed)
        except UpstreamError as error:
            if error.status_code not in (404, 410):
                raise
            missing += 1
            continue
        href = file_of(
            response.content,
            model=model,
            tile=tile,
            day=newest,
            asset_hosts=config.source.asset_hosts,
        )
        if href is None:
            unknown += 1
            continue
        item = tile_item(config, tile=tile, day=newest, href=href, doi=doi)
        if not _inside(item["bbox"], config.spatial_extent.bbox):
            unknown += 1
            continue
        items.append(item)

    not_loadable = len(chosen) - len(items)
    if not_loadable / len(chosen) > MAX_NOT_LOADABLE_FRACTION:
        raise UpstreamShapeError(
            f"{not_loadable} of {len(chosen)} tiles of {newest} are not loadable — over the 1% abort threshold "
            "(M5-09 plan §4.1)"
        )
    return MaterializeOutcome(
        status="loaded",
        source_version=version,
        listed=len(chosen),
        in_bucket=len(items),
        missing=missing,
        withheld=withheld,
        unknown=unknown,
        items=tuple(items),
    )
