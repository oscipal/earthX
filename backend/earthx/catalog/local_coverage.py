"""Coverage of a materialized one-off product: the union of its own items (M3-11c).

`adr/0009` §6, Otto's answer to F5 (23.09.2026): a single coverage product's honest
coverage is not its collection's global bbox — that would show the oceans and the
gap over the South Caucasus as covered for the Copernicus DEM — but the union of its
items' own footprints, drawn as an **area**, not a density: every cell would show
exactly one coverage, so there is nothing to count.

This is `catalog`'s own SQL over `pgstac.items`. `adr/0004` §5 ("Wo welcher Teil
liegt") puts the grid, the counting rule and the aggregation itself in `catalog`
because they are the platform's own decisions, not a source's protocol — the area
rule here is the same kind of decision, just for the one case a source cannot answer
at all (it has no search API, `adr/0009` §11). This module never imports `adapters`
(`.importlinter`); the two federated ways (`adapters.earth_search_coverage`,
`adapters.eopf_sample_coverage`) are reached through `adapters.coverage` instead,
which `api.coverage_route` dispatches to for everything that is not this one.

**Two filters this way cannot honour, on purpose.** A materialized one-off product
carries no `eo:cloud_cover`, and — for a dataset with `capabilities.time_range=False`
— its area does not change with the calendar. `api.coverage_route` drops both before
they reach here (M3-11c, Otto 26.09.2026) and reports them back as
``CoverageResult.ignored_filters``, so the platform never claims to have answered a
question it silently ignored.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

import psycopg
from shapely.errors import ShapelyError
from shapely.geometry import shape as shapely_shape

from earthx.catalog.coverage import (
    Completeness,
    CoverageCache,
    CoverageProviderMismatch,
    CoverageQuery,
    CoverageResult,
    InvalidCoverageQuery,
)
from earthx.catalog.registry import CoverageProvider, DatasetConfig

# Otto, M3-11c F3 (26.09.2026): fixed and short, not tied to `adr/0005` F1's
# open/closed-window rule. The one expensive case — the unfiltered world view,
# measured at ~1 s in the plan step's §3 — then costs that once every five minutes
# for every viewer, not once per request; a fresh load of the dataset is visible
# within the same five minutes without M3-11b having to reach into this cache.
AREA_TTL_S = 5 * 60

_ITEMS_TABLE = "pgstac.items"


async def area_coverage(
    query: CoverageQuery,
    config: DatasetConfig,
    *,
    conn: psycopg.AsyncConnection,
    cache: CoverageCache | None = None,
) -> CoverageResult:
    """The area a materialized one-off product's own items cover, cropped to
    ``query``'s spatial and time filter.

    Valid only for ``coverage.provider is LOCAL_SQL`` **and**
    ``capabilities.single_coverage_product`` — the dispatch that combination
    requires lives in `api.coverage_route`, which is also what strips
    ``max_cloud_cover`` and (for a dataset without a time axis) ``datetime``
    before calling this; both are checked again here as
    :class:`CoverageProviderMismatch`/defensive reads, not trusted from the
    caller alone, the same posture `earth_search_coverage.aggregate_coverage`
    and `eopf_sample_coverage.sample_coverage` already take for their own
    provider check.
    """
    if config.coverage.provider is not CoverageProvider.LOCAL_SQL:
        raise CoverageProviderMismatch(
            f"{config.dataset_id} is answered by {config.coverage.provider.value}, not by local-sql"
        )
    if not config.capabilities.single_coverage_product:
        # The registry pairs `local-sql` with materialized items unconditionally
        # (M3-11a K-05); the *area* way additionally needs a single coverage
        # product, because a materialized time series has no such union to draw
        # (a density is the honest answer there, and M3-11c does not build it,
        # §4.1 F4 of the plan step — `api.coverage_route` answers `501` before
        # this is ever called for such an entry).
        raise CoverageProviderMismatch(
            f"{config.dataset_id}: local-sql without single_coverage_product has no area to answer with"
        )
    if query.intersects is not None:
        check_intersects_is_valid(query.intersects)

    key = _cache_key(query)
    if cache is not None:
        cached = await cache.get(key)
        if cached is not None:
            return _result(query, cached, from_cache=True)

    stored = await _query_area(conn, query)
    if cache is not None:
        await cache.set(key, stored, ttl_s=AREA_TTL_S, dataset_id=query.dataset_id)
    return _result(query, stored, from_cache=False)


def check_intersects_is_valid(geometry: Mapping[str, Any]) -> None:
    """Refused here, before it ever reaches SQL: a self-intersecting polygon makes
    GEOS answer with the coordinate of the fault, and that text must reach neither
    the response nor the log (projektplan.md 7, point 6). Refusing it here means it
    is never asked, rather than caught and reworded after the fact.
    """
    try:
        shape = shapely_shape(geometry)
    except (ShapelyError, ValueError, TypeError, KeyError, AttributeError):
        raise InvalidCoverageQuery("intersects is not a valid GeoJSON geometry") from None
    if not shape.is_valid:
        raise InvalidCoverageQuery("intersects is not a valid geometry (for instance, it crosses itself)")


def _clip_sql(query: CoverageQuery) -> tuple[str, dict[str, Any]] | None:
    """The SQL fragment for the query's spatial filter, and its bound parameters —
    or ``None`` for no filter at all, in which case the whole union is asked for.

    Only the *shape* of the SQL depends on the query (a bbox crossing the
    antimeridian needs the union of two rectangles, `adr/0009` §3.1's own tiles
    never do but a viewport can); every value is still a bound parameter, nothing
    from the request is written into the SQL text itself.
    """
    if query.bbox is not None:
        west, south, east, north = query.bbox
        if west <= east:
            return (
                "ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)",
                {"west": west, "south": south, "east": east, "north": north},
            )
        return (
            "ST_Union("
            "ST_MakeEnvelope(%(west)s, %(south)s, 180, %(north)s, 4326), "
            "ST_MakeEnvelope(-180, %(south)s, %(east)s, %(north)s, 4326))",
            {"west": west, "south": south, "east": east, "north": north},
        )
    if query.intersects is not None:
        return (
            "ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326)",
            {"geojson": json.dumps(dict(query.intersects))},
        )
    return None


async def _query_area(conn: psycopg.AsyncConnection, query: CoverageQuery) -> dict[str, Any]:
    """One row: the GeoJSON of the (clipped) union, and its bbox — or all ``NULL``
    when nothing matched, which :func:`_result` reads as an empty area.
    """
    where = ["collection = %(dataset_id)s"]
    params: dict[str, Any] = {"dataset_id": query.dataset_id}
    union_expr = "ST_Union(geometry)"

    clip = _clip_sql(query)
    if clip is not None:
        clip_sql, clip_params = clip
        where.append(f"geometry && {clip_sql}")
        params.update(clip_params)
        union_expr = f"ST_Intersection(ST_Union(geometry), {clip_sql})"

    # The same overlap rule pgstac's own search uses for a time window: an item is
    # in if its own range touches the asked one at all. Only added when the query
    # actually carries a bound — `api.coverage_route` has already dropped both for
    # a dataset without a time axis (module docstring).
    if query.start is not None:
        where.append("end_datetime >= %(start)s")
        params["start"] = query.start
    if query.end is not None:
        where.append("datetime <= %(end)s")
        params["end"] = query.end

    # `ST_CollectionExtract(…, 3)` because a clip along a tile edge can leave a
    # sliver of a line or a point behind; `ST_Multi` so the answer is always a
    # `MultiPolygon`, never a bare `Polygon`, whatever the union collapses to.
    # No tolerance (M3-11c plan step §3): the area covers exactly the footprints,
    # gaps and holes included.
    sql = f"""
        SELECT
            ST_AsGeoJSON(ST_Multi(ST_CollectionExtract(g, 3)), 6),
            ST_XMin(g), ST_YMin(g), ST_XMax(g), ST_YMax(g)
        FROM (
            SELECT ST_Simplify({union_expr}, 0) AS g
            FROM {_ITEMS_TABLE}
            WHERE {" AND ".join(where)}
        ) AS unioned
    """
    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()

    geojson, xmin, ymin, xmax, ymax = row if row is not None else (None, None, None, None, None)
    if geojson is None:
        return {"area": _EMPTY_AREA, "extent": None}
    area = json.loads(geojson)
    if not area.get("coordinates"):
        return {"area": area, "extent": None}
    return {"area": area, "extent": [xmin, ymin, xmax, ymax]}


# "Fläche, aber leer" (Meer, ein Zeitfenster ohne Treffer) stays distinguishable
# from "kein Flächenweg" (`area: null` everywhere else) — plan step §4.3.
_EMPTY_AREA: dict[str, Any] = {"type": "MultiPolygon", "coordinates": []}


def _cache_key(query: CoverageQuery) -> str:
    """A hash of the normalised question. ``level`` and ``max_cloud_cover`` are
    deliberately left out: the area does not depend on either (there is no grid to
    resolve to, and this way never reads cloud cover), so two requests that differ
    only in one of those are one cache entry, not two.
    """
    payload = json.dumps(
        {
            "dataset": query.dataset_id,
            "bbox": None if query.bbox is None else [float(value) for value in query.bbox],
            "intersects": None if query.intersects is None else json.dumps(query.intersects, sort_keys=True),
            "start": None if query.start is None else query.start.isoformat(),
            "end": None if query.end is None else query.end.isoformat(),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"coverage-area:{hashlib.sha256(payload.encode()).hexdigest()}"


def _result(query: CoverageQuery, stored: dict[str, Any], *, from_cache: bool) -> CoverageResult:
    extent = stored["extent"]
    return CoverageResult(
        dataset_id=query.dataset_id,
        level=0,
        cells=(),
        total_count=None,
        # `adr/0009` §6: the platform holds every item of a materialized one-off
        # product, so there is nothing left uncounted — unlike `check_completeness`,
        # nothing is being compared against a total that does not apply here (the
        # same reasoning `extent_result` already carries).
        completeness=Completeness.COMPLETE,
        histogram=(),
        from_cache=from_cache,
        extent=None if extent is None else tuple(extent),
        area=stored["area"],
    )


__all__ = ["AREA_TTL_S", "area_coverage", "check_intersects_is_valid"]
