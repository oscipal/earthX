"""Tiles and statistics for one item of one dataset (adr/0006 §5, Option B).

The routes are TiTiler's, not ours: `titiler.core`'s ``TilerFactory`` already
carries tiles, tilejson, info, statistics and preview, and adr/0006 §3.1 measured
that replacing its ``path_dependency`` takes the free ``url`` parameter out of the
OpenAPI schema altogether. What is left to do here is small and is exactly the
three things TiTiler leaves open:

* **which reader opens the data** — :func:`open_asset`, which hands a COG path to
  :class:`earthx.readers.cog.CogReader` and a Zarr asset to
  :class:`earthx.readers.zarr_reader.ZarrReader` (M2-09a); both refuse anything the
  gateway has not cleared;
* **which routes exist** — no viewer (it would need a free URL to be useful), no
  ``/bbox`` and no ``/feature`` (the AOI download is M2-06), no OGC Maps;
* **statistics with a cache**, because a cold read costs the ~1 s adr/0006 §3.4
  measured, and it is the same second before every first tile of a view.

What is deliberately *not* here: `gateway`. `access` may not import it
(architekturplan.md 3.1), which is why the process entrypoint moved to
``earthx.api.tiler`` (adr/0006 §5.1, Otto's answer 5) — that module builds the
two dependencies this factory hangs them on.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from typing import Any, Protocol

import rasterio
from attrs import define, field
from fastapi import Depends
from rio_tiler.io import BaseReader
from starlette.concurrency import run_in_threadpool
from titiler.core.factory import TilerFactory
from titiler.core.models.responses import Statistics
from titiler.core.resources.responses import JSONResponse

from earthx.readers.cog import AssetPath, CogReader
from earthx.readers.zarr_reader import ZarrAsset, ZarrReader

LOGGER = logging.getLogger("earthx.access.tiles")


def open_asset(src_path: Any, **reader_params: Any) -> BaseReader:
    """Open what the path dependency built — a COG path or a Zarr asset (M2-09a).

    The format is decided in the registry and applied in ``earthx.api.tiler``, which
    is the only place that sees the entry; by the time a path gets here it already
    *is* one of the two, so the dispatch reads it off the type rather than asking a
    catalogue `access` may not reach at render time.

    A function, not a class, because that is all TiTiler's factory needs of
    ``reader``: it calls it and enters the result (``with self.reader(src_path, …)``).
    """
    if isinstance(src_path, ZarrAsset):
        return ZarrReader(src_path, **reader_params)
    return CogReader(src_path, **reader_params)


class StatsCache(Protocol):
    """What the statistics endpoint needs of a cache — structurally, not by import.

    `catalog`'s ``PostgresStatsCache`` fits it; so does anything a test hands in.
    `access` never learns that there is a database behind it (KLAERUNGEN B9 is about
    the worker core, but the same reason applies: a render path that imports a
    driver is a render path that cannot run without one).
    """

    async def get(self, key: str) -> dict[str, Any] | None: ...

    async def set(self, key: str, value: dict[str, Any], *, dataset_id: str) -> None: ...


def statistics_cache_key(path: AssetPath | ZarrAsset, parameters: dict[str, Any]) -> str:
    """One key for one question: which asset, and everything that shapes the numbers.

    Both readers' paths answer to the same three names, so a Zarr statistic is cached
    the same way a COG's is — the format does not change what the numbers are of.

    A hash rather than the values themselves, so that no address and no parameter
    text ends up in a database column (projektplan.md 7, point 6).
    """
    payload = json.dumps(
        {
            "dataset": path.dataset_id,
            "item": path.item_id,
            "asset": path.asset,
            "parameters": parameters,
        },
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@define(kw_only=True)
class EarthxTilerFactory(TilerFactory):
    """TiTiler's tiler factory with our reader, our route set and a cached statistic."""

    reader: Callable[..., BaseReader] = open_asset

    # A cache is optional everywhere it appears: without one this is slower, never
    # wrong (E5, adr/0001 §9.3). The default is "no cache", so a factory built in a
    # test needs nothing.
    stats_cache_dependency: Callable[..., StatsCache | None] = field(default=lambda: None)

    # The map viewer needs a URL it can paste; `/bbox` and `/feature` are the AOI
    # download of M2-06; OGC Maps is off in TiTiler itself. All three are decisions,
    # not omissions (adr/0006 §3.1).
    add_viewer: bool = False
    add_part: bool = False
    add_ogc_maps: bool = False

    def statistics(self) -> None:
        """Register ``GET /statistics`` — the same answer as TiTiler's, with a cache.

        Only the GET variant. TiTiler's second, POST-with-GeoJSON statistics is the
        statistic of an area of interest; that belongs with the AOI paths of M2-06,
        and a route nobody has thought about is a route nobody has secured.
        """

        @self.router.get(
            "/statistics",
            response_class=JSONResponse,
            response_model=Statistics,
            responses={200: {"content": {"application/json": {}}, "description": "Return dataset's statistics."}},
            operation_id=f"{self.operation_prefix}getStatistics",
        )
        async def statistics(
            src_path=Depends(self.path_dependency),
            reader_params=Depends(self.reader_dependency),
            layer_params=Depends(self.layer_dependency),
            dataset_params=Depends(self.dataset_dependency),
            image_params=Depends(self.img_preview_dependency),
            stats_params=Depends(self.stats_dependency),
            histogram_params=Depends(self.histogram_dependency),
            env=Depends(self.environment_dependency),
            cache=Depends(self.stats_cache_dependency),
        ) -> dict[str, Any]:
            """Statistics of one asset, over the whole scene."""
            parameters = {
                "layer": layer_params.as_dict(),
                "dataset": dataset_params.as_dict(),
                "image": image_params.as_dict(),
                "stats": stats_params.as_dict(),
                "histogram": histogram_params.as_dict(),
            }
            key = None
            if cache is not None and isinstance(src_path, (AssetPath, ZarrAsset)):
                key = statistics_cache_key(src_path, parameters)
                cached = await _cache_get(cache, key)
                if cached is not None:
                    return cached

            # The read is blocking (GDAL over HTTP range requests) and belongs in a
            # thread, not on the event loop this endpoint shares with every other
            # request of the process.
            statistics = await run_in_threadpool(
                _read_statistics,
                self.reader,
                src_path,
                env=env,
                reader_params=reader_params.as_dict(),
                layer_params=layer_params.as_dict(),
                dataset_params=dataset_params.as_dict(),
                image_params=image_params.as_dict(),
                stats_params=stats_params.as_dict(),
                histogram_params=histogram_params.as_dict(),
            )
            if key is not None:
                await _cache_set(cache, key, statistics, dataset_id=src_path.dataset_id)
            return statistics


