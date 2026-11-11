"""Tile times per zoom level over the real tile path (M5-30b part 1, adr/0032 §8.5, F11).

    python -m earthx.api.measure_tiles <dataset_id> --bbox W,S,E,N [--datetime A/B] [--asset KEY]
        [--zooms 0-14] [--max-files 64] [--max-items 500] [--threads 4] [--format table|json]

Run by hand through the compose profile ``measure`` (``docker compose run --rm measure-tiles …``), never by a plain
``docker compose up``: it reads real files at the source, which CI and an ordinary start must not.

What it measures is the cost of one mosaic tile at each zoom level, without the count limits of the route
(``MIN_MOSAIC_ZOOM``, ``MAX_SCENES_PER_TILE``, ``MAX_MOSAIC_ITEMS``), which are what the measurement is for
(adr/0032 §6.2). Everything else is the tile path's own:

* the items of one overpass (:func:`~earthx.catalog.registry.overpass_key`), the largest in the rectangle, in the
  order of the mosaic (:func:`~earthx.access.crop_rules.mosaic_order`); the rectangle only chooses the overpass and
  the asset, **each zoom level fetches the items in the bounds of its own tile** (up to ``--max-items``) and keeps
  those of the chosen overpass;
* each address resolved in `access` and cleared through the gateway policy of the registry, as the tiler does;
* the scenes a tile touches read by the mosaic tile's own reader with the tiler's GDAL configuration.

**Cold and warm.** Each zoom level reads in a process of its own, spawned before it opens a file, so GDAL's caches
are empty: once cold, then the same tile again warm. A CDN in front of the source can still be warm.

**Requests and bytes** are counted from GDAL's debug lines (``VSICURL: Downloading a-b``) as numbers only; no line is
kept or written. **No rectangle, address or item id** is printed, also not in an error, which names only its kind.

**The source is spared:** a tile that touches more than ``--max-files`` files is not read; its row says how many.
If the fetch of a tile returns ``--max-items`` items, the list may be cut and the files it touches are not all known:
the row says ``over items cap`` instead of a count that is too small.

``--threads`` is the number of scenes the mosaic reader opens at the same time (1 to 16, default the tile route's).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import multiprocessing
import re
import sys
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import morecantile
import numpy as np
import psycopg
from rasterio.io import MemoryFile
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from earthx.access.crop_rules import mosaic_order
from earthx.access.mosaic_tiles import MAX_MOSAIC_THREADS, MOSAIC_THREADS, MosaicScenes, MosaicTileReader
from earthx.access.resolve import AssetResolutionError, ResolvedAsset, open_asset_ref, resolve_asset
from earthx.adapters import ADAPTER_SPECS, MAX_LIMIT, AdapterSpecs, SearchParams, search_items
from earthx.api.dependencies import policy_from_registry
from earthx.api.item_source import OrderRefused
from earthx.api.mosaic_tiles import footprints_of, union_bounds
from earthx.catalog.datasets import registry as dataset_registry
from earthx.catalog.pgstac import search_items_in_bbox
from earthx.catalog.registry import (
    ConfigError,
    DatasetConfig,
    DatasetRegistry,
    ItemHolding,
    LicenseTier,
    MissingProperty,
    UnknownDatasetError,
    ViewerInfo,
    group_by_overpass,
    overpass_key,
)
from earthx.gateway import CachingResolver, Gateway, Policy, user_agent_from_env
from earthx.gateway.gdal import tile_gdal_options
from earthx.logging import configure_logging
from earthx.readers.cog import AssetPath
from earthx.readers.errors import AssetRejected

__all__ = [
    "TILE_SIZE",
    "CannotMeasure",
    "Chosen",
    "Gathered",
    "ZoomRow",
    "choose",
    "count_downloads",
    "main",
    "measure_zoom",
    "parse_args",
    "read_twice",
    "render_table",
    "resolve_overpass",
    "run",
    "scenes_touching_tile",
    "tile_at_centre",
    "tile_bounds",
]

LOGGER = logging.getLogger("earthx.api.measure_tiles")

#: The size of a mosaic tile (`access.mosaic_tiles.EarthxMosaicTilerFactory.tile_size`).
TILE_SIZE = 512
#: The longest one zoom level may take before its process is stopped.
ZOOM_TIMEOUT_S = 900.0
_TMS = morecantile.tms.get("WebMercatorQuad")
# The range of one request in GDAL's debug line; the address that follows it is never read.
_DOWNLOADING = re.compile(r"Downloading ((?:\d+-\d+(?:,\s*)?)+)")
_RANGE = re.compile(r"(\d+)-(\d+)")


#: Fetches the items whose footprint meets a rectangle (west, south, east, north in EPSG:4326), at most ``--max-items``.
Fetch = Callable[[tuple[float, float, float, float]], list[dict[str, Any]]]


class CannotMeasure(Exception):
    """Why a run cannot measure, in words of this module only: they name no rectangle, address or item."""


def _bbox(value: str) -> tuple[float, float, float, float]:
    try:
        west, south, east, north = (float(part) for part in value.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError("--bbox is four numbers W,S,E,N") from None
    if not all(map(math.isfinite, (west, south, east, north))):
        raise argparse.ArgumentTypeError("--bbox takes finite numbers")
    if not (-180 <= west < east <= 180 and -85 <= south < north <= 85):
        raise argparse.ArgumentTypeError("--bbox is W,S,E,N in degrees, west below east, south below north")
    return west, south, east, north


def _zooms(value: str) -> tuple[int, ...]:
    try:
        low, dash, high = value.partition("-")
        first, last = int(low), int(high if dash else low)
    except ValueError:
        raise argparse.ArgumentTypeError("--zooms is a level or a range like 0-14") from None
    if not 0 <= first <= last <= 24:
        raise argparse.ArgumentTypeError("--zooms lies within 0-24, low to high")
    return tuple(range(first, last + 1))


def _datetime(value: str) -> tuple[datetime | None, datetime | None]:
    start, _, end = value.partition("/")

    def instant(text: str) -> datetime | None:
        if text in ("", ".."):
            return None
        try:
            return datetime.fromisoformat(text if "T" in text else f"{text}T00:00:00+00:00")
        except ValueError:
            raise argparse.ArgumentTypeError("--datetime is A/B with ISO dates or instants") from None

    bounds = instant(start), instant(end if end else start)
    if end == "" and bounds[0] is not None:
        bounds = bounds[0], bounds[0].replace(hour=23, minute=59, second=59)
    return bounds


def _positive(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("a whole number above 0") from None
    if number < 1:
        raise argparse.ArgumentTypeError("a whole number above 0")
    return number


def _threads(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--threads is a whole number from 1 to {MAX_MOSAIC_THREADS}") from None
    if not 1 <= number <= MAX_MOSAIC_THREADS:
        raise argparse.ArgumentTypeError(f"--threads is a whole number from 1 to {MAX_MOSAIC_THREADS}")
    return number


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m earthx.api.measure_tiles",
        description="Tile times per zoom level over the real tile path (adr/0032 §8.5).",
    )
    parser.add_argument("dataset_id")
    parser.add_argument("--bbox", type=_bbox, required=True, help="W,S,E,N in degrees; never printed")
    parser.add_argument("--datetime", type=_datetime, default=(None, None), help="A/B, a day, or open with ..")
    parser.add_argument("--asset", default=None, help="asset key; default: the first of default_render that is there")
    parser.add_argument("--zooms", type=_zooms, default=tuple(range(15)), help="a level or a range, default 0-14")
    parser.add_argument("--max-files", type=_positive, default=64, help="tiles touching more files are not read")
    parser.add_argument("--max-items", type=_positive, default=500, help="items taken from the search at most")
    parser.add_argument(
        "--threads", type=_threads, default=MOSAIC_THREADS, help="scenes read at the same time, 1 to 16"
    )
    parser.add_argument("--format", choices=("table", "json"), default="table")
    return parser.parse_args(list(argv))


@dataclass(frozen=True, slots=True)
class Chosen:
    """The overpass that is measured and its asset, as the rectangle shows them."""

    dataset_id: str
    asset: str
    key: tuple[str, ...]
    items_found: int
    overpasses: int


@dataclass(frozen=True, slots=True)
class Gathered:
    """The scenes of the overpass that is measured, in the order the mosaic reads them."""

    dataset_id: str
    asset: str
    items_found: int
    overpasses: int
    order: tuple[str, ...]
    refs: Mapping[str, ResolvedAsset]
    outlines: Mapping[str, BaseGeometry]
    skipped: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class ZoomRow:
    """One zoom level: what the tile over the middle of the rectangle touched, read and cost."""

    zoom: int
    files: int
    status: str
    read: int = 0
    cold_s: float | None = None
    warm_s: float | None = None
    cold_requests: int | None = None
    cold_mb: float | None = None
    warm_requests: int | None = None
    warm_mb: float | None = None
    filled: float | None = None
    tiff_kb: float | None = None


def count_downloads(messages: Sequence[str]) -> tuple[int, int]:
    """Requests and bytes in GDAL's ``VSICURL: Downloading a-b[, c-d]`` lines; a line is one request."""
    requests = 0
    total = 0
    for message in messages:
        found = _DOWNLOADING.search(message)
        if found is None:
            continue
        requests += 1
        total += sum(int(end) - int(start) + 1 for start, end in _RANGE.findall(found.group(1)))
    return requests, total


