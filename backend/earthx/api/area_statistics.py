"""The statistics of an order's area, as its result would carry them (NM4-19, adr/0006 Nachtrag NM4-19).

``POST /collections/{dataset}/statistics`` takes the order the processing panel builds for a job —
the order itself, without the envelope of the job route — and answers with the ``statistics`` of the
AOI its result would carry. The order becomes a recipe through the job's own intake
(:func:`~earthx.api.intake.estimate_order`, no request to an asset), the recipe is read and counted
by the job's own code (:func:`~earthx.processing.core.area_statistics`): the colour scale of the
preview is then the one of the result.

The AOI travels in the body and nowhere else: the path names the dataset only, the access log writes
method, path, status and duration (`earthx.logging`), and the one line of this route names no
area, no item and no key. The key of the cache is a hash over the recipe and with it over the AOI
(Q8): it lives as long as a recipe does (Q10, :data:`AREA_STATISTICS_TTL_S`), and stays in this
process and the database.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from typing import Any

import rasterio
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from rasterio.errors import RasterioError, RasterioIOError
from starlette.concurrency import run_in_threadpool

import earthx
from earthx.access.aoi_upload import MAX_AOI_POINTS
from earthx.access.tiles import StatsCache
from earthx.api.item_source import OrderRefused
from earthx.objectstore.results import RESULT_TTL

__all__ = [
    "AREA_STATISTICS_ROUTE",
    "AREA_STATISTICS_TTL_S",
    "MAX_AREA_BODY_BYTES",
    "MAX_AREA_FILES",
    "area_statistics_cache_key",
    "area_statistics_endpoint",
]

LOGGER = logging.getLogger("earthx.api.area_statistics")

AREA_STATISTICS_ROUTE = "/collections/{dataset}/statistics"

#: The cap of the job route (`processing_route.MAX_BODY_BYTES`, Otto's answer 3); a test holds the two equal.
MAX_AREA_BODY_BYTES = 1_048_576

#: Files a measure opens at most, scenes times assets (KE4): each costs about a second cold, one after the other.
MAX_AREA_FILES = 16

#: As long as a recipe lives (Q10): the key is a hash over the AOI.
AREA_STATISTICS_TTL_S = RESULT_TTL.total_seconds()

#: A read failure is tried once more with freshly opened files, as the GET statistics do.
_READ_ATTEMPTS = 2


def area_statistics_cache_key(recipe: Any) -> str:
    """The key of one measure: the recipe without its ``recipe_id``, and the version that counts it.

    A hash of the recipe's own hash, which is internal (Q8); it is never logged, never in a URL and never
    in an answer.
    """
    from earthx.processing.recipe import recipe_hash

    payload = json.dumps(
        {"kind": "area-statistics/v2", "earthx": earthx.__version__, "recipe": recipe_hash(recipe)},
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _read_body(request: Request) -> bytes:
    """The body within the cap, read until the cap and no further (KE3)."""
    media = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media != "application/json":
        raise HTTPException(status_code=415, detail="send the order as application/json")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_AREA_BODY_BYTES:
        raise HTTPException(status_code=413, detail=f"the order is over the {MAX_AREA_BODY_BYTES} byte cap")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_AREA_BODY_BYTES:
            raise HTTPException(status_code=413, detail=f"the order is over the {MAX_AREA_BODY_BYTES} byte cap")
        chunks.append(chunk)
    if not size:
        raise HTTPException(status_code=400, detail="the request has no body")
    return b"".join(chunks)


def _positions(coordinates: Any) -> int:
    """How many positions a GeoJSON ``coordinates`` array holds; what is not one the intake refuses later.

    Without recursion, so that an array nested a thousand deep is counted, not a ``RecursionError``.
    """
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


def _check_order(raw: bytes, dataset: str) -> None:
    """What can be refused before the intake fetches an item: no area, too many positions, another dataset.

    Anything else that is wrong with the order is the intake's to say, in its own words.
    """
    try:
        order = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="the order is not JSON") from None
    except RecursionError:
        raise HTTPException(status_code=400, detail="the order is nested too deeply") from None
    if not isinstance(order, dict):
        raise HTTPException(status_code=422, detail="the order is a JSON object")
    aoi = order.get("aoi")
    if aoi is None:
        raise HTTPException(status_code=422, detail="aoi: the area is measured for an order with an AOI only")
    if isinstance(aoi, dict) and _positions(aoi.get("coordinates")) > MAX_AOI_POINTS:
        raise HTTPException(status_code=413, detail=f"aoi: the area has more than {MAX_AOI_POINTS} positions")
    inputs = order.get("inputs")
    if isinstance(inputs, list) and inputs and isinstance(inputs[0], dict) and "dataset" in inputs[0]:
        if inputs[0]["dataset"] != dataset:
            raise HTTPException(status_code=422, detail="inputs: the order is for another dataset than the path names")


def _measure(recipe: Any, env: dict[str, str]) -> Any:
    from earthx.processing import core
    from earthx.processing.statistics import MEASURE_PERCENTILES

    for attempt in range(_READ_ATTEMPTS):
        try:
            with rasterio.Env(**env):
                return core.area_statistics(
                    recipe, max_pixels=core.MAX_AREA_PIXELS, extra_percentiles=MEASURE_PERCENTILES
                )
        except RasterioIOError:
            # GDAL's text names the address it could not read; only the fact goes to the log.
            if attempt + 1 == _READ_ATTEMPTS:
                raise HTTPException(status_code=502, detail="the asset could not be read from the source") from None
            LOGGER.warning("could not read the asset from the source, retrying once")
        except RasterioError as error:
            # Not the tiler's handler, which logs the traceback: GDAL's text can name the address here too.
            LOGGER.error("the asset could not be processed", extra={"error_type": type(error).__name__})
            raise HTTPException(status_code=500, detail="the asset could not be processed") from None
    raise AssertionError("unreachable")


def _refusal(error: Exception) -> HTTPException | None:
    """The status of a refusal of the worker core, or ``None`` for an error that is no refusal."""
    from earthx.processing.errors import (
        AoiOutsideInputs,
        GridMismatch,
        RecipeInvalid,
        ScalingMismatch,
        UnsupportedRecipe,
    )

    for kind, status in (
        (AoiOutsideInputs, 422),
        (RecipeInvalid, 422),
        (GridMismatch, 422),
        (UnsupportedRecipe, 422),
        (ScalingMismatch, 502),
    ):
        if isinstance(error, kind):
            return HTTPException(status_code=status, detail=str(error))
    return None


async def _cached(cache: StatsCache | None, key: str) -> dict[str, Any] | None:
    if cache is None:
        return None
    try:
        return await cache.get(key)
    except Exception as error:
        # The text of a database error can repeat the values of the statement: the kind of error only.
        LOGGER.warning("statistics cache unreadable, measuring instead", extra={"error_type": type(error).__name__})
        return None


async def _store(cache: StatsCache | None, key: str, value: dict[str, Any], dataset: str) -> None:
    if cache is None:
        return
    try:
        await cache.set(key, value, dataset_id=dataset, ttl_s=AREA_STATISTICS_TTL_S)
    except Exception as error:
        LOGGER.warning("statistics cache not writable, answer is not stored", extra={"error_type": type(error).__name__})


def area_statistics_endpoint(cache_dependency: Callable[..., Any]) -> Callable[..., Any]:
    """The route, with the statistics cache of the tiler (``api.tiler.area_statistics_cache``) as its dependency."""

    async def area_statistics_route(
        request: Request, dataset: str, cache: StatsCache | None = Depends(cache_dependency)
    ) -> JSONResponse:
        """The statistics of the AOI the result of this order would carry (NM4-19)."""
        from earthx.api.intake import estimate_order
        from earthx.processing.operators import REGISTRY

        raw = await _read_body(request)
        _check_order(raw, dataset)
        state = request.app.state
        try:
            recipe = (
                await estimate_order(
                    raw,
                    registry=state.earthx_registry,
                    operators=REGISTRY,
                    item_source=state.earthx_item_source,
                    announce=False,
                )
            ).recipe
        except OrderRefused as refused:
            raise HTTPException(status_code=refused.status_code, detail=refused.detail) from None
        entry = recipe.inputs[0]
        files = len(entry.groups[0]) * len(entry.assets)
        if files > MAX_AREA_FILES:
            raise HTTPException(
                status_code=413, detail=f"a measure opens at most {MAX_AREA_FILES} files (scenes times assets), not {files}"
            )
        key = area_statistics_cache_key(recipe)
        started = time.monotonic()
        answer = await _cached(cache, key)
        cached = answer is not None
        if answer is None:
            try:
                measured = await run_in_threadpool(_measure, recipe, state.earthx_gdal_options)
            except Exception as error:
                refusal = _refusal(error)
                if refusal is None:
                    raise
                raise refusal from None
            answer = {"bands": measured.bands, "exact": measured.exact, "factor": measured.factor}
            await _store(cache, key, answer, entry.dataset)
            pixels = measured.pixels_read
        else:
            pixels = 0
        LOGGER.info(
            "area statistics measured",
            extra={
                "dataset": entry.dataset,
                "scenes": len(entry.groups[0]),
                "assets": len(entry.assets),
                "factor": answer["factor"],
                "pixels_read": pixels,
                "cached": cached,
                "seconds": round(time.monotonic() - started, 3),
            },
        )
        return JSONResponse(answer, headers={"Cache-Control": "no-store"})

    return area_statistics_route
