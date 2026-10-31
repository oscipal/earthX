"""``/coverage/{dataset_id}``: the coverage seam wired to `api` (M2-05b), ``GET`` for a map extent, ``POST`` for an AOI.

At the base app, beside ``/health`` and outside ``/stac`` (plans/m2/m2-05-coverage.md
§6.6, F1 a): the answer is not a STAC object, and ``/stac`` stays the namespace of
the standard, in case the real STAC aggregation extension lands there one day.

What this module adds beyond ``catalog.coverage``, ``catalog.local_coverage`` and
``adapters.coverage`` is deliberately small (Otto's scope for M2-05b, widened by
M3-11c): reading the query parameters, turning them into a checked
:class:`~earthx.catalog.coverage.CoverageQuery`, deciding which of the three ways of
adr/0004 §5 answers a dataset (K-06), and mapping every error to a status code. Three
things the scope names explicitly:

* **The source's response body never reaches the answer or a log line** (plan §3.5).
  ``gateway.UpstreamError`` carries an excerpt for the traceback and for
  :mod:`earthx.adapters.earth_search_coverage`'s own tests, but this route never
  reads ``error.excerpt`` — only the status the exception type already names.
* **Nothing here logs an AOI.** The one log line this route writes carries
  ``dataset_id``, the clamped ``level``, ``completeness`` and the answer's origin —
  never ``bbox``, ``intersects`` or a value of ``query``, only the *names* of the
  search filters that were set (DS-02 plan §6.4, rule 8).
* **An AOI is never in the URL** (NM4-57, M4 Q8): a ``GET`` URL stands in access logs, proxies and the
  browser's history. With an AOI the question is a ``POST`` and the area stands in the body only. The
  ``GET`` is for the visible map extent, which is no AOI: it is a box on the grid the interface rounds it
  to (:func:`is_map_extent`), and a ``GET`` with ``intersects``, or with a box that is off that grid, is
  refused with a ``400`` that says to send the area with ``POST``.
* **A time window this dataset cannot honour is dropped, not silently applied**
  (M3-11c, Otto 26.09.2026): ``datetime`` for a dataset with
  ``capabilities.time_range=False`` is named in the answer's ``ignored_filters``
  rather than just disappearing from the query.

``query`` (DS-02b) carries the search filters of the dataset's registry entry, in the
form of the STAC query extension and read by the same code as ``POST /stac/search``
(`api.search_filters`): only the properties and operators the entry names. This route
asks for exactly one dataset, so a filter it does not offer is a ``400`` here, not an
entry in ``ignored_filters`` (plan §6.4, rule 7) — there is no second dataset the filter
could still apply to.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, replace
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, ValidationError
from stac_fastapi.types.rfc3339 import str_to_interval

from earthx.adapters import AdapterSpecs
from earthx.adapters import coverage as adapter_coverage
from earthx.adapters.errors import UpstreamShapeError
from earthx.api.search_filters import read_search_conditions
from earthx.catalog.coverage import (
    HISTOGRAM_INTERVAL,
    MAX_GEOTILE_LEVEL,
    CoverageProviderMismatch,
    CoverageQuery,
    CoverageResult,
    InvalidCoverageQuery,
    UpstreamCoverageShapeError,
    level_for_viewport,
)
from earthx.catalog.local_coverage import area_coverage, check_intersects_is_valid
from earthx.catalog.registry import CoverageProvider, DatasetRegistry, RetiredDatasetError, UnknownDatasetError
from earthx.catalog.search_cache import PostgresSearchCache
from earthx.catalog.search_filters import InvalidFilter
from earthx.gateway import GatewayError, UpstreamError, UpstreamTimeout, UpstreamUnreachable

LOGGER = logging.getLogger("earthx.api.coverage")

# `local-sql` without a single coverage product has no density path built yet
# (M3-11c plan step §4.1 F4): a materialized time series would need its own
# zoomed-grid counting over `pgstac.items`, which no dataset needs in M3. With a
# single coverage product, `local-sql` *is* implemented — as the area way below,
# not through this set (it never goes through `IMPLEMENTED_PROVIDERS`, see
# `_area_path`).
#
# Public because onboarding checklist point 2 reads it: "a coverage provider is
# assigned" is only worth anything if something answers for that provider
# (projektuebersicht.md §5, D4).
IMPLEMENTED_PROVIDERS = frozenset({CoverageProvider.UPSTREAM_AGGREGATION})

# NM4-57: a body larger than this is no coverage question. An AOI outline of a few thousand points fits
# many times over; the cap only keeps a request from holding the process while it is read.
MAX_BODY_BYTES = 1_000_000

# The map extent the interface asks for is rounded outward to blocks of ``2^3 x 2^3`` cells of its level
# (`frontend/src/coverage.ts`, ``VIEWPORT_ROUND_LEVELS``), so a small pan asks the same question. That is
# what makes it recognisable here: an AOI's box lies on no such grid.
VIEWPORT_ROUND_LEVELS = 3
# In cells of the block grid. The interface writes the edges as shortest round-trip decimals, so the
# arithmetic below lands within 1e-9 of a whole cell; an arbitrary coordinate does not.
_GRID_TOLERANCE = 1e-6


def _area_path(config: Any) -> bool:
    """Whether this entry answers through the ``local-sql`` area way (M3-11c):
    the union of its own items' footprints, for a materialized one-off product.
    ``local-sql`` without ``single_coverage_product`` is the density path that is
    not built (F4), and never reaches this function's caller as ``True``; a
    one-off product with upstream aggregation cannot be registered (adr/0004 §5).
    """
    return config.capabilities.single_coverage_product and config.coverage.provider is CoverageProvider.LOCAL_SQL


_NUMBER_TOO_LARGE = "a number in the request is too large"
_AREA_WITH_POST = "an area is sent with POST, in the body; GET takes only the visible map extent"


class CoverageBody(BaseModel):
    """The body of ``POST /coverage/{dataset_id}``: the query parameters of the ``GET``, the area among them.

    ``query`` is the search filters as an object here, not as the JSON text a URL needs. Strict, so a
    number sent as text is refused and not read; unknown fields are refused too.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    zoom: int
    bbox: tuple[float, float, float, float] | None = None
    intersects: dict[str, Any] | None = None
    datetime: str | None = None
    query: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class _Ask:
    """One coverage question as both routes hand it on: read, not yet checked against the registry."""

    zoom: int
    bbox: tuple[float, float, float, float] | None
    intersects: dict[str, Any] | None
    interval: str | None
    # The body `read_search_conditions` takes: `{}` or `{"query": ...}`.
    filters: dict[str, Any]