def _read_statistics(
    reader: Callable[..., BaseReader],
    src_path: AssetPath | ZarrAsset,
    *,
    env: dict[str, str],
    reader_params: dict[str, Any],
    layer_params: dict[str, Any],
    dataset_params: dict[str, Any],
    image_params: dict[str, Any],
    stats_params: dict[str, Any],
    histogram_params: dict[str, Any],
) -> dict[str, Any]:
    """TiTiler's own statistics, as plain JSON.

    Plain JSON and not the models, because the same value goes into the cache and
    comes back out of it: a cache hit and a cold read are then the same answer by
    construction, not by inspection.
    """
    with rasterio.Env(**env):
        with reader(src_path, **reader_params) as src_dst:
            image = src_dst.preview(**layer_params, **image_params, **dataset_params)
            statistics = image.statistics(**stats_params, hist_options=histogram_params)
    return {name: value.model_dump(mode="json") for name, value in statistics.items()}


async def _cache_get(cache: StatsCache, key: str) -> dict[str, Any] | None:
    try:
        return await cache.get(key)
    except Exception:
        # E5: a cache that fails makes the platform slower, never wrong. Broad on
        # purpose — whatever the store does, the answer is read from the asset.
        LOGGER.warning("statistics cache unreadable, reading the asset instead", exc_info=True)
        return None


async def _cache_set(cache: StatsCache, key: str, value: dict[str, Any], *, dataset_id: str) -> None:
    try:
        await cache.set(key, value, dataset_id=dataset_id)
    except Exception:
        # The answer is already in hand; failing now would throw it away over bookkeeping.
        LOGGER.warning("statistics cache not writable, answer is not stored", exc_info=True)
