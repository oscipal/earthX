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
import os
from collections.abc import Callable
from typing import Annotated, Any, Literal, Protocol

import morecantile
import rasterio
from attrs import define, field
from fastapi import Depends, HTTPException, Path, Query, Request
from morecantile.defaults import TileMatrixSets
from rio_tiler.io import BaseReader
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import QueryParams
from titiler.core.factory import TilerFactory
from titiler.core.models.mapbox import TileJSON
from titiler.core.models.responses import Statistics
from titiler.core.resources.enums import ImageType
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

    # The registry's released zoom range (`earthx:viewer`), or ``None`` where a test
    # builds a factory without one. `access` may import `catalog` (architekturplan.md
    # 3.1), but the registry lookup itself needs the app's dataset id from the path
    # and lives in `api.tiler`, which is the only place composing this factory sees
    # both the request and the registry — so this stays a plain callable, the same
    # shape as ``stats_cache_dependency``.
    viewer_zoom_dependency: Callable[..., tuple[int, int] | None] = field(default=lambda: None)

    # The map viewer needs a URL it can paste; `/bbox` and `/feature` are the AOI
    # download of M2-06; OGC Maps is off in TiTiler itself. All three are decisions,
    # not omissions (adr/0006 §3.1).
    add_viewer: bool = False
    add_part: bool = False
    add_ogc_maps: bool = False
    # `/preview` is off for two reasons that point the same way (M2-10). It carries
    # no zoom, so the released-levels check of `api.tiler` has nothing to check it
    # against; and it computes no target resolution, so for a Zarr dataset it reads
    # the level the asset names — the native 10 m of sentinel-2-l2a-zarr3, the very
    # read the released range exists to prevent. Nothing asks for it: the viewer
    # builds tile URLs, and the browse preview is a tile on the coarsest released
    # level. A preview worth having would have to pick its own resolution, which is
    # a task of its own rather than a route left standing.
    add_preview: bool = False

    # One tile matrix set, because the released range is a range of *its* levels
    # (`earthx:viewer`, measured in WebMercatorQuad — adr/0007 §12.10). z14 in
    # WorldCRS84Quad is roughly one WebMercator level finer, so a second grid would
    # let the same number mean two resolutions and walk straight through the check.
    # It is also the only grid the client asks for (`frontend/src/api.ts`).
    supported_tms: TileMatrixSets = TileMatrixSets({"WebMercatorQuad": morecantile.tms.get("WebMercatorQuad")})

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

    def tilejson(self) -> None:  # noqa: C901
        """Register ``GET /{tileMatrixSetId}/tilejson.json`` — TiTiler's, with one change.

        ``minzoom``/``maxzoom`` default to the registry's released range
        (``viewer_zoom_dependency``) instead of rio-tiler's reader-computed ones (M3-04,
        the gap ``api.tiler._check_zoom_released`` used to leave open): a client that
        builds its tile requests from this document, rather than the fixed range the
        viewer already hardcodes, is then bounded by the same range the tile route
        enforces.

        **Deliberate departure from TiTiler's own precedence:** TiTiler lets an
        explicit ``minzoom``/``maxzoom`` query parameter overwrite its default
        outright, trusting the caller. Once the default is a *released* range rather
        than a reader's computed one, that trust would defeat the point of releasing
        one at all — a caller could read its own out-of-range value straight back out
        of a query parameter it set itself and still be sent to a level the tile
        route refuses. So here an explicit value is honoured only within the
        registry's range (:func:`_validate_zoom_override`): narrowing or shifting the
        advertised range is still a caller's choice, but a value outside it, or a
        ``minzoom`` above ``maxzoom``, is the same ``400`` the tile route itself gives
        a level nobody serves. Where there is no released range at all
        (``viewer_zoom`` is ``None`` — a factory built without the dependency, as
        some tests do), nothing is validated and TiTiler's original precedence holds.

        Everything else — the tile URL, the reader-derived bounds and metadata — is
        unchanged from TiTiler's own implementation; only the zoom source differs.
        """

        def tilejson(
            request: Request,
            tileMatrixSetId,
            tilesize: Annotated[
                int | None,
                Query(gt=0, description="Tilesize in pixels. Default to 512."),
            ] = 512,
            tile_format: Annotated[
                ImageType | None,
                Query(
                    description="Default will be automatically defined if the output image needs a mask (png) or not (jpeg)."
                ),
            ] = None,
            minzoom: Annotated[
                int | None,
                Query(description="Overwrite default minzoom, within the dataset's released range."),
            ] = None,
            maxzoom: Annotated[
                int | None,
                Query(description="Overwrite default maxzoom, within the dataset's released range."),
            ] = None,
            src_path=Depends(self.path_dependency),
            reader_params=Depends(self.reader_dependency),
            tile_params=Depends(self.tile_dependency),
            layer_params=Depends(self.layer_dependency),
            dataset_params=Depends(self.dataset_dependency),
            post_process=Depends(self.process_dependency),
            colormap=Depends(self.colormap_dependency),
            render_params=Depends(self.render_dependency),
            env=Depends(self.environment_dependency),
            viewer_zoom=Depends(self.viewer_zoom_dependency),
        ):
            """Return TileJSON document for a dataset."""
            _validate_zoom_override(
                minzoom, maxzoom, viewer_zoom, dataset=str(request.path_params.get("dataset"))
            )
            route_params = {
                "z": "{z}",
                "x": "{x}",
                "y": "{y}",
                "tileMatrixSetId": tileMatrixSetId,
            }
            if tile_format:
                route_params["format"] = tile_format.value
            tiles_url = self.url_for(request, "tile", **route_params)

            qs_key_to_remove = [
                "tilematrixsetid",
                "tile_format",
                "minzoom",
                "maxzoom",
            ]
            qs: list[tuple[str, Any]] = [
                (key, value) for (key, value) in request.query_params._list if key.lower() not in qs_key_to_remove
            ]
            if "tilesize" not in request.query_params:
                qs.append(("tilesize", str(tilesize)))
            tiles_url += f"?{QueryParams(qs)}"

            tms = self.supported_tms.get(tileMatrixSetId)
            with rasterio.Env(**env):
                LOGGER.info(f"opening data with reader: {self.reader}")
                with self.reader(src_path, tms=tms, **reader_params.as_dict()) as src_dst:
                    default_minzoom, default_maxzoom = (
                        viewer_zoom if viewer_zoom is not None else (src_dst.minzoom, src_dst.maxzoom)
                    )
                    body = {
                        "bounds": src_dst.get_geographic_bounds(tms.rasterio_geographic_crs),
                        "minzoom": minzoom if minzoom is not None else default_minzoom,
                        "maxzoom": maxzoom if maxzoom is not None else default_maxzoom,
                        "tiles": [tiles_url],
                        "attribution": os.environ.get("TITILER_DEFAULT_ATTRIBUTION"),
                    }

                    # Custom TiTiler tilejson fields
                    body["raster_layers"] = self.get_renders(src_dst)

                    info = src_dst.info()
                    body["band_descriptions"] = getattr(info, "band_descriptions", None)
                    body["data_type"] = getattr(info, "dtype", None)
                    body["minmax"] = getattr(info, "minmax", None)

            return body

        # `tileMatrixSetId`'s choices depend on `self.supported_tms`, a value that
        # only exists once this method runs. Under `from __future__ import
        # annotations` every other annotation above is a string too, resolved lazily
        # against the module's globals — which never include `self`. Assigning the
        # already-built type here, after `def`, skips that lazy resolution entirely
        # (`typing.get_type_hints` only evaluates a *string* annotation), the same way
        # TiTiler's own module manages it by not using postponed annotations at all.
        tilejson.__annotations__["tileMatrixSetId"] = Annotated[
            Literal[tuple(self.supported_tms.list())],
            Path(description="Identifier selecting one of the TileMatrixSetId supported."),
        ]
        self.router.get(
            "/{tileMatrixSetId}/tilejson.json",
            response_model=TileJSON,
            responses={200: {"description": "Return a tilejson"}},
            response_model_exclude_none=True,
            operation_id=f"{self.operation_prefix}getTileJSON",
        )(tilejson)


def _validate_zoom_override(
    minzoom: int | None, maxzoom: int | None, viewer_zoom: tuple[int, int] | None, *, dataset: str
) -> None:
    """An explicit ``minzoom``/``maxzoom`` may narrow the released range, never leave it.

    See the "Deliberate departure" note on :meth:`EarthxTilerFactory.tilejson` for
    why this exists at all. A dataset without a released range validates nothing
    (``viewer_zoom`` is ``None``), the same as TiTiler's own, unrestricted override.
    """
    if viewer_zoom is None:
        return
    viewer_min, viewer_max = viewer_zoom
    for name, value in (("minzoom", minzoom), ("maxzoom", maxzoom)):
        if value is not None and not viewer_min <= value <= viewer_max:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{name} {value} is not released for {dataset!r}, "
                    f"which serves z{viewer_min} to z{viewer_max}"
                ),
            )
    final_min = minzoom if minzoom is not None else viewer_min
    final_max = maxzoom if maxzoom is not None else viewer_max
    if final_min > final_max:
        raise HTTPException(status_code=400, detail=f"minzoom {final_min} is above maxzoom {final_max}")


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
