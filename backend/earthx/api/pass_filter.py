"""The search judged per overpass: a pass stays or falls as a whole (DS-03c, Otto 05.11.2026).

``api`` fetches the scenes of the source **without** the filters of the property kind (a scene that fails one alone may
belong to a pass that meets it), cuts the source's order into clusters, groups the scenes of a cluster by the overpass key of
the registry (``results_group_by``) and judges every group:

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

Why clusters: the source gives scenes by acquisition time, and the scenes of one overpass lie within minutes of each
other, but scenes of another overpass can lie between them. The order is cut where the time between two neighbours exceeds
:data:`CLUSTER_GAP`; every pass lies inside one cluster, so a pass is never judged in two halves, and the marker of the next
response stands on a boundary between clusters. A cluster is cut at :data:`MAX_CLUSTER` scenes, and then the pass that lies
across the cut is judged in two parts (a search of a very large area at a very busy time; the answer's
``earthx:aoi_filter`` does not say so).

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
from datetime import datetime
from typing import Any

import anyio
import anyio.to_thread
from rasterio import Env
from rasterio.errors import RasterioError
from shapely.geometry.base import BaseGeometry

from earthx.access.aoi_clouds import AoiClouds, aoi_pass_cache_key, measure_aoi_pass
from earthx.access.crop_rules import mosaic_order
from earthx.access.outlines import AoiOutlines, mosaic_weights, outline_of
from earthx.access.resolve import AssetResolutionError, ResolvedAsset, open_asset_ref, resolve_asset
from earthx.adapters import ItemPage
from earthx.api.aoi_cloud_filter import (
    FETCH_MARGIN_S,
    PAGE_SIZE,
    RESPONSE_SCENES,
    RESPONSE_SECONDS,
    SEARCH_SCENES,
    AoiFilterRequest,
    AoiMeasurer,
    Cursor,
    FilterOutcome,
    SceneMeasure,
    decode_cursor,
    detach,
    encode_cursor,
    settle,
)
from earthx.catalog.registry import MissingProperty, ViewerInfo, group_key
from earthx.catalog.search_filters import Condition, RangeCondition, ValuesCondition
from earthx.gateway import GatewayError, host_of
from earthx.readers import AssetRejected
from earthx.readers.cog import AssetPath

LOGGER = logging.getLogger("earthx.api.pass_filter")

#: Scenes further apart in time than this belong to different clusters (30 minutes: the scenes of one overpass of an
#: area lie within minutes of each other; a datatake of the satellite is shorter than this between two neighbouring tiles).
CLUSTER_GAP_S = 30 * 60
#: Most scenes of one cluster; a longer run is cut here (see the module text).
MAX_CLUSTER = PAGE_SIZE
#: Passes judged at once; `gateway.ReadSlots` holds the real limit per host.
CONCURRENT_PASSES = 4

__all__ = [
    "CLUSTER_GAP_S",
    "MAX_CLUSTER",
    "PassMeasurer",
    "judge_properties",
    "mosaic_ordered",
    "overpass_key",
    "run_pass_filter",
    "settle",
    "weighted_value",
]

GroupOf = Callable[[Mapping[str, Any]], tuple[str, ...]]
OrderOf = Callable[[Sequence[dict[str, Any]]], list[dict[str, Any]]]
MeasurePass = Callable[[Sequence[dict[str, Any]]], Awaitable[SceneMeasure | None]]


# -- the pieces of a request ------------------------------------------------------------------------------------


def overpass_key(viewer: ViewerInfo) -> GroupOf:
    """The overpass key of an item, from the registry's ``results_group_by``; an item that lacks a part of it stands alone."""

    def key_of(item: Mapping[str, Any]) -> tuple[str, ...]:
        try:
            return group_key(item, viewer, viewer.results_group_by)
        except MissingProperty:
            return ("item", str(item.get("id")))

    return key_of


