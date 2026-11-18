"""The daily climate grids of MeteoSwiss as items of one day each (M5-11 PR 2, adr/0029 §8a.1 package b).

The source is the archive item of the collection ``ch.meteoschweiz.ogd-surface-derived-grid`` on the STAC API of the
FSDI (``source.endpoint``). It lists one NetCDF-4 file per quantity, grid and year. Only the consolidated annual files
of the archive are read, up to the last completed year (adr/0029 F5, Otto 17.11.2026): names of the form
``ogd-surface-derived-grid-archive.<quantity>_<grid>.swiss.lv95_<start>_<end>.nc`` (plan §10.7); neither ``-last``
nor the preliminary daily files.

The quantities of an entry are the keys of its ``band_units`` (``TabsD``, ``RhiresD`` …, as MeteoSwiss names them,
plan A14). Each file is referenced with :func:`~earthx.discovery.netcdf_refs.reference_file` (5–8 ranged requests, no
data), and every day of every file becomes one asset of the item of that day, with the ``earthx:refs`` of its chunk.
A day a file does not carry is no asset; a day no file carries is no item (plan §10.9).

**The day of an item** (Otto, 18.11.2026, from the product documentation of MeteoSwiss): the files stamp each day at
00:00 UTC. ``RhiresD`` is the sum from 06:00 UTC of that day to 06:00 UTC of the next (ProdDoc_RhiresD); ``TabsD``,
``TminD`` and ``TmaxD`` hold 00:00–24:00 UTC (ProdDoc_TabsD); ``SrelD`` midnight to midnight (ProdDoc_SrelD), in UTC
like every reference time stamp of the open data. ``start_datetime`` is that start, ``end_datetime`` the last second
before the next day starts, ``datetime`` the start.

**The version of a run** is the ETag of the archive item, the selection of the entry (quantities, first and last year)
and a hash over the name, the address, ``file:checksum`` and ``updated`` of every chosen file. A ``304`` on
``If-None-Match`` is "unchanged" after one request; the request is conditional only while the selection is the same, so
a longer period or another quantity is loaded although the archive did not change. A ``200`` whose chosen files hash as
before is "unchanged" too, without reading a file. Otherwise every chosen file is referenced
anew (plan A4: only changed files come with M5-24).

Lives in ``discovery`` and not in ``adapters``: only here may ``h5py`` open a file (``.importlinter``,
``h5py-only-in-discovery``). ``discovery.materialize`` dispatches to it through its own table.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import numpy
from pyproj import Transformer

from earthx.adapters import MaterializeOutcome, NotMaterialized, UnsupportedSource, UpstreamShapeError
from earthx.adapters.cop_dem_bucket import MAX_NOT_LOADABLE_FRACTION
from earthx.catalog.registry import DatasetConfig, ItemHolding
from earthx.discovery.netcdf_refs import FileReferences, UnsupportedLayout, reference_file, step_references
from earthx.gateway import Gateway, host_of
from earthx.gateway.errors import UpstreamError

LOGGER = logging.getLogger("earthx.discovery.meteoswiss_grid")

NETCDF_MEDIA_TYPE = "application/x-netcdf"
#: Both grids are LV95 (the names say ``swiss.lv95``); a file whose grid_mapping names another code fails the run.
CRS = "EPSG:2056"


@dataclass(frozen=True, slots=True)
class Product:
    """What MeteoSwiss says of one quantity: the grid it is delivered on and the hour (UTC) its day starts."""

    grid: str
    day_starts_at: int


PRODUCTS = {
    "TabsD": Product("ch01r", 0),
    "TminD": Product("ch01r", 0),
    "TmaxD": Product("ch01r", 0),
    "SrelD": Product("ch01r", 0),
    "RhiresD": Product("ch01h", 6),
}

ARCHIVE_NAME = re.compile(
    r"^ogd-surface-derived-grid-archive\.(?P<quantity>[a-z0-9]+)_(?P<grid>ch01[rh])\.swiss\.lv95_"
    r"(?P<start>\d{14})_(?P<end>\d{14})\.nc$"
)
DAY = timedelta(days=1)
_LAST_SECOND = DAY - timedelta(seconds=1)
_EDGE_POINTS = 16
_TO_WGS84 = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
_HASH_PREFIX = "sha256:"


@dataclass(frozen=True, slots=True)
class AnnualFile:
    quantity: str
    year: int
    name: str
    href: str


def _products(config: DatasetConfig) -> tuple[list[str], Product]:
    """The quantities of the entry and the product they share; one grid and one day per entry."""
    quantities = list(config.band_units)
    unknown = [quantity for quantity in quantities if quantity not in PRODUCTS]
    if not quantities or unknown:
        raise UnsupportedSource(f"{config.dataset_id}: band_units names no daily MeteoSwiss quantity {unknown or ''}")
    products = {PRODUCTS[quantity] for quantity in quantities}
    if len(products) != 1:
        raise UnsupportedSource(f"{config.dataset_id}: its quantities lie on different grids or days")
    return quantities, products.pop()


def _one_year(start: str, end: str) -> int | None:
    """The year of a file stamped from 1 January to 31 December or to 1 January of the next year, else ``None``."""
    year = int(start[:4])
    if start[4:] != "0101000000":
        return None
    if (end[:4] == start[:4] and end[4:8] == "1231") or end == f"{year + 1}0101000000":
        return year
    return None


def choose_files(
    config: DatasetConfig, assets: dict[str, Any], *, first_year: int, last_year: int
) -> tuple[dict[tuple[str, int], AnnualFile], int, int]:
    """The annual files of the entry's quantities from ``first_year`` to ``last_year``; and the count of withheld
    (other years) and unknown (of the entry's quantity and grid, but not one year on an asset host) files."""
    quantities, product = _products(config)
    by_name = {quantity.lower(): quantity for quantity in quantities}
    chosen: dict[tuple[str, int], AnnualFile] = {}
    withheld = unknown = 0
    for name, asset in assets.items():
        match = ARCHIVE_NAME.match(name.lower())
        if match is None or match["quantity"] not in by_name or match["grid"] != product.grid:
            continue
        quantity = by_name[match["quantity"]]
        year = _one_year(match["start"], match["end"])
        href = asset.get("href") if isinstance(asset, dict) else None
        if year is None or not isinstance(href, str) or not href.startswith("https://") or host_of(href) not in config.source.asset_hosts:
            unknown += 1
            continue
        if not first_year <= year <= last_year:
            withheld += 1
            continue
        if (quantity, year) in chosen:
            raise UpstreamShapeError(f"the archive lists two files of {quantity} for {year}")
        chosen[(quantity, year)] = AnnualFile(quantity, year, name, href)
    return chosen, withheld, unknown


def _digest(chosen: dict[tuple[str, int], AnnualFile], assets: dict[str, Any]) -> str:
    lines = sorted(
        "\t".join((file.name, file.href, str(assets[file.name].get("file:checksum", "")), str(assets[file.name].get("updated", ""))))
        for file in chosen.values()
    )
    return _HASH_PREFIX + hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _split(version: str | None) -> tuple[str | None, str | None, str | None]:
    """(ETag, selection, hash) of a version this module wrote; an older or foreign one is none of them."""
    rest, _, digest = (version or "").rpartition("|")
    etag, _, selection = rest.rpartition("|")
    if not digest.startswith(_HASH_PREFIX) or not selection:
        return None, None, None
    return etag or None, selection, digest


def _unchanged(version: str) -> MaterializeOutcome:
    return MaterializeOutcome(
        status="unchanged", source_version=version, listed=0, in_bucket=0, missing=0, withheld=0, unknown=0, items=()
    )


def grid_footprint(references: FileReferences) -> tuple[list[float], dict[str, Any]]:
    """``bbox`` and ``geometry`` in WGS 84 of the whole grid, its edges densified before they are transformed."""
    a, _, c, _, e, f = references.layout.transform
    rows, columns = references.layout.shape[1], references.layout.shape[2]
    west, east = c, c + a * columns
    south, north = sorted((f, f + e * rows))
    steps = [i / _EDGE_POINTS for i in range(_EDGE_POINTS)]
    ring_xy = (
        [(west + s * (east - west), south) for s in steps]
        + [(east, south + s * (north - south)) for s in steps]
        + [(east - s * (east - west), north) for s in steps]
        + [(west, north - s * (north - south)) for s in steps]
    )
    lons, lats = _TO_WGS84.transform([x for x, _ in ring_xy], [y for _, y in ring_xy])
    ring = [[round(lon, 7), round(lat, 7)] for lon, lat in zip(lons, lats, strict=True)]
    ring.append(ring[0])
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return [min(xs), min(ys), max(xs), max(ys)], {"type": "Polygon", "coordinates": [ring]}


def _check_file(file: AnnualFile, references: FileReferences, grid: FileReferences | None) -> list[date]:
    """The days of one file, after the checks that make its references safe to write into items."""
    layout = references.layout
    what = f"the file of {file.quantity} for {file.year}"
    if layout.crs != CRS:
        raise UpstreamShapeError(f"{what} lies in {layout.crs}, not {CRS}")
    if grid is not None and (layout.shape[1:] != grid.layout.shape[1:] or layout.transform != grid.layout.transform):
        raise UpstreamShapeError(f"{what} lies on another grid than the files before it")
    if references.last_modified is None:
        raise UpstreamShapeError(f"{what} names no Last-Modified, which the items carry as updated")
    days: list[date] = []
    for instant in references.times:
        if instant.timetz() != time(0, tzinfo=UTC) or instant.year != file.year:
            raise UpstreamShapeError(f"{what} holds a time step that is not midnight UTC of a day of {file.year}")
        days.append(instant.date())
    if len(set(days)) != len(days):
        raise UpstreamShapeError(f"{what} holds a day twice")
    return days


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def day_item(
    config: DatasetConfig,
    day: date,
    steps: dict[str, tuple[AnnualFile, FileReferences, int]],
    *,
    product: Product,
    footprint: tuple[list[float], dict[str, Any]],
) -> dict[str, Any]:
    """The item of one day: an asset per quantity the files carry that day."""
    start = datetime.combine(day, time(product.day_starts_at, tzinfo=UTC))
    bbox, geometry = footprint
    assets: dict[str, Any] = {}
    updated: list[datetime] = []
    for quantity in sorted(steps):
        file, references, step = steps[quantity]
        assert references.last_modified is not None
        updated.append(parsedate_to_datetime(references.last_modified))
        assets[quantity] = {
            "href": file.href,
            "type": NETCDF_MEDIA_TYPE,
            "roles": ["data"],
            "earthx:refs": step_references(references, step),
            "raster:bands": [
                {
                    "data_type": numpy.dtype(references.layout.dtype).name,
                    "nodata": "nan",
                    "unit": config.band_units[quantity],
                }
            ],
        }
    gsd = abs(next(iter(steps.values()))[1].layout.transform[0])
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": f"{config.dataset_id}-{day.strftime('%Y%m%d')}",
        "collection": config.dataset_id,
        "bbox": bbox,
        "geometry": geometry,
        "properties": {
            "datetime": _instant(start),
            "start_datetime": _instant(start),
            "end_datetime": _instant(start + _LAST_SECOND),
            "updated": _instant(max(updated)),
            "gsd": gsd,
            "proj:code": CRS,
        },
        "assets": assets,
        "links": [],
    }


