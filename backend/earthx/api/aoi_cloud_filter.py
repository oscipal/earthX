"""The filter "Within AOI" of the search: scenes kept by the cloud share inside the AOI (DS-03 plan §6.5, §6.18).

``earthx:aoi_cloud_cover`` is no property of the source, so the source never hears of it. ``api`` asks the source
for pages of 100 with every other filter, measures each scene in the order the source gives them
(:class:`AoiMeasurer`, on ``access.aoi_clouds``) and keeps those whose share lies in the range (:func:`run_filter`).
A response stops at the first of: ``limit`` scenes kept, :data:`RESPONSE_SCENES` checked, :data:`RESPONSE_SECONDS` of
the clock, :data:`SEARCH_SCENES` checked in the whole search, or the end of the source. It may therefore carry fewer
than ``limit`` scenes, or none; the page marker (:class:`Cursor`) says where the next response goes on and carries
the counts of the search so far.

The AOI is measured and never leaves this process: it goes to no log, no URL and not to the source, and the marker
holds a hash of it (the key of the filter), no coordinate. Nothing here logs an address, an item id, a bound of the
range or a cache key; the one line per response (KE3) names the dataset and counts.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import math
import threading
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import anyio
import anyio.to_thread
import rasterio
import shapely
from rasterio.errors import RasterioError
from shapely.errors import ShapelyError
from shapely.geometry import MultiPolygon, box, shape
from stac_fastapi.types.rfc3339 import str_to_interval

from earthx.access.aoi_clouds import AoiClouds, aoi_clouds_cache_key, canonical_aoi, measure_aoi_clouds
from earthx.access.aoi_upload import MAX_AOI_POINTS
from earthx.access.resolve import AssetResolutionError, ResolvedAsset, open_asset_ref, resolve_asset
from earthx.access.tiles import StatsCache
from earthx.adapters import MAX_LIMIT, InvalidQuery, ItemPage
from earthx.catalog.registry import DatasetConfig
from earthx.catalog.search_filters import InvalidFilter, RangeCondition
from earthx.gateway import GatewayError, Policy, ReadSlots, Resolver, host_of
from earthx.readers import AssetRejected
from earthx.readers.cog import AssetPath

LOGGER = logging.getLogger("earthx.api.aoi_cloud_filter")

# DS-03 plan §6.9 KE2: constants, not configuration.
#: Scenes checked in one response (§6.5 step 4).
RESPONSE_SCENES = 100
#: Seconds of one response; under the 10 s a source gets in a mixed search (``api.mixed_search.SOURCE_TIMEOUT_S``).
RESPONSE_SECONDS = 8.0
#: Scenes checked in the whole search, over every response (F2a).
SEARCH_SCENES = 500
#: A new page of the source is not fetched with less than this left of the response: a cold page can take seconds, and
#: the mixed search cuts a source off at ``SOURCE_TIMEOUT_S``, which would lose the scenes already found.
FETCH_MARGIN_S = 2.0
#: Scenes measured ahead at once. `ReadSlots` holds the real limit per host; this keeps the readers busy.
CONCURRENT_READS = 6
#: A measure lives at most seven days: its key can be recomputed from the AOI (F2e).
CACHE_TTL_S = 7 * 24 * 60 * 60
#: The body of a search that carries an AOI to measure (§6.5 condition 2).
MAX_BODY_BYTES = 1_048_576

#: One page of the source (`adapters.MAX_LIMIT`), the largest one it is asked for.
PAGE_SIZE = MAX_LIMIT

TOKEN_VERSION = 1
_BBOX_TOLERANCE = 1e-7

# GDAL words a failed read with the address in it ("HTTP response code on https://..."), and rasterio logs that.
_GDAL_LOGGERS = ("rasterio._env", "rasterio._base", "rasterio._io", "rasterio._err")


# -- the request ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AoiFilterRequest:
    """The filter of one collection as the search asks it: the range of the share, the AOI to measure, and the
    ``key`` that binds a page marker to both (a hash, never the AOI itself)."""

    dataset_id: str
    condition: RangeCondition
    aoi: Mapping[str, Any]
    key: str


def read_aoi_request(
    dataset_id: str,
    condition: RangeCondition,
    *,
    datetime_value: str | None,
    bbox: Sequence[float] | None,
    intersects: Mapping[str, Any] | None,
    earthx_aoi: Any,
) -> AoiFilterRequest:
    """The filter of ``dataset_id`` with its AOI, or the :class:`InvalidFilter` of a request a caller has to change.

    Two conditions (§6.5): a date range with both ends, and an area. The area is ``intersects`` as a ``Polygon`` or
    ``MultiPolygon``, or the ``bbox``; when the search sends the bounding box because the AOI has too many
    positions, ``earthx:aoi`` is the AOI itself and lies inside that box. No message names a value.
    """
    _require_period(datetime_value)
    aoi = _area(bbox, intersects, earthx_aoi)
    return AoiFilterRequest(
        dataset_id=dataset_id, condition=condition, aoi=aoi, key=_filter_key(dataset_id, condition, aoi)
    )


def _require_period(datetime_value: str | None) -> None:
    interval = str_to_interval(datetime_value) if datetime_value else None
    if not isinstance(interval, tuple) or None in interval:
        raise InvalidFilter("the cloud share in the AOI needs a date range with a start and an end")


def _area(bbox: Sequence[float] | None, intersects: Mapping[str, Any] | None, earthx_aoi: Any) -> dict[str, Any]:
    if earthx_aoi is not None:
        if intersects is not None:
            raise InvalidFilter("earthx:aoi goes with the bbox that holds it, not with intersects")
        if bbox is None:
            raise InvalidFilter("earthx:aoi goes with the bbox that holds it")
        polygon = _polygonal(earthx_aoi, "earthx:aoi")
        if not _bbox_polygon(bbox).buffer(_BBOX_TOLERANCE).covers(polygon):
            raise InvalidFilter("earthx:aoi lies outside the bbox")
        return json.loads(shapely.to_geojson(polygon))
    if intersects is not None:
        return json.loads(shapely.to_geojson(_polygonal(intersects, "intersects")))
    if bbox is not None:
        return json.loads(shapely.to_geojson(_bbox_polygon(bbox)))
    raise InvalidFilter("the cloud share in the AOI needs an area")


def _bbox_polygon(bbox: Sequence[float]) -> Any:
    if len(bbox) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in bbox):
        raise InvalidFilter("bbox needs four numbers: west, south, east, north")
    west, south, east, north = bbox
    if not (-90 <= south < north <= 90 and -180 <= west <= 180 and -180 <= east <= 180):
        raise InvalidFilter("bbox is outside the globe or upside down")
    if west > east:  # across the antimeridian
        return MultiPolygon([box(west, south, 180, north), box(-180, south, east, north)])
    if west == east:
        raise InvalidFilter("bbox has no area")
    return box(west, south, east, north)


def _polygonal(geometry: Any, label: str) -> Any:
    """``geometry`` as a valid shapely Polygon or MultiPolygon, within the limits of an uploaded AOI."""
    if (
        not isinstance(geometry, Mapping)
        or geometry.get("type") not in ("Polygon", "MultiPolygon")
        or not isinstance(geometry.get("coordinates"), list)
    ):
        raise InvalidFilter("the cloud share in the AOI needs an area")
    if _positions(geometry["coordinates"]) > MAX_AOI_POINTS:
        raise InvalidFilter(f"{label} has more than {MAX_AOI_POINTS} positions")
    try:
        polygon = shape(dict(geometry))
        bounds = polygon.bounds
        usable = (
            all(math.isfinite(v) for v in bounds)
            and -180 <= bounds[0] <= bounds[2] <= 180
            and -90 <= bounds[1] <= bounds[3] <= 90
            and polygon.is_valid
            and polygon.area > 0
        )
    except (ShapelyError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        usable = False
    if not usable:
        raise InvalidFilter(f"{label} is not a valid polygon on the globe")
    return polygon


def _positions(coordinates: Any) -> int:
    """How many positions a ``coordinates`` array holds, counted without recursion (a deep array is no crash)."""
    count, pending = 0, [coordinates]
    while pending:
        value = pending.pop()
        if not isinstance(value, list):
            continue
        if value and all(isinstance(number, (int, float)) for number in value):
            count += 1
        else:
            pending.extend(value)
    return count


def _filter_key(dataset_id: str, condition: RangeCondition, aoi: Mapping[str, Any]) -> str:
    payload = {"dataset": dataset_id, "range": [condition.minimum, condition.maximum], "aoi": canonical_aoi(aoi)}
    return hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


# -- the page marker --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Cursor:
    """Where the next response goes on, and the counts of the search so far (§6.9 F2c).

    ``page`` is the marker of the source's page the position lies on (``None`` for the first), ``offset`` the first
    scene of it not yet checked.
    """

    page: str | None = None
    offset: int = 0
    checked: int = 0
    found: int = 0
    unreadable: int = 0


def encode_cursor(key: str, cursor: Cursor) -> str:
    payload = {
        "v": TOKEN_VERSION,
        "k": "aoi",
        "h": key,
        "p": cursor.page,
        "i": cursor.offset,
        "c": cursor.checked,
        "f": cursor.found,
        "u": cursor.unreadable,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(encoded.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(token: str, key: str) -> Cursor:
    """The position a marker of this module names, or ``InvalidQuery`` in our own words (adr/0005 rule III).

    A marker of another search, or of a search without the filter, is refused: the filter and the AOI are bound to it.
    """
    padded = token + "=" * (-len(token) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, binascii.Error) as error:
        raise InvalidQuery("page token is not readable") from error
    if not isinstance(payload, dict) or payload.get("k") != "aoi" or payload.get("v") != TOKEN_VERSION:
        raise InvalidQuery("page token is not one of a search with the cloud share in the AOI")
    if payload.get("h") != key:
        raise InvalidQuery("page token belongs to a different search")
    page = payload.get("p")
    counts = [payload.get(name) for name in ("i", "c", "f", "u")]
    if (page is not None and not isinstance(page, str)) or not all(
        isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in counts
    ):
        raise InvalidQuery("page token carries no position")
    offset, checked, found, unreadable = counts
    if offset >= PAGE_SIZE or checked >= SEARCH_SCENES or found + unreadable > checked:
        raise InvalidQuery("page token carries a position this search does not reach")
    return Cursor(page=page, offset=offset, checked=checked, found=found, unreadable=unreadable)


# -- measuring one scene ----------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SceneMeasure:
    """What is known of one scene in the AOI: the numbers of ``earthx:aoi_measure`` (§6.5)."""

    cloud_pixels: int
    data_pixels: int
    data_percent: float
    resolution: float
    cached: bool = False

    @property
    def cloud_percent(self) -> float | None:
        """Clouds in percent of the valid pixels, one decimal; ``None`` without a valid pixel (§6.7)."""
        if self.data_pixels == 0:
            return None
        return round(100 * self.cloud_pixels / self.data_pixels, 1)

    def as_measure(self) -> dict[str, Any]:
        return {
            "data_percent": self.data_percent,
            "cloud_pixels": self.cloud_pixels,
            "data_pixels": self.data_pixels,
            "resolution": self.resolution,
        }

    @classmethod
    def of(cls, counts: AoiClouds) -> SceneMeasure:
        return cls(counts.cloud_pixels, counts.data_pixels, counts.data_percent, counts.resolution)

    @classmethod
    def stored(cls, value: Any) -> SceneMeasure | None:
        """The measure back from the cache, or ``None`` for an entry that is not one (it counts as a miss)."""
        if not isinstance(value, Mapping):
            return None
        cloud, data = value.get("cloud_pixels"), value.get("data_pixels")
        percent, resolution = value.get("data_percent"), value.get("resolution")
        if not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (cloud, data)) or cloud > data:
            return None
        numbers = (percent, resolution)
        if not all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) for n in numbers):
            return None
        return cls(cloud, data, float(percent), float(resolution), cached=True)


Measure = Callable[[Mapping[str, Any]], Awaitable[SceneMeasure | None]]


_READING = threading.local()


class _HideAddresses(logging.Filter):
    """Drops a log line with an address in it, but only in a thread that is measuring a scene."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(_READING, "active", False):
            return True
        message = record.getMessage().lower()
        return not any(part in message for part in ("http", "/vsi", "curl error", "gdal signalled"))