def build_router(registry: DatasetRegistry, adapters: AdapterSpecs) -> APIRouter:
    """The router, built against the registry and adapter table of the app that
    mounts it (``api.main.build_app``), so one app answers ``/coverage`` from the
    same registry it routes search and items by (M4-01b).
    """
    router = APIRouter()

    @router.get("/coverage/{dataset_id}")
    async def get_coverage(
        request: Request,
        dataset_id: str,
        zoom: Annotated[int, Query(description="viewport zoom; the geotile level before adr/0004 §5's caps clamp it")],
        bbox: Annotated[
            str | None,
            Query(
                description="west,south,east,north of the visible map extent, on the grid of its level "
                "(no AOI: an area is sent with POST)"
            ),
        ] = None,
        datetime: Annotated[
            str | None, Query(description="a STAC interval: an instant, start/end, start/.. or ../end")
        ] = None,
        search_filters: Annotated[
            str | None,
            Query(
                alias="query",
                description="the dataset's search filters as JSON in the STAC query extension, e.g. gte/lte, in",
            ),
        ] = None,
    ) -> dict[str, Any]:
        # Not a parameter of the signature on purpose: an unknown one would be dropped without a word, and
        # the answer would be a world overview where an area was asked for.
        if any(name.lower() == "intersects" for name in request.query_params):
            raise HTTPException(status_code=400, detail=_AREA_WITH_POST)
        box = _parse_bbox(bbox)
        if box is not None and not is_map_extent(box, zoom):
            raise HTTPException(status_code=400, detail=_AREA_WITH_POST)
        return await answer(
            request,
            dataset_id,
            _Ask(
                zoom=zoom,
                bbox=box,
                intersects=None,
                interval=datetime,
                filters={} if search_filters is None else {"query": _parse_query(search_filters)},
            ),
        )

    @router.post(
        "/coverage/{dataset_id}",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": CoverageBody.model_json_schema()}},
            }
        },
    )
    async def post_coverage(request: Request, dataset_id: str) -> dict[str, Any]:
        """The coverage of an AOI: the same question as ``GET``, with the area in the body (NM4-57)."""
        body = await _read_body(request)
        return await answer(
            request,
            dataset_id,
            _Ask(
                zoom=body.zoom,
                bbox=body.bbox,
                intersects=body.intersects,
                interval=body.datetime,
                filters={} if body.query is None else {"query": body.query},
            ),
        )

    async def answer(request: Request, dataset_id: str, ask: _Ask) -> dict[str, Any]:
        try:
            config = registry.get(dataset_id)
        except RetiredDatasetError as error:
            raise HTTPException(status_code=410, detail=error.retired.message) from None
        except UnknownDatasetError:
            raise HTTPException(status_code=404, detail=f"no dataset {dataset_id!r}") from None

        area_path = _area_path(config)
        if not area_path and config.coverage.provider not in IMPLEMENTED_PROVIDERS:
            # `local-sql` without `single_coverage_product` is the density path
            # M3-11c does not build (plan step §4.1 F4): no dataset needs it in M3.
            raise HTTPException(
                status_code=501,
                detail=f"{dataset_id!r} has no coverage answer yet ({config.coverage.provider.value})",
            )

        has_spatial_filter = ask.bbox is not None or ask.intersects is not None
        start, end = _datetime_bounds(ask.interval)
        try:
            read = read_search_conditions(ask.filters, [dataset_id], lambda _: config.search_filters)
        except InvalidFilter as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        except OverflowError:
            # A whole number of more than 300 digits has no float; the parser reads it, the checks cannot.
            raise HTTPException(status_code=400, detail=_NUMBER_TOO_LARGE) from None
        if read.aoi:
            # DS-03 plan §6.5 (KE6): the coverage counts at the source, without a raster, so it cannot apply these.
            raise HTTPException(
                status_code=400, detail="the coverage map cannot apply the cloud share in the AOI; search for scenes"
            )
        conditions = read.by_collection.get(dataset_id)
        try:
            query = CoverageQuery(
                dataset_id=dataset_id,
                level=level_for_viewport(ask.zoom, config, has_spatial_filter=has_spatial_filter),
                bbox=ask.bbox,
                intersects=ask.intersects,
                start=start,
                end=end,
                conditions=conditions,
            )
        except InvalidCoverageQuery as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        except OverflowError:
            raise HTTPException(status_code=400, detail=_NUMBER_TOO_LARGE) from None

        # A time window this dataset structurally cannot honour is dropped here, once,
        # for every way — not left to each way to remember on its own (Otto,
        # 26.09.2026, M3-11c). `time_range=False` applies to any provider a future
        # dataset without a time axis might use. A search filter is never dropped: a
        # materialized dataset, which the area way answers, carries none (registry),
        # so `query` is already a `400` for it above.
        ignored_filters: list[str] = []
        if not config.capabilities.time_range and (query.start is not None or query.end is not None):
            query = replace(query, start=None, end=None)
            ignored_filters.append("datetime")

        # Checked ahead of the pool below, on purpose: a malformed request is a
        # `400` whether or not the database happens to be reachable, and the two
        # must never trade places (an unlucky pool outage must not mask a
        # self-intersecting polygon as "the catalogue is not available").
        if area_path and query.intersects is not None:
            try:
                check_intersects_is_valid(query.intersects)
            except InvalidCoverageQuery as error:
                raise HTTPException(status_code=400, detail=str(error)) from None

        gateway = request.app.state.earthx_gateway
        pool = getattr(request.app.state, "earthx_cache_pool", None)
        try:
            if area_path:
                if pool is None:
                    raise HTTPException(status_code=503, detail="the catalogue is not available")
                async with pool.connection() as conn:
                    result = await area_coverage(query, config, conn=conn, cache=PostgresSearchCache(conn))
            elif pool is None:
                result = await adapter_coverage(query, config, adapters=adapters, gateway=gateway)
            else:
                async with pool.connection() as conn:
                    result = await adapter_coverage(
                        query, config, adapters=adapters, gateway=gateway, cache=PostgresSearchCache(conn)
                    )
        except InvalidCoverageQuery as error:
            # `area_coverage`'s own defensive re-checks (`local_coverage.py`): of
            # `check_intersects_is_valid` and of search filters, which a materialized
            # dataset has none of. The route above already refuses both before this
            # call is ever made, so this is unreachable through this route today,
            # kept for a caller of `area_coverage` that skips them.
            raise HTTPException(status_code=400, detail=str(error)) from None
        except CoverageProviderMismatch as error:
            # Reachable only if the registry and this route disagree about the
            # dataset's provider, which the checks above already rule out — kept
            # as a 501 rather than an assertion, because a wrong answer here must
            # never look like a wrong AOI.
            raise HTTPException(status_code=501, detail=str(error)) from None
        except UpstreamTimeout:
            raise HTTPException(status_code=504, detail="the source did not answer in time") from None
        except (UpstreamError, UpstreamUnreachable, GatewayError):
            # Neither the status nor the source's own body travels on (§3.5 of the
            # plan): the body can carry the AOI back, and only our own text is kept.
            LOGGER.warning("coverage upstream failed", extra={"dataset": dataset_id})
            raise HTTPException(status_code=502, detail="the source did not deliver a coverage answer") from None
        except (UpstreamCoverageShapeError, UpstreamShapeError):
            # `UpstreamShapeError` is the search path misbehaving
            # (`federated_search.require_feature_list` and friends);
            # `UpstreamCoverageShapeError` is the aggregation's own reading of the
            # answer. Both mean the same thing to a caller: unreadable, not ours.
            raise HTTPException(
                status_code=502, detail="the source answered something coverage could not read"
            ) from None

        if ignored_filters:
            result = replace(result, ignored_filters=tuple(ignored_filters))

        LOGGER.info(
            "coverage answered",
            extra={
                "dataset": dataset_id,
                "level": result.level,
                "completeness": result.completeness.value,
                "from_cache": result.from_cache,
                "answer": "area" if area_path else "density",
                "filters": sorted(conditions or ()),
                "ignored_filters": result.ignored_filters,
            },
        )
        return _serialise(result)

    return router