class _Downloads(logging.Handler):
    """Counts GDAL's download lines; keeps the numbers, never the text."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.requests = 0
        self.bytes = 0

    def emit(self, record: logging.LogRecord) -> None:
        requests, total = count_downloads([record.getMessage()])
        self.requests += requests
        self.bytes += total

    def take(self) -> tuple[int, int]:
        taken = self.requests, self.bytes
        self.requests = self.bytes = 0
        return taken


def tile_bounds(tile: morecantile.Tile) -> tuple[float, float, float, float]:
    """West, south, east, north of ``tile`` in EPSG:4326, kept inside the valid latitudes and longitudes."""
    west, south, east, north = _TMS.bounds(tile)
    return max(west, -180.0), max(south, -90.0), min(east, 180.0), min(north, 90.0)


def tile_at_centre(bbox: tuple[float, float, float, float], zoom: int) -> morecantile.Tile:
    west, south, east, north = bbox
    return _TMS.tile((west + east) / 2, (south + north) / 2, zoom)


def scenes_touching_tile(
    order: Sequence[str], outlines: Mapping[str, BaseGeometry], tile: morecantile.Tile
) -> list[str]:
    """The ids of ``order`` whose outline meets ``tile``, in that order (as `api.mosaic_tiles.scenes_touching`)."""
    area = box(*_TMS.bounds(tile))
    return [item_id for item_id in order if outlines[item_id].intersects(area)]


def _tiff_bytes(image: Any) -> int:
    """The size of the tile's first band as a pyramid tile would be stored (adr/0032 §5.2, §8.5 point 3)."""
    band = image.array[0]
    floating = np.issubdtype(band.dtype, np.floating)
    fill = image.nodata if image.nodata is not None else (np.nan if floating else 0)
    values = np.ma.filled(band, fill).astype(band.dtype)
    profile = {
        "driver": "GTiff",
        "width": values.shape[1],
        "height": values.shape[0],
        "count": 1,
        "dtype": values.dtype.name,
        "crs": image.crs,
        "transform": image.transform,
        "tiled": True,
        "blockxsize": TILE_SIZE,
        "blockysize": TILE_SIZE,
        "compress": "DEFLATE",
        "predictor": 3 if floating else 2,
        "nodata": float(fill),
    }
    with MemoryFile() as memory:
        with memory.open(**profile) as target:
            target.write(values, 1)
        return len(memory.read())