@contextmanager
def without_gdal_addresses() -> Iterator[None]:
    """Inside the block, the log lines of GDAL's errors in this thread leave out the address of the file."""
    hide_gdal_addresses()
    _READING.active = True
    try:
        yield
    finally:
        _READING.active = False


def hide_gdal_addresses() -> None:
    """Put the filter on the loggers of ``rasterio``, where GDAL's errors become lines; idempotent.

    The filter works only in a thread inside :func:`without_gdal_addresses`, so it changes nothing for the rest of
    the process (the tests of other routes read GDAL's own warning there).
    """
    for name in _GDAL_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(entry, _HideAddresses) for entry in logger.filters):
            logger.addFilter(_HideAddresses())


class AoiMeasurer:
    """Measures the cloud share of one scene in the AOI: from the cache, else by reading the classification.

    A scene it cannot read gives ``None`` (counted as unreadable, §6.9 KE5): no asset on the item, an address the
    gateway refuses, a read that fails, an AOI that does not fit the raster. Reading runs in a thread, inside a slot
    of the host (``gateway.ReadSlots``) and the GDAL environment of the gateway. ``limiter`` bounds the threads
    that read, for the whole process; without one the shared pool of the process is used.
    """

    def __init__(
        self,
        config: DatasetConfig,
        aoi: Mapping[str, Any],
        *,
        policy: Policy,
        resolver: Resolver,
        gdal_options: Mapping[str, str | int],
        slots: ReadSlots,
        cache: StatsCache | None,
        limiter: anyio.CapacityLimiter | None = None,
    ) -> None:
        mask = config.mask
        if mask is None or not mask.cloud_classes:
            raise ValueError(f"{config.dataset_id} has no classification to measure clouds on")
        self._config = config
        self._asset = mask.asset
        self._classes = mask.cloud_classes
        self._aoi = aoi
        self._policy = policy
        self._resolver = resolver
        self._options = dict(gdal_options)
        self._slots = slots
        self._cache = cache
        self._limiter = limiter

    async def __call__(self, item: Mapping[str, Any]) -> SceneMeasure | None:
        try:
            ref = resolve_asset(item, self._config, self._asset)
        except AssetResolutionError:
            return None
        key = aoi_clouds_cache_key(self._config.dataset_id, ref.item_id, ref.asset, self._classes, self._aoi)
        stored = SceneMeasure.stored(await self._cached(key))
        if stored is not None:
            return stored
        # Waiting for a free reader happens here, in the event loop, not in a thread of the shared pool.
        counts = await anyio.to_thread.run_sync(self._read, ref, limiter=self._limiter)
        if counts is None:
            return None
        measure = SceneMeasure.of(counts)
        await self._store(key, measure)
        return measure

    def _read(self, ref: ResolvedAsset) -> AoiClouds | None:
        """The counts of one scene, or ``None`` where it cannot be read. Runs in a thread."""
        if ref.reader != "cog":
            return None
        try:
            path = open_asset_ref(ref, self._policy, self._resolver)
            with self._slots.slot(host_of(ref.href)), rasterio.Env(**self._options), without_gdal_addresses():
                assert isinstance(path, AssetPath)  # a COG, as checked above
                return measure_aoi_clouds(path, self._aoi, self._classes)
        except (AssetRejected, GatewayError, RasterioError, ValueError, OSError):
            # GDAL's text and the AOI's errors can name the address or a position: the fact only, counted by the caller.
            return None

    async def _cached(self, key: str) -> Any:
        if self._cache is None:
            return None
        try:
            return await self._cache.get(key)
        except Exception as error:
            # The text of a database error can repeat the statement's values: the kind of error only.
            LOGGER.warning("cloud share cache unreadable, measuring", extra={"error_type": type(error).__name__})
            return None

    async def _store(self, key: str, measure: SceneMeasure) -> None:
        if self._cache is None:
            return
        try:
            await self._cache.set(key, measure.as_measure(), dataset_id=self._config.dataset_id, ttl_s=CACHE_TTL_S)
        except Exception as error:
            LOGGER.warning("cloud share cache not writable, not stored", extra={"error_type": type(error).__name__})