async def _read_body(request: Request) -> CoverageBody:
    """The body as a checked :class:`CoverageBody`, or a ``400`` in our own words.

    Never FastAPI's own ``422``: its detail quotes the input, and the input is the AOI.
    """
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail=f"the body is over the {MAX_BODY_BYTES} byte cap")
    try:
        return CoverageBody.model_validate_json(bytes(content))
    except ValidationError:
        # Not the error's text: it quotes the document.
        raise HTTPException(status_code=400, detail="the body is not a coverage question") from None


def is_map_extent(bbox: tuple[float, float, float, float], zoom: int) -> bool:
    """Whether ``bbox`` is a visible map extent as the interface asks for it, and so no AOI.

    The interface rounds the extent outward to the block grid of ``zoom - VIEWPORT_ROUND_LEVELS`` before it
    asks (`coverage.ts`, ``roundBboxToGrid``): every edge lies on a cell edge of that level. A box drawn or
    uploaded by a person does not, except by a chance of about one in a million per edge. The arithmetic is
    the geotile one of :func:`earthx.catalog.coverage.cell_bbox`, run backwards, without clamping a latitude to
    the Web-Mercator square: the interface's world view reaches 87.7° north through a rounding error at the
    pole, which lies exactly one row beyond the square (position -1), and any other polar latitude is no row.
    """
    if not all(math.isfinite(value) for value in bbox):
        return False
    west, south, east, north = bbox
    side = 2 ** min(max(zoom - VIEWPORT_ROUND_LEVELS, 0), MAX_GEOTILE_LEVEL)
    positions = (
        (west + 180) / 360 * side,
        (east + 180) / 360 * side,
        _mercator_fraction(north) * side,
        _mercator_fraction(south) * side,
    )
    return all(
        -1 - _GRID_TOLERANCE <= p <= side + 1 + _GRID_TOLERANCE and abs(p - round(p)) <= _GRID_TOLERANCE for p in positions
    )


