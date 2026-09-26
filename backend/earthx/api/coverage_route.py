"""``GET /coverage/{dataset_id}``: the coverage seam wired to `api` (M2-05b).

At the base app, beside ``/health`` and outside ``/stac`` (plans/m2-05-coverage.md
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
  never ``bbox``, ``intersects`` or ``max_cloud_cover``.
* **A filter this dataset cannot honour is dropped, not silently applied** (M3-11c,
  Otto 26.09.2026): ``datetime`` for a dataset with ``capabilities.time_range=False``,
  and ``max_cloud_cover`` on the ``local-sql`` area way, which has no cloud cover to
  filter on. Both are named in the answer's ``ignored_filters`` rather than just
  disappearing from the query.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from stac_fastapi.types.rfc3339 import str_to_interval

from earthx.adapters import coverage as adapter_coverage
from earthx.adapters.federated_search import UpstreamShapeError
from earthx.catalog.coverage import (
    HISTOGRAM_INTERVAL,
    CoverageProviderMismatch,
    CoverageQuery,
    CoverageResult,
    InvalidCoverageQuery,
    UpstreamCoverageShapeError,
    extent_result,
    level_for_viewport,
)
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.local_coverage import area_coverage, check_intersects_is_valid
from earthx.catalog.registry import CoverageProvider, DatasetRegistry, UnknownDatasetError
from earthx.catalog.search_cache import PostgresSearchCache
from earthx.gateway import GatewayError, UpstreamError, UpstreamTimeout, UpstreamUnreachable

LOGGER = logging.getLogger("earthx.api.coverage")

# `local-sql` without a single coverage product has no density path built yet
# (M3-11c plan step §4.1 F4): a materialized time series would need its own
# zoomed-grid counting over `pgstac.items`, which no dataset needs in M3. With a
# single coverage product, `local-sql` *is* implemented — as the area way below,
# not through this set (it never goes through `IMPLEMENTED_PROVIDERS`, the same
# way `single_coverage_product` already skips it for `upstream-aggregation`/
# `sample`, see `_area_path`).
#
# Public because onboarding checklist point 2 reads it: "a coverage provider is
# assigned" is only worth anything if something answers for that provider
# (projektuebersicht.md §5, D4).
IMPLEMENTED_PROVIDERS = frozenset({CoverageProvider.UPSTREAM_AGGREGATION, CoverageProvider.SAMPLE})


def _area_path(config: Any) -> bool:
    """Whether this entry answers through the ``local-sql`` area way (M3-11c):
    the union of its own items' footprints, for a materialized one-off product.
    A one-off product with any other provider keeps the unchanged extent way
    below; ``local-sql`` without ``single_coverage_product`` is the density path
    that is not built (F4), and never reaches this function's caller as ``True``.
    """
    return config.capabilities.single_coverage_product and config.coverage.provider is CoverageProvider.LOCAL_SQL


def build_router(registry: DatasetRegistry = REGISTRY) -> APIRouter:
    """The router, built against ``registry`` — a parameter so a test can pass its
    own registry, the same shape ``api.tiler.build_app`` already uses.
    """
    router = APIRouter()

    @router.get("/coverage/{dataset_id}")
    async def get_coverage(
        request: Request,
        dataset_id: str,
        zoom: Annotated[int, Query(description="viewport zoom; the geotile level before adr/0004 §5's caps clamp it")],
        bbox: Annotated[str | None, Query(description="west,south,east,north")] = None,
        intersects: Annotated[str | None, Query(description="a GeoJSON Polygon or MultiPolygon")] = None,
        datetime: Annotated[
            str | None, Query(description="a STAC interval: an instant, start/end, start/.. or ../end")
        ] = None,
        max_cloud_cover: Annotated[float | None, Query(description="percentage, 0..100")] = None,
    ) -> dict[str, Any]:
        try:
            config = registry.get(dataset_id)
        except UnknownDatasetError:
            raise HTTPException(status_code=404, detail=f"no dataset {dataset_id!r}") from None

        area_path = _area_path(config)
        if config.capabilities.single_coverage_product and not area_path:
            # Checked before any other provider is asked, unchanged since M2-05b: a
            # one-off product answered by upstream aggregation or a sample has an
            # extent, not a density (adr/0004 §5, "Einmal-Produkte") — nothing here
            # reads a filter, the same as before M3-11c. `local-sql` is the one
            # provider this entry can pair with that answers a real question
            # instead (the area way, `area_path` above).
            return _serialise(extent_result(config.dataset_id, config.spatial_extent.bbox))

        if not area_path and config.coverage.provider not in IMPLEMENTED_PROVIDERS:
            # `local-sql` without `single_coverage_product` is the density path
            # M3-11c does not build (plan step §4.1 F4): no dataset needs it in M3.
            raise HTTPException(
                status_code=501,
                detail=f"{dataset_id!r} has no coverage answer yet ({config.coverage.provider.value})",
            )

        has_spatial_filter = bbox is not None or intersects is not None
        start, end = _datetime_bounds(datetime)
        try:
            query = CoverageQuery(
                dataset_id=dataset_id,
                level=level_for_viewport(zoom, config, has_spatial_filter=has_spatial_filter),
                bbox=_parse_bbox(bbox),
                intersects=_parse_intersects(intersects),
                start=start,
                end=end,
                max_cloud_cover=max_cloud_cover,
            )
        except InvalidCoverageQuery as error:
            raise HTTPException(status_code=400, detail=str(error)) from None

        # A filter this dataset structurally cannot honour is dropped here, once,
        # for every way — not left to each way to remember on its own (Otto,
        # 26.09.2026, M3-11c). `time_range=False` applies to any provider a future
        # dataset without a time axis might use; `max_cloud_cover` only to the area
        # way, which has no such property on a one-off product.
        ignored_filters: list[str] = []
        if not config.capabilities.time_range and (query.start is not None or query.end is not None):
            query = replace(query, start=None, end=None)
            ignored_filters.append("datetime")
        if area_path and query.max_cloud_cover is not None:
            query = replace(query, max_cloud_cover=None)
            ignored_filters.append("max_cloud_cover")

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
                result = await adapter_coverage(query, config, gateway=gateway, registry=registry)
            else:
                async with pool.connection() as conn:
                    result = await adapter_coverage(
                        query, config, gateway=gateway, registry=registry, cache=PostgresSearchCache(conn)
                    )
        except InvalidCoverageQuery as error:
            # `area_coverage`'s own defensive re-check of `check_intersects_is_valid`
            # (`local_coverage.py`) — the route above already validates the same
            # geometry before this call is ever made, so this is unreachable through
            # this route today, kept for a caller of `area_coverage` that skips it.
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
            # `UpstreamShapeError` is `sample_coverage`'s own search path
            # misbehaving (`federated_search.require_feature_list` and friends);
            # `UpstreamCoverageShapeError` is either way's own reading of the
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
                "ignored_filters": result.ignored_filters,
            },
        )
        return _serialise(result)

    return router


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


def _parse_intersects(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="intersects is not valid JSON") from None
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="intersects is not a GeoJSON object")
    return parsed


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


router = build_router()


__all__ = ["build_router", "router"]