# -- the loop ---------------------------------------------------------------------------------------------------


@dataclass(slots=True)
class FilterOutcome:
    """One response of the filter: the scenes kept, the marker to go on with, and the counts."""

    items: list[dict[str, Any]]
    next_token: str | None
    checked: int
    found: int
    unreadable: int
    limit_reached: bool

    def summary(self) -> dict[str, Any]:
        """``earthx:aoi_filter`` of the answer (§6.5): counts over the whole search up to here."""
        return {
            "checked": self.checked,
            "found": self.found,
            "unreadable": self.unreadable,
            "limit_reached": self.limit_reached,
        }


@dataclass(slots=True)
class _Tally:
    """The counts of the search up to now, and of this response alone."""

    checked: int
    found: int
    unreadable: int
    scenes: int = 0
    cached: int = 0
    levels: Counter[str] = field(default_factory=Counter)
    kept: list[dict[str, Any]] = field(default_factory=list)

    def done(self, limit: int) -> bool:
        """The response has what it may take: ``limit`` scenes kept, or all the scenes it may check."""
        return len(self.kept) >= limit or self.scenes >= RESPONSE_SCENES or self.checked >= SEARCH_SCENES

    def take(self, item: Mapping[str, Any], measure: SceneMeasure | None, condition: RangeCondition) -> None:
        self.checked += 1
        self.scenes += 1
        if measure is None:
            self.unreadable += 1
            return
        self.cached += measure.cached
        self.levels[str(measure.resolution)] += 1
        percent = measure.cloud_percent
        # The value as the answer shows it, so what the list shows and what the filter kept agree.
        if percent is None or not _within(percent, condition):
            return
        self.found += 1
        self.kept.append(_with_measure(item, percent, measure))