def _filled(image: Any) -> float:
    """The share of pixels with a value in at least one band."""
    valid = ~np.ma.getmaskarray(image.array).all(axis=0)
    return float(np.count_nonzero(valid)) / valid.size


@contextmanager
def _counting_gdal_lines() -> Iterator[_Downloads]:
    """GDAL's lines go to a counter and nowhere else while the read runs; the logger is as it was afterwards.

    The lines name the address, so they must not reach a handler of the process during the measurement. The tests
    read in the process of pytest, where a changed logger would leak into the next test (#336).
    """
    downloads = _Downloads()
    gdal_logger = logging.getLogger("rasterio")
    level, propagate = gdal_logger.level, gdal_logger.propagate
    gdal_logger.addHandler(downloads)
    gdal_logger.setLevel(logging.DEBUG)
    gdal_logger.propagate = False
    try:
        yield downloads
    finally:
        gdal_logger.removeHandler(downloads)
        gdal_logger.setLevel(level)
        gdal_logger.propagate = propagate


def read_twice(
    scenes: Sequence[AssetPath],
    dataset_id: str,
    bounds: tuple[float, float, float, float],
    tile: tuple[int, int, int],
    gdal_config: Mapping[str, str],
    *,
    threads: int = MOSAIC_THREADS,
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    """Read ``tile`` from ``scenes`` with the mosaic tile's reader, cold and then warm, and say what each cost.

    Runs in the process of one zoom level. Any failure is a row with its kind, never with its text.
    """
    reader = MosaicTileReader(
        MosaicScenes(dataset_id, tuple(scenes), bounds), gdal_config={**gdal_config, "CPL_DEBUG": "ON"}, threads=threads
    )
    x, y, z = tile
    result: dict[str, Any] = {}
    with _counting_gdal_lines() as downloads:
        try:
            for kind in ("cold", "warm"):
                started = clock()
                image = reader.tile(x, y, z, tilesize=TILE_SIZE)
                result[f"{kind}_s"] = round(clock() - started, 3)
                requests, total = downloads.take()
                result[f"{kind}_requests"] = requests
                result[f"{kind}_mb"] = round(total / 1e6, 3)
            result["filled"] = round(_filled(image), 3)
            result["tiff_kb"] = round(_tiff_bytes(image) / 1e3, 1)
            result["status"] = "ok"
        except Exception as error:  # noqa: BLE001 - a row names the kind of any failure; the text can hold an address
            result["status"] = type(error).__name__
    return result


def _zoom_process(
    refs: list[dict[str, Any]],
    dataset_id: str,
    bounds: tuple[float, float, float, float],
    tile: tuple[int, int, int],
    gdal_config: dict[str, str],
    threads: int,
    answer: Any,
) -> None:
    """One zoom level in a process of its own: the scenes cleared again through the registry's gateway policy, then read."""
    try:
        policy = policy_from_registry(dataset_registry())
        resolve = CachingResolver()
        scenes = [open_asset_ref(ResolvedAsset.from_json(ref), policy, resolve) for ref in refs]
    except Exception as error:  # noqa: BLE001 - the kind only, as in `read_twice`
        answer.send({"status": type(error).__name__})
    else:
        answer.send(read_twice(scenes, dataset_id, bounds, tile, gdal_config, threads=threads))  # type: ignore[arg-type]
    answer.close()


def _in_own_process(
    refs: Sequence[ResolvedAsset],
    dataset_id: str,
    bounds: tuple[float, float, float, float],
    tile: tuple[int, int, int],
    gdal_config: Mapping[str, str],
    *,
    threads: int = MOSAIC_THREADS,
) -> dict[str, Any]:
    """:func:`read_twice` in a spawned process, so GDAL starts with empty caches."""
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    plain = [ref.to_json() for ref in refs]
    process = context.Process(
        target=_zoom_process, args=(plain, dataset_id, bounds, tile, dict(gdal_config), threads, send), daemon=True
    )
    process.start()
    send.close()
    try:
        if receive.poll(ZOOM_TIMEOUT_S):
            return receive.recv()
        return {"status": "timeout"}
    except EOFError:
        return {"status": "crashed"}
    finally:
        process.join(5)
        if process.is_alive():
            process.kill()


def _in_overpass(item: Mapping[str, Any], viewer: ViewerInfo, key: tuple[str, ...]) -> bool:
    try:
        return overpass_key(item, viewer) == key
    except MissingProperty:
        return False


def measure_zoom(
    config: DatasetConfig,
    chosen: Chosen,
    zoom: int,
    bbox: tuple[float, float, float, float],
    *,
    fetch: Fetch,
    policy: Policy,
    resolve: Any,
    max_files: int,
    max_items: int,
    gdal_config: Mapping[str, str],
    threads: int = MOSAIC_THREADS,
    read: Callable[..., dict[str, Any]] = _in_own_process,
) -> ZoomRow:
    """One zoom level: the items in the bounds of its tile, those of the chosen overpass, and the read of the tile."""
    viewer = config.viewer
    assert viewer is not None  # checked by the caller
    tile = tile_at_centre(bbox, zoom)
    items = fetch(tile_bounds(tile))
    # A full list may be cut: the files the tile touches are then not all known.
    cut = len(items) >= max_items
    unknown = "over items cap" if cut else "no scenes"
    mine = [item for item in items if _in_overpass(item, viewer, chosen.key)]
    if not mine:
        return ZoomRow(zoom, 0, unknown)
    try:
        gathered = resolve_overpass(config, chosen, mine, policy, resolve)
    except CannotMeasure:
        return ZoomRow(zoom, 0, "over items cap" if cut else "unreadable")
    touching = scenes_touching_tile(gathered.order, gathered.outlines, tile)
    if not touching:
        return ZoomRow(zoom, 0, unknown)
    if len(touching) > max_files:
        return ZoomRow(zoom, len(touching), "over cap")
    if cut:
        return ZoomRow(zoom, len(touching), "over items cap")
    bounds = union_bounds({item_id: gathered.outlines[item_id] for item_id in touching})
    scenes = [gathered.refs[item_id] for item_id in touching]
    outcome = read(scenes, chosen.dataset_id, bounds, (tile.x, tile.y, tile.z), gdal_config, threads=threads)
    known = {name: outcome[name] for name in ZoomRow.__dataclass_fields__ if name in outcome}
    return ZoomRow(zoom=zoom, files=len(touching), read=len(touching), **{"status": "failed", **known})


def _asset_of(config: DatasetConfig, items: Sequence[Mapping[str, Any]], asked: str | None) -> str:
    if asked is not None:
        return asked
    candidates = config.default_render.assets if config.default_render is not None else ()
    for key in candidates:
        if any(key in (item.get("assets") or {}) for item in items):
            return key
    raise CannotMeasure("the dataset names no default asset these items carry; pass --asset")


def choose(config: DatasetConfig, items: Sequence[dict[str, Any]], asked_asset: str | None) -> Chosen:
    """The largest overpass of ``items`` (the first of equals) and the asset that is measured."""
    viewer = config.viewer
    assert viewer is not None  # checked by the caller
    keyed = [item for item in items if _has_overpass_key(item, viewer)]
    groups = group_by_overpass(keyed, viewer)
    if not groups:
        raise CannotMeasure("no item in the rectangle carries an overpass key")
    key = max(groups, key=lambda candidate: len(groups[candidate]))
    return Chosen(
        dataset_id=config.dataset_id,
        asset=_asset_of(config, groups[key], asked_asset),
        key=key,
        items_found=len(items),
        overpasses=len(groups),
    )


def _has_overpass_key(item: Mapping[str, Any], viewer: ViewerInfo) -> bool:
    try:
        overpass_key(item, viewer)
    except MissingProperty:
        return False
    return True


def resolve_overpass(
    config: DatasetConfig, chosen: Chosen, items: Sequence[dict[str, Any]], policy: Policy, resolve: Any
) -> Gathered:
    """The items of ``chosen``'s overpass among ``items``, resolved and cleared as the mosaic tile does, in its order."""
    viewer = config.viewer
    assert viewer is not None  # checked by the caller
    skipped: dict[str, int] = {}
    largest: list[dict[str, Any]] = []
    for item in items:
        try:
            if overpass_key(item, viewer) == chosen.key:
                largest.append(item)
        except MissingProperty:
            skipped["no overpass key"] = skipped.get("no overpass key", 0) + 1
    asset = chosen.asset
    refs: dict[str, ResolvedAsset] = {}
    crs: dict[str, str | None] = {}
    with_asset: dict[str, dict[str, Any]] = {}
    for item in largest:
        try:
            ref = resolve_asset(item, config, asset)
            path = open_asset_ref(ref, policy, resolve)
        except (AssetResolutionError, AssetRejected) as error:
            kind = type(error).__name__
            skipped[kind] = skipped.get(kind, 0) + 1
            continue
        if not isinstance(path, AssetPath):
            raise CannotMeasure("the measurement reads COGs; this dataset is read as Zarr")
        refs[ref.item_id] = ref
        crs[ref.item_id] = ref.crs
        with_asset[ref.item_id] = item
    if not refs:
        raise CannotMeasure(f"no item of the overpass has a readable asset {asset!r}")
    try:
        outlines = footprints_of(with_asset)
    except OrderRefused:
        raise CannotMeasure("an item of the overpass has no usable outline") from None
    return Gathered(
        dataset_id=config.dataset_id,
        asset=asset,
        items_found=len(items),
        overpasses=chosen.overpasses,
        order=tuple(mosaic_order(crs)),
        refs=refs,
        outlines=outlines,
        skipped=skipped,
    )


def gather(
    config: DatasetConfig,
    items: Sequence[dict[str, Any]],
    asked_asset: str | None,
    policy: Policy,
    resolve: Any,
) -> Gathered:
    """The largest overpass of ``items``, resolved and cleared as the mosaic tile does, in its order."""
    return resolve_overpass(config, choose(config, items, asked_asset), items, policy, resolve)


async def _federated_items(
    config: DatasetConfig,
    bbox: tuple[float, float, float, float],
    datetime_range: tuple[datetime | None, datetime | None],
    max_items: int,
    policy: Policy,
    resolve: Any,
    adapters: AdapterSpecs,
) -> list[dict[str, Any]]:
    start, end = datetime_range
    found: list[dict[str, Any]] = []
    token: str | None = None
    async with Gateway(policy, resolve=resolve) as gateway:
        while len(found) < max_items:
            params = SearchParams(
                bbox=bbox, start=start, end=end, limit=min(MAX_LIMIT, max_items - len(found)), page_token=token
            )
            page = await search_items(config, params, adapters=adapters, gateway=gateway)
            found.extend(page.items)
            token = page.next_page_token
            if not token or not page.items:
                break
    return found


def _materialized_items(
    config: DatasetConfig, bbox: tuple[float, float, float, float], max_items: int
) -> list[dict[str, Any]]:
    with psycopg.connect("") as conn:
        return search_items_in_bbox(conn, config.dataset_id, bbox, max_items)  # type: ignore[return-value]


def make_fetch(
    config: DatasetConfig, args: argparse.Namespace, policy: Policy, resolve: Any, adapters: AdapterSpecs
) -> Fetch:
    """The search of the dataset's source, for any rectangle, with the run's ``--datetime`` and ``--max-items``."""
    if config.source.item_holding is ItemHolding.MATERIALIZED:
        return lambda bbox: _materialized_items(config, bbox, args.max_items)
    return lambda bbox: asyncio.run(
        _federated_items(config, bbox, args.datetime, args.max_items, policy, resolve, adapters)
    )


def check_dataset(registry: DatasetRegistry, dataset_id: str) -> DatasetConfig:
    """The entry, or the :class:`CannotMeasure` that says why it cannot be measured (as the tile route refuses it)."""
    try:
        config = registry.get(dataset_id)
    except UnknownDatasetError:
        raise CannotMeasure(f"no dataset {dataset_id!r} in the registry") from None
    if config.license.tier is LicenseTier.CATALOG:
        raise CannotMeasure(f"{dataset_id!r} is a catalogue entry only; nothing of it is displayed")
    if config.viewer is None:
        raise CannotMeasure(f"{dataset_id!r} names no released zoom range (earthx:viewer)")
    return config


def render_table(gathered: Gathered, rows: Sequence[ZoomRow], max_files: int, threads: int = MOSAIC_THREADS) -> str:
    def cell(value: Any) -> str:
        return "–" if value is None else str(value)

    skipped = ", ".join(f"{count} {kind}" for kind, count in sorted(gathered.skipped.items())) or "none"
    lines = [
        f"Dataset `{gathered.dataset_id}`, asset `{gathered.asset}`: {gathered.items_found} items found in the rectangle, "
        f"{gathered.overpasses} overpasses; measured the largest, {len(gathered.order)} scenes there "
        f"(skipped: {skipped}). Tile {TILE_SIZE} px over the middle of the rectangle, the items fetched per tile; "
        f"at most {max_files} files read per tile, {threads} threads.",
        "",
        "| z | files | status | cold s | warm s | cold requests | cold MB | warm requests | warm MB | filled | GeoTIFF kB |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    row.zoom, row.files, row.status, row.cold_s, row.warm_s, row.cold_requests, row.cold_mb,
                    row.warm_requests, row.warm_mb, row.filled, row.tiff_kb,
                )
            )
            + " |"
        )
    return "\n".join(lines)


