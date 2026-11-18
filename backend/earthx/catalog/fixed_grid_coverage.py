"""Coverage of a series of daily time steps over one fixed grid (M5-11 plan §5.4, adr/0029 §8a.2).

Every item of such a dataset covers the whole grid, so a density would show the same number everywhere. The answer is
the extent of the entry, cropped to the spatial filter, as an **area**, with the number of time steps in the time
window and a histogram of them per month. All of it is reckoned from the entry: no query per item, no database.

The time steps are days (the cadence of M5-11, plan A11): the first starts at ``temporal_extent.start``, each lasts one
day, the last ends at ``temporal_extent.end``. A step is counted when its day touches the window, the overlap rule of
the item search. A day the source lacks is still counted here; the items show the gap (plan §10.9).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from shapely.geometry import box, mapping
from shapely.geometry import shape as shapely_shape
from shapely.ops import unary_union

from earthx.catalog.coverage import (
    Completeness,
    CoverageProviderMismatch,
    CoverageQuery,
    CoverageResult,
    HistogramBucket,
    InvalidCoverageQuery,
)
from earthx.catalog.local_coverage import check_intersects_is_valid
from earthx.catalog.registry import CoverageProvider, DatasetConfig

STEP = timedelta(days=1)
# An item's end is the last second of its day (inclusive, as STAC reads `end_datetime`).
_LAST_SECOND = STEP - timedelta(seconds=1)


def fixed_grid_coverage(query: CoverageQuery, config: DatasetConfig) -> CoverageResult:
    """The extent cropped to ``query``'s area, and the days of ``query``'s window, counted per month."""
    if config.coverage.provider is not CoverageProvider.FIXED_GRID:
        raise CoverageProviderMismatch(
            f"{config.dataset_id} is answered by {config.coverage.provider.value}, not by fixed-grid"
        )
    if query.conditions is not None:
        raise InvalidCoverageQuery(f"{config.dataset_id}: the fixed-grid way has no search filters")
    first, last = config.temporal_extent.start, config.temporal_extent.end
    if first is None or last is None:
        raise CoverageProviderMismatch(f"{config.dataset_id}: fixed-grid needs a closed temporal_extent")

    area = box(*config.spatial_extent.bbox)
    if query.bbox is not None:
        west, south, east, north = query.bbox
        clip = box(west, south, east, north) if west <= east else unary_union([box(west, south, 180, north), box(-180, south, east, north)])
        area = area.intersection(clip)
    if query.intersects is not None:
        check_intersects_is_valid(query.intersects)
        area = area.intersection(shapely_shape(query.intersects))
    area = unary_union([part for part in getattr(area, "geoms", [area]) if part.geom_type == "Polygon" and not part.is_empty])

    steps = int((last - first) // STEP) + 1
    low, high = 0, steps - 1
    if query.start is not None:
        low = max(low, _ceil_steps(query.start - first - _LAST_SECOND))
    if query.end is not None:
        high = min(high, (query.end - first) // STEP)
    if area.is_empty or low > high:
        return _result(query, None, ())
    return _result(query, area, _months(first, int(low), int(high)))


def _ceil_steps(span: timedelta) -> int:
    return -((-span) // STEP)


def _months(first: datetime, low: int, high: int) -> tuple[HistogramBucket, ...]:
    """The steps ``low``..``high`` counted by the month (UTC) their day starts in."""
    buckets: list[HistogramBucket] = []
    start = first + low * STEP
    month = datetime(start.year, start.month, 1, tzinfo=UTC)
    while True:
        following = datetime(month.year + month.month // 12, month.month % 12 + 1, 1, tzinfo=UTC)
        in_month = range(max(low, _ceil_steps(month - first)), min(high, _ceil_steps(following - first) - 1) + 1)
        if not in_month:
            break
        buckets.append(HistogramBucket(start=month, count=len(in_month)))
        month = following
    return tuple(buckets)


def _result(query: CoverageQuery, area: Any, histogram: tuple[HistogramBucket, ...]) -> CoverageResult:
    if area is None:
        geojson: dict[str, Any] = {"type": "MultiPolygon", "coordinates": []}
        extent = None
    else:
        polygons = list(getattr(area, "geoms", [area]))
        geojson = {"type": "MultiPolygon", "coordinates": [mapping(p)["coordinates"] for p in polygons]}
        extent = tuple(float(value) for value in area.bounds)
    return CoverageResult(
        dataset_id=query.dataset_id,
        level=0,
        cells=(),
        total_count=sum(bucket.count for bucket in histogram),
        completeness=Completeness.COMPLETE,
        histogram=histogram,
        from_cache=False,
        extent=extent,  # type: ignore[arg-type]
        area=geojson,
    )


__all__ = ["STEP", "fixed_grid_coverage"]