def _instant(item: Mapping[str, Any]) -> float | None:
    """The acquisition instant of an item in seconds, or ``None`` where it has none that reads."""
    properties = item.get("properties")
    value = properties.get("datetime") if isinstance(properties, Mapping) else None
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


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
        counts = await anyio.to_thread.run_sync(self._read_pass, refs, limiter=self._limiter)
        if counts is None:
            return None
        measure = SceneMeasure.of(counts)
        await self._store(key, measure)
        return measure

    def _touches(self, item: Mapping[str, Any]) -> bool:
        outline = outline_of(item)
        return outline is None or self._outlines.touches(outline)  # an item without an outline is read to be sure

    def _read_pass(self, refs: Sequence[ResolvedAsset]) -> AoiClouds | None:
        """The counts of the merged scenes, or ``None`` where they cannot be read. Runs in a thread."""
        if any(ref.reader != "cog" for ref in refs):
            return None
        try:
            paths = [open_asset_ref(ref, self._policy, self._resolver) for ref in refs]
            with ExitStack() as stack:
                for host in sorted({host_of(ref.href) for ref in refs}):
                    stack.enter_context(self._slots.slot(host))
                stack.enter_context(Env(**self._options))
                assert all(isinstance(path, AssetPath) for path in paths)  # COGs, as checked above
                return measure_aoi_pass([p for p in paths if isinstance(p, AssetPath)], self._aoi, self._classes)
        except (AssetRejected, GatewayError, RasterioError, ValueError, OSError):
            # GDAL's text and the AOI's errors can name the address or a position: the fact only, counted by the caller.
            return None


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


async def _read_cluster(
    fetch_page: Callable[[str | None], Awaitable[ItemPage]], position: tuple[str | None, int]
) -> tuple[list[dict[str, Any]], tuple[str | None, int] | None]:
    """The scenes of the cluster that starts at ``position``, and where the next one starts (``None``: the source ends).

    Pages are fetched as the cluster needs them: a cluster that runs to the end of a page goes on in the next."""
    marker, offset = position
    cluster: list[dict[str, Any]] = []
    previous: float | None = None
    while True:
        page = await fetch_page(marker)
        for index in range(offset, len(page.items)):
            item = page.items[index]
            instant = _instant(item)
            if cluster and (
                len(cluster) >= MAX_CLUSTER
                or instant is None
                or previous is None
                or abs(previous - instant) > CLUSTER_GAP_S
            ):
                return cluster, (marker, index)
            cluster.append(dict(item))
            previous = instant
        if not page.next_page_token:
            return cluster, None
        marker, offset = page.next_page_token, 0


async def run_pass_filter(
    request: AoiFilterRequest,
    *,
    fetch_page: Callable[[str | None], Awaitable[ItemPage]],
    group_of: GroupOf,
    order_of: OrderOf,
    measure_pass: MeasurePass,
    limit: int,
    token: str | None,
    binding: str = "",
    clock: Callable[[], float] = time.monotonic,
) -> FilterOutcome:
    """One response of a search per pass, from the position ``token`` names (``None``: the beginning).

    The same limits and the same marker as :func:`~earthx.api.aoi_cloud_filter.run_filter` (a response ends at ``limit`` scenes
    kept, 100 scenes checked, 8 s, 500 scenes checked in the search, or the end of the source), but the unit is a cluster of
    scenes: the response ends between two clusters, never inside one, and so may carry a few more scenes than ``limit``
    (a pass is not cut). A cluster whose passes cannot all be judged in time is left for the next response, which finds
    the readings the first one began in the cache.
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
    while position is not None and not tally.done(limit, len(kept)) and clock() < deadline:
        if fetched and deadline - clock() < FETCH_MARGIN_S:
            break
        fetched = True
        cluster, following = await _read_cluster(fetch_page, position)
        if not cluster:
            position = following
            continue
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for item in cluster:
            groups.setdefault(group_of(item), []).append(item)
        verdicts = await _judge_groups(
            request, list(groups.values()), order_of, measure_pass, aoi, max(deadline - clock(), 0)
        )
        if verdicts is None:  # out of time: this cluster is for the next response
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
    seconds: float,
) -> list[_Verdict] | None:
    """The verdicts of ``groups`` (a few at once), or ``None`` if they are not all in within ``seconds``.

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