def _mercator_fraction(latitude: float) -> float:
    """How far down the Web-Mercator square a latitude falls: 0 at its north edge, 1 at its south edge."""
    return (1 - math.asinh(math.tan(math.radians(latitude))) / math.pi) / 2


def _parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    parts = value.split(",")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox needs four comma-separated values")
    try:
        west, south, east, north = (float(part) for part in parts)
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox values must be numbers") from None
    return (west, south, east, north)


def _parse_query(value: str) -> Any:
    try:
        return json.loads(value)
    except (ValueError, RecursionError):
        # ValueError also covers a number too long to read (4300 digits), which is no JSONDecodeError. Not the
        # exception's text: it quotes the document.
        raise HTTPException(status_code=400, detail="query is not valid JSON") from None


def _datetime_bounds(value: str | None) -> tuple[Any, Any]:
    """A STAC interval string as (start, end) — ``str_to_interval`` itself answers a
    malformed one with its own ``400`` (the same helper ``api.federating_client``
    uses for ``/stac`` searches).
    """
    parsed = str_to_interval(value)
    if parsed is None:
        return None, None
    if isinstance(parsed, tuple):
        return parsed
    return parsed, parsed


def _serialise(result: CoverageResult) -> dict[str, Any]:
    """The wire shape: cells compact as ``{"k","n"}`` (plan §6.1, F4 a) — the
    polygon of a cell is arithmetic the client already has (``cell_bbox``), not a
    payload we would otherwise pay for on every world overview.
    """
    return {
        "dataset_id": result.dataset_id,
        "grid": result.grid,
        "level": result.level,
        "counting": result.counting,
        "cells": [{"k": cell.key, "n": cell.count} for cell in result.cells],
        "counted": result.counted,
        "total_count": result.total_count,
        "completeness": result.completeness.value,
        "max_count": result.max_count,
        "histogram": [{"t": _instant(bucket.start), "n": bucket.count} for bucket in result.histogram],
        "histogram_interval": HISTOGRAM_INTERVAL,
        "footprints_advised": result.footprints_advised,
        "from_cache": result.from_cache,
        "extent": None if result.extent is None else list(result.extent),
        "area": result.area,
        "ignored_filters": list(result.ignored_filters),
    }


def _instant(value: Any) -> str:
    return value.isoformat().replace("+00:00", "Z")


__all__ = ["build_router"]
