"""``GET /coverage/{dataset_id}``: the coverage seam wired to `api` (M2-05b).

At the base app, beside ``/health`` and outside ``/stac`` (plans/m2-05-coverage.md
§6.6, F1 a): the answer is not a STAC object, and ``/stac`` stays the namespace of
the standard, in case the real STAC aggregation extension lands there one day.

What this module adds beyond ``catalog.coverage`` and ``adapters.earth_search_coverage``
is deliberately small (Otto's scope for M2-05b): reading the query parameters, turning
them into a checked :class:`~earthx.catalog.coverage.CoverageQuery`, and mapping every
error to a status code. Two things the scope names explicitly:

* **The source's response body never reaches the answer or a log line** (plan §3.5).
  ``gateway.UpstreamError`` carries an excerpt for the traceback and for
  :mod:`earthx.adapters.earth_search_coverage`'s own tests, but this route never
  reads ``error.excerpt`` — only the status the exception type already names.
* **Nothing here logs an AOI.** The one log line this route writes carries
  ``dataset_id``, the clamped ``level``, ``completeness`` and the answer's origin —
  never ``bbox``, ``intersects`` or ``max_cloud_cover``.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from stac_fastapi.types.rfc3339 import str_to_interval

from earthx.adapters.earth_search_coverage import aggregate_coverage
from earthx.adapters.eopf_sample_coverage import sample_coverage
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
from earthx.catalog.registry import CoverageProvider, DatasetRegistry, UnknownDatasetError
from earthx.catalog.search_cache import PostgresSearchCache
from earthx.gateway import GatewayError, UpstreamError, UpstreamTimeout, UpstreamUnreachable

LOGGER = logging.getLogger("earthx.api.coverage")

# local-sql (adr/0004 §5) has no caller yet — no dataset in M2 has its own items
# in pgstac (plan §8). Both other ways do, and share the `CoverageSource` seam.
_IMPLEMENTED_PROVIDERS = frozenset({CoverageProvider.UPSTREAM_AGGREGATION, CoverageProvider.SAMPLE})


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

        # Checked before any provider is asked: a one-off product has an extent, not
        # a density (adr/0004 §5, "Einmal-Produkte"), and registry.py already refuses
        # to pair the flag with upstream aggregation — so this can never fall through
        # to the density path by mistake.
        if config.capabilities.single_coverage_product:
            return _serialise(extent_result(config.dataset_id, config.spatial_extent.bbox))

        if config.coverage.provider not in _IMPLEMENTED_PROVIDERS:
            # local-sql has no caller yet (plan §8: "kein Datensatz in M2 hat
            # eigene Items im pgstac"); upstream-aggregation and sample both do
            # (M2-05b, M2-09b-3).
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

        # Same seam either way (`CoverageSource`, adr/0004 §5): both answer
        # `(query, config, *, gateway, registry, cache=None)`, so the registry
        # entry alone decides which one is asked.
        is_upstream = config.coverage.provider is CoverageProvider.UPSTREAM_AGGREGATION
        source = aggregate_coverage if is_upstream else sample_coverage
        gateway = request.app.state.earthx_gateway
        pool = getattr(request.app.state, "earthx_cache_pool", None)
        try:
            if pool is None:
                result = await source(query, config, gateway=gateway, registry=registry)
            else:
                async with pool.connection() as conn:
                    result = await source(
                        query, config, gateway=gateway, registry=registry, cache=PostgresSearchCache(conn)
                    )
        except CoverageProviderMismatch as error:
            # Reachable only if the registry and this route disagree about the
            # dataset's provider, which the check above already rules out — kept as
            # a 501 rather than an assertion, because a wrong answer here must never
            # look like a wrong AOI.
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

        LOGGER.info(
            "coverage answered",
            extra={
                "dataset": dataset_id,
                "level": result.level,
                "completeness": result.completeness.value,
                "from_cache": result.from_cache,
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
    }


def _instant(value: Any) -> str:
    return value.isoformat().replace("+00:00", "Z")


router = build_router()


__all__ = ["build_router", "router"]
