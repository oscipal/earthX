"""The daily climate grids of MeteoSwiss as items of one day each (M5-11 PR 2, M5-58 PR 2; adr/0029 §8a.1, adr/0038).

The source is the item list of the collection ``ch.meteoschweiz.ogd-surface-derived-grid`` on the STAC API of the FSDI
(``source.endpoint``). Three kinds of its NetCDF-4 files hold days, one file per quantity and grid each (M5-58 plan
§11.2), all named ``ogd-surface-derived-grid<kind>.<quantity>_<grid>.swiss.lv95_<start>_<end>.nc``:

- ``-archive`` in the item ``CH archive``: one year, consolidated, **final**; re-processed once in February;
- ``-last`` in the items ``CH at MM.YYYY``: the days of one month, consolidated, **final**; overwritten on the 26th;
- no kind in the items ``CH at DD.MM.YYYY``: one day, preliminary, **provisional**.

A file is a **unit**, a source item a **group** (adr/0038 §3.3); :mod:`earthx.discovery.materialize_units` decides
what changed and which file an asset of a day carries (the higher state, then the younger file). The quantities of an
entry are the keys of its ``band_units``; archive files count from the first year of ``temporal_extent``.

**One request when nothing changed** (plan §11.4): the list answers without ETag or Last-Modified, so the SHA-256 of
its pages is the validator of the group "list"; the same hash ends the run there. Otherwise each source item is
judged by the SHA-256 of its JSON, and a file of a changed item by ``file:checksum`` from the list: no request for a
file that did not change. The selection of the entry (quantities, first year) is part of every validator, so another
selection lists everything again.

**Precipitation while provisional** is the product ``RprelimD`` at the source and the asset ``RhiresD`` here, with
``earthx:source_product: RprelimD`` (M5-58 F4): band math, look and download stay the same over all days.

Each file is referenced with :func:`~earthx.discovery.netcdf_refs.reference_file` (5–8 ranged requests, no data);
every day of it gives one asset to the item of that day, with the ``earthx:refs`` of its chunk, the file's
Last-Modified as ``updated`` and the ``expires`` of its source item.

**The day of an item** (Otto, 18./19.11.2026, from the product documentation of MeteoSwiss): the files stamp each day
at 00:00 UTC. ``RhiresD`` and ``RprelimD`` are the sum from 06:00 UTC of that day to 06:00 UTC of the next
(ProdDoc_RhiresD, ProdDoc_RprelimD); ``TabsD``, ``TminD`` and ``TmaxD`` hold 00:00–24:00 UTC (ProdDoc_TabsD),
``SrelD`` midnight to midnight (ProdDoc_SrelD), provisional or not (M5-58 A16). ``start_datetime`` is that start,
``end_datetime`` the last second before the next day starts, ``datetime`` the start.

Lives in ``discovery`` and not in ``adapters``: only here may ``h5py`` open a file (``.importlinter``,
``h5py-only-in-discovery``). ``discovery.materialize`` dispatches to it through its own table.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import numpy
from pyproj import Transformer

from earthx.adapters import UnsupportedSource, UpstreamShapeError
from earthx.catalog.registry import DatasetConfig, ItemHolding, ItemState
from earthx.catalog.source_units import BuiltUnit, Contribution, SourceUnit, UnitListing, Validators
from earthx.discovery.netcdf_refs import FileReferences, UnsupportedLayout, reference_file, step_references
from earthx.gateway import Gateway, host_of

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

FILE_NAME = re.compile(
    r"^ogd-surface-derived-grid(?P<kind>-archive|-last|)\.(?P<quantity>[a-z0-9]+)_(?P<grid>ch01[rh])\.swiss\.lv95_"
    r"(?P<start>\d{14})_(?P<end>\d{14})\.nc$"
)
#: The state of each kind of file (M5-58 plan §11.2): only the day items are preliminary.
STATES = {"-archive": ItemState.FINAL, "-last": ItemState.FINAL, "": ItemState.PROVISIONAL}
_SPANS = {"-archive": "annual", "-last": "monthly", "": "daily"}
#: A product the source names otherwise while it is provisional, and the band it is here (M5-58 F4).
PROVISIONAL_PRODUCTS = {"RprelimD": "RhiresD"}
#: The group of the whole list, beside the source items; no item id has this form.
LIST_GROUP = "(item list)"
_PAGE_SIZE = 100
_MAX_PAGES = 20
DAY = timedelta(days=1)
_LAST_SECOND = DAY - timedelta(seconds=1)
_EDGE_POINTS = 16
_TO_WGS84 = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)


@dataclass(frozen=True, slots=True)
class SourceFile:
    """What the name of one file says: the asset it gives, the product it holds, its kind and its two stamps."""

    asset_key: str
    product: str
    kind: str
    start: str
    end: str

    @property
    def year(self) -> int | None:
        """The year of an annual file of the archive, ``None`` for any other file or one that is not one year."""
        return _one_year(self.start, self.end) if self.kind == "-archive" else None

    @property
    def what(self) -> str:
        """The file in an error, without its name or address."""
        return f"the {_SPANS[self.kind]} file of {self.product} from {self.start[:8]}"


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


def parse_name(config: DatasetConfig, name: str) -> SourceFile | None:
    """What the file ``name`` gives the entry, or ``None`` where it gives nothing (another quantity, grid or kind)."""
    quantities, product = _products(config)
    match = FILE_NAME.match(name.lower())
    if match is None or match["grid"] != product.grid:
        return None
    names = {quantity.lower(): (quantity, quantity) for quantity in quantities}
    if match["kind"] == "":
        names |= {source.lower(): (band, source) for source, band in PROVISIONAL_PRODUCTS.items() if band in quantities}
    if match["quantity"] not in names:
        return None
    asset_key, source_product = names[match["quantity"]]
    return SourceFile(asset_key, source_product, match["kind"], match["start"], match["end"])


def _validator(selection: str, digest: str) -> str:
    return f"{selection}|sha256:{digest}"


def _sha256(data: Any) -> str:
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _item_list(config: DatasetConfig, gateway: Gateway) -> tuple[list[Any], str]:
    """Every item of the collection, page by page, and the SHA-256 over the bodies of all pages."""
    features: list[Any] = []
    digest = hashlib.sha256()
    url: str | None = f"{config.source.endpoint}?limit={_PAGE_SIZE}"
    for _ in range(_MAX_PAGES):
        if url is None:
            return features, digest.hexdigest()
        response = await gateway.get(url)
        try:
            page = response.json()
        except ValueError:
            page = None
        if response.status_code != 200 or not isinstance(page, dict) or not isinstance(page.get("features"), list):
            raise UpstreamShapeError("the item list of the climate grids is no STAC item collection")
        digest.update(response.content)
        features.extend(page["features"])
        links = page.get("links") if isinstance(page.get("links"), list) else []
        url = next((link.get("href") for link in links if isinstance(link, dict) and link.get("rel") == "next"), None)
    raise UpstreamShapeError(f"the item list of the climate grids runs over {_MAX_PAGES} pages")


def _files_of(
    config: DatasetConfig, feature: Mapping[str, Any], first_year: int
) -> tuple[dict[str, tuple[SourceFile, Any]], int]:
    """The files of the entry in one source item, by name, and the count of those passed over (not one year, not on an
    asset host)."""
    assets = feature.get("assets")
    if not isinstance(assets, dict):
        return {}, 0
    chosen: dict[str, tuple[SourceFile, Any]] = {}
    slots: set[tuple[str, int | None]] = set()
    passed = 0
    for name, asset in assets.items():
        file = parse_name(config, name)
        if file is None:
            continue
        year = file.year
        if year is not None and year < first_year:
            continue
        href = asset.get("href") if isinstance(asset, dict) else None
        if (
            (file.kind == "-archive" and year is None)
            or not isinstance(href, str)
            or not href.startswith("https://")
            or host_of(href) not in config.source.asset_hosts
        ):
            passed += 1
            continue
        if (file.asset_key, year) in slots:
            raise UpstreamShapeError(
                f"a source item lists two files of {file.asset_key}" + (f" for {year}" if year else "")
            )
        slots.add((file.asset_key, year))
        chosen[name] = (file, asset)
    return chosen, passed


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


async def list_units(config: DatasetConfig, *, gateway: Gateway, known_groups: Mapping[str, str | None]) -> UnitListing:
    """The source items with files of the entry, each judged by the hash of its JSON, and the files of the changed ones;
    after one request "unchanged" where the whole list hashes as before (M5-58 plan §11.4)."""
    if config.source.item_holding is not ItemHolding.MATERIALIZED:
        raise UnsupportedSource(f"{config.dataset_id} is not materialized; its items are not built here")
    quantities, _ = _products(config)
    if config.temporal_extent.start is None:
        raise UnsupportedSource(f"{config.dataset_id}: temporal_extent names the first day to load")
    first_year = config.temporal_extent.start.astimezone(UTC).year
    selection = f"{','.join(sorted(quantities))}:{first_year}"

    features, digest = await _item_list(config, gateway)
    whole = _validator(selection, digest)
    if known_groups.get(LIST_GROUP) == whole:
        return UnitListing(groups=dict(known_groups), unchanged_groups=frozenset(known_groups), units=())

    groups: dict[str, str | None] = {LIST_GROUP: whole}
    unchanged: set[str] = set()
    units: list[SourceUnit] = []
    passed = 0
    for feature in features:
        files, skipped = _files_of(config, feature, first_year) if isinstance(feature, dict) else ({}, 0)
        passed += skipped
        if not files:
            continue
        group = feature.get("id")
        if not isinstance(group, str) or not group or group in groups:
            raise UpstreamShapeError("a source item with files of the entry has no id of its own")
        groups[group] = _validator(selection, _sha256(feature))
        if known_groups.get(group) == groups[group]:
            unchanged.add(group)
            continue
        properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        for name, (file, asset) in sorted(files.items()):
            listed = Validators(
                etag=None,
                last_modified=_text(asset.get("updated")),
                checksum=_text(asset.get("file:checksum")),
                content_sha256=None,
            )
            units.append(
                SourceUnit(
                    key=name,
                    group=group,
                    href=asset["href"],
                    state=STATES[file.kind],
                    validators=listed,
                    expires=_text(properties.get("expires")),
                )
            )
    if len(groups) == 1:
        raise UpstreamShapeError(f"the source lists no file of {', '.join(quantities)}")
    if passed:
        LOGGER.warning(
            f"{passed} files of the entry's quantities are no single year or lie outside its asset hosts; passed over",
            extra={"dataset_id": config.dataset_id},
        )
    return UnitListing(groups=groups, unchanged_groups=frozenset(unchanged), units=tuple(units))


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


def _check_file(file: SourceFile, references: FileReferences, grid: FileReferences | None) -> list[date]:
    """The days of one file, after the checks that make its references safe to write into items."""
    layout = references.layout
    what = file.what
    if layout.crs != CRS:
        raise UpstreamShapeError(f"{what} lies in {layout.crs}, not {CRS}")
    if grid is not None and (layout.shape[1:] != grid.layout.shape[1:] or layout.transform != grid.layout.transform):
        raise UpstreamShapeError(f"{what} lies on another grid than the files before it")
    if references.last_modified is None:
        raise UpstreamShapeError(f"{what} names no Last-Modified, which the items carry as updated")
    days: list[date] = []
    for instant in references.times:
        if instant.timetz() != time(0, tzinfo=UTC):
            raise UpstreamShapeError(f"{what} holds a time step that is not midnight UTC")
        days.append(instant.date())
    if not days or len(set(days)) != len(days):
        raise UpstreamShapeError(f"{what} holds no day or a day twice")
    # The span its kind promises (plan §11.2): a day, the days of one month, the days of the year its name says.
    if file.kind == "" and len(days) != 1:
        raise UpstreamShapeError(f"{what} holds more than one day")
    if file.kind == "-last" and len({(day.year, day.month) for day in days}) != 1:
        raise UpstreamShapeError(f"{what} holds days of more than one month")
    if file.kind == "-archive" and any(day.year != int(file.start[:4]) for day in days):
        raise UpstreamShapeError(f"{what} holds a day of another year")
    return days


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def day_frame(
    config: DatasetConfig, day: date, *, product: Product, footprint: tuple[list[float], dict[str, Any]], gsd: float
) -> dict[str, Any]:
    """The item of one day without its assets: what every file of that day gives alike."""
    start = datetime.combine(day, time(product.day_starts_at, tzinfo=UTC))
    bbox, geometry = footprint
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
            "gsd": gsd,
            "proj:code": CRS,
        },
        "links": [],
    }


def day_asset(
    config: DatasetConfig, unit: SourceUnit, file: SourceFile, references: FileReferences, step: int
) -> dict[str, Any]:
    """The asset one file gives to the item of its ``step``-th day."""
    assert references.last_modified is not None
    asset: dict[str, Any] = {
        "href": unit.href,
        "type": NETCDF_MEDIA_TYPE,
        "roles": ["data"],
        "earthx:refs": step_references(references, step),
        "raster:bands": [
            {
                "data_type": numpy.dtype(references.layout.dtype).name,
                "nodata": "nan",
                "unit": config.band_units[file.asset_key],
            }
        ],
        "updated": _instant(parsedate_to_datetime(references.last_modified)),
    }
    if file.product != file.asset_key:
        asset["earthx:source_product"] = file.product
    if unit.expires:
        asset["expires"] = unit.expires
    return asset


def _inside(bbox: list[float], extent: tuple[float, float, float, float]) -> bool:
    west, south, east, north = extent
    return west <= bbox[0] and south <= bbox[1] and bbox[2] <= east and bbox[3] <= north


async def build_units(config: DatasetConfig, *, gateway: Gateway, units: Sequence[SourceUnit]) -> tuple[BuiltUnit, ...]:
    """The contributions of each file: an asset to the item of every day it holds."""
    _, product = _products(config)
    grid: FileReferences | None = None
    footprint: tuple[list[float], dict[str, Any]] | None = None
    made: list[BuiltUnit] = []
    for count, unit in enumerate(units, start=1):
        file = parse_name(config, unit.key)
        if file is None:
            raise UpstreamShapeError(f"{config.dataset_id}: a unit that is no file of the entry")
        try:
            references = await reference_file(gateway, unit.href)
        except UnsupportedLayout as error:
            raise UpstreamShapeError(f"{file.what}: {error}") from None
        days = _check_file(file, references, grid)
        if grid is None:
            grid, footprint = references, grid_footprint(references)
            if not _inside(footprint[0], config.spatial_extent.bbox):
                raise UnsupportedSource(
                    f"{config.dataset_id}: the grid {json.dumps(footprint[0])} reaches beyond spatial_extent; "
                    "follow the entry up"
                )
        assert footprint is not None
        gsd = abs(references.layout.transform[0])
        contributions = tuple(
            Contribution(
                item_id=f"{config.dataset_id}-{day.strftime('%Y%m%d')}",
                asset_key=file.asset_key,
                asset=day_asset(config, unit, file, references, step),
                item=day_frame(config, day, product=product, footprint=footprint, gsd=gsd),
            )
            for step, day in enumerate(days)
        )
        validators = Validators(
            etag=references.etag, last_modified=references.last_modified, checksum=None, content_sha256=None
        )
        made.append(BuiltUnit(key=unit.key, contributions=contributions, validators=validators))
        LOGGER.info(f"referenced {count} of {len(units)} files", extra={"dataset_id": config.dataset_id})
    return tuple(made)