def render_json(gathered: Gathered, rows: Sequence[ZoomRow], max_files: int, threads: int = MOSAIC_THREADS) -> str:
    return json.dumps(
        {
            "dataset": gathered.dataset_id,
            "asset": gathered.asset,
            "items_found": gathered.items_found,
            "overpasses": gathered.overpasses,
            "scenes": len(gathered.order),
            "skipped": dict(gathered.skipped),
            "tile_size": TILE_SIZE,
            "max_files": max_files,
            "threads": threads,
            "rows": [asdict(row) for row in rows],
        },
        indent=2,
    )


def run(
    args: argparse.Namespace,
    registry: DatasetRegistry,
    *,
    adapters: AdapterSpecs = ADAPTER_SPECS,
    fetch: Fetch | None = None,
    resolve: Any = None,
    read: Callable[..., dict[str, Any]] = _in_own_process,
) -> str:
    config = check_dataset(registry, args.dataset_id)
    policy = policy_from_registry(registry)
    resolve = CachingResolver() if resolve is None else resolve
    if fetch is None:
        fetch = make_fetch(config, args, policy, resolve, adapters)
    items = fetch(args.bbox)
    if not items:
        raise CannotMeasure("no item in the rectangle")
    chosen = choose(config, items, args.asset)
    gathered = resolve_overpass(config, chosen, items, policy, resolve)
    gdal_config = tile_gdal_options(policy)
    rows = [
        measure_zoom(
            config, chosen, zoom, args.bbox, fetch=fetch, policy=policy, resolve=resolve, max_files=args.max_files,
            max_items=args.max_items, gdal_config=gdal_config, threads=args.threads, read=read,
        )
        for zoom in args.zooms
    ]
    if args.format == "json":
        return render_json(gathered, rows, args.max_files, args.threads)
    return render_table(gathered, rows, args.max_files, args.threads)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging()
    try:
        user_agent_from_env()
    except ValueError as error:  # names the variable, never its value (M5-18 §3.1)
        print(f"measure failed: {error}", file=sys.stderr)
        return 1
    try:
        print(run(args, dataset_registry()))
    except (CannotMeasure, ConfigError) as error:
        print(f"measure failed: {error}", file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001 - the kind only: a source's or the driver's text can name an address
        print(f"measure failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
