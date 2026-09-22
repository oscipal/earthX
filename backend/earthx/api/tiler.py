"""Process entrypoint for `tiler` (architekturplan.md 3.2, adr/0006 §5.1).

It used to be ``earthx.access.main``. It moved here because the tile path needs
three things from `gateway` — a :class:`Policy` built from the registry,
``check_url`` and ``gdal_options`` — and `access` may not import `gateway`
(architekturplan.md 3.1). `api` is the module that composes; so the composition
lives here and `access` keeps the rendering (Otto's answer 5 of 20.09.2026).

What is composed:

* **the path dependency** — ``dataset`` and ``item`` from the path, ``asset``
  from the query, resolved through the registry and the adapter into an
  :class:`~earthx.readers.cog.AssetPath`. This is the only place in the process
  where an address is built, and it cannot build one without ``check_url``. There
  is no free ``url`` parameter anywhere in the schema; a test proves it.
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

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from rasterio.errors import RasterioError
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
from earthx.access.tiles import EarthxTilerFactory
from earthx.adapters.earth_search import (
    InvalidQuery,
    UnknownCollection,
    UnsupportedSource,
    get_item,
)
from earthx.api.dependencies import cache_pool, policy_from_registry
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import DatasetRegistry, LicenseTier, UnknownDatasetError
from earthx.catalog.search_cache import PostgresSearchCache
from earthx.catalog.stats_cache import PostgresStatsCache
from earthx.gateway import CachingResolver, Gateway, GatewayError, UpstreamError, UpstreamTimeout
from earthx.gateway.gdal import gdal_options
from earthx.readers.cog import AssetPath, CogReader, asset_path

LOGGER = logging.getLogger("earthx.api.tiler")

# One item of one collection, the same shape the STAC API of `api` uses for the
# metadata of that very item. The tiler answers under its own port (docker-compose),
# so the two never collide.
ROUTER_PREFIX = "/collections/{dataset}/items/{item}"

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


def _resolve_asset_path(
    state: Any, stac_item: dict[str, Any], *, dataset: str, item: str, asset: str
) -> AssetPath:
    """The href of ``asset`` on ``stac_item``, cleared through the gateway policy."""
    href = _resolve_asset_href(stac_item, asset)
    try:
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
) -> AssetPath:
    """Turn dataset, item and asset into a path GDAL may open — and nothing else.

    ``asset`` is required rather than defaulted from the registry's standard
    visualisation: a tile URL is supposed to say what it shows (adr/0001 Z4), and a
    default that lives in the registry would make two releases of the platform answer
    the same URL with two pictures. The standard visualisation travels to the client
    on the collection (``earthx:default_render``), which is where it can be a default.
    """
    state = request.app.state
    stac_item = await _fetch_item(state, dataset, item)
    return _resolve_asset_path(state, stac_item, dataset=dataset, item=item, asset=asset)


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
    language: str = Field(default="de", description="language of the notice file, ISO 639-1")


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
    registry: DatasetRegistry = state.earthx_registry
    try:
        config = registry.get(dataset)
    except UnknownDatasetError:
        raise HTTPException(status_code=404, detail=f"no dataset {dataset!r}") from None

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
        check_size_cap(item_count=len(matched), asset_count=len(body.assets))
    except AoiTooLarge as error:
        raise HTTPException(status_code=413, detail=str(error)) from None

    crops = [
        AssetCrop(
            asset=asset,
            paths=tuple(
                _resolve_asset_path(state, matched_item, dataset=dataset, item=matched_item["id"], asset=asset)
                for matched_item in matched
            ),
        )
        for asset in body.assets
    ]

    try:
        zip_bytes = await run_in_threadpool(
            build_download_zip,
            config=config,
            reader_cls=CogReader,
            crops=crops,
            aoi_geometry=body.aoi,
            item_ids=[matched_item["id"] for matched_item in matched],
            language=body.language,
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
            "assets": len(body.assets),
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

    @app.exception_handler(RasterioError)
    async def _rasterio_error(request: Request, error: RasterioError):
        return _problem(502, "the asset could not be read from the source")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "tiler"}

    return app


def _problem(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


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