def last_year_of(config: DatasetConfig) -> int:
    """The year the last day of ``temporal_extent`` starts in: the newest annual file the entry loads."""
    assert config.temporal_extent.end is not None
    return (config.temporal_extent.end - _LAST_SECOND).astimezone(UTC).year


def _inside(bbox: list[float], extent: tuple[float, float, float, float]) -> bool:
    west, south, east, north = extent
    return west <= bbox[0] and south <= bbox[1] and bbox[2] <= east and bbox[3] <= north


async def materialize_items(
    config: DatasetConfig,
    *,
    gateway: Gateway,
    known_version: str | None,
    expected_items: int | None = None,
    today: date | None = None,
) -> MaterializeOutcome:
    """An item for every day of the chosen annual files, or "unchanged" against the archive item and the chosen files."""
    if config.source.item_holding is not ItemHolding.MATERIALIZED:
        raise NotMaterialized(f"{config.dataset_id} is not materialized; its items are not built here")
    quantities, product = _products(config)
    first, last = config.temporal_extent.start, config.temporal_extent.end
    if first is None or last is None:
        raise UnsupportedSource(f"{config.dataset_id}: temporal_extent is closed for the years to load")
    last_year = min(last_year_of(config), (today or datetime.now(UTC).date()).year - 1)

    # What the entry asks for: a 304 says only that the archive is as it was, not that the entry still wants the same.
    first_year = first.astimezone(UTC).year
    selection = f"{','.join(sorted(quantities))}:{first_year}-{last_year}"
    known_etag, known_selection, known_digest = _split(known_version)
    headers = {"if-none-match": known_etag} if known_etag and known_selection == selection else None
    response = await gateway.get(config.source.endpoint, headers=headers)
    if response.status_code == 304 and known_version:
        return _unchanged(known_version)
    try:
        assets = response.json().get("assets")
    except (ValueError, AttributeError):
        assets = None
    if response.status_code != 200 or not isinstance(assets, dict):
        raise UpstreamShapeError("the archive item is no STAC item with assets")
    chosen, withheld, unknown = choose_files(config, assets, first_year=first_year, last_year=last_year)
    if not chosen:
        raise UpstreamShapeError(f"the archive lists no annual file of {', '.join(quantities)}")
    digest = _digest(chosen, assets)
    etag = response.headers.get("etag")
    version = f"{etag or ''}|{selection}|{digest}"
    if digest == known_digest:
        return _unchanged(version)

    by_day: dict[date, dict[str, tuple[AnnualFile, FileReferences, int]]] = defaultdict(dict)
    grid: FileReferences | None = None
    missing = 0
    for count, key in enumerate(sorted(chosen, key=lambda k: (k[1], k[0])), start=1):
        file = chosen[key]
        try:
            references = await reference_file(gateway, file.href)
        except UpstreamError as error:
            if error.status_code not in (404, 410):
                raise
            missing += 1
            continue
        except UnsupportedLayout as error:
            raise UpstreamShapeError(f"the file of {file.quantity} for {file.year}: {error}") from None
        days = _check_file(file, references, grid)
        grid = grid or references
        for step, day in enumerate(days):
            by_day[day][file.quantity] = (file, references, step)
        LOGGER.info(f"referenced {count} of {len(chosen)} annual files", extra={"dataset_id": config.dataset_id})
    if missing / len(chosen) > MAX_NOT_LOADABLE_FRACTION:
        raise UpstreamShapeError(f"{missing} of {len(chosen)} annual files are gone — over the 1% abort threshold")
    assert grid is not None

    footprint = grid_footprint(grid)
    if not _inside(footprint[0], config.spatial_extent.bbox):
        raise UnsupportedSource(
            f"{config.dataset_id}: the grid {json.dumps(footprint[0])} reaches beyond spatial_extent; follow the entry up"
        )
    items = tuple(day_item(config, day, by_day[day], product=product, footprint=footprint) for day in sorted(by_day))
    return MaterializeOutcome(
        status="loaded",
        source_version=version,
        listed=len(chosen),
        in_bucket=len(chosen) - missing,
        missing=missing,
        withheld=withheld,
        unknown=unknown,
        items=items,
    )
