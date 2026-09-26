"""Copernicus DEM GLO-30, direct from its AWS bucket (M3-11b, `adr/0009`).

Unlike every other adapter in this package, this one does not *search*: the
bucket has no catalogue and no search API (`adr/0009` §3.1, §5). What it has is
`tileList.txt` (one tile name per line) and a fixed naming scheme that gives a
tile's location without opening it. This module turns that into STAC items,
once, for the one-off command in `discovery` (M3-11b plan §3.1) — it is a
*materializer*, not a search adapter, and stays out of `adapters._ADAPTERS`
(the search/get-item dispatch table) for exactly that reason; `adapters.
materialize_items` is the only way in.

Three things this module refuses to trust, all measured in the M3-11b plan
step (`docs/plans/m3-11b-dem-adapter.md` §2):

* **The list itself.** A line that does not fit the tile naming pattern fails
  the whole run rather than being skipped (`adr/0009` §11 — "Quell-Listen
  lügen", the lesson `last.txt` at Hansen GFC already taught).
* **That every listed tile actually has a directory.** The bucket's own
  prefix listing is checked against the list before anything is loaded (§3.2).
* **That every listed tile is meant to be public.** `blacklist.txt` — the
  bucket's own withdrawal list — is checked too, so a tile Copernicus has
  since withdrawn is not materialized just because `tileList.txt` has not
  caught up.

Everything here goes through ``gateway`` (KLAERUNGEN B8): two small files, a
paginated bucket listing, nothing else. No asset is ever opened — the item this
module builds only *names* the DEM COG by its href; reading it is `readers`'
job, unchanged (M3-11b plan §6, "Nicht anfassen: readers").
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException

from earthx.adapters.federated_search import UnsupportedSource, UpstreamShapeError
from earthx.catalog.datasets import DEM_ACQUISITION_END, DEM_ACQUISITION_START
from earthx.catalog.registry import DatasetConfig, ItemHolding
from earthx.gateway import Gateway

# The two small files at the bucket root (`adr/0009` §7.3, M3-11b plan §2.1, §2.2).
TILE_LIST_PATH = "/tileList.txt"
BLACKLIST_PATH = "/blacklist.txt"

# How many prefixes one bucket listing page asks for. 27 pages cover the whole
# bucket today (M3-11b plan §2.2); the number itself is AWS's own maximum.
LISTING_PAGE_SIZE = 1000

# STAC's own media type for a Cloud Optimized GeoTIFF, the same string every
# COG asset in this repo's fixtures already carries.
COG_MEDIA_TYPE = "image/tiff; application=geotiff; profile=cloud-optimized"

# Above this share of the list not being loadable (missing from the bucket, or
# withheld), the run aborts without writing anything (M3-11b plan §3.2, F2):
# past this point it is more likely that *this run* is broken (a bad listing, a
# network hiccup) than that a twenty-fifth of the DEM vanished overnight.
MAX_NOT_LOADABLE_FRACTION = 0.01

# `Copernicus_DSM_COG_10_N46_00_E010_00_DEM` — the exact shape every line of
# `tileList.txt` has to have (measured against all 26,450 lines, M3-11b plan
# §2.1). A line that does not match this is a naming change we have not seen
# and must not silently guess the meaning of.
_TILE_NAME_RE = re.compile(r"^Copernicus_DSM_COG_10_(?P<ns>[NS])(?P<lat>\d{2})_00_(?P<ew>[EW])(?P<lon>\d{3})_00_DEM$")

# The same coordinate signature, found *inside* a name that may carry a
# different prefix or suffix — `blacklist.txt` names its tiles
# `Copernicus_DSM_10_<coord>_DEM.tif`, one word and one extension short of
# `tileList.txt`'s own `Copernicus_DSM_COG_10_<coord>_DEM` (M3-11b plan §2.2).
# Matching just the coordinate lets the three sources (list, bucket listing,
# blacklist) agree on what tile they mean without agreeing on how to spell it.
_COORD_RE = re.compile(r"[NS]\d{2}_00_[EW]\d{3}_00")


class NotMaterialized(UnsupportedSource):
    """This dataset's items are not materialized here (M3-11a K-05)."""


