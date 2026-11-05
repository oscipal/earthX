"""The search judged per overpass: a pass stays or falls as a whole (DS-03c, Otto 05.11.2026).

``api`` fetches the scenes of the source **without** the filters of the property kind (a scene that fails one alone may
belong to a pass that meets it), groups them by the overpass key of the registry
(:func:`~earthx.catalog.registry.overpass_key`, ``results_group_by``: the one rule of the results list, the mosaic job and the
mosaic tile; Otto, 05.11.2026, on #293) and judges every group:

* **Coverage** of the AOI by the union of the outlines of the scenes of the pass (no pixel).
* **Filters on a share of an area** (``SearchFilter.area_based``) without "Filter within AOI only": the value of the pass is
  the mean of the values of its scenes, weighted by the area each adds to the mosaic when the scenes lie in the order of
  :func:`~earthx.access.crop_rules.mosaic_order` (:func:`~earthx.access.outlines.mosaic_weights`): a place in an overlap
  counts once. That is an approximation (a scene's value is for its whole tile, and the outline is not its valid pixels);
  the filter "within the AOI" below is not.
* **Measures within the AOI** (``within_aoi``): counted on the merged pixels of the scenes
  (:func:`~earthx.access.aoi_clouds.measure_aoi_pass`), each pixel once, from the first valid scene in the order of the mosaic.
* **Filters without an area** (the satellite, the sun): the pass meets one if every one of its scenes does, which is the same
  as "the value is unique in the pass" where it is unique (DS-03c, proposal in the PR for the rest).

When a group is complete: the source gives its scenes newest first (``adapters.federated_search.SORTBY``), and the key of the
pass starts with the UTC day of acquisition (``acquisition_day``). All scenes of one day therefore follow each other, and a
group is complete once a scene of another day comes, or the source ends. The loop reads the scenes of one day (a **block**,
across pages of the source where it has to), groups them with the registry's key and judges the groups; the marker of the next
response stands between two blocks. No rule of its own decides what a pass is. A block is cut at :data:`MAX_DAY_SCENES`
scenes (the most a search checks), and then the pass across the cut is judged in two parts (not seen in practice).

**No response ends without progress** (Otto, 05.11.2026): the first block of a response is judged to the end, whatever the
response's own time says. A pass is read within :func:`~earthx.api.aoi_cloud_filter.read_seconds` of its scenes, in parallel,
and once more if that failed; only then it is skipped (counted under ``unreadable``) and the search goes on.

Nothing here logs an address, an item id, a bound of a range or a key; the one line per response names the dataset and counts.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import date
from functools import partial
from typing import Any

from rasterio import Env
from rasterio.errors import RasterioError
from shapely.geometry.base import BaseGeometry

from earthx.access.aoi_clouds import (
    AssetPath,
    EnterRead,
    ReadDeadlineExceeded,
    aoi_pass_cache_key,
    measure_aoi_pass,
)
from earthx.access.crop_rules import mosaic_order
from earthx.access.outlines import AoiOutlines, mosaic_weights, outline_of
from earthx.access.resolve import AssetResolutionError, ResolvedAsset, open_asset_ref, resolve_asset
from earthx.adapters import ItemPage
from earthx.api.aoi_cloud_filter import (
    FETCH_MARGIN_S,
    RESPONSE_SCENES,
    RESPONSE_SECONDS,
    SEARCH_SCENES,
    AoiFilterRequest,
    AoiMeasurer,
    Cursor,
    FilterOutcome,
    ReadOutcome,
    SceneMeasure,
    _deadline,
    decode_cursor,
    detach,
    encode_cursor,
    read_seconds,
    settle,
)
from earthx.catalog.registry import MissingProperty, ViewerInfo, acquisition_day, overpass_key
from earthx.catalog.search_filters import Condition, RangeCondition, ValuesCondition
from earthx.gateway import GatewayError, host_of
from earthx.readers import AssetRejected

LOGGER = logging.getLogger("earthx.api.pass_filter")

#: Most scenes of one block (the scenes of one UTC day); a longer run is cut here (see the module text).
MAX_DAY_SCENES = SEARCH_SCENES
#: Passes judged at once; `gateway.ReadSlots` holds the real limit per host.
CONCURRENT_PASSES = 4

__all__ = [
    "MAX_DAY_SCENES",
    "PassMeasurer",
    "day_of",
    "judge_properties",
    "mosaic_ordered",
    "pass_key_of",
    "run_pass_filter",
    "settle",
    "weighted_value",
]

GroupOf = Callable[[Mapping[str, Any]], tuple[str, ...]]
DayOf = Callable[[Mapping[str, Any]], date | None]
OrderOf = Callable[[Sequence[dict[str, Any]]], list[dict[str, Any]]]
MeasurePass = Callable[[Sequence[dict[str, Any]]], Awaitable[SceneMeasure | None]]


# -- the pieces of a request ------------------------------------------------------------------------------------


def pass_key_of(viewer: ViewerInfo) -> GroupOf:
    """The overpass key of an item (:func:`~earthx.catalog.registry.overpass_key`); an item that lacks a part of it stands alone."""

    def key_of(item: Mapping[str, Any]) -> tuple[str, ...]:
        try:
            return overpass_key(item, viewer)
        except MissingProperty:
            return ("item", str(item.get("id")))

    return key_of


def day_of(viewer: ViewerInfo) -> DayOf:
    """The UTC day of acquisition of an item, by the registry's rule (``acquisition_day``): the day its pass belongs to."""
    return partial(_day, viewer)