def _within(percent: float, condition: RangeCondition) -> bool:
    return (condition.minimum is None or percent >= condition.minimum) and (
        condition.maximum is None or percent <= condition.maximum
    )


def _with_measure(item: Mapping[str, Any], percent: float, measure: SceneMeasure) -> dict[str, Any]:
    properties = {
        **(item.get("properties") or {}),
        "earthx:aoi_cloud_cover": percent,
        "earthx:aoi_measure": measure.as_measure(),
    }
    return {**item, "properties": properties}


async def run_filter(
    request: AoiFilterRequest,
    *,
    fetch_page: Callable[[str | None], Awaitable[ItemPage]],
    measure: Measure,
    limit: int,
    token: str | None,
    binding: str = "",
    clock: Callable[[], float] = time.monotonic,
) -> FilterOutcome:
    """One response of a search with the filter, from the position ``token`` names (``None``: the beginning).

    ``binding`` is what else the marker belongs to (the source's own search: period, area, other filters), hashed
    into its key so that a marker sent with another search is refused on the first page too, where the source's
    marker does not yet say which search it came from.

    ``fetch_page(marker)`` is the source's page (of :data:`PAGE_SIZE`) for the marker of its own; ``measure(item)`` is
    :class:`AoiMeasurer`'s call. Scenes are taken in the source's order and the position moves past a scene only
    once it is checked, so the next response misses none and repeats none. Several scenes are measured at once; those
    measured past the point a response stops are dropped.
    """
    started = clock()
    deadline = started + RESPONSE_SECONDS
    key = hashlib.sha256((request.key + binding).encode("ascii")).hexdigest()
    cursor = decode_cursor(token, key) if token else Cursor()
    tally = _Tally(cursor.checked, cursor.found, cursor.unreadable)
    position: tuple[str | None, int] | None = (cursor.page, cursor.offset)
    fetched = False
    while position is not None and not tally.done(limit) and clock() < deadline:
        if fetched and deadline - clock() < FETCH_MARGIN_S:
            break
        page = await fetch_page(position[0])
        fetched = True
        taken = await _take_page(page.items[position[1] :], tally, request.condition, measure, limit, clock, deadline)
        if position[1] + taken < len(page.items):
            position = (position[0], position[1] + taken)
            break
        position = (page.next_page_token, 0) if page.next_page_token else None
    limit_reached = position is not None and tally.checked >= SEARCH_SCENES
    next_token = None
    if position is not None and not limit_reached:
        next_token = encode_cursor(
            key, Cursor(position[0], position[1], tally.checked, tally.found, tally.unreadable)
        )
    outcome = FilterOutcome(tally.kept, next_token, tally.checked, tally.found, tally.unreadable, limit_reached)
    LOGGER.info(
        "aoi cloud filter",
        extra={
            "dataset": request.dataset_id,
            "checked": tally.scenes,
            "found": len(tally.kept),
            "from_cache": tally.cached,
            "unreadable": tally.unreadable - cursor.unreadable,
            "limit_reached": limit_reached,
            "levels": dict(tally.levels),
            "seconds": round(clock() - started, 3),
        },
    )
    return outcome


