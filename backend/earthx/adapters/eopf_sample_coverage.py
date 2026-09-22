"""Declared-sample coverage for the EOPF STAC API — the fourth adapter capability
over a source without an aggregation extension (adr/0004 §5 Option 6; M2-09b plan
§4.2, §10 F5).

`earth_search_coverage.py` answers from one `GET /aggregate` request that already
carries cells, a total and a histogram. This source has no such endpoint — no
`numberMatched`, no `/aggregate`, measured in the M2-09b plan step (plan §3) and
already visible in `federated_search.matched_count` returning `None` on every one
of its search answers. The only way of adr/0004 §5 left for a source like this is
Option 6: pull real footprints through the ordinary search this adapter already
speaks, rasterize them onto the geotile grid ourselves — one footprint into the
cell its centroid falls in, `catalog.coverage.geotile_key`, the same rule every
other way uses — and say plainly that this is a sample, not a census.

**The cap.** Otto's answer to plan §10 F5: five pages of a hundred items, the same
500 as `catalog.coverage.FOOTPRINT_THRESHOLD` and the frontend's own
`FOOTPRINT_FETCH_LIMIT` (`frontend/src/coverage.ts`) — measured at the plan step
at around 2 s for five pages against the live source. Reaching the cap does not
fail the request: the sample is exactly what was drawn before the cap, and the
answer already says so through `completeness`.

**`total_count` is deliberately `None`.** A sample is compared against nothing
(plan §4.2); `catalog.coverage.check_completeness(sampled=True)` returns `SAMPLE`
regardless of what a total would otherwise imply, which is also what keeps
`CoverageResult.footprints_advised` `False` — a sample must not silently turn into
a footprint view the way a checked, small total would (M2-07c's replacement rule).

**No new request shape.** Only `eopf_stac.search_items` is asked, the ordinary item
search this adapter already speaks — passing our own `cache` through it as well,
so a page already seen keeps its existing per-page lifetime (`federated_search`)
instead of this way inventing a second cache for the same answer.

The one thing the search body cannot carry that `CoverageQuery` can is a polygon:
`federated_search.SearchParams` has no `intersects` field (no source measured in
this codebase needs one for an item search). An `intersects` filter is reduced to
its bounding box here before it goes out — a superset of the asked area, the same
kind of reduction `earth_search_coverage` already performs when a polygon does not
fit a URL (adr/0004 §3.4). The answer is a declared sample either way, so being a
little too generous about which footprints it draws from does not change what the
result claims.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from shapely.errors import ShapelyError
from shapely.geometry import shape as shapely_shape

from earthx.adapters.cache import SearchCache
from earthx.adapters.eopf_stac import resolve_dataset, search_items
from earthx.adapters.federated_search import SearchParams
from earthx.catalog.coverage import (
    CoverageCell,
    CoverageProviderMismatch,
    CoverageQuery,
    CoverageResult,
    HistogramBucket,
    InvalidCoverageQuery,
    UpstreamCoverageShapeError,
    check_completeness,
    geotile_key,
    level_for_viewport,
)
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import CoverageProvider, DatasetConfig, DatasetRegistry
from earthx.gateway import Gateway

# Otto, plan §10 F5: five pages of a hundred, the same 500 the frontend already
# fetches before switching to a density (`FOOTPRINT_THRESHOLD`,
# `frontend/src/coverage.ts::FOOTPRINT_FETCH_LIMIT`) — a shared number, not a new one.
SAMPLE_PAGE_SIZE = 100
SAMPLE_PAGES = 5


async def sample_coverage(
    query: CoverageQuery,
    config: DatasetConfig | None = None,
    *,
    gateway: Gateway,
    registry: DatasetRegistry = REGISTRY,
    cache: SearchCache | None = None,
) -> CoverageResult:
    """Density, histogram and a declared-sample completeness, from paged search.

    ``config=None`` looks the dataset up here; ``api`` passes the entry it already
    holds, the same shape ``aggregate_coverage`` accepts (``CoverageSource``).
    """
    config = config if config is not None else resolve_dataset(query.dataset_id, registry)
    if config.dataset_id != query.dataset_id:
        raise CoverageProviderMismatch(f"{query.dataset_id} was asked for, {config.dataset_id} was handed in")
    if config.coverage.provider is not CoverageProvider.SAMPLE:
        raise CoverageProviderMismatch(
            f"{config.dataset_id} is answered by {config.coverage.provider.value}, not by a declared sample"
        )

    # Same defensive re-clamp as `earth_search_coverage._clamped`: the route of
    # M2-05b already clamps the viewport zoom, but the guarantee must not depend on
    # it, or it would fall away silently if that clamp ever moved.
    level = level_for_viewport(query.level, config, has_spatial_filter=query.has_spatial_filter)
    bbox = _bbox_of(query)

    cell_counts: dict[str, int] = {}
    month_counts: dict[datetime, int] = {}
    page_token: str | None = None
    for _ in range(SAMPLE_PAGES):
        page = await search_items(
            query.dataset_id,
            SearchParams(bbox=bbox, start=query.start, end=query.end, limit=SAMPLE_PAGE_SIZE, page_token=page_token),
            gateway=gateway,
            registry=registry,
            cache=cache,
        )
        for item in page.items:
            if not _passes_cloud_filter(item, query.max_cloud_cover):
                continue
            longitude, latitude = _centroid(item)
            key = geotile_key(longitude, latitude, level)
            cell_counts[key] = cell_counts.get(key, 0) + 1
            month = _month_start(item)
            month_counts[month] = month_counts.get(month, 0) + 1
        if page.next_page_token is None:
            break
        page_token = page.next_page_token

    cells = tuple(CoverageCell(key=key, count=count) for key, count in sorted(cell_counts.items()))
    histogram = tuple(HistogramBucket(start=start, count=count) for start, count in sorted(month_counts.items()))
    return CoverageResult(
        dataset_id=query.dataset_id,
        level=level,
        cells=cells,
        total_count=None,
        completeness=check_completeness(sum(cell_counts.values()), None, sampled=True),
        histogram=histogram,
        # Individual pages may have come from `cache`, but the answer itself is
        # assembled fresh from however many of them that was — a page-level cache
        # hit is not the same claim `aggregate_coverage.from_cache` makes about one
        # request that either happened or did not.
        from_cache=False,
    )


def _bbox_of(query: CoverageQuery) -> tuple[float, float, float, float] | None:
    """The search's own bbox filter — see the module docstring on why `intersects`
    is reduced to its bounds rather than sent as it is."""
    if query.bbox is not None:
        return query.bbox
    if query.intersects is None:
        return None
    try:
        return shapely_shape(query.intersects).bounds
    except (ShapelyError, ValueError, TypeError, KeyError, AttributeError):
        raise InvalidCoverageQuery("intersects is not a usable GeoJSON geometry") from None


def _centroid(item: Mapping[str, Any]) -> tuple[float, float]:
    """A footprint's centroid as (longitude, latitude), or the reason it has none.

    Its own error rather than a skipped item: a source that hands back items
    without a usable footprint is not answering the question this way was built
    to answer, the same posture `earth_search_coverage._buckets` takes for a
    malformed aggregation bucket — nothing malformed becomes part of an answer.
    """
    geometry = item.get("geometry")
    if not isinstance(geometry, Mapping):
        raise UpstreamCoverageShapeError("an item carries no geometry to rasterize")
    try:
        point = shapely_shape(geometry).centroid
    except (ShapelyError, ValueError, TypeError, KeyError, AttributeError):
        raise UpstreamCoverageShapeError("an item carries a geometry that could not be read") from None
    if point.is_empty:
        raise UpstreamCoverageShapeError("an item carries an empty geometry")
    return point.x, point.y


def _month_start(item: Mapping[str, Any]) -> datetime:
    """The month `item["properties"]["datetime"]` falls in, at UTC midnight of its
    first day — the same monthly bucketing `HISTOGRAM_INTERVAL` names."""
    properties = item.get("properties")
    value = properties.get("datetime") if isinstance(properties, Mapping) else None
    if not isinstance(value, str):
        raise UpstreamCoverageShapeError("an item carries no datetime to bucket")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise UpstreamCoverageShapeError("an item's datetime is not a STAC instant") from None
    return instant.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _passes_cloud_filter(item: Mapping[str, Any], max_cloud_cover: float | None) -> bool:
    """Whether the item stays in the sample under ``max_cloud_cover``.

    Client-side, because this source's search body carries no query filter of any
    kind (plan §4.2 names only `bbox`, `datetime` and paging as genuinely shared;
    a filter extension was never measured here). An item without a readable
    `eo:cloud_cover` is left out rather than kept: this way cannot show that it
    would have passed a filter it cannot check, and a sample that quietly counted
    it anyway would claim more than it measured — the same caution
    `check_completeness` already applies to the answer as a whole.
    """
    if max_cloud_cover is None:
        return True
    properties = item.get("properties")
    value = properties.get("eo:cloud_cover") if isinstance(properties, Mapping) else None
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value <= max_cloud_cover


__all__ = ["SAMPLE_PAGE_SIZE", "SAMPLE_PAGES", "sample_coverage"]