def _day(viewer: ViewerInfo, item: Mapping[str, Any]) -> date | None:
    return acquisition_day(item, viewer)


# -- judging one pass -------------------------------------------------------------------------------------------


def _number(item: Mapping[str, Any], name: str) -> float | None:
    properties = item.get("properties")
    value = properties.get(name) if isinstance(properties, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _scene_meets(item: Mapping[str, Any], name: str, condition: Condition) -> bool:
    """One item against one condition on one of its properties, as the source would judge it: a property it does not
    carry meets nothing."""
    properties = item.get("properties")
    value = properties.get(name) if isinstance(properties, Mapping) else None
    if isinstance(condition, ValuesCondition):
        return isinstance(value, str) and value in condition.values
    number = _number(item, name)
    return number is not None and _bounded(number, condition)


def _bounded(value: float, condition: RangeCondition) -> bool:
    return (condition.minimum is None or value >= condition.minimum) and (
        condition.maximum is None or value <= condition.maximum
    )


def weighted_value(items: Sequence[Mapping[str, Any]], name: str, weights: Sequence[float] | None) -> float | None:
    """The value of a property for the pass: its mean over the scenes, weighted by ``weights``; ``None`` if there is none.

    A pass of one scene has the scene's own value, exact. A scene with weight 0 (an earlier scene has all its area) has no say,
    so a value it lacks is no reason to have none; a scene with weight that lacks one is."""
    if len(items) == 1:
        return _number(items[0], name)
    if weights is None or len(weights) != len(items):
        return None
    total = 0.0
    weighted = 0.0
    for item, weight in zip(items, weights, strict=True):
        if weight <= 0:
            continue
        value = _number(item, name)
        if value is None:
            return None
        total += weight
        weighted += weight * value
    return weighted / total if total > 0 else None


def judge_properties(
    request: AoiFilterRequest, items: Sequence[dict[str, Any]], outlines: Sequence[BaseGeometry | None]
) -> bool:
    """Whether the pass meets every filter on a property of its scenes (see the module text for the two rules)."""
    weights: list[float] | None = None
    weighed = False
    for name, condition in request.scene_conditions.items():
        entry = request.filters.get(name)
        if entry is not None and entry.area_based and isinstance(condition, RangeCondition):
            if not weighed:
                weights, weighed = mosaic_weights(outlines), True
            value = weighted_value(items, name, weights)
            if value is None or not _bounded(value, condition):
                return False
        elif not all(_scene_meets(item, name, condition) for item in items):
            return False
    return True


# -- measuring the merged pixels --------------------------------------------------------------------------------


class PassMeasurer(AoiMeasurer):
    """The measure of an overpass inside the AOI: the pixels of its scenes merged, each place counted once.

    A pass with one scene that touches the AOI has that scene's measure, from the cache of the scenes. A pass with several is
    read onto one grid (:func:`~earthx.access.aoi_clouds.measure_aoi_pass`): the counts of the separate scenes are not
    added up, because each scene picks its own overview level for the AOI and a place in an overlap would count twice. The
    result is cached for the set of scenes. A scene that does not touch the AOI is not read.
    """

    def __init__(self, *args: Any, aoi_outlines: AoiOutlines, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._outlines = aoi_outlines

    async def measure_pass(self, items: Sequence[dict[str, Any]]) -> SceneMeasure | None:
        """``items`` are in the order of the mosaic."""
        touching = [item for item in items if self._touches(item)]
        if not touching:
            return SceneMeasure(0, 0, 0.0, 0.0)  # no data at all in the AOI; nothing to read
        if len(touching) == 1:
            return await self(touching[0])
        try:
            refs = [resolve_asset(item, self._config, self._asset) for item in touching]
        except AssetResolutionError:
            return None
        key = aoi_pass_cache_key(
            self._config.dataset_id, [ref.item_id for ref in refs], self._asset, self._classes, self._aoi
        )
        stored = SceneMeasure.stored(await self._cached(key))
        if stored is not None:
            return stored
        counts = await self.attempts(partial(self._read_pass, refs, read_seconds(len(refs))))
        if counts is None:
            return None
        measure = SceneMeasure.of(counts)
        await self._store(key, measure)
        return measure

    def _touches(self, item: Mapping[str, Any]) -> bool:
        outline = outline_of(item)
        return outline is None or self._outlines.touches(outline)  # an item without an outline is read to be sure

    def _read_pass(self, refs: Sequence[ResolvedAsset], seconds: float) -> ReadOutcome:
        """One try at the counts of the merged scenes. Runs in a thread; the scenes are read in parallel, each inside the slot
        of its host and the GDAL environment of the gateway, and the time is that of :func:`read_seconds`."""
        if any(ref.reader != "cog" for ref in refs):
            return ReadOutcome(None, retry=False)
        try:
            paths = [open_asset_ref(ref, self._policy, self._resolver) for ref in refs]
            hosts = {str(path): host_of(ref.href) for path, ref in zip(paths, refs, strict=True)}
            clean = [path for path in paths if isinstance(path, AssetPath)]  # COGs, as checked above

            def enter(path: AssetPath) -> ExitStack:
                stack = ExitStack()
                stack.enter_context(self._slots.slot(hosts[str(path)]))
                stack.enter_context(Env(**self._options))
                return stack

            read: EnterRead = enter
            with _deadline(seconds):
                return ReadOutcome(measure_aoi_pass(clean, self._aoi, self._classes, enter=read), retry=False)
        except (ReadDeadlineExceeded, GatewayError, RasterioError, OSError):
            # GDAL's text can name the address: the fact only, counted by the caller. Another try may do better.
            return ReadOutcome(None, retry=True)
        except (AssetRejected, ValueError):
            return ReadOutcome(None, retry=False)


def mosaic_ordered(config: Any, asset: str) -> OrderOf:
    """``items`` in the order the mosaic reads them (:func:`~earthx.access.crop_rules.mosaic_order`)."""

    def order(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        crs: dict[str, str | None] = {}
        by_id: dict[str, dict[str, Any]] = {}
        for item in items:
            item_id = str(item.get("id"))
            by_id[item_id] = item
            try:
                crs[item_id] = resolve_asset(item, config, asset).crs
            except AssetResolutionError:
                crs[item_id] = None
        return [by_id[item_id] for item_id in mosaic_order(crs)]

    return order


# -- the loop ---------------------------------------------------------------------------------------------------


@dataclass(slots=True)
class _Verdict:
    """What the judgement of one pass found."""

    items: list[dict[str, Any]]
    kept: bool
    unreadable: bool = False
    cached: bool = False
    resolution: float | None = None


async def _judge(
    request: AoiFilterRequest,
    items: Sequence[dict[str, Any]],
    *,
    order_of: OrderOf,
    measure_pass: MeasurePass,
    aoi: AoiOutlines | None,
) -> _Verdict:
    """One pass: the cheap questions first (coverage, properties), the reading of pixels last and only if needed."""
    ordered = order_of(items)
    outlines = [outline_of(item) for item in ordered]
    if request.coverage is not None and aoi is not None:
        share = aoi.coverage(outlines)
        if share is None or not _bounded(share, request.coverage):
            return _Verdict(ordered, kept=False)
    if request.scene_conditions and not judge_properties(request, ordered, outlines):
        return _Verdict(ordered, kept=False)
    if not request.conditions:
        return _Verdict(ordered, kept=True)
    measure = await measure_pass(ordered)
    if measure is None:
        return _Verdict(ordered, kept=False, unreadable=True)
    meets = all(
        (value := measure.value_of(kind, request.share_classes)) is not None and _bounded(value, condition)
        for kind, condition in request.conditions.items()
    )
    return _Verdict(ordered, kept=meets, cached=measure.cached, resolution=measure.resolution)


@dataclass(slots=True)
class _Tally:
    checked: int
    found: int
    unreadable: int
    scenes: int = 0
    cached: int = 0
    passes: int = 0
    levels: Counter[str] = field(default_factory=Counter)

    def done(self, limit: int, kept: int) -> bool:
        return kept >= limit or self.scenes >= RESPONSE_SCENES or self.checked >= SEARCH_SCENES


async def _read_day(
    fetch_page: Callable[[str | None], Awaitable[ItemPage]], position: tuple[str | None, int], day_of: DayOf
) -> tuple[list[dict[str, Any]], tuple[str | None, int] | None]:
    """The scenes of one UTC day from ``position`` on (a block), and where the next block starts (``None``: the source ends).

    The source gives scenes newest first, so the scenes of a day follow each other. Pages are fetched as the block needs them:
    a day that runs to the end of a page goes on in the next. A scene with no day stands alone."""
    marker, offset = position
    block: list[dict[str, Any]] = []
    block_day: date | None = None
    while True:
        page = await fetch_page(marker)
        for index in range(offset, len(page.items)):
            item = page.items[index]
            day = day_of(item)
            if block and (len(block) >= MAX_DAY_SCENES or day is None or day != block_day):
                return block, (marker, index)
            block.append(dict(item))
            block_day = day
        if not page.next_page_token:
            return block, None
        marker, offset = page.next_page_token, 0


async def run_pass_filter(
    request: AoiFilterRequest,
    *,
    fetch_page: Callable[[str | None], Awaitable[ItemPage]],
    group_of: GroupOf,
    day_of: DayOf,
    order_of: OrderOf,
    measure_pass: MeasurePass,
    limit: int,
    token: str | None,
    binding: str = "",
    clock: Callable[[], float] = time.monotonic,
) -> FilterOutcome:
    """One response of a search per pass, from the position ``token`` names (``None``: the beginning).

    The same limits and the same marker as :func:`~earthx.api.aoi_cloud_filter.run_filter` (a response ends at ``limit`` scenes
    kept, 100 scenes checked, 8 s, 500 scenes checked in the search, or the end of the source), but the unit is a block, the
    scenes of one UTC day: the response ends between two blocks, never inside one, and so may carry a few more scenes than
    ``limit`` (a pass is not cut). **The first block of a response is judged to the end, whatever the clock says**, so that a
    response always moves on; a pass that cannot be read in its time and a second try is skipped and counted. A later block
    whose passes cannot all be judged within the response's own time is left for the next response, which finds the readings
    the first one began in the cache.
    """
    started = clock()
    deadline = started + RESPONSE_SECONDS
    key = hashlib.sha256((request.key + binding).encode("ascii")).hexdigest()
    cursor = decode_cursor(token, key) if token else Cursor()
    tally = _Tally(cursor.checked, cursor.found, cursor.unreadable)
    aoi = request.outlines()
    kept: list[dict[str, Any]] = []
    position: tuple[str | None, int] | None = (cursor.page, cursor.offset)
    fetched = False
    while position is not None and not tally.done(limit, len(kept)) and (clock() < deadline or tally.scenes == 0):
        if fetched and deadline - clock() < FETCH_MARGIN_S:
            break
        fetched = True
        cluster, following = await _read_day(fetch_page, position, day_of)
        if not cluster:
            position = following
            continue
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for item in cluster:
            groups.setdefault(group_of(item), []).append(item)
        verdicts = await _judge_groups(
            request,
            list(groups.values()),
            order_of,
            measure_pass,
            aoi,
            None if tally.scenes == 0 else max(deadline - clock(), 0),
        )
        if verdicts is None:  # out of time: this block is for the next response
            break
        # The verdicts hold the same dicts as `cluster`, in the order of the mosaic; the answer keeps the source's order.
        keep_ids = {id(item) for verdict in verdicts if verdict.kept for item in verdict.items}
        kept_here = [item for item in cluster if id(item) in keep_ids]
        kept.extend(kept_here)
        tally.scenes += len(cluster)
        tally.checked += len(cluster)
        tally.found += len(kept_here)
        for verdict in verdicts:
            tally.passes += 1
            if verdict.unreadable:
                tally.unreadable += len(verdict.items)
            if verdict.resolution is not None:
                tally.cached += len(verdict.items) if verdict.cached else 0
                tally.levels[str(verdict.resolution)] += len(verdict.items)
        position = following
    limit_reached = position is not None and tally.checked >= SEARCH_SCENES
    next_token = None
    if position is not None and not limit_reached:
        next_token = encode_cursor(key, Cursor(position[0], position[1], tally.checked, tally.found, tally.unreadable))
    outcome = FilterOutcome(kept, next_token, tally.checked, tally.found, tally.unreadable, limit_reached)
    LOGGER.info(
        "pass filter",
        extra={
            "dataset": request.dataset_id,
            "checked": tally.scenes,
            "found": len(kept),
            "passes": tally.passes,
            "from_cache": tally.cached,
            "unreadable": tally.unreadable - cursor.unreadable,
            "limit_reached": limit_reached,
            "levels": dict(tally.levels),
            "seconds": round(clock() - started, 3),
        },
    )
    return outcome


async def _judge_groups(
    request: AoiFilterRequest,
    groups: Sequence[list[dict[str, Any]]],
    order_of: OrderOf,
    measure_pass: MeasurePass,
    aoi: AoiOutlines | None,
    seconds: float | None,
) -> list[_Verdict] | None:
    """The verdicts of ``groups`` (a few at once), or ``None`` if they are not all in within ``seconds`` (``None``: wait for them).

    Passes still reading when time is up are not cancelled (a task stopped in the middle of a database call leaves its
    connection broken): they finish on their own, store their measure, and the next response asks for the same passes first."""
    gate = asyncio.Semaphore(CONCURRENT_PASSES)

    async def one(items: list[dict[str, Any]]) -> _Verdict:
        async with gate:
            return await _judge(request, items, order_of=order_of, measure_pass=measure_pass, aoi=aoi)

    tasks = [asyncio.ensure_future(one(items)) for items in groups]
    done, pending = await asyncio.wait(tasks, timeout=seconds)
    if pending:
        for task in pending:
            detach(task)
        return None
    return [task.result() for task in tasks]

