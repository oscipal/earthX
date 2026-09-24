"""Process entrypoint for `tiler` (architekturplan.md 3.2, adr/0006 §5.1).

It used to be ``earthx.access.main``. It moved here because the tile path needs
three things from `gateway` — a :class:`Policy` built from the registry,
``check_url`` and ``gdal_options`` — and `access` may not import `gateway`
(architekturplan.md 3.1). `api` is the module that composes; so the composition
lives here and `access` keeps the rendering (Otto's answer 5 of 20.09.2026).

What is composed:

* **the path dependency** — ``dataset`` and ``item`` from the path, ``asset``
  from the query, resolved through the registry and the adapter into an
  :class:`~earthx.readers.cog.AssetPath` or, where the registry says the dataset is
  Zarr, a :class:`~earthx.readers.zarr_reader.ZarrAsset` (M2-09a). This is the only
  place in the process where an address is built, the only place the format is
  decided, and it cannot build either without ``check_url``. There is no free
  ``url`` parameter anywhere in the schema; a test proves it.
* **the environment dependency** — ``gdal_options(policy)``, so the central GDAL
  configuration of M1-03 applies at every endpoint rather than wherever someone
  remembered it.
* **the caches** — the item cache the adapter already had (24 h, so a tile does
  not re-fetch the item), the statistics cache of adr/0006 (30 days), and the
  resolver cache of M2-14 (5 s, so a batch of tiles resolves the asset host once
  rather than once per tile). All three are optional in the same sense: without
  them the tiler is slower, never wrong (E5), and none of them caches a verdict —
  every address still passes ``check_addresses`` on every request.

The image is fully determined by the URL (adr/0001 Z4): the asset is named in it,
the stretch travels as ``rescale``/``colormap_name``, and nothing here is
remembered between two requests. Two instances answer the same URL with the same
bytes, which is what makes the answers cacheable in front of the process.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

import morecantile
from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from rasterio.errors import RasterioError, RasterioIOError
from rasterio.warp import transform_bounds
from rio_tiler.errors import RioTilerError, TileOutsideBounds
from starlette.concurrency import run_in_threadpool

from earthx.access.download import (
    AoiOutsideItems,
    AoiTooLarge,
    AssetCrop,
    InvalidAoi,
    build_download_zip,
    check_size_cap,
    filter_items_intersecting_aoi,
    parse_aoi_geometry,
)
from earthx.access.tiles import EarthxTilerFactory, open_asset
from earthx.adapters import (
    InvalidQuery,
    UnknownCollection,
    UnsupportedSource,
    get_item,
)
from earthx.api.dependencies import cache_pool, policy_from_registry
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import (
    DataFormat,
    DatasetConfig,
    DatasetRegistry,
    LicenseTier,
    UnknownDatasetError,
)
from earthx.catalog.search_cache import PostgresSearchCache
from earthx.catalog.stats_cache import PostgresStatsCache
from earthx.gateway import CachingResolver, Gateway, GatewayError, UpstreamError, UpstreamTimeout, UrlRejected
from earthx.gateway.gdal import gdal_options
from earthx.readers.cog import AssetPath, asset_path
from earthx.readers.zarr_reader import ZarrAsset, ZarrAssetError, split_asset_key, zarr_asset

LOGGER = logging.getLogger("earthx.api.tiler")

# One item of one collection, the same shape the STAC API of `api` uses for the
# metadata of that very item. The tiler answers under its own port (docker-compose),
# so the two never collide.
ROUTER_PREFIX = "/collections/{dataset}/items/{item}"

# The formats a reader exists for. `LEGACY` is the prototype's shape and has none
# in the target path, so it is a 501 rather than an attempt (adr/0007 §6 point 2).
_READABLE_FORMATS = frozenset({DataFormat.COG, DataFormat.ZARR})

# The download route (M2-06) names only the dataset in its path — the item(s) and
# the asset(s) travel in the body (a mosaic can name several of each, and an AOI
# polygon does not belong in a query string) — so it cannot share ROUTER_PREFIX.
DOWNLOAD_ROUTE = "/collections/{dataset}/download"


def _resolve_asset_href(item: dict[str, Any], asset: str) -> str:
    """The address of one asset, or a 404 that says which of the two is missing."""
    assets = item.get("assets")
    entry = assets.get(asset) if isinstance(assets, dict) else None
    href = entry.get("href") if isinstance(entry, dict) else None
    if not isinstance(href, str):
        raise HTTPException(status_code=404, detail=f"the item carries no asset {asset!r}")
    return href


async def _fetch_item(state: Any, dataset: str, item: str) -> dict[str, Any]:
    """The item, or the ``HTTPException`` its absence or the source's failure maps to.

    Shared by :func:`dataset_asset_path` and the download route of M2-06 — both
    turn a ``dataset``/``item`` pair into a STAC item through the same cached
    ``earthx_item_source``, and a source failure means the same thing to a tile
    request and a crop request.
    """
    try:
        return await state.earthx_item_source(dataset, item)
    except UnknownCollection:
        raise HTTPException(status_code=404, detail=f"no dataset {dataset!r}") from None
    except UnsupportedSource as error:
        raise HTTPException(status_code=501, detail=str(error)) from None
    except InvalidQuery as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    except UpstreamError as error:
        if error.status_code == 404:
            raise HTTPException(status_code=404, detail=f"no item {item!r} in {dataset!r}") from None
        # The source answered something we do not pass on. Its text is not repeated:
        # it can carry the query, and the query can carry an AOI (projektplan.md 7).
        raise HTTPException(status_code=502, detail="the source did not deliver the item") from None
    except UpstreamTimeout:
        raise HTTPException(status_code=504, detail="the source did not answer in time") from None
    except GatewayError:
        # Unreachable, too large, too many redirects: the source's side of the line.
        # Broad on purpose — a gateway error that has no branch of its own is still an
        # answer about the source, and a 500 would call it our mistake.
        raise HTTPException(status_code=502, detail="the item could not be fetched") from None


def _proj_code(stac_item: dict[str, Any]) -> str | None:
    """The item's own CRS, in either spelling STAC has for it.

    ``proj:code`` is the projection extension v2, ``proj:epsg`` the v1 field our own
    API still emits (adr/0007 §6 point 4). A Zarr store may carry no CRS at all
    (§3.4), and then this is the only place it can come from; where the store does
    carry one, this stays the fallback.
    """
    properties = stac_item.get("properties")
    if not isinstance(properties, dict):
        return None
    code = properties.get("proj:code")
    if isinstance(code, str) and code:
        return code
    epsg = properties.get("proj:epsg")
    return f"EPSG:{epsg}" if isinstance(epsg, int) else None


# Forced onto the coarsest `multiscales` level there is: adr/0007 §12.11 point 8
# measured the difference against a fine level at ~5% in `p98`, and the read stays
# cheap regardless of where on the extent the item sits.
_COARSEST_LEVEL = float("inf")


def _target_gsd(request: Request, stac_item: dict[str, Any]) -> float | None:
    """The ground sample distance a Zarr read should aim for, or ``None`` to leave
    the level exactly as the asset names it.

    Three cases, and only three — everything else reads the level the item's asset
    already points at, unchanged since M2-09a:

    * **``/statistics``** is answered on the coarsest level there is (§12.11 point 8).
    * **a tile request** names ``z``/``x``/``y``/``tileMatrixSetId`` in its own route
      (TiTiler's own path, matched here through ``request.path_params`` rather than
      a parameter of this function, so nothing here has to repeat TiTiler's route
      shape). The real ground resolution of that tile is computed from its own
      bounds, reprojected into the item's CRS — not read off a fixed zoom table,
      because a Web Mercator tile's real resolution scales with ``cos(latitude)``
      (adr/0007 §12.10) and a table would pick the wrong level near either end of
      this dataset's 34°–72° N extent.
    * **anything else** (a preview, the AOI crop) computes nothing and returns
      ``None`` — a crop wants the resolution its asset names, not the coarsest
      level statistics settles for.
    """
    if request.url.path.endswith("/statistics"):
        return _COARSEST_LEVEL
    path_params = request.path_params
    if not {"z", "x", "y", "tileMatrixSetId"} <= path_params.keys():
        return None
    crs = _proj_code(stac_item)
    if crs is None:
        return None
    try:
        tms = morecantile.tms.get(str(path_params["tileMatrixSetId"]))
        z = int(path_params["z"])
        west, south, east, north = tms.bounds(int(path_params["x"]), int(path_params["y"]), z)
        item_west, _, item_east, _ = transform_bounds("EPSG:4326", crs, west, south, east, north)
        tile_size = tms.matrix(z).tileWidth
    except Exception:
        # A resolution this cannot compute (an unknown TMS id, a CRS transform
        # that fails) is not worth failing the tile over — it reads the level the
        # asset names instead, the same as before this feature existed.
        LOGGER.warning("could not compute a target resolution for the tile", exc_info=True)
        return None
    return abs(item_east - item_west) / tile_size


def _dataset_config(state: Any, dataset: str) -> DatasetConfig:
    """The registry entry for ``dataset``, or a 404.

    adr/0005 rule I: an unknown collection is a 404 and not an empty answer that
    looks valid. Every route of this process starts here, so the refusal reads the
    same whether it came from a tile, the statistics or a crop.
    """
    registry: DatasetRegistry = state.earthx_registry
    try:
        return registry.get(dataset)
    except UnknownDatasetError:
        raise HTTPException(status_code=404, detail=f"no dataset {dataset!r}") from None


def _check_zoom_released(request: Request, config: DatasetConfig) -> None:
    """Refuse a tile outside the zoom range the registry releases for this dataset.

    Otto's first addition to M2-10 F1: the registry field tells the *viewer* which
    levels to ask for, but nothing stops another client from asking for z20 — which
    for a Zarr dataset means a tile read off the native 10 m level, an order of
    magnitude more bytes for pixels no sharper than z14 already gives. The boundary
    therefore lives here as well, not only in the client.

    Checked before the item is fetched, so a refused level costs no request to the
    source.

    Only a *tile* carries a level. The other routes on this dependency —
    ``/statistics`` (answered on the coarsest level there is), ``/info``,
    ``/point`` and ``/tilejson.json`` — have no ``z`` to check and pass through.
    ``/preview`` used to be among them and is gone (`access.tiles`): it carried no
    level *and* computed no target resolution, so for a Zarr dataset it read the
    native one. The AOI crop is not on this dependency at all; it resolves its own
    paths and is answered at the asset's own resolution by design (M2-06).

    ``/tilejson.json`` no longer advertises the reader's own zoom range: M3-04 gives
    it :func:`_viewer_zoom_range`, so it names the same range this function enforces.
    """
    level = request.path_params.get("z")
    if level is None:
        return
    viewer = config.viewer
    if viewer is None:
        # Not a caller's mistake — the entry never said which levels it serves. 501
        # for the same reason a format without a reader is one: the platform has not
        # been set up for this, and guessing a range is exactly what KLAERUNGEN B10
        # forbids.
        raise HTTPException(
            status_code=501,
            detail=f"{config.dataset_id!r} names no released zoom range (earthx:viewer)",
        )
    try:
        zoom = int(level)
    except (TypeError, ValueError):
        # TiTiler's own route typed this parameter; anything that gets past it is
        # its refusal to make, not ours.
        return
    if not viewer.min_zoom <= zoom <= viewer.max_zoom:
        raise HTTPException(
            status_code=400,
            detail=(
                f"zoom level {zoom} is not released for {config.dataset_id!r}, "
                f"which serves z{viewer.min_zoom} to z{viewer.max_zoom}"
            ),
        )


def _viewer_zoom_range(request: Request) -> tuple[int, int]:
    """The registry's released zoom range for the dataset in the path (M3-04).

    Feeds :meth:`~earthx.access.tiles.EarthxTilerFactory.tilejson` its
    ``minzoom``/``maxzoom`` defaults, so the document a client follows names the same
    range :func:`_check_zoom_released` enforces on every tile of this dataset, not the
    range rio-tiler computes from the asset. A dataset without a released range is a
    501, the same refusal :func:`_check_zoom_released` gives a tile of it.
    """
    dataset = str(request.path_params.get("dataset"))
    config = _dataset_config(request.app.state, dataset)
    viewer = config.viewer
    if viewer is None:
        raise HTTPException(
            status_code=501,
            detail=f"{config.dataset_id!r} names no released zoom range (earthx:viewer)",
        )
    return viewer.min_zoom, viewer.max_zoom


def _resolve_asset_path(
    state: Any,
    stac_item: dict[str, Any],
    *,
    config: DatasetConfig,
    item: str,
    asset: str,
    target_gsd: float | None = None,
) -> AssetPath | ZarrAsset:
    """The href of ``asset`` on ``stac_item``, cleared through the gateway policy.

    **The registry's ``format`` picks the reader**, here and nowhere else: `access`
    renders whatever it is handed and the client sends the same tile URL either way
    (M2-09a). A format without a reader is refused rather than read as a COG — a
    silent fallback would turn a registry mistake into a wrong picture.

    For a Zarr dataset, ``asset`` may carry a variable after the registry's
    ``ZarrInfo.variable_separator`` (adr/0007 §12.11, plan §10 F2) — split off
    *before* the href is looked up, because the item only ever advertises the
    group side of that key.
    """
    dataset = config.dataset_id
    if config.format not in _READABLE_FORMATS:
        raise HTTPException(
            status_code=501,
            detail=f"{dataset!r} is stored as {config.format.value}, which no reader opens",
        )
    if config.format is DataFormat.ZARR:
        separator = config.zarr.variable_separator if config.zarr is not None else None
        try:
            item_asset, variable = split_asset_key(asset, separator)
        except UrlRejected as error:
            # The caller's own query parameter is shaped wrong — a 400, not the 502
            # below, which is about what the *item* points at.
            raise HTTPException(status_code=400, detail=str(error)) from None
    try:
        if config.format is DataFormat.ZARR:
            href = _resolve_asset_href(stac_item, item_asset)
            return zarr_asset(
                href,
                state.earthx_policy,
                dataset_id=dataset,
                item_id=item,
                asset=asset,
                crs=_proj_code(stac_item),
                resolve=state.earthx_resolver,
                variable=variable,
                target_gsd=target_gsd,
            )
        href = _resolve_asset_href(stac_item, asset)
        return asset_path(
            href,
            state.earthx_policy,
            dataset_id=dataset,
            item_id=item,
            asset=asset,
            resolve=state.earthx_resolver,
        )
    except GatewayError:
        # An address the registry does not cover. This is the refusal adr/0006 §3.3
        # describes, and it is the source's problem, not the caller's — hence 502.
        raise HTTPException(
            status_code=502,
            detail="the item points at a host this dataset does not declare (asset_hosts)",
        ) from None


async def dataset_asset_path(
    request: Request,
    dataset: Annotated[str, Path(description="dataset id of the registry")],
    item: Annotated[str, Path(description="item id at the source")],
    asset: Annotated[str, Query(description="asset key of the item, e.g. `visual`")],
) -> AssetPath | ZarrAsset:
    """Turn dataset, item and asset into something a reader may open — and nothing else.

    A tile also has to name a level this dataset is released for
    (:func:`_check_zoom_released`) — checked first, so a level nobody serves costs
    no request to the source.

    ``asset`` is required rather than defaulted from the registry's standard
    visualisation: a tile URL is supposed to say what it shows (adr/0001 Z4), and a
    default that lives in the registry would make two releases of the platform answer
    the same URL with two pictures. The standard visualisation travels to the client
    on the collection (``earthx:default_render``), which is where it can be a default.
    """
    state = request.app.state
    config = _dataset_config(state, dataset)
    _check_zoom_released(request, config)
    stac_item = await _fetch_item(state, dataset, item)
    target_gsd = _target_gsd(request, stac_item)
    return _resolve_asset_path(state, stac_item, config=config, item=item, asset=asset, target_gsd=target_gsd)


class DownloadRequest(BaseModel):
    """Body of ``POST /collections/{dataset}/download`` (M2-06, architekturplan 6.4 D3).

    A POST body rather than URL parameters, unlike the tile path's Z4 rule: the
    tile URL has to be cache-stable and CDN-able, but a crop answers once and is
    never cached (D11), and an AOI polygon can be far larger than fits comfortably
    in a query string. ``items`` carries more than one id only for a mosaic
    (adr/0006 §4.2 Option M1) — a single item is simply a list of one.
    """

    items: list[str] = Field(min_length=1, max_length=64, description="item ids, one scene each")
    assets: list[str] = Field(min_length=1, max_length=32, description="asset keys, e.g. `visual`")
    aoi: dict[str, Any] = Field(description="a GeoJSON Polygon or MultiPolygon, in WGS84")


async def download_crop(
    request: Request,
    dataset: Annotated[str, Path(description="dataset id of the registry")],
    body: DownloadRequest,
) -> StreamingResponse:
    """The AOI crop as a ZIP of COGs plus :data:`~earthx.access.download.NOTICE_FILENAME`.

    Every check that can run before an asset is opened runs first, in the order
    M2-06's acceptance criteria list the failures: unknown dataset, licence tier,
    a malformed AOI, an unknown item, an AOI that touches none of the given items,
    then the size cap — only after all of that does anything reach `gateway`.
    """
    state = request.app.state
    config = _dataset_config(state, dataset)

    if config.license.tier is not LicenseTier.PROCESSING:
        # A download hands out the source's pixels, cropped but otherwise
        # unmodified — the same tier the onboarding checklist (KLAERUNGEN B11)
        # already requires for operators, jobs and the datacube.
        raise HTTPException(
            status_code=403,
            detail=f"{dataset!r}'s licence does not permit a data export (KLAERUNGEN B11)",
        )

    try:
        aoi = parse_aoi_geometry(body.aoi)
    except InvalidAoi as error:
        raise HTTPException(status_code=400, detail=str(error)) from None

    items = await asyncio.gather(*(_fetch_item(state, dataset, item_id) for item_id in body.items))
    matched = filter_items_intersecting_aoi(items, aoi)
    if not matched:
        raise HTTPException(status_code=400, detail="the AOI does not touch any of the given items")

    try:
        check_size_cap(item_count=len(matched), asset_count=len(set(body.assets)))
    except AoiTooLarge as error:
        raise HTTPException(status_code=413, detail=str(error)) from None

    # Deduplicated, order kept: `assets` is a caller's list and may repeat a key,
    # and two identical keys would otherwise write the same file name into the
    # archive twice (M2-10 review). One request for `visual` is one `visual.tif`.
    wanted = list(dict.fromkeys(body.assets))
    crops = [
        AssetCrop(
            asset=asset,
            paths=tuple(
                _resolve_asset_path(
                    state, matched_item, config=config, item=matched_item["id"], asset=asset
                )
                for matched_item in matched
            ),
        )
        for asset in wanted
    ]

    try:
        zip_bytes = await run_in_threadpool(
            build_download_zip,
            config=config,
            open_reader=open_asset,
            crops=crops,
            aoi_geometry=body.aoi,
            item_ids=[matched_item["id"] for matched_item in matched],
        )
    except AoiOutsideItems as error:
        # The bbox prefilter passed but the geometry itself misses every item's
        # actual footprint (a bbox is not the data — MGRS tiles are rotated).
        raise HTTPException(status_code=400, detail=str(error)) from None
    except RioTilerError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    except (RasterioError, GatewayError):
        raise HTTPException(status_code=502, detail="the asset could not be read from the source") from None

    LOGGER.info(
        "download answered",
        extra={
            "dataset": dataset,
            "items": len(matched),
            "assets": len(wanted),
            "bytes": len(zip_bytes),
        },
    )
    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{dataset}-crop.zip"'},
    )


def gdal_environment(request: Request) -> dict[str, str]:
    """The central GDAL configuration (M1-03), built once per process."""
    return request.app.state.earthx_gdal_options


async def statistics_cache(request: Request) -> AsyncIterator[PostgresStatsCache | None]:
    """A statistics cache on its own connection, or None when there is no pool.

    None is a valid answer: a tiler started without a database renders, it just
    re-reads every statistic (E5).
    """
    pool = getattr(request.app.state, "earthx_cache_pool", None)
    if pool is None:
        yield None
        return
    async with pool.connection() as conn:
        yield PostgresStatsCache(conn)


def build_item_source(registry: DatasetRegistry, gateway: Gateway, pool: Any):
    """How the tiler gets an item: through the adapter, the gateway and the item cache.

    A closure rather than a dependency of its own, so that a test can put a recorded
    item in its place without a database and without a network (adr/0002 §2).
    """

    async def item_source(dataset_id: str, item_id: str) -> dict[str, Any]:
        if pool is None:
            return await get_item(dataset_id, item_id, gateway=gateway, registry=registry)
        async with pool.connection() as conn:
            return await get_item(
                dataset_id, item_id, gateway=gateway, registry=registry, cache=PostgresSearchCache(conn)
            )

    return item_source


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with (
        cache_pool() as pool,
        Gateway(app.state.earthx_policy, resolve=app.state.earthx_resolver) as gateway,
    ):
        app.state.earthx_cache_pool = pool
        app.state.earthx_item_source = build_item_source(REGISTRY, gateway, pool)
        yield


def build_app(registry: DatasetRegistry = REGISTRY, *, lifespan=_lifespan) -> FastAPI:
    """The tiler application, with everything the factory needs hung on it.

    ``registry`` and ``lifespan`` are arguments so that a test can build the same app
    against a registry of its own and without a database — not so that a deployment
    can: the process entrypoint below takes neither.
    """
    policy = policy_from_registry(registry)
    app = FastAPI(title="earthx-tiler", lifespan=lifespan)
    # Read at request time through the two small dependencies above, so a route
    # never closes over something a test cannot replace.
    app.state.earthx_policy = policy
    app.state.earthx_gdal_options = gdal_options(policy)
    # One resolver for the process, shared by the path dependency and the gateway:
    # a tile batch resolves the asset host once instead of once per tile (M2-14).
    # It caches the resolver's answer only — every address is checked again on
    # every request, by `check_url` as before.
    app.state.earthx_resolver = CachingResolver()
    app.state.earthx_item_source = None
    # The download route (M2-06) needs the dataset's licence, title and terms —
    # nothing the path dependency above already carries.
    app.state.earthx_registry = registry

    factory = EarthxTilerFactory(
        path_dependency=dataset_asset_path,
        environment_dependency=gdal_environment,
        stats_cache_dependency=statistics_cache,
        viewer_zoom_dependency=_viewer_zoom_range,
        router_prefix=ROUTER_PREFIX,
        name="tiles",
    )
    app.include_router(factory.router, prefix=ROUTER_PREFIX, tags=["Tiles"])
    app.add_api_route(
        DOWNLOAD_ROUTE,
        download_crop,
        methods=["POST"],
        tags=["Download"],
    )

    @app.exception_handler(TileOutsideBounds)
    async def _tile_outside(request: Request, error: TileOutsideBounds):
        return _problem(404, "the tile does not touch this item")

    @app.exception_handler(RioTilerError)
    async def _rio_tiler_error(request: Request, error: RioTilerError):
        # Band names, expressions, colormaps: what the caller asked for cannot be
        # rendered from this asset. The message is rio-tiler's own and names no address.
        return _problem(400, str(error))

    # Module-level, not a closure like the others above: a test builds its own
    # bare app around `EarthxTilerFactory` (`access.tiles`, no registry, no
    # gateway) and needs the same two handlers on it to check the mapping below
    # without a real `build_app()` (backend/tests/earthx/api/test_statistics_read_errors.py).
    app.add_exception_handler(RasterioIOError, _rasterio_io_error)
    app.add_exception_handler(RasterioError, _rasterio_error)

    @app.exception_handler(ZarrAssetError)
    async def _zarr_asset_error(request: Request, error: ZarrAssetError):
        # The item and the store disagree — a missing group, a missing variable, no
        # consolidated metadata, no CRS anywhere (adr/0007 §3.4, §3.5). The caller
        # asked for an asset the item advertises, so this is the source's side of the
        # line, like every other 502 here. The message names dataset, item and asset,
        # never an address.
        return _problem(502, str(error))

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "tiler"}

    return app


def _problem(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


async def _rasterio_io_error(request: Request, error: RasterioIOError) -> JSONResponse:
    """A genuine read failure: GDAL could not get bytes from the source.

    Applies to every route on this dependency, not only `/statistics` — the one
    place this actually fired is what led here (M3-03 review). Logged with the
    traceback, which the single handler this replaced discarded outright.
    `RasterioIOError` is `rasterio.errors`' one subclass of `OSError`; every other
    `RasterioError` goes to :func:`_rasterio_error` below instead of here.
    """
    LOGGER.warning("could not read the asset from the source", exc_info=True)
    return _problem(502, "the asset could not be read from the source")


async def _rasterio_error(request: Request, error: RasterioError) -> JSONResponse:
    """Every `RasterioError` that is *not* a read failure (:func:`_rasterio_io_error`).

    GDAL has over two dozen of these — an unsupported resampling algorithm, an
    invalid array shape, a GDAL version mismatch — none of which are about the
    source being unreachable. Reporting one as "could not be read from the
    source" would say something false about where the problem is and could hide a
    genuine code-level bug behind the same message a real upstream failure gets.
    This is our side of the line rather than the source's, hence `error`, not
    `warning`.
    """
    LOGGER.error("the asset could not be processed", exc_info=True)
    return _problem(500, "the asset could not be processed")


app = build_app()


__all__ = [
    "DOWNLOAD_ROUTE",
    "ROUTER_PREFIX",
    "DownloadRequest",
    "app",
    "build_app",
    "dataset_asset_path",
    "download_crop",
]