async def _take_page(
    items: Sequence[dict[str, Any]],
    tally: _Tally,
    condition: RangeCondition,
    measure: Measure,
    limit: int,
    clock: Callable[[], float],
    deadline: float,
) -> int:
    """Check the scenes of ``items`` in order until the response is done; the number taken.

    A window of scenes ahead is measured at once. The ones not taken when the response ends are not cancelled (a task
    stopped in the middle of a database call leaves its connection broken): they finish on their own, keep their
    slot only as long as they read, and store their measure, which is what the next response asks for first.
    """
    tasks: list[asyncio.Future[SceneMeasure | None]] = []
    taken = 0
    try:
        for index, item in enumerate(items):
            if tally.done(limit) or clock() >= deadline:
                break
            allowance = min(RESPONSE_SCENES - tally.scenes, SEARCH_SCENES - tally.checked)
            while len(tasks) < min(len(items), index + min(CONCURRENT_READS, allowance)):
                tasks.append(asyncio.ensure_future(measure(items[len(tasks)])))
            done, _ = await asyncio.wait({tasks[index]}, timeout=max(deadline - clock(), 0))
            if not done:
                break
            tally.take(item, tasks[index].result(), condition)
            taken += 1
    finally:
        for task in tasks[taken:]:
            _detach(task)
    return taken


#: The measurements a response left running; held here so that nothing collects them before they are done.
_DETACHED: set[asyncio.Future[SceneMeasure | None]] = set()


def _detach(task: asyncio.Future[SceneMeasure | None]) -> None:
    if task.done():
        _settled(task)
        return
    _DETACHED.add(task)
    task.add_done_callback(_settled)


def _settled(task: asyncio.Future[SceneMeasure | None]) -> None:
    """A measurement nobody waits for any more is over; a bug in it is logged by its kind and nothing else."""
    _DETACHED.discard(task)
    if not task.cancelled() and task.exception() is not None:
        LOGGER.warning("a scene could not be measured", extra={"error_type": type(task.exception()).__name__})


async def settle() -> None:
    """Wait for the measurements the responses left running; the lifespan of ``api`` and the tests call this."""
    while _DETACHED:
        await asyncio.wait(set(_DETACHED))
