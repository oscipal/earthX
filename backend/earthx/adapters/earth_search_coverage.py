"""Coverage aggregation for Earth Search v1 — the fourth adapter capability.

``architekturplan.md`` 6.1 lists aggregation beside discovery, search and access
resolution, and adr/0004 §5 puts the knowledge of *how a particular source
aggregates* here rather than in ``catalog``: that ``/aggregate`` answers GET only,
what the parameters are called, that the cell count is capped at 10 000 and that the
``overflow`` field lies about it.

Its own module, next to ``earth_search.py``, because that one is already long and
speaks a different endpoint. What the two share — our catalogue deciding whether a
collection exists, the endpoint, the STAC time window, the two cache lifetimes, and a
cache that may fail — is imported from there, not copied.

**One request, not three.** Cells, total and histogram are asked for together, so that
the completeness probe of rule V compares numbers from the *same* answer (adr/0004
§3.1). Asking twice would compare two moments and call the difference truncation.

**The AOI survives in the query string or it is named.** ``/aggregate`` takes no POST,
so a polygon has to fit into the URL, and the source answers ``414`` somewhere above
5.4 kB (adr/0004 §3.4). A polygon that would not fit is reduced — first thinned, then
to its bounding box — and every reduction sets the flag that makes the answer
``truncated``. That way the map says it is showing something else than what was asked,
instead of silently answering a different question.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from earthx.adapters.cache import CacheValue, SearchCache
from earthx.adapters.earth_search import (
    cache_get,
    cache_set,
    endpoint_of,
    resolve_dataset,
    stac_interval,
    ttl_for_window,
)
from earthx.catalog.coverage import (
    CoverageCell,
    CoverageProviderMismatch,
    CoverageQuery,
    CoverageResult,
    HistogramBucket,
    InvalidCoverageQuery,
    UpstreamCoverageShapeError,
    check_completeness,
    parse_cell_key,
)
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import CoverageProvider, DatasetConfig, DatasetRegistry
from earthx.gateway import Gateway, UrlTooLong

LOGGER = logging.getLogger("earthx.adapters.earth_search_coverage")

# The three aggregations we ask for, in one request (adr/0004 §3.1). Measured against
# the live source on 20.09.2026: 0,33–0,83 s and under 8 kB for a filtered question.
AGGREGATIONS = ("total_count", "grid_geotile_frequency", "datetime_frequency")

# adr/0004 §3.4: the source refuses a URL somewhere above 5.4 kB. Rather than bisect
# that limit we thin a polygon to this many points first, which measured at 5.4 kB for
# 200 points, and fall back to the bounding box if even that does not fit.
MAX_AOI_POINTS = 200

# Otto, F3 of 20.09.2026: the completely unfiltered world overview keeps its answer for
# a day. At thirty million items a day of new scenes changes nothing visible on it, and
# it is the one view every user sees first. Everything else follows adr/0005 rule II
# through ``ttl_for_window``.
TTL_WORLD_OVERVIEW_S = 24 * 60 * 60

# The cached shape is versioned: a row written by an older release is read as a miss
# rather than misread (same reasoning as the page marker in earth_search.py).
CACHE_VERSION = 1


async def aggregate_coverage(
    query: CoverageQuery,
    config: DatasetConfig | None = None,
    *,
    gateway: Gateway,
    registry: DatasetRegistry = REGISTRY,
    cache: SearchCache | None = None,
) -> CoverageResult:
    """Density, histogram and a checked completeness, from ``GET /aggregate``.

    ``config=None`` looks the dataset up here; ``api`` passes the entry it already
    holds. ``cache=None`` is a valid call: without a cache this is slower, never wrong
    (E5).
    """
    config = config if config is not None else resolve_dataset(query.dataset_id, registry)
    if config.dataset_id != query.dataset_id:
        raise CoverageProviderMismatch(f"{query.dataset_id} was asked for, {config.dataset_id} was handed in")
    if config.coverage.provider is not CoverageProvider.UPSTREAM_AGGREGATION:
        raise CoverageProviderMismatch(
            f"{config.dataset_id} is answered by {config.coverage.provider.value}, not by upstream aggregation"
        )

    key = _cache_key(query)
    cached = await cache_get(cache, key)
    if _is_usable(cached):
        return _result(query, cached, from_cache=True)

    stored = await _ask_source(query, config, gateway=gateway)
    await cache_set(cache, key, stored, ttl_s=_ttl(query), dataset_id=query.dataset_id)
    return _result(query, stored, from_cache=False)


async def _ask_source(query: CoverageQuery, config: DatasetConfig, *, gateway: Gateway) -> CacheValue:
    """One GET, with the AOI reduced as far as the URL limit makes necessary.

    The reductions are tried in order and each one is a weaker answer than the last, so
    the first that fits wins and the flag it set travels with the result.
    """
    url = f"{endpoint_of(config)}/aggregate"
    refused: UrlTooLong | None = None
    for area, simplified in _area_variants(query):
        try:
            response = await gateway.get(url, params=_params(query, config, area))
        except UrlTooLong as error:
            # Refused before anything left the house, which is the point of the check
            # (adr/0004 §5, Gateway). Try the next, smaller shape of the same question.
            LOGGER.info("coverage query too long for the source, reducing the area", extra={"dataset": query.dataset_id})
            refused = error
            continue
        return _storable(response.json(), simplified_aoi=simplified)
    # Only reachable if even a bounding box does not fit, which would mean the limit was
    # never about the AOI. The gateway's own refusal says more than a guess of ours.
    raise refused if refused is not None else UpstreamCoverageShapeError("no request could be built")


def _area_variants(query: CoverageQuery) -> tuple[tuple[Mapping[str, Any] | tuple[float, ...] | None, bool], ...]:
    """The area as asked, then thinned, then as a box — with the flag each one earns."""
    if query.intersects is None:
        return ((query.bbox, False),)
    thinned = _thin(query.intersects, MAX_AOI_POINTS)
    variants: list[tuple[Mapping[str, Any] | tuple[float, ...] | None, bool]] = [(query.intersects, False)]
    if thinned is not query.intersects:
        variants.append((thinned, True))
    variants.append((_bounds_of(query.intersects), True))
    return tuple(variants)


def _thin(geometry: Mapping[str, Any], limit: int) -> Mapping[str, Any]:
    """Drop points at a regular stride until the outline is within ``limit`` points.

    Crude on purpose: this is the fallback before the bounding box, not a topology
    library, and whichever of the two answers it is marked as truncated either way. The
    first and last point of every ring are kept, so the ring stays closed.
    """
    rings = _rings(geometry)
    total = sum(len(ring) for ring in rings)
    if total <= limit or not rings:
        return geometry
    stride = math.ceil(total / limit)
    thinned = [_thin_ring(ring, stride) for ring in rings]
    return _with_rings(geometry, thinned)


def _thin_ring(ring: list[Any], stride: int) -> list[Any]:
    """Keep every ``stride``-th point of the ring and close it again."""
    kept = ring[:-1:stride] or list(ring[:1])
    return [*kept, kept[0]]


def _rings(geometry: Mapping[str, Any]) -> list[list[Any]]:
    coordinates = geometry.get("coordinates") or []
    if geometry.get("type") == "Polygon":
        return [ring for ring in coordinates if isinstance(ring, list)]
    return [ring for polygon in coordinates if isinstance(polygon, list) for ring in polygon if isinstance(ring, list)]


def _with_rings(geometry: Mapping[str, Any], rings: list[list[Any]]) -> Mapping[str, Any]:
    if geometry.get("type") == "Polygon":
        return {"type": "Polygon", "coordinates": rings}
    shapes: list[list[list[Any]]] = []
    index = 0
    for polygon in geometry.get("coordinates") or []:
        count = len(polygon)
        shapes.append(rings[index : index + count])
        index += count
    return {"type": "MultiPolygon", "coordinates": shapes}


def _bounds_of(geometry: Mapping[str, Any]) -> tuple[float, float, float, float]:
    points = [point for ring in _rings(geometry) for point in ring if isinstance(point, (list, tuple)) and len(point) >= 2]
    if not points:
        raise InvalidCoverageQuery("the area carries no usable coordinates")
    longitudes = [float(point[0]) for point in points]
    latitudes = [float(point[1]) for point in points]
    return (min(longitudes), min(latitudes), max(longitudes), max(latitudes))


def _params(
    query: CoverageQuery, config: DatasetConfig, area: Mapping[str, Any] | tuple[float, ...] | None
) -> dict[str, str]:
    """The query string of ``GET /aggregate``, exactly as measured on 20.09.2026."""
    params = {
        "collections": config.source.source_collection_id,
        "aggregations": ",".join(AGGREGATIONS),
        "grid_geotile_frequency_precision": str(query.level),
        "datetime_frequency_interval": query.interval,
    }
    if isinstance(area, Mapping):
        params["intersects"] = json.dumps(area, separators=(",", ":"))
    elif area is not None:
        params["bbox"] = ",".join(str(float(value)) for value in area)
    window = stac_interval(query.start, query.end)
    if window is not None:
        params["datetime"] = window
    if query.max_cloud_cover is not None:
        params["query"] = json.dumps({"eo:cloud_cover": {"lt": query.max_cloud_cover}}, separators=(",", ":"))
    return params


def _storable(payload: Any, *, simplified_aoi: bool) -> CacheValue:
    """What we keep of the upstream answer: cells, total, histogram, and the flag.

    Reduced here rather than at the cache, so a cache hit and a live answer go through
    exactly the same translation afterwards — the same reasoning as in ``earth_search``.
    """
    if not isinstance(payload, dict):
        raise UpstreamCoverageShapeError("aggregation answer is not a JSON object")
    aggregations = payload.get("aggregations")
    if not isinstance(aggregations, list):
        raise UpstreamCoverageShapeError("aggregation answer carries no aggregations")
    by_name = {entry.get("name"): entry for entry in aggregations if isinstance(entry, dict)}

    cells = [
        {"k": key, "n": frequency}
        for key, frequency in _buckets(by_name.get("grid_geotile_frequency"), "grid_geotile_frequency")
    ]
    # Every key is read once, here, so a cell that is not on the grid cannot reach a
    # map layer — and cannot be stored either.
    for cell in cells:
        parse_cell_key(cell["k"])
    histogram = [
        {"t": key, "n": frequency} for key, frequency in _buckets(by_name.get("datetime_frequency"), "datetime_frequency")
    ]
    return {
        "v": CACHE_VERSION,
        "cells": cells,
        "histogram": histogram,
        "total": _total_count(by_name.get("total_count")),
        "simplified_aoi": simplified_aoi,
    }


def _buckets(aggregation: Any, name: str) -> list[tuple[str, int]]:
    """The buckets of one aggregation as (key, count).

    A missing aggregation is empty rather than an error: the source may legitimately
    have nothing in the window. A *malformed* one is an error — what is not a bucket
    must not become a cell by being passed on.
    """
    if aggregation is None:
        return []
    if not isinstance(aggregation, dict):
        raise UpstreamCoverageShapeError(f"{name} is not an aggregation object")
    buckets = aggregation.get("buckets") or []
    if not isinstance(buckets, list):
        raise UpstreamCoverageShapeError(f"{name} carries no bucket list")
    read: list[tuple[str, int]] = []
    for bucket in buckets:
        if not isinstance(bucket, dict):
            raise UpstreamCoverageShapeError(f"{name} holds something that is not a bucket")
        key, frequency = bucket.get("key"), bucket.get("frequency")
        if not isinstance(key, str) or not isinstance(frequency, int) or isinstance(frequency, bool):
            raise UpstreamCoverageShapeError(f"{name} holds a bucket without a key and a count")
        read.append((key, frequency))
    return read


def _total_count(aggregation: Any) -> int | None:
    """``total_count``, or None where the source did not state one.

    None is not an error and not a zero: rule V turns it into ``truncated``, because a
    source that cannot state a total cannot prove completeness.
    """
    if not isinstance(aggregation, dict):
        return None
    value = aggregation.get("value")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _is_usable(cached: CacheValue | None) -> bool:
    """A stored row of the shape this release writes — anything else counts as a miss."""
    return (
        isinstance(cached, dict)
        and cached.get("v") == CACHE_VERSION
        and isinstance(cached.get("cells"), list)
        and isinstance(cached.get("histogram"), list)
    )


def _result(query: CoverageQuery, stored: CacheValue, *, from_cache: bool) -> CoverageResult:
    cells = tuple(CoverageCell(key=cell["k"], count=cell["n"]) for cell in stored["cells"])
    counted = sum(cell.count for cell in cells)
    total = stored.get("total")
    return CoverageResult(
        dataset_id=query.dataset_id,
        level=query.level,
        cells=cells,
        counted=counted,
        total_count=total,
        completeness=check_completeness(counted, total, simplified_aoi=bool(stored.get("simplified_aoi"))),
        histogram=tuple(
            HistogramBucket(start=_instant(bucket["t"]), count=bucket["n"]) for bucket in stored["histogram"]
        ),
        from_cache=from_cache,
    )


def _instant(value: str) -> datetime:
    """A histogram key as the source writes it: ``2024-01-01T00:00:00.000Z``."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise UpstreamCoverageShapeError("a histogram bucket is not dated with an instant") from None


def _ttl(query: CoverageQuery) -> float:
    """The lifetime of this answer (adr/0004 §5, adr/0005 rule II, Otto F3)."""
    return TTL_WORLD_OVERVIEW_S if query.is_unfiltered else ttl_for_window(query.end)


def _cache_key(query: CoverageQuery) -> str:
    """A hash of the normalised question, so two spellings of it are one entry.

    Numbers go in as floats and instants as their UTC text, the same normalisation the
    search fingerprint does. The key is opaque, so no coordinate is stored outside the
    payload and none can reach a log through it.
    """
    payload = json.dumps(
        {
            "dataset": query.dataset_id,
            "level": query.level,
            "bbox": None if query.bbox is None else [float(value) for value in query.bbox],
            "intersects": None if query.intersects is None else json.dumps(query.intersects, sort_keys=True),
            "datetime": stac_interval(query.start, query.end),
            "cloud": None if query.max_cloud_cover is None else float(query.max_cloud_cover),
            "interval": query.interval,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(f"coverage:{payload}".encode()).hexdigest()