@dataclass(frozen=True, slots=True)
class MaterializeOutcome:
    """What one materialize run found, and the items it is safe to write.

    ``status`` is ``"unchanged"`` when a conditional request against
    ``known_version`` came back ``304`` — the bucket answered without a body,
    so every count below is ``0`` and ``items`` is empty; there was nothing new
    to reconcile or build. Otherwise ``"loaded"``.
    """

    status: str
    source_version: str
    listed: int
    in_bucket: int
    missing: int
    withheld: int
    unknown: int
    items: tuple[dict[str, Any], ...]


def _bbox_from_coord(ns: str, lat: str, ew: str, lon: str) -> tuple[float, float, float, float]:
    """The nominal 1x1-degree cell a tile name's south-west corner names.

    `M3-11b` F3: the *nominal* cell, not the file's own bounds (which overhang
    it by half a pixel on two sides, pixel-is-point — measured, plan §2.3). The
    Coverage of M3-11c wants tiles that tile without a gap or an overlap; the
    real reader reads the real bounds off the file regardless of what an item
    claims.
    """
    lat_value, lon_value = int(lat), int(lon)
    if not 0 <= lat_value <= 90:
        raise UpstreamShapeError(f"tile latitude {ns}{lat} is out of range")
    if not 0 <= lon_value <= 180:
        raise UpstreamShapeError(f"tile longitude {ew}{lon} is out of range")
    south = float(lat_value if ns == "N" else -lat_value)
    west = float(lon_value if ew == "E" else -lon_value)
    return (west, south, west + 1.0, south + 1.0)


def _parse_tile_list(raw: bytes) -> dict[str, tuple[str, tuple[float, float, float, float]]]:
    """Every tile name in ``tileList.txt``, mapped to its coordinate key and bbox.

    A trailing blank line is ignored (`tileList.txt` itself ends CRLF, measured);
    any other line that does not fit :data:`_TILE_NAME_RE` fails the whole run —
    a naming change we have not seen is not one line to skip, it means the list
    no longer means what this adapter was built to read (`adr/0009` §11).
    """
    tiles: dict[str, tuple[str, tuple[float, float, float, float]]] = {}
    for line in raw.decode("utf-8").splitlines():
        name = line.strip()
        if not name:
            continue
        match = _TILE_NAME_RE.match(name)
        if match is None:
            raise UpstreamShapeError(f"tileList.txt line does not match the DEM tile name pattern: {name!r}")
        bbox = _bbox_from_coord(**match.groupdict())
        tiles[name] = (match.group(0)[len("Copernicus_DSM_COG_10_") : -len("_DEM")], bbox)
    return tiles


def _coord_keys(names: Iterable[str]) -> set[str]:
    """The coordinate signature of every name that carries one (blacklist entries,
    bucket prefixes) — names with a different prefix or extension still match."""
    keys: set[str] = set()
    for name in names:
        match = _COORD_RE.search(name)
        if match is not None:
            keys.add(match.group(0))
    return keys


def _local_tag(tag: str) -> str:
    """An XML tag without its namespace URI (`{ns}Tag` -> `Tag`)."""
    return tag.rsplit("}", 1)[-1]


def _parse_listing_page(raw: bytes) -> tuple[list[str], str | None]:
    """The common prefixes of one ``ListObjectsV2`` page, and its continuation token.

    Read by local tag name rather than a hardcoded namespace URI, so a future S3
    XML schema revision does not silently stop matching (there is exactly one
    `Prefix`-tagged element per real tile prefix under `CommonPrefixes`; the
    request's own top-level `<Prefix/>` echo is empty and filtered out below).
    """
    try:
        root = DefusedET.fromstring(raw)
    except (ParseError, DefusedXmlException) as error:
        raise UpstreamShapeError(f"bucket listing is not valid XML: {error}") from error
    prefixes: list[str] = []
    next_token: str | None = None
    for element in root.iter():
        tag = _local_tag(element.tag)
        if tag == "Prefix" and element.text:
            prefixes.append(element.text.rstrip("/"))
        elif tag == "NextContinuationToken" and element.text:
            next_token = element.text
    return prefixes, next_token


async def _list_bucket_prefixes(config: DatasetConfig, *, gateway: Gateway) -> set[str]:
    """Every top-level prefix of the bucket, as coordinate keys (M3-11b plan §2.2)."""
    prefixes: list[str] = []
    token: str | None = None
    root = f"{config.source.endpoint}/"
    while True:
        params = {"list-type": "2", "delimiter": "/", "max-keys": str(LISTING_PAGE_SIZE)}
        if token is not None:
            params["continuation-token"] = token
        response = await gateway.get(root, params=params)
        page_prefixes, token = _parse_listing_page(response.content)
        prefixes.extend(page_prefixes)
        if token is None:
            break
    return _coord_keys(prefixes)


def _stac_instant(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _item(name: str, bbox: tuple[float, float, float, float], *, config: DatasetConfig) -> dict[str, Any]:
    """One STAC item for one DEM tile. No asset but ``data`` — the source's own
    preview is a TIFF (M3-11b plan §2.2), which a browser cannot show; a
    quicklook stand-in for the DEM is M3-12's job, not this adapter's."""
    west, south, east, north = bbox
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    href = f"{config.source.endpoint}/{name}/{name}.tif"
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": name,
        "collection": config.dataset_id,
        "bbox": [west, south, east, north],
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {
            # F1: no single acquisition instant exists for the whole product
            # (`adr/0009` §10.1) — a period, the same for every tile, belonging
            # to the *product*, not a measurement of this one tile.
            "datetime": None,
            "start_datetime": _stac_instant(DEM_ACQUISITION_START),
            "end_datetime": _stac_instant(DEM_ACQUISITION_END),
            # Nominal resolution (`adr/0009` §3.1); the download size estimate
            # (M3-18) falls back to a worst case without it.
            "gsd": 30.0,
            "proj:code": "EPSG:4326",
        },
        "assets": {
            "data": {
                "href": href,
                "type": COG_MEDIA_TYPE,
                "roles": ["data"],
            }
        },
        "links": [],
    }


async def materialize_items(
    config: DatasetConfig,
    *,
    gateway: Gateway,
    known_version: str | None,
) -> MaterializeOutcome:
    """Build every DEM item this bucket currently offers, or report "unchanged".

    Refuses a dataset this module does not materialize (a caller error, the
    same way :func:`earthx.adapters.get_item` refuses a materialized one —
    M3-11a §3.5's safety net, mirrored here for the other direction).
    """
    if config.source.item_holding is not ItemHolding.MATERIALIZED:
        raise NotMaterialized(
            f"{config.dataset_id} is not materialized; adapters.materialize_items does not build its items"
        )

    tile_list_url = f"{config.source.endpoint}{TILE_LIST_PATH}"
    headers = {"if-none-match": known_version} if known_version else None
    response = await gateway.get(tile_list_url, headers=headers)
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
        raise UpstreamShapeError("tileList.txt answered without an ETag; a materialize run cannot be resumed later")

    tiles = _parse_tile_list(response.content)

    blacklist_url = f"{config.source.endpoint}{BLACKLIST_PATH}"
    blacklist_response = await gateway.get(blacklist_url)
    withheld_coords = _coord_keys(blacklist_response.content.decode("utf-8").splitlines())

    bucket_coords = await _list_bucket_prefixes(config, gateway=gateway)
    if not bucket_coords:
        raise UpstreamShapeError("the bucket listing came back with no prefixes at all")

    listed_coords = {coord for coord, _bbox in tiles.values()}
    withheld = listed_coords & withheld_coords
    missing = listed_coords - bucket_coords - withheld
    unknown = bucket_coords - listed_coords

    not_loadable = len(missing) + len(withheld)
    if listed_coords and not_loadable / len(listed_coords) > MAX_NOT_LOADABLE_FRACTION:
        raise UpstreamShapeError(
            f"{not_loadable} of {len(listed_coords)} listed tiles are not loadable "
            f"({len(missing)} missing from the bucket, {len(withheld)} withheld) — "
            "over the 1% abort threshold (M3-11b plan §3.2)"
        )

    items = tuple(
        _item(name, bbox, config=config)
        for name, (coord, bbox) in tiles.items()
        if coord not in withheld and coord not in missing
    )

    return MaterializeOutcome(
        status="loaded",
        source_version=new_version,
        listed=len(listed_coords),
        in_bucket=len(bucket_coords),
        missing=len(missing),
        withheld=len(withheld),
        unknown=len(unknown),
        items=items,
    )
