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
  Zarr, a :class:`~earthx.readers.zarr_reader.ZarrAsset` (M2-09a). The resolution
  itself lives in :mod:`earthx.access.resolve` since M4-01a, where `processing` can
  reach it too; this process hands it the policy and maps its refusals to HTTP. It
  cannot build an address without ``check_url``. There is no free ``url``
  parameter anywhere in the schema; a test proves it.
* **the environment dependency** — ``tile_gdal_options(policy)``, so the central GDAL
  configuration of M1-03 applies at every endpoint rather than wherever someone
  remembered it. The AOI crop of the download route reads under
  ``crop_gdal_options(policy)``: the same, except that it keeps parallel range reads
  (NM4-26 §10, §13).
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
import dataclasses
import logging
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Annotated, Any, Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.dependencies.utils import solve_dependencies
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from rasterio.errors import RasterioError, RasterioIOError
from rio_tiler.errors import RioTilerError, TileOutsideBounds
from rio_tiler.models import ImageData
from shapely.geometry import mapping as shapely_mapping
from starlette.concurrency import run_in_threadpool
from titiler.core.dependencies import BidxParams

from earthx.access.band_export import ExportPlanError, band_count, band_meta_of_items, band_table, plan_files
from earthx.access.colormaps import catalog as colormap_catalog
from earthx.access.crop_rules import MAX_JOB_BYTES, mosaic_order, target_crs
from earthx.access.download import (
    LARGE_DOWNLOAD_THRESHOLD_BYTES,
    AoiOutsideItems,
    AoiTooLarge,
    AssetCrop,
    CorruptOutput,
    GroupCrop,
    InvalidAoi,
    PlannedOutput,
    attribution_years,
    build_download_zip,
    check_item_count_cap,
    check_output_size_cap,
    compute_crop_region,
    filter_items_intersecting_aoi,
    parse_aoi_geometry,
    plan_outputs,
)
from earthx.access.mosaic_tiles import (
    EarthxMosaicTilerFactory,
    EarthxOverviewTilerFactory,
    MosaicLayout,
    MosaicScenes,
    ReadBudget,
    open_mosaic,
)
from earthx.access.resolve import (
    AssetNotOnItem,
    InvalidAssetKey,
    MalformedItem,
    NoReader,
    ResolvedAsset,
    check_is_raster,
    open_asset_ref,
    resolve_asset,
    target_gsd_for,
)
from earthx.access.tiles import EarthxTilerFactory, open_asset
from earthx.adapters import (
    ADAPTER_SPECS,
    AdapterSpecs,
    check_adapter_specs,
)
from earthx.api import mosaic_tiles
from earthx.api.area_statistics import AREA_STATISTICS_ROUTE, area_statistics_endpoint
from earthx.api.citation import citation_bib
from earthx.api.dependencies import cache_pool, policy_from_registry
from earthx.api.item_source import (
    OrderRefused,
    build_item_batch_source,
    build_item_source,
    check_item_holdings,
    malformed_item_detail,
)
from earthx.api.mosaic_selection import Selection, SelectionStore, outline_source
from earthx.api.result_tiles import ROUTER_PREFIX as RESULT_ROUTER_PREFIX
from earthx.api.result_tiles import ResultSources, build_result_factory
from earthx.catalog.datasets import registry as dataset_registry
from earthx.catalog.mosaic_selection import selection_id
from earthx.catalog.registry import (
    AcquisitionYearMissing,
    DatasetConfig,
    DatasetRegistry,
    ItemHolding,
    LicenseTier,
    OverviewMode,
    RetiredDatasetError,
    UnknownDatasetError,
)
from earthx.catalog.stats_cache import PooledStatsCache, PostgresStatsCache
from earthx.gateway import CachingResolver, Gateway, GatewayError, user_agent_from_env
from earthx.gateway.gdal import crop_gdal_options, tile_gdal_options
from earthx.logging import RequestIdMiddleware, configure_logging, get_request_id
from earthx.objectstore.errors import StoreConfigError
from earthx.objectstore.results import Store
from earthx.readers import AssetRejected, GeoreferenceMismatch
from earthx.readers.cog import AssetPath
from earthx.readers.zarr_reader import ZarrAsset, ZarrAssetError

LOGGER = logging.getLogger("earthx.api.tiler")

# One item of one collection, the same shape the STAC API of `api` uses for the
# metadata of that very item. The tiler answers under its own port (docker-compose),
# so the two never collide.
ROUTER_PREFIX = "/collections/{dataset}/items/{item}"

# The tiles of the scenes of one overpass read as one (M4-17b); the scenes are a selection, named by its id in the path
# (M5-30b part 3), which `POST` to MOSAIC_SELECTION_ROUTE creates.
MOSAIC_ROUTER_PREFIX = mosaic_tiles.ROUTER_PREFIX
MOSAIC_SELECTION_ROUTE = "/collections/{dataset}/mosaic"

# The tile of the substitute a dataset shows below its first level (plan M5-30b §4.8).
OVERVIEW_ROUTER_PREFIX = mosaic_tiles.OVERVIEW_ROUTER_PREFIX

# Where the tiles of a job result begin (`result_tiles.ROUTER_PREFIX` up to its identifier).
RESULT_PATH_START = "/results/"

# The download route (M2-06) names only the dataset in its path — the item(s) and
# the asset(s) travel in the body (a mosaic can name several of each, and an AOI
# polygon does not belong in a query string) — so it cannot share ROUTER_PREFIX.
DOWNLOAD_ROUTE = "/collections/{dataset}/download"

# The order of the scenes of a pass, without a mosaic (NM4-24): a POST with the ids in the body, as a pass the mosaic
# tile refuses can have more scenes than a URL takes. Apart from the mosaic router, whose routes are the tile and its TileJSON.
SCENE_ORDER_ROUTE = "/collections/{dataset}/scene-order"
BANDS_ROUTE = "/collections/{dataset}/bands"
# Scenes one such request may name: the largest overpasses of a continental AOI over a season stay far below it.
MAX_ORDER_ITEMS = 500

# At most one download whose planned output reaches LARGE_DOWNLOAD_THRESHOLD_BYTES
# runs at a time in this process (F10a, M3-18 §10): measured (plan §10.3/§10.4)
# a single such crop can peak at several GB RSS in the same process that also
# serves tiles, so two of them at once must not both run. Checked-then-acquired
# with no `await` in between, which is race-free on asyncio's single-threaded
# event loop (a second concurrent request cannot interleave between the check
# and the `async with`).
_LARGE_DOWNLOAD_LOCK = asyncio.Lock()


async def _fetch_item(state: Any, dataset: str, item: str) -> dict[str, Any]:
    """The item, or the ``HTTPException`` its absence or the source's failure maps to.

    Shared by :func:`dataset_asset_path` and the download route of M2-06; what a
    failure means is decided once, in :func:`earthx.api.item_source.fetch_item_or_refuse`.
    The fetch goes through the process's :class:`~earthx.api.mosaic_tiles.ItemFetches`, the
    one the mosaic tile uses: the six tiles of a cold scene that a map view asks for at the
    same moment fetch the item once (NM4-26 S2), and a failure reaches every one of them as
    the same refusal.
    """
    try:
        return await state.earthx_item_fetches.get(state.earthx_item_source, dataset, item)
    except OrderRefused as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None


def _dataset_config(state: Any, dataset: str) -> DatasetConfig:
    """The registry entry for ``dataset``, or a 404 (a 410 with the reason for a retired one, adr/0017).

    adr/0005 rule I: an unknown collection is a 404 and not an empty answer that
    looks valid. Every route of this process starts here, so the refusal reads the
    same whether it came from a tile, the statistics or a crop.
    """
    registry: DatasetRegistry = state.earthx_registry
    try:
        return registry.get(dataset)
    except RetiredDatasetError as error:
        raise HTTPException(status_code=410, detail=error.retired.message) from None
    except UnknownDatasetError:
        raise HTTPException(status_code=404, detail=f"no dataset {dataset!r}") from None


def _check_display_allowed(config: DatasetConfig) -> None:
    """Refuse a tile, statistics, info, point or tilejson read below licence tier
    'display' (KLAERUNGEN B11, M3-02 K-03, Otto's answer of 23.09.2026).

    A dataset at tier `catalog` is a link to the source, never something this
    platform renders itself — the registry already refuses such an entry a
    `viewer` field (`DatasetConfig._check_license_tier`), so without this check
    `_check_zoom_released` below would answer it with a `501` ("names no released
    zoom range") instead of the `403` this is about. Called first, and before any
    item is fetched, for the same reason `_check_zoom_released` is: a refused
    dataset costs no request to the source. The download route enforces the
    stricter `processing` tier on its own (`download_crop`) and is unaffected.
    """
    if config.license.tier is LicenseTier.CATALOG:
        raise HTTPException(
            status_code=403,
            detail=f"{config.dataset_id!r}'s licence permits a catalogue entry only, no display (KLAERUNGEN B11)",
        )


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


def _resolve_ref(stac_item: dict[str, Any], *, config: DatasetConfig, item: str, asset: str) -> ResolvedAsset:
    """``asset`` of ``stac_item`` resolved in `access`, or the ``HTTPException`` its refusal maps to.

    ``item`` is the id the caller asked for; the resolved asset carries the item's own.
    """
    try:
        return resolve_asset(stac_item, config, asset)
    except NoReader as error:
        raise HTTPException(status_code=501, detail=str(error)) from None
    except InvalidAssetKey as error:
        # The caller's own query parameter is shaped wrong — a 400, not the 502
        # below, which is about what the *item* points at.
        raise HTTPException(status_code=400, detail=str(error)) from None
    except AssetNotOnItem as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    except MalformedItem:
        raise HTTPException(status_code=502, detail=malformed_item_detail(item)) from None


def _open_ref(
    state: Any, ref: ResolvedAsset, *, target_gsd: float | None = None, decode_cf: bool = True
) -> AssetPath | ZarrAsset:
    """``ref`` cleared through the gateway policy, or the ``HTTPException`` its refusal maps to."""
    try:
        return open_asset_ref(ref, state.earthx_policy, state.earthx_resolver, target_gsd=target_gsd, decode_cf=decode_cf)
    except AssetRejected:
        # An address the registry does not cover. This is the refusal adr/0006 §3.3
        # describes, and it is the source's problem, not the caller's — hence 502.
        raise HTTPException(
            status_code=502,
            detail="the item points at a host this dataset does not declare (asset_hosts)",
        ) from None


def _resolve_asset_path(
    state: Any,
    stac_item: dict[str, Any],
    *,
    config: DatasetConfig,
    item: str,
    asset: str,
    target_gsd: float | None = None,
) -> AssetPath | ZarrAsset:
    """``asset`` of ``stac_item``, resolved in `access` and cleared through the gateway
    policy — or the ``HTTPException`` its refusal maps to.

    The resolution itself is :func:`~earthx.access.resolve.resolve_asset` and
    :func:`~earthx.access.resolve.open_asset_ref`; what is left here is the HTTP
    answer to each refusal.
    """
    ref = _resolve_ref(stac_item, config=config, item=item, asset=asset)
    return _open_ref(state, ref, target_gsd=target_gsd)


def _in_mosaic_order(items: list[dict[str, Any]], *, config: DatasetConfig, asset: str) -> list[dict[str, Any]]:
    """``items`` in the order the mosaic job and the mosaic tile read them (:func:`mosaic_order`).

    The CRS of each scene is that of ``asset``, resolved as the mosaic tile resolves it. A single
    item has no order, and nothing is resolved for it.
    """
    if len(items) < 2:
        return items
    refs = [_resolve_ref(stac_item, config=config, item=str(stac_item.get("id")), asset=asset) for stac_item in items]
    by_id = {ref.item_id: stac_item for ref, stac_item in zip(refs, items, strict=True)}
    return [by_id[item_id] for item_id in mosaic_order({ref.item_id: ref.crs for ref in refs})]


@dataclass(frozen=True, slots=True)
class OperatorInput:
    """What the path of an operator tile stands for: its assets and the chain of steps (operator, parameters).

    Defined here and typed loosely on purpose: the tiler does not load the worker core when it
    starts (M4-14), only when the first operator tile asks for it. `processing.tile` reads this
    object by its two attributes (``TileInputs``); the statistics cache of `access` reads ``dataset_id`` and
    ``cache_identity()`` (``CacheIdentity``).
    """

    inputs: tuple[tuple[Any, AssetPath | ZarrAsset], ...]
    steps: tuple[tuple[Any, Any], ...]
    #: The bands the picture shows, with the steps made to leave them (NM4-43d, NM4-64); ``None`` for steps of version 1.
    bands: tuple[str, ...] | None = None

    @property
    def dataset_id(self) -> str:
        return self.inputs[0][1].dataset_id

    def cache_identity(self) -> dict[str, Any]:
        """What the statistics of these inputs depend on, for the cache key: the assets with their scaling and units, the steps.

        The address is left out (the key is a hash of the question, not of where the bytes are), like the key of one asset.
        """
        return {
            "inputs": [entry.model_dump(mode="json", exclude={"asset": {"href"}}) for entry, _ in self.inputs],
            "steps": [[operator.op, operator.op_version, params.model_dump(mode="json")] for operator, params in self.steps],
        }


@dataclass(frozen=True, slots=True)
class MosaicOperatorInput:
    """What the path of a mosaic tile with steps stands for (NM4-04): per scene its assets, the steps, the extent.

    The scenes are those the tile reads, in the order of the mosaic, each with the same assets in the order of
    the URL; ``processing.tile`` reads it by its attributes (``MosaicTileInputs``), like :class:`OperatorInput`.
    """

    dataset_id: str
    scenes: tuple[tuple[tuple[Any, AssetPath | ZarrAsset], ...], ...]
    steps: tuple[tuple[Any, Any], ...]
    bounds: tuple[float, float, float, float]
    #: The bands the picture shows, as for :class:`OperatorInput`.
    bands: tuple[str, ...] | None = None


def _operator_support() -> Any:
    """The worker core's operator side, imported when the first operator tile needs it.

    A start of the tiler stays light (``test_tiler_start_is_light``): `processing` brings numexpr
    and the COG writer, which a tiler that never sees ``op`` has no use for.
    """
    from earthx.api.intake import describe_bands
    from earthx.processing import operators, tile
    from earthx.processing.errors import RecipeInvalid, UnknownOperator
    from earthx.processing.recipe import ResolvedAssetModel, ResolvedInput

    return SimpleNamespace(
        registry=operators.REGISTRY,
        applicable=operators.applicable,
        tier=operators.Tier,
        unknown_operator=UnknownOperator,
        resolved_input=ResolvedInput,
        resolved_asset=ResolvedAssetModel,
        reader=tile.OperatorTileReader,
        mosaic_reader=tile.MosaicOperatorTileReader,
        judge_described_bands=tile.judge_described_bands,
        plan_band=tile.plan_band,
        option_refused=tile.TileOptionRefused,
        recipe_invalid=RecipeInvalid,
        describe_bands=describe_bands,
    )


# A tile URL that carries an operator names it, its version and its parameters, and
# nothing else of the recipe (adr/0014 §6.2): no recipe id, no hash, no AOI (Q8). It may
# repeat the three, equally often and in the order of the steps: the longest start of a
# recipe that runs as a tile (§6.1, plan M4-18 F1).
MAX_OPERATOR_ASSETS = 16
MAX_OPERATOR_PARAMS_CHARS = 2048
MAX_OPERATOR_STEPS = 4
#: The longest name of a band a tile URL may ask for; the bands of a dataset are named by its assets, variables and steps.
MAX_BAND_CHARS = 128
#: A picture shows one band, or this many as its red, green and blue (NM4-64).
COLOUR_BANDS = 3
_OPERATOR_ROUTES = frozenset({"tile", "tilejson", "statistics"})

# TiTiler's free band-math and algorithm parameters. They computed on raw values with
# every numexpr function, outside R5 and the scaling of adr/0014 §5.4; `op=band_math`
# is the one way to ask for an expression (plan M4-09, F3).
_FREE_PARAMETERS = ("expression", "algorithm", "algorithm_params")


def _refuse_free_parameters(request: Request) -> None:
    for name in _FREE_PARAMETERS:
        if name in request.query_params:
            raise HTTPException(
                status_code=400,
                detail=f"{name!r} is not accepted; ask for an expression with op=band_math&op_version=1&params=…",
            )


def _operator_step(
    support: Any, operators: Any, config: DatasetConfig, *, op: str, version: str, raw: str, where: str
) -> tuple[Any, Any]:
    """One step of the chain: its operator and validated parameters, or the ``HTTPException`` its refusal maps to.

    ``where`` prefixes every message of a chain of several steps (``"step 1: "`` for the second): counted from
    0 like the refusals of the recipe and the order (``processing/recipe.py``, ``api/intake.py``), which is how the
    panel finds the step. A single step reads as it always did.
    """
    if len(raw) > MAX_OPERATOR_PARAMS_CHARS:
        raise HTTPException(status_code=400, detail=f"{where}params are at most {MAX_OPERATOR_PARAMS_CHARS} characters")
    # ASCII digits only: `int()` also reads other scripts' digits, which the query validation of
    # `operator_post_process` refuses afterwards — after the item has been fetched.
    if not (version.isascii() and version.isdecimal()):
        raise HTTPException(status_code=400, detail=f"{where}op_version is a whole number")
    try:
        operator = operators.operator(op, int(version))
    except support.unknown_operator as error:
        raise HTTPException(status_code=422, detail=f"{where}{error}") from None
    if support.tier.T1 not in operator.tiers or operator.kind != "pixel":
        raise HTTPException(status_code=422, detail=f"{where}{operator.op!r} does not run as a tile")
    try:
        params = operator.params.model_validate_json(raw, strict=True)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(map(str, entry['loc'])) or 'params'}: {entry['msg']}"
            for entry in error.errors(include_url=False, include_input=False, include_context=False)
        )
        raise HTTPException(status_code=400, detail=f"{where}params: {problems}") from None
    reasons = support.applicable(operator, config, params)
    if reasons:
        raise HTTPException(status_code=422, detail=f"{where}{operator.op!r} cannot run here: {'; '.join(reasons)}")
    return operator, params


def _operator_request(request: Request, config: DatasetConfig) -> list[tuple[Any, Any]] | None:
    """The steps ``(operator, parameters)`` of the ``op`` in the query, or ``None`` when the URL names none.

    ``op``, ``op_version`` and ``params`` come in threes: each as often as the others, at most
    :data:`MAX_OPERATOR_STEPS` times, the first of each being the first step. Every step has to run as a tile
    (``T1``, ``pixel``) and to apply to the dataset on its own; the bands each one leaves for the next are
    judged by the reader, before the first pixel.

    ``400`` for a query that is malformed or whose parameters do not validate (R5 included); ``422`` for one
    that is well formed but not something this platform does here — an operator it does not know, one that
    does not run as a tile, one the dataset does not allow.
    """
    query = request.query_params
    names = ("op", "op_version", "params")
    given = [name for name in names if name in query]
    if not given:
        return None
    support = _operator_support()
    operators = getattr(request.app.state, "earthx_operators", None) or support.registry
    columns = [query.getlist(name) for name in names]
    if len(given) != 3 or len({len(column) for column in columns}) != 1:
        raise HTTPException(status_code=400, detail="op, op_version and params go together, equally often")
    if len(columns[0]) > MAX_OPERATOR_STEPS:
        raise HTTPException(status_code=400, detail=f"a tile takes at most {MAX_OPERATOR_STEPS} steps")
    chained = len(columns[0]) > 1
    return [
        _operator_step(
            support, operators, config, op=op, version=version, raw=raw, where=f"step {index}: " if chained else ""
        )
        for index, (op, version, raw) in enumerate(zip(*columns, strict=True))
    ]


def _bands_request(request: Request) -> tuple[str, ...] | None:
    """The ``band`` of the query: the one band of the stock a tile shows (NM4-43d), or ``None`` where the URL names none.

    Or three, in the order red, green, blue, for a colour picture (NM4-64): one ``rescale`` for all three, or one for
    each channel in the same order (UI-03d), and no colormap, which paints one band. Two bands have no picture.

    ``400`` for a name that is empty, longer than :data:`MAX_BAND_CHARS` or given twice, for a number of names other
    than one or three, and for a colormap or a number of ``rescale`` other than one or three next to three; whether
    the steps leave such bands is for :func:`_band_plan`.
    """
    given = request.query_params.getlist("band")
    if not given:
        return None
    if len(given) not in (1, COLOUR_BANDS) or not all(1 <= len(name) <= MAX_BAND_CHARS for name in given):
        raise HTTPException(
            status_code=400,
            detail=f"name one band, or three for red, green and blue, of at most {MAX_BAND_CHARS} characters each",
        )
    if len(set(given)) != len(given):
        raise HTTPException(status_code=400, detail="name each band once")
    if len(given) > 1:
        if any(name in request.query_params for name in ("colormap_name", "colormap")):
            raise HTTPException(status_code=400, detail="a picture of three bands takes no colormap")
        if len(request.query_params.getlist("rescale")) not in (0, 1, COLOUR_BANDS):
            raise HTTPException(
                status_code=400, detail="a picture of three bands takes one rescale for all of them or one for each"
            )
    return tuple(given)


def _band_plan(support: Any, entries: list[Any], steps: list[tuple[Any, Any]], bands: tuple[str, ...] | None) -> Any:
    """The plan of the bands a tile shows (:func:`~earthx.processing.tile.plan_band`), or the ``HTTPException`` of its refusal.

    Judged on what the items describe, before any file is opened: ``422`` with the name for a band the steps do not leave
    or a step that does not fit the bands, ``400`` for a ``band`` next to a step of version 1. ``None`` for steps of
    version 1 without a ``band``: they leave the bands they leave and nothing is dropped.
    """
    try:
        return support.plan_band(entries, steps, bands)
    except support.option_refused as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    except support.recipe_invalid as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


def _operator_input(
    state: Any,
    stac_item: dict[str, Any],
    *,
    config: DatasetConfig,
    item: str,
    assets: list[str],
    steps: list[tuple[Any, Any]],
    bands: tuple[str, ...] | None,
    target_gsd: float | None,
) -> OperatorInput:
    """The assets of an operator tile, each with the bands and scaling source the item describes.

    With steps of version 2 only the assets the shown band needs are opened (NM4-43d), and the limit of
    :data:`MAX_OPERATOR_ASSETS` is the limit of those.
    """
    support = _operator_support()
    refs, entries = [], []
    for key in assets:
        ref = _resolve_ref(stac_item, config=config, item=item, asset=key)
        try:
            described, scaling, unit = support.describe_bands(stac_item, config, ref)
            entries.append(
                support.resolved_input(
                    asset=support.resolved_asset(**ref.to_json()),
                    version=None,
                    bands=described,
                    scaling=scaling,
                    unit=unit,
                    gsd=None,
                )
            )
        except OrderRefused as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail) from None
        except ValidationError:
            raise HTTPException(status_code=502, detail=malformed_item_detail(item)) from None
        refs.append(ref)
    plan = _band_plan(support, entries, steps, bands)
    wanted = set(assets if plan is None else plan.assets)
    if len(wanted) > MAX_OPERATOR_ASSETS:
        raise HTTPException(status_code=400, detail=f"the tile reads {len(wanted)} assets, at most {MAX_OPERATOR_ASSETS}")
    inputs = []
    for ref, entry in zip(refs, entries, strict=True):
        if entry.asset.asset not in wanted:
            continue
        try:
            # Item scaling is applied by the core, so the reader reads raw; without it the
            # reader's own CF decoding applies (adr/0014 §5.4, F7a) — the job's rule.
            target = _open_ref(state, ref, target_gsd=target_gsd, decode_cf=entry.scaling == "store-cf")
        except OrderRefused as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail) from None
        inputs.append((entry, target))
    if plan is None:
        return OperatorInput(tuple(inputs), tuple(steps))
    return OperatorInput(tuple(inputs), plan.steps, plan.bands)


async def dataset_asset_path(
    request: Request,
    dataset: Annotated[str, Path(description="dataset id of the registry")],
    item: Annotated[str, Path(description="item id at the source")],
    asset: Annotated[
        list[str],
        Query(description="asset key of the item, e.g. `visual`; several only together with `op`"),
    ],
) -> AssetPath | ZarrAsset | OperatorInput:
    """Turn dataset, item and asset into something a reader may open — and nothing else.

    A tile also has to name a level this dataset is released for
    (:func:`_check_zoom_released`) — checked first, so a level nobody serves costs
    no request to the source.

    ``asset`` is required rather than defaulted from the registry's standard
    visualisation: a tile URL is supposed to say what it shows (adr/0001 Z4), and a
    default that lives in the registry would make two releases of the platform answer
    the same URL with two pictures. The standard visualisation travels to the client
    on the collection (``earthx:default_render``), which is where it can be a default.

    With ``op``, ``op_version`` and ``params`` the URL asks for an operator over one or
    several assets of the item (M4-09, adr/0014 §6.2) — on a tile, its TileJSON or the statistics (M4-19c) only. The three
    may repeat, up to :data:`MAX_OPERATOR_STEPS` times, for a chain of steps (M4-18b).
    """
    state = request.app.state
    config = _dataset_config(state, dataset)
    _check_display_allowed(config)
    _check_zoom_released(request, config)
    _refuse_free_parameters(request)
    requested = _operator_request(request, config)
    if requested is None:
        if "band" in request.query_params:
            raise HTTPException(status_code=400, detail="band is for tiles with op")
        if len(asset) != 1:
            raise HTTPException(status_code=400, detail="name one asset, or several together with op")
        stac_item = await _fetch_item(state, dataset, item)
        target_gsd = target_gsd_for(request, stac_item)
        return _resolve_asset_path(state, stac_item, config=config, item=item, asset=asset[0], target_gsd=target_gsd)
    route = request.scope.get("route")
    if getattr(route, "name", None) not in _OPERATOR_ROUTES:
        raise HTTPException(status_code=400, detail="op is for tiles, their TileJSON and statistics only")
    if len(set(asset)) != len(asset):
        raise HTTPException(status_code=400, detail="name each asset once")
    bands = _bands_request(request)
    stac_item = await _fetch_item(state, dataset, item)
    target_gsd = target_gsd_for(request, stac_item)
    return _operator_input(
        state,
        stac_item,
        config=config,
        item=item,
        assets=asset,
        steps=requested,
        bands=bands,
        target_gsd=target_gsd,
    )


_OpQuery = Annotated[
    list[str] | None, Query(description="operator of a computed tile, such as `band_math`; repeated for a chain")
]
_OpVersionQuery = Annotated[
    list[Annotated[int, Field(ge=1)]] | None, Query(description="version of the operator, once per `op`")
]
_ParamsQuery = Annotated[
    list[str] | None,
    Query(description=f"its parameters, as JSON, once per `op`; at most {MAX_OPERATOR_PARAMS_CHARS} characters each"),
]


_BandQuery = Annotated[
    list[Annotated[str, Field(max_length=MAX_BAND_CHARS)]] | None,
    Query(
        description=(
            "the band of the stock a tile with steps of version 2 shows; the last band a `band_math` step added if none is "
            "named, else the first. Three, in the order red, green, blue, for a colour picture (no colormap; one "
            "`rescale`, or one per channel). "
            f"At most {MAX_BAND_CHARS} characters each"
        ),
    ),
]


def _kernels(steps: tuple[tuple[Any, Any], ...]) -> Callable[[ImageData], ImageData]:
    def chain(image: ImageData) -> ImageData:
        for operator, parameters in steps:
            image = operator.run(image, parameters)
        return image

    return chain


def operator_post_process(
    src_path: Annotated[Any, Depends(dataset_asset_path)],
    op: _OpQuery = None,
    op_version: _OpVersionQuery = None,
    params: _ParamsQuery = None,
    band: _BandQuery = None,
) -> Callable[[ImageData], ImageData] | None:
    """TiTiler's ``process_dependency`` for our tile: the operators' kernels, the ones a job calls.

    The path dependency has already validated ``op`` and ``band`` and built the inputs, so this only
    hands the kernels, one after the other, to the factory. TiTiler's own ``algorithm``
    parameters are gone (plan M4-09, F3).
    """
    if not isinstance(src_path, OperatorInput):
        return None
    return _kernels(src_path.steps)


def _open_reader(src_path: Any, **reader_params: Any) -> Any:
    """The reader of the tile: ours for an operator's inputs, `access`'s for a single asset."""
    if isinstance(src_path, OperatorInput):
        return _operator_support().reader(src_path, **reader_params)
    return open_asset(src_path, **reader_params)


def _open_mosaic_reader(src_path: Any, **reader_params: Any) -> Any:
    """The reader of the mosaic tile: the worker core's for steps (NM4-04), `access`'s for the scenes alone."""
    if isinstance(src_path, MosaicOperatorInput):
        return _operator_support().mosaic_reader(src_path, **reader_params)
    return open_mosaic(src_path, **reader_params)


def _declared_query(request: Request) -> set[str]:
    """The query parameters the matched route declares, its own and those of its dependencies."""

    def names(dependant: Any) -> Iterator[str]:
        yield from (parameter.alias for parameter in dependant.query_params)
        for sub in dependant.dependencies:
            yield from names(sub)

    route = request.scope.get("route")
    return set(names(route.dependant)) if route is not None else set()


async def _validate_before_fetching(request: Request) -> None:
    """Everything FastAPI would check of this request, before a single item is fetched.

    FastAPI solves the dependencies of a route one after the other and checks the route's own path and
    query parameters last, so the path dependency below would fetch up to 64 items for a request that is
    refused afterwards for its format, its tile matrix set or a ``tilesize``. This runs the same solving
    on the matched route without that dependency and the steps that hang on it (``op`` is judged by the path
    dependency itself, before the fetch): the other dependencies (``bidx``, ``rescale``, the
    zoom limits of a TileJSON …) and the route's own parameters are checked here, and a refusal is the
    ``422`` FastAPI would have answered, with nothing asked of the source.
    """
    route = request.scope["route"]
    skipped = (mosaic_scenes, mosaic_post_process, overview_scenes)
    dependant = dataclasses.replace(
        route.dependant, dependencies=[sub for sub in route.dependant.dependencies if sub.call not in skipped]
    )
    async with AsyncExitStack() as stack:
        solved = await solve_dependencies(
            request=request,
            dependant=dependant,
            dependency_overrides_provider=request.app,
            async_exit_stack=stack,
            embed_body_fields=False,
        )
    if solved.errors:
        raise RequestValidationError(solved.errors)


def _mosaic_zooms(config: DatasetConfig) -> tuple[int, int]:
    """The levels a mosaic tile of this dataset serves: the released range (adr/0032 §6.2).

    Since M5-30b every released level has a mosaic; the budget per tile bounds what one costs. ``501`` without a
    released range, before any item is fetched.
    """
    if config.viewer is None:
        raise HTTPException(
            status_code=501, detail=f"{config.dataset_id!r} names no released zoom range (earthx:viewer)"
        )
    return config.viewer.min_zoom, config.viewer.max_zoom


def _mosaic_zoom_range(request: Request) -> tuple[int, int]:
    """The zoom range of a mosaic's TileJSON: what :func:`_mosaic_zooms` says for the dataset in the path."""
    return _mosaic_zooms(_dataset_config(request.app.state, str(request.path_params.get("dataset"))))


_SELECTION_DATABASE_DETAIL = "mosaic tiles need the item cache and the stored selections, and the catalogue database is not reachable"


def _selection_store(state: Any) -> SelectionStore:
    """The store of the selections, or the ``503`` that says there is no database to keep them in."""
    store = getattr(state, "earthx_mosaic_selections", None)
    if getattr(state, "earthx_cache_pool", None) is None or store is None:
        raise OrderRefused(503, _SELECTION_DATABASE_DETAIL, "items")
    return store


async def _load_selection(state: Any, dataset: str, selection: str) -> Selection:
    """The selection a tile URL names: ``410`` where it is gone, ``404`` where it belongs to another dataset.

    A selection that expired or never was is gone the same way for the map: it creates it again from its list, which gives
    the same id (adr/0032 §10.2).
    """
    store = _selection_store(state)
    try:
        chosen = await store.get(selection)
    except psycopg.Error as error:
        # The kind of failure only: the driver's text can name the host and the user.
        LOGGER.warning("the catalogue database failed under a mosaic tile: %s", type(error).__name__)
        raise OrderRefused(503, _SELECTION_DATABASE_DETAIL, "items") from None
    if chosen is None:
        raise OrderRefused(
            410,
            f"no selection {selection!r}: it expired or never existed; create it again with POST /collections/{dataset}/mosaic",
            "items",
        )
    if chosen.dataset_id != dataset:
        raise OrderRefused(404, f"no selection {selection!r} of {dataset!r}", "items")
    return chosen


async def mosaic_scenes(
    request: Request,
    dataset: Annotated[str, Path(description="dataset id of the registry")],
    selection: Annotated[str, Path(description="id of a selection, from `POST /collections/{dataset}/mosaic`")],
) -> MosaicScenes | MosaicOperatorInput | MosaicLayout:
    """Turn dataset and selection into the scenes a mosaic tile reads, in the order it reads them.

    The path dependency of the mosaic route, in the order of plan M4-17 §4.2: everything that costs no request first
    (licence, level, the shape of the query), then the selection, then the items of the scenes **this tile** reads and
    last the address of each through the gateway policy, as for the tile of one item. The selection holds the order,
    which the creation took from the **whole** list, and the outline of each scene, so a tile that touches only some
    scenes still picks the scene the mosaic job over the same list picks (S5, `access.crop_rules.mosaic_order`) and
    fetches no other item (M5-30b part 3).

    A TileJSON names no tile and fetches no item: it answers from the order and the extent the selection holds.

    With ``op``, ``op_version`` and ``params`` (NM4-04) the tile is the preview of the mosaic job: the steps are
    judged as on the tile of one item, and the dataset has to allow what the job's order needs — all before the
    selection is read (KE1, KE2). The band the tile shows is judged on the first scene it reads.
    """
    state = request.app.state
    config = _dataset_config(state, dataset)
    _check_display_allowed(config)
    _check_zoom_released(request, config)
    _mosaic_zooms(config)
    try:
        mosaic_tiles.check_length(request.scope.get("raw_path") or b"", request.scope.get("query_string") or b"")
        grid = mosaic_tiles.mosaic_tile(request.path_params)
        mosaic_tiles.check_selection_id(selection)
        mosaic_tiles.check_query(request.query_params, _declared_query(request))
    except OrderRefused as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    steps = _operator_request(request, config)
    bands = _bands_request(request) if steps is not None else None
    if steps is None and "band" in request.query_params:
        raise HTTPException(status_code=400, detail="band is for tiles with op")
    try:
        if steps is not None and not config.capabilities.reprojection:
            # The words of the mosaic job's order (`api.intake._one_overpass`): the tile shows nothing it refuses.
            raise OrderRefused(
                422, f"{config.dataset_id!r} does not allow reprojection, which a mosaic of scenes may need", "applicable"
            )
        await _validate_before_fetching(request)
        chosen = await _load_selection(state, dataset, selection)
    except OrderRefused as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    assets = list(chosen.assets)
    if steps is None and len(assets) != 1:
        raise HTTPException(status_code=400, detail="a selection of several assets is for tiles with op")
    plan = run_steps = judged = None
    if steps is not None:
        # What the steps and the bands the selection stored decide, before any item is fetched (KE1): the TileJSON refuses
        # what a tile refuses, and the first scene a tile reads is no longer needed to say which assets the band needs.
        plan, assets, run_steps, judged = _judge_on_selection(chosen, steps, bands)
    if grid is None:
        return _layout(chosen, plan, judged, steps is not None)
    fetches, source = state.earthx_item_fetches, state.earthx_item_source
    try:
        touching = mosaic_tiles.touching_scenes(chosen.order, chosen.outlines, grid)
        cut = mosaic_tiles.scenes_touching(
            chosen.order, chosen.outlines, grid, files_per_scene=len(assets), touching=touching
        )
        items = await mosaic_tiles.fetch_items(fetches, source, dataset, cut.read)
    except OrderRefused as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    read = cut.read
    refs = {(item_id, key): _resolve_ref(items[item_id], config=config, item=item_id, asset=key) for item_id in read for key in assets}
    outcome = mosaic_tiles.TileOutcome.of(request.scope)
    budget = ReadBudget(mosaic_tiles.TILE_TIME_BUDGET_S)
    if outcome is not None:
        outcome.left_out = cut.left_out
        # Only the read without steps keeps to the time; the worker core reads a tile with steps (NM4-04).
        outcome.budget = budget if steps is None else None
    if steps is None:
        scenes = tuple(
            _open_ref(state, refs[(item_id, assets[0])], target_gsd=target_gsd_for(request, items[item_id]))
            for item_id in read
        )
        return MosaicScenes(dataset, scenes, chosen.bounds, budget)
    scenes_with_steps = []
    for item_id in read:
        described = {key: _describe_one(items, refs, config, item_id, key) for key in assets}
        scenes_with_steps.append(
            tuple(
                (
                    described[key],
                    _open_ref(
                        state,
                        refs[(item_id, key)],
                        target_gsd=target_gsd_for(request, items[item_id]),
                        decode_cf=described[key].scaling == "store-cf",
                    ),
                )
                for key in assets
            )
        )
    return MosaicOperatorInput(
        dataset, tuple(scenes_with_steps), tuple(run_steps), chosen.bounds, None if plan is None else plan.bands
    )


def _judge_on_selection(
    chosen: Selection, steps: list[tuple[Any, Any]], bands: tuple[str, ...] | None
) -> tuple[Any, list[str], list[tuple[Any, Any]], Any]:
    """The band plan and the steps judged on what the selection stored of its assets: ``(plan, assets, steps, left)``.

    The scenes of a selection were checked to scale, name and unit each asset alike when it was created, so the first
    scene's description stands for all. The refusals are those of the tile of one item: ``422`` with the name for a
    band the steps do not leave or a step that does not fit, ``400`` for a ``band`` next to a step of version 1.
    ``left`` is what the steps leave of the bands (``None`` where the items do not say how many bands an asset has).
    """
    support = _operator_support()
    entries = {key: support.resolved_input.model_validate(chosen.described[key]) for key in chosen.assets}
    plan = _band_plan(support, list(entries.values()), steps, bands)
    assets = list(chosen.assets if plan is None else plan.assets)
    run_steps = steps if plan is None else list(plan.steps)
    try:
        left = support.judge_described_bands([entries[key] for key in assets], run_steps)
    except support.recipe_invalid as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return plan, assets, run_steps, left


def _layout(chosen: Selection, plan: Any, left: Any, with_steps: bool) -> MosaicLayout:
    """What the TileJSON of a selection says of the bands, from what the selection stored and no scene.

    With steps the band or the three bands the picture shows (``None`` for steps of version 1), their unit where they
    share one, and ``float32``, the type the steps compute in; without steps the data type the scenes share.
    """
    if with_steps:
        units = {band.unit for band in left.bands} if left is not None else set()
        return MosaicLayout(
            chosen.dataset_id,
            chosen.order,
            chosen.bounds,
            None if plan is None else tuple(plan.bands),
            next(iter(units)) if len(units) == 1 else None,
            "float32",
        )
    stored = _operator_support().resolved_input.model_validate(chosen.described[chosen.assets[0]])
    types = {band.data_type for band in stored.bands}
    return MosaicLayout(
        chosen.dataset_id, chosen.order, chosen.bounds, data_type=next(iter(types)) if len(types) == 1 else None
    )


def _selection_answer(dataset: str, selection: str, status_code: int) -> JSONResponse:
    """The answer of the creation: the id and where its tiles and its TileJSON are, relative to this app."""
    base = f"/collections/{dataset}/mosaic/{selection}"
    return JSONResponse(
        status_code=status_code,
        content={"id": selection, "tiles": f"{base}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}", "tilejson": f"{base}/WebMercatorQuad/tilejson.json"},
    )


async def _read_selection_body(request: Request) -> mosaic_tiles.SelectionRequest:
    """The body of the creation, read up to :data:`~earthx.api.mosaic_tiles.MAX_SELECTION_BODY_BYTES` and no further.

    ``413`` from the ``Content-Length`` before a byte is read, and from the bytes read for a body that did not say; ``422``
    for one that is no JSON of the right shape, with the names of the fields and no value.
    """
    limit = mosaic_tiles.MAX_SELECTION_BODY_BYTES
    too_large = OrderRefused(413, f"the body of a selection is at most {limit} bytes", "order")
    declared = request.headers.get("content-length", "")
    if declared.isdecimal() and int(declared) > limit:
        raise too_large
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > limit:
            raise too_large
    try:
        return mosaic_tiles.SelectionRequest.model_validate_json(bytes(raw))
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(map(str, entry['loc'])) or 'body'}: {entry['msg']}"
            for entry in error.errors(include_url=False, include_input=False, include_context=False)
        )
        raise OrderRefused(422, f"the body of a selection is not valid: {problems}", "order") from None


async def create_mosaic_selection(
    request: Request, dataset: Annotated[str, Path(description="dataset id of the registry")]
) -> JSONResponse:
    """Create the selection of a mosaic: ``{"id", "tiles", "tilejson"}``, ``201``, or ``200`` where it exists (M5-30b part 3).

    The body is ``{"items": [...], "assets": [...]}``: two to :data:`~earthx.api.mosaic_tiles.MAX_SELECTION_ITEMS`
    scenes of one overpass, each once, and the assets they are read from. The id is the hash of that content
    (`catalog.mosaic_selection.selection_id`), so the same content is the same id wherever and whenever it is created, and
    creating one that exists only moves its end seven days out, without a request to the source. Otherwise the scenes are
    fetched in batches (one search of the source for a hundred ids, not a request each), checked as a tile checks them
    (one overpass, every asset on every scene, a usable outline), put in the order of the mosaic job and stored with
    their outlines, so that a tile fetches only the scenes it reads.

    Everything that costs no request comes first: dataset, licence tier, the released range, the shape of the body.
    """
    state = request.app.state
    config = _dataset_config(state, dataset)
    _check_display_allowed(config)
    _mosaic_zooms(config)
    viewer = config.viewer
    assert viewer is not None  # `_mosaic_zooms` answered 501 otherwise
    try:
        body = await _read_selection_body(request)
        ids, assets = mosaic_tiles.check_selection(body.items, body.assets)
        store = _selection_store(state)
        selection = selection_id(dataset, assets, ids)
        try:
            if await store.renew(selection):
                return _selection_answer(dataset, selection, 200)
        except psycopg.Error as error:
            LOGGER.warning("the catalogue database failed under a mosaic selection: %s", type(error).__name__)
            raise OrderRefused(503, _SELECTION_DATABASE_DETAIL, "items") from None
        batches = getattr(state, "earthx_item_batches", None)
        if batches is None:
            raise OrderRefused(503, _SELECTION_DATABASE_DETAIL, "items")
        items = await mosaic_tiles.fetch_selection_items(batches, dataset, ids)
        mosaic_tiles.check_one_overpass(items, viewer)
        refs = {(item_id, key): _resolve_ref(items[item_id], config=config, item=item_id, asset=key) for item_id in ids for key in assets}
        _check_one_crs_per_scene(refs, ids, assets)
        order = mosaic_order({item_id: refs[(item_id, assets[0])].crs for item_id in ids})
        described = _describe_alike(items, refs, config=config, order=order, assets=assets)
        chosen = Selection.build(
            selection,
            dataset,
            assets,
            {item_id: outline_source(items[item_id]) for item_id in ids},
            order,
            {key: described[(order[0], key)].model_dump(mode="json") for key in assets},
        )
        try:
            await store.put(chosen)
        except psycopg.Error as error:
            LOGGER.warning("the catalogue database failed under a mosaic selection: %s", type(error).__name__)
            raise OrderRefused(503, _SELECTION_DATABASE_DETAIL, "items") from None
    except OrderRefused as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    LOGGER.info("mosaic selection created with %d scenes of %d assets", len(ids), len(assets))
    return _selection_answer(dataset, selection, 201)


async def overview_scenes(
    request: Request, dataset: Annotated[str, Path(description="dataset id of the registry")]
) -> MosaicScenes:
    """The scenes of the substitute that a tile below the first level of ``dataset`` reads (plan M5-30b §4.8, A5).

    The route hangs on the dataset and the tile alone, so that a tile has the same URL and the same picture for every
    user, whatever they selected. Only a dataset with ``overview: substitute`` has it (else ``404``), and the licence of
    the dataset and of the substitute allow display. The level has to lie below the first level of the dataset
    (else ``400``); from there on the dataset's own tiles serve. What the pixels are is the substitute's picture, drawn
    with the display parameters of the request; the route has no statistics, no info and no TileJSON.

    The items are those of the substitute that touch the tile, from our own pgstac, in the order of the mosaic
    and cut to the budget per tile. The asset is the first of the substitute's default render that an item carries.
    """
    state = request.app.state
    config = _dataset_config(state, dataset)
    _check_display_allowed(config)
    viewer = config.viewer
    if viewer is None or viewer.overview is not OverviewMode.SUBSTITUTE or viewer.overview_substitute is None:
        raise HTTPException(status_code=404, detail=f"{dataset!r} draws no substitute below its first level")
    substitute = _dataset_config(state, viewer.overview_substitute)
    _check_display_allowed(substitute)
    assert substitute.default_render is not None  # the registry compares the unit of its default band
    _refuse_free_parameters(request)
    try:
        try:
            zoom = int(request.path_params["z"])
        except (KeyError, ValueError):
            raise OrderRefused(400, "not a tile of a grid this tiler serves", "order") from None
        if not 0 <= zoom < viewer.min_zoom:
            raise OrderRefused(
                400,
                f"zoom level {zoom} is not below the first level of {dataset!r}, z{viewer.min_zoom}, where its own tiles begin",
                "order",
            )
        grid = mosaic_tiles.mosaic_tile(request.path_params)
        assert grid is not None  # the path has a level
        await _validate_before_fetching(request)
        if substitute.source.item_holding is not ItemHolding.MATERIALIZED:
            # No dataset names a federated substitute yet: its items would come from the source's own search, which
            # this route has no budget for. Refused until a case exists and decides it.
            raise OrderRefused(501, "a federated dataset cannot serve as a substitute yet", "items")
        found, capped = await mosaic_tiles.items_in_tile(getattr(state, "earthx_cache_pool", None), substitute.dataset_id, grid)
        refs: dict[str, ResolvedAsset] = {}
        items: dict[str, dict[str, Any]] = {}
        for stac_item in found:
            key = next((key for key in substitute.default_render.assets if key in (stac_item.get("assets") or {})), None)
            if key is None:
                continue
            item_id = str(stac_item.get("id"))
            refs[item_id] = _resolve_ref(stac_item, config=substitute, item=item_id, asset=key)
            items[item_id] = stac_item
        if not items:
            raise OrderRefused(404, "the tile does not touch these items", "items")
        outlines = mosaic_tiles.footprints_of(items)
        order = mosaic_order({item_id: ref.crs for item_id, ref in refs.items()})
        touching = mosaic_tiles.scenes_touching(order, outlines, grid)
    except OrderRefused as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    budget = ReadBudget(mosaic_tiles.TILE_TIME_BUDGET_S)
    outcome = mosaic_tiles.TileOutcome.of(request.scope)
    if outcome is not None:
        outcome.left_out = touching.left_out + int(capped)
        outcome.budget = budget
        outcome.source = mosaic_tiles.SUBSTITUTE_SOURCE
    scenes = tuple(
        _open_ref(state, refs[item_id], target_gsd=target_gsd_for(request, items[item_id])) for item_id in touching.read
    )
    return MosaicScenes(substitute.dataset_id, scenes, mosaic_tiles.union_bounds(outlines), budget)


def overview_post_process() -> None:
    """The ``process_dependency`` of the substitute's tile: none. No ``algorithm``, no steps; a picture only."""
    return None


class MosaicOrderRequest(BaseModel):
    """Body of ``POST /collections/{dataset}/scene-order`` (NM4-24): the scenes of one pass and the asset they are read from.

    A field the route does not know is refused, as a parameter the mosaic tile does not declare is: an AOI or a filter
    that was quietly dropped would look like an answer to a question the route never heard.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[str] = Field(
        min_length=mosaic_tiles.MIN_MOSAIC_ITEMS,
        max_length=MAX_ORDER_ITEMS,
        description="item ids of one pass, each once",
    )
    asset: str = Field(min_length=1, max_length=128, description="the asset key whose CRS decides the order")


async def scene_order(
    request: Request, dataset: Annotated[str, Path(description="dataset id of the registry")], body: MosaicOrderRequest
) -> dict[str, list[str]]:
    """The order a mosaic reads these scenes in, without a mosaic: ``{"order": [item id, ...]}`` (NM4-24).

    For a pass the mosaic tile cannot take (more than 64 scenes, a mosaic the tile refused) the map draws the scenes
    one by one; this answers with the order of :func:`mosaic_order` so that they lie in an overlap as the mosaic, the crop and the export have them. The ids travel in the body, as 64 and more of
    them do not belong in a URL. Only the items and the CRS of the asset are read, no pixel; the licence tier and
    the item cache are those of the mosaic tile.
    """
    state = request.app.state
    config = _dataset_config(state, dataset)
    _check_display_allowed(config)
    try:
        if len(set(body.items)) != len(body.items):
            raise OrderRefused(400, "name each item once", "order")
        if not all(mosaic_tiles.ITEM_ID.match(item_id) for item_id in body.items):
            raise OrderRefused(400, "an item id has the shape the sources give theirs", "order")
        if getattr(state, "earthx_cache_pool", None) is None:
            raise OrderRefused(
                503, "scene orders need the item cache, and the catalogue database is not reachable", "items"
            )
        ids = sorted(body.items)
        items = await mosaic_tiles.fetch_items(state.earthx_item_fetches, state.earthx_item_source, dataset, ids)
        crs_by_item = {
            item_id: _resolve_ref(items[item_id], config=config, item=item_id, asset=body.asset).crs for item_id in ids
        }
        return {"order": mosaic_order(crs_by_item)}
    except OrderRefused as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None


def _describe_one(
    items: dict[str, dict[str, Any]],
    refs: dict[tuple[str, str], ResolvedAsset],
    config: DatasetConfig,
    item_id: str,
    key: str,
) -> Any:
    """One asset of one item as a resolved input with the bands and scaling its item describes; nothing is opened."""
    support = _operator_support()
    ref = refs[(item_id, key)]
    try:
        bands, scaling, unit = support.describe_bands(items[item_id], config, ref)
        return support.resolved_input(
            asset=support.resolved_asset(**ref.to_json()),
            version=None,
            bands=bands,
            scaling=scaling,
            unit=unit,
            gsd=None,
        )
    except OrderRefused as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    except ValidationError:
        raise HTTPException(status_code=502, detail=malformed_item_detail(item_id)) from None


def _check_one_crs_per_scene(refs: dict[tuple[str, str], ResolvedAsset], ids: list[str], assets: list[str]) -> None:
    """``422`` for a selection whose assets of one scene lie in different CRS (M5-30b part 3, F6).

    The order of a mosaic is decided per scene from one CRS (:func:`~earthx.access.crop_rules.mosaic_order`), and the
    selection stores one order for all its assets. A scene reads all its assets in the CRS its item names, so the
    check can only fail where the resolution gives an asset a CRS of its own.
    """
    for item_id in ids:
        if len({refs[(item_id, key)].crs for key in assets}) > 1:
            raise OrderRefused(
                422,
                f"the assets of scene {item_id!r} lie in different coordinate reference systems; "
                "a mosaic reads each scene in one",
                "items",
            )


def _describe_alike(
    items: dict[str, dict[str, Any]],
    refs: dict[tuple[str, str], ResolvedAsset],
    *,
    config: DatasetConfig,
    order: list[str],
    assets: list[str],
) -> dict[tuple[str, str], Any]:
    """Each asset of each scene with the bands and scaling its item describes, judged as the job judges them.

    At the creation of a selection, over **all** its scenes and assets, so that every tile of it gives the same answer
    (NM4-04 §8.1) and no tile has to compare scenes: the scenes scale each asset alike and name the same units (the part of
    the job's ``check_alike`` the items decide; the files are compared by the reader), and a Zarr mosaic lies in one CRS
    (``check_scope``). ``422`` with the words of the mosaic job. Nothing is opened.
    """
    described = {(item_id, key): _describe_one(items, refs, config, item_id, key) for item_id in order for key in assets}
    first = order[0]
    for key in assets:
        anchor = described[(first, key)]
        for item_id in order[1:]:
            entry = described[(item_id, key)]
            if (entry.scaling, [(b.scale, b.offset) for b in entry.bands]) != (
                anchor.scaling,
                [(b.scale, b.offset) for b in anchor.bands],
            ):
                raise OrderRefused(422, f"the scenes of the mosaic scale {key!r} differently", "items")
            if (entry.unit, [b.unit for b in entry.bands]) != (anchor.unit, [b.unit for b in anchor.bands]):
                raise OrderRefused(
                    422,
                    f"the scenes of the mosaic differ in the bands, data type, nodata or unit of {key!r}",
                    "items",
                )
    read = list(refs.values())
    if any(ref.reader == "zarr" for ref in read) and len({ref.crs for ref in read}) > 1:
        raise OrderRefused(
            422, "a mosaic of Zarr scenes needs all scenes in one CRS; warping Zarr is not done yet", "items"
        )
    return described


def mosaic_post_process(
    src_path: Annotated[Any, Depends(mosaic_scenes)],
    op: _OpQuery = None,
    op_version: _OpVersionQuery = None,
    params: _ParamsQuery = None,
    band: _BandQuery = None,
) -> Callable[[ImageData], ImageData] | None:
    """The ``process_dependency`` of the mosaic tile: the kernels of the steps after the mosaic, as in the job."""
    if not isinstance(src_path, MosaicOperatorInput):
        return None
    return _kernels(src_path.steps)


#: On a `413` of the crop: whether the same selection fits an export job (M4-11 K5); M4-11b-2 reads it.
#: ``available``: it fits. ``too-large`` (M4-11b K9): it would run as a job but is over the job's cap, so
#: the dialog can say why the job is not offered. No header: no job for this selection at all.
EXPORT_JOB_HEADER = "X-Export-Job"
EXPORT_JOB_AVAILABLE = "available"
EXPORT_JOB_TOO_LARGE = "too-large"

# The longest a crop may be estimated to take and still run in the request (adr/0032 §10.3, F13, Otto 11.11.2026).
# Replaces the fixed 25 scenes: the estimate of `processing.plan` counts the files opened and the megabytes read.
MAX_CROP_SECONDS = 60.0


def estimated_crop_seconds(files: int, input_bytes: int) -> float:
    """Seconds a crop is estimated to take: a first open per file plus the time per megabyte (adr/0014 §5.5)."""
    from earthx.processing.plan import SECONDS_PER_ASSET, SECONDS_PER_INPUT_MB

    return SECONDS_PER_ASSET * files + SECONDS_PER_INPUT_MB * input_bytes / 1_000_000


def _export_job_headers(config: DatasetConfig, planned_total: int) -> dict[str, str] | None:
    """Whether the refused crop fits an export job (M4-11 K5): COG only (F6), under the job's own cap (F5).

    A word, no number and no geometry, like ``X-Skipped-Groups``.
    """
    if config.zarr is not None:
        return None
    return {EXPORT_JOB_HEADER: EXPORT_JOB_AVAILABLE if planned_total <= MAX_JOB_BYTES else EXPORT_JOB_TOO_LARGE}


# The stages of `OrderRefused` at which a crop is refused rather than delivered without
# its `recipe.json` (Otto, 07.10.2026): a foreign host, an input gone from its source.
_RECIPE_ABORTS = frozenset({"hosts", "version"})


class DownloadRequest(BaseModel):
    """Body of ``POST /collections/{dataset}/download`` (M2-06, architekturplan 6.4 D3).

    A POST body rather than URL parameters, unlike the tile path's Z4 rule: the
    tile URL has to be cache-stable and CDN-able, but a crop answers once and is
    never cached (D11), and an AOI polygon can be far larger than fits comfortably
    in a query string.

    ``groups`` (M3-17, replacing the flat ``items`` list of M2-06/M3-18):
    item ids, grouped exactly as the results list groups them (the same
    per-overpass grouping PR #84's group outline already draws on the map) —
    "download folgt der Ansicht" (P19). Each group mosaics into its own
    merged file; more than one group lands in the same ZIP as separate files
    (:func:`~earthx.access.download.build_download_zip`). A single group is
    simply a list of one, the M2-06 shape.
    """

    groups: list[list[str]] = Field(
        min_length=1,
        max_length=64,
        description="item ids per group, one merged file per group, as the results list groups them",
    )
    assets: list[str] = Field(min_length=1, max_length=32, description="asset keys, e.g. `visual`")
    aoi: dict[str, Any] = Field(description="a GeoJSON Polygon or MultiPolygon, in WGS84")
    resolution: Literal[1] = Field(
        default=1,
        description=(
            "Always 1, the resolution of the source: a coarser factor is no longer offered (Otto, 03.11.2026, NM4-75). "
            "A file is in the resolution of its source, or in `common_resolution` for one multi-band file. "
            "Any other value is refused."
        ),
    )
    form: Literal["per_band", "per_resolution", "multi_band"] = Field(
        default="per_band",
        description=(
            "`per_band`: one GeoTIFF per band in its own resolution; `per_resolution`: one multi-band GeoTIFF per "
            "resolution that occurs; `multi_band`: one GeoTIFF at `common_resolution`. Nothing is converted except "
            "for `multi_band` (NM4-75)."
        ),
    )
    common_resolution: float | None = Field(
        default=None,
        gt=0,
        le=1000,
        description="the pixel size in metres of the one file of `multi_band`; with no other form",
    )

    @model_validator(mode="after")
    def _form_and_resolution_agree(self) -> DownloadRequest:
        if (self.form == "multi_band") != (self.common_resolution is not None):
            raise ValueError("common_resolution goes with the form multi_band, and with no other")
        return self

    @field_validator("groups")
    @classmethod
    def _groups_are_nonempty_and_disjoint(cls, groups: list[list[str]]) -> list[list[str]]:
        """Each group names at least one item, and no item id repeats across (or within) a group.

        A repeat would either mosaic the same scene onto itself for no reason,
        or — across two groups — write the same item into two merged files
        without saying which one "really" contains it; refused up front (422)
        rather than silently accepted (M3-17 plan §5).
        """
        if any(len(group) == 0 for group in groups):
            raise ValueError("each group must name at least one item")
        seen: set[str] = set()
        for group in groups:
            for item_id in group:
                if item_id in seen:
                    raise ValueError(f"item {item_id!r} is named more than once across the groups")
                seen.add(item_id)
        return groups


async def download_crop(
    request: Request,
    dataset: Annotated[str, Path(description="dataset id of the registry")],
    body: DownloadRequest,
) -> StreamingResponse:
    """The AOI crop as a ZIP of COGs plus :data:`~earthx.access.download.NOTICE_FILENAME`.

    Every check that can run before an asset is opened runs first, in the order
    M2-06's acceptance criteria list the failures: unknown dataset, licence tier,
    a malformed AOI, an unknown item, an AOI that touches none of the given items,
    the item-count guard, then the output size cap (M3-18: built from the AOI and
    the items' own metadata, not from how many items or assets were asked for),
    then the estimated duration (:data:`MAX_CROP_SECONDS`, adr/0032 §10.3)
    — only after all of that does anything reach `gateway`.

    **Per group, not per item (M3-17).** ``body.groups`` names one or more
    groups; each is filtered and cropped on its own extent exactly as a
    single-group request always was. A group that does not touch the AOI at
    all is *dropped*, not a failure — the request only fails with a `400`
    once every group has been dropped that way, the same threshold a
    single-group request already had. The item-count and output-size caps
    below cover the *whole* request, summed over every surviving group: two
    groups that would each fit alone can still add up to more than one
    download is allowed to cost.
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

    # One fetch per item id, even where two groups would otherwise ask for it
    # twice — the request validator already refuses that, so this dict never
    # loses an entry to a second fetch overwriting the first.
    all_ids = [item_id for group in body.groups for item_id in group]
    fetched_items = await asyncio.gather(*(_fetch_item(state, dataset, item_id) for item_id in all_ids))
    items_by_id = dict(zip(all_ids, fetched_items, strict=True))

    surviving_groups: list[tuple[list[dict[str, Any]], Any]] = []
    skipped_item_ids: list[str] = []
    for group_ids in body.groups:
        group_items = [items_by_id[item_id] for item_id in group_ids]
        matched = filter_items_intersecting_aoi(group_items, aoi)
        if not matched:
            skipped_item_ids.extend(group_ids)
            continue
        try:
            # AOI ∩ union of this group's own item footprints (Otto,
            # 23.09.2026, M3-18 §13) — the same geometry the frontend's group
            # outline already shows before a download starts (PR #84,
            # `groupOutline.ts`). Tighter than the bbox pre-filter above, so
            # it also catches the case that filter passed on a bbox alone but
            # the items' real, often rotated footprints do not actually reach
            # (bug A, Otto's review of PR #86) — such a group is dropped the
            # same way a group missing the bbox pre-filter already is.
            region = compute_crop_region(matched, aoi)
        except AoiOutsideItems:
            skipped_item_ids.extend(group_ids)
            continue
        surviving_groups.append((matched, region))

    if not surviving_groups:
        raise HTTPException(status_code=400, detail="the AOI does not touch any of the given items")

    # The attribution names the year of acquisition, from the scenes that stay (NM4-01); a scene with
    # no date is refused before anything is read, not given the year of the download.
    try:
        years = attribution_years(config, [item for matched, _ in surviving_groups for item in matched])
    except AcquisitionYearMissing as error:
        raise HTTPException(status_code=422, detail=f"{error}; the attribution of this dataset names the year") from None

    # Deduplicated, order kept: `assets` is a caller's list and may repeat a key,
    # and two identical keys would otherwise write the same file name into the
    # archive twice (M2-10 review). One request for `visual` is one `visual.tif`.
    wanted = list(dict.fromkeys(body.assets))
    # An auxiliary file that is no raster (the ZIP of XYZ files) is refused before any band is described or read.
    try:
        for matched, _ in surviving_groups:
            for matched_item in matched:
                for asset in wanted:
                    check_is_raster(matched_item, config, asset)
    except InvalidAssetKey as error:
        raise HTTPException(status_code=400, detail=str(error)) from None

    # What the items say about each band, for the names of the files and BANDS.txt (NM4-75), and the plan of the
    # files: refused here, before anything is read, when the bands and the form do not make one.
    if config.zarr is not None and body.form != "per_band":
        raise HTTPException(status_code=422, detail="this dataset is a Zarr store; only one file per band is offered")
    all_matched = [item for matched, _ in surviving_groups for item in matched]
    band_metas = {
        asset: band_meta_of_items(
            all_matched, asset, unit=config.band_unit(asset),
            categorical=config.mask is not None and config.mask.asset == asset,
        )
        for asset in wanted
    }  # fmt: skip
    if body.form != "per_band":
        several = [
            asset
            for asset in wanted
            if any((band_count(item, asset) or 1) > 1 for item in all_matched if asset in item.get("assets", {}))
        ]
        if several:
            raise HTTPException(
                status_code=422, detail=f"{', '.join(several)} has several bands in one file; only one file per band can hold it"
            )
    try:
        plan_files(body.form, [band_metas[asset] for asset in wanted], body.common_resolution)
    except ExportPlanError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None

    # Each file at the resolution of its source, or all at the common one (NM4-75).
    planned_by_group: list[list[PlannedOutput]] = [
        plan_outputs(matched, wanted, region, pixel_size=body.common_resolution) for matched, region in surviving_groups
    ]
    try:
        check_item_count_cap(sum(len(matched) for matched, _ in surviving_groups))
    except AoiTooLarge as error:
        raise HTTPException(status_code=413, detail=str(error)) from None
    planned_total = sum(output.total_bytes for planned in planned_by_group for output in planned)
    try:
        check_output_size_cap([output for planned in planned_by_group for output in planned])
    except AoiTooLarge as error:
        # Over the synchronous cap, the same selection may still run as an export job (M4-11 K5).
        raise HTTPException(status_code=413, detail=str(error), headers=_export_job_headers(config, planned_total)) from None
    # After the size cap, so that no size refusal changes its place. The files the crop opens: every scene of
    # every group, once per wanted asset.
    seconds = estimated_crop_seconds(sum(len(matched) for matched, _ in surviving_groups) * len(wanted), planned_total)
    if seconds > MAX_CROP_SECONDS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"This crop would take about {seconds:.0f} s; at most {MAX_CROP_SECONDS:.0f} s run here. "
                + ("Run it as a job." if config.zarr is None else "Select fewer scenes or draw a smaller area.")
            ),
            headers=_export_job_headers(config, planned_total),
        )

    # The scenes of a group are read in the order of the mosaic job and the mosaic tile, not in the
    # order of the selection (NM4-02): where scenes overlap, the crop then keeps the pixels the
    # preview shows. After the caps, so that no refusal changes its place.
    surviving_groups = [
        (_in_mosaic_order(matched, config=config, asset=wanted[0]), region) for matched, region in surviving_groups
    ]

    def _crops_for(matched_items: list[dict[str, Any]]) -> list[AssetCrop]:
        return [
            AssetCrop(
                asset=asset,
                paths=tuple(
                    _resolve_asset_path(
                        state, matched_item, config=config, item=matched_item["id"], asset=asset
                    )
                    for matched_item in matched_items
                ),
            )
            for asset in wanted
        ]

    # Scenes of one mosaic in more than one coordinate system are reprojected onto the one grid; BANDS.txt says so.
    bands_notes: list[str] = []
    for matched, _ in surviving_groups:
        crs_names = sorted(
            {
                ref.crs
                for stac_item in matched
                if (ref := _resolve_ref(stac_item, config=config, item=str(stac_item.get("id")), asset=wanted[0])).crs
            }
        )
        if len(crs_names) > 1:
            target = target_crs({str(item.get("id")): _resolve_ref(item, config=config, item=str(item.get("id")), asset=wanted[0]).crs for item in matched})
            bands_notes = [
                "Note: the scenes of a mosaic of this download lie in more than one coordinate reference system "
                f"({', '.join(crs_names)}); those not in {target} were reprojected to it and merged."
            ]
            break

    first_matched, first_region = surviving_groups[0]
    first_crops = _crops_for(first_matched)
    additional_groups = [
        GroupCrop(
            item_ids=[matched_item["id"] for matched_item in matched],
            crops=_crops_for(matched),
            region_geometry=shapely_mapping(region),
        )
        for matched, region in surviving_groups[1:]
    ]

    # The worker core stays out of the tiler's start (the intake imports it), so it is
    # loaded when the first crop asks for its recipe.
    from earthx.api.intake import acquired_day, crop_recipe_json, recipe_json_with_methods

    accepted_at = datetime.now(timezone.utc)
    recipe_omitted_cause: str | None = None
    try:
        recipe_json: bytes | None = crop_recipe_json(
            config,
            groups=[matched for matched, _ in surviving_groups],
            assets=wanted,
            aoi=body.aoi,
            accepted_at=accepted_at,
            years=years,
            layout={
                "form": body.form,
                **({"resolution_m": body.common_resolution} if body.common_resolution is not None else {}),
            },
        )
    except OrderRefused as refused:
        # By cause (Otto, 07.10.2026): an address its dataset does not declare, or an
        # input that is gone from its source, stops the download. Anything else the
        # items' metadata does to the recipe costs the ZIP its `recipe.json` only.
        if refused.stage in _RECIPE_ABORTS:
            LOGGER.warning("crop recipe refused", extra={"dataset": dataset, "stage": refused.stage})
            raise HTTPException(status_code=refused.status_code, detail=refused.detail) from None
        LOGGER.warning("crop recipe omitted", extra={"dataset": dataset, "stage": refused.stage})
        recipe_json = None
        recipe_omitted_cause = refused.stage
    # The methods text lies in the recipe, so it comes and goes with it (M4-19a, NM4-08).
    if recipe_json is not None:
        recipe_json = recipe_json_with_methods(
            recipe_json,
            config,
            acquired_on=acquired_day([item for matched, _ in surviving_groups for item in matched], config),
        )
    bib = citation_bib(config, downloaded=accepted_at.date(), years=years)

    total_planned_bytes = sum(output.total_bytes for planned in planned_by_group for output in planned)
    large = total_planned_bytes >= LARGE_DOWNLOAD_THRESHOLD_BYTES
    if large and _LARGE_DOWNLOAD_LOCK.locked():
        raise HTTPException(
            status_code=503,
            detail="another large download is running, try again shortly",
            headers={"Retry-After": "30"},
        )

    async def _build_zip() -> bytes:
        return await run_in_threadpool(
            build_download_zip,
            config=config,
            open_reader=open_asset,
            crops=first_crops,
            aoi_geometry=body.aoi,
            region_geometry=shapely_mapping(first_region),
            item_ids=[matched_item["id"] for matched_item in first_matched],
            additional_groups=additional_groups,
            skipped_item_ids=skipped_item_ids,
            recipe_json=recipe_json,
            citation_bib=bib,
            recipe_omitted_cause=recipe_omitted_cause,
            years=years,
            form=body.form,
            common_resolution=body.common_resolution,
            band_metas=band_metas,
            bands_notes=bands_notes,
            # The GDAL/VSI settings `gateway` also uses for the tile path
            # (timeouts, the read cache, no directory listings on open) —
            # missing here until M3-18 (F7 Nebenbefund), so a crop's reads
            # were unbounded and uncached. `rasterio.Env` is thread-local
            # (adr/0006's own `_read_statistics` follows the same pattern), so
            # it has to be entered inside the threadpool call, not around it.
            # The crop's own profile, not the tiles': it keeps parallel range
            # reads, which a crop gains from (NM4-26 §13, §18 point 1).
            gdal_env=state.earthx_crop_gdal_options,
        )

    try:
        if large:
            async with _LARGE_DOWNLOAD_LOCK:
                zip_bytes = await _build_zip()
        else:
            zip_bytes = await _build_zip()
    except AoiOutsideItems as error:
        # The bbox prefilter passed but the geometry itself misses every item's
        # actual footprint (a bbox is not the data — MGRS tiles are rotated).
        raise HTTPException(status_code=400, detail=str(error)) from None
    except ExportPlanError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except RioTilerError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    except (RasterioIOError, GatewayError):
        # A genuine read failure only (Otto, 23.09.2026, PR #86 review): a bug in
        # our own COG-writing code can just as easily raise a `RasterioError` that
        # is *not* `RasterioIOError` (an invalid transform, a block-size
        # constraint, a bad array shape — the same distinction the tile path's
        # `_rasterio_error`/`_rasterio_io_error` handlers already draw). Catching
        # the whole `RasterioError` hierarchy here used to relabel any of those as
        # "could not be read from the source", which is false and hides a code
        # bug behind the same message a real upstream failure gets. Anything that
        # is not `RasterioIOError` is deliberately left to propagate: `build_app`
        # already registers `_rasterio_error` for exactly this route, which logs
        # the real exception (with the request id, `logging.py`'s formatter) and
        # answers 500, never silently.
        raise HTTPException(status_code=502, detail="the asset could not be read from the source") from None
    except CorruptOutput:
        # Our own output failed its read-back twice (M3-22, F1): never hand it
        # out. The request id is in the body too, so a user can quote it.
        LOGGER.error("a generated download file did not pass verification", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=(
                "a generated file did not pass verification. Please try again; "
                f"if it keeps failing, report request ID {get_request_id()}."
            ),
        ) from None

    skipped_group_count = len(body.groups) - len(surviving_groups)
    LOGGER.info(
        "download answered",
        extra={
            "dataset": dataset,
            "groups": len(surviving_groups),
            "skipped_groups": skipped_group_count,
            "items": sum(len(matched) for matched, _ in surviving_groups),
            "assets": len(wanted),
            "bytes": len(zip_bytes),
        },
    )
    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{dataset}-crop.zip"',
            # A group dropped for not touching the AOI at all (above) is
            # recorded inside the ZIP's ATTRIBUTION.txt (`skipped_item_ids`),
            # but that only reaches the user after the file is already saved —
            # these two headers let the download dialog say so *before* that,
            # review finding 1: "der Nutzer muss das sehen". Counts only
            # (`X-Skipped-Groups`/`X-Total-Groups`), never item ids or
            # anything geometry-shaped, so the CLAUDE.md rule against AOI/query
            # data in a header still holds.
            "X-Total-Groups": str(len(body.groups)),
            "X-Skipped-Groups": str(skipped_group_count),
        },
    )


class BandsRequest(BaseModel):
    """Body of ``POST /collections/{dataset}/bands`` (NM4-75): the scenes the download dialog is opened for."""

    model_config = ConfigDict(extra="forbid")

    items: list[str] = Field(min_length=1, max_length=25, description="item ids, each once")

    @field_validator("items")
    @classmethod
    def _once(cls, items: list[str]) -> list[str]:
        if len(set(items)) != len(items):
            raise ValueError("name each item once")
        return items


async def bands_of_items(
    request: Request, dataset: Annotated[str, Path(description="dataset id of the registry")], body: BandsRequest
) -> dict[str, list[dict[str, Any]]]:
    """The bands the download dialog offers for these scenes (NM4-75), from the items and the registry alone.

    The GeoTIFF assets of the first scene without the pictures the registry calls auxiliary, each with the name, common name
    and wavelength the item gives it, its pixel size (the finest over the scenes), type, scale, offset, nodata and unit,
    whether it is the classification layer, and whether it starts ticked. A dataset with no file per band (a Zarr store) has
    none. No pixel is read; the ids travel in the body.
    """
    state = request.app.state
    config = _dataset_config(state, dataset)
    items = await asyncio.gather(*(_fetch_item(state, dataset, item_id) for item_id in body.items))
    if config.zarr is not None:
        return {"bands": []}
    table = band_table(
        items,
        auxiliary=config.auxiliary_assets,
        mask_asset=config.mask.asset if config.mask is not None else None,
        unit_of=config.band_unit,
    )
    return {"bands": [{**meta.to_json(), "preselected": ticked} for meta, ticked in table]}


def gdal_environment(request: Request) -> dict[str, str]:
    """The central GDAL configuration (M1-03) of the tile routes, built once per process."""
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


def area_statistics_cache(request: Request) -> PooledStatsCache | None:
    """The statistics cache for the measure of an area (NM4-19): a connection only around a read or a write."""
    pool = getattr(request.app.state, "earthx_cache_pool", None)
    return None if pool is None else PooledStatsCache(pool)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    user_agent_from_env()  # M5-18 §3.1: a bad EARTHX_USER_AGENT stops the start
    async with (
        cache_pool() as pool,
        Gateway(app.state.earthx_policy, resolve=app.state.earthx_resolver) as gateway,
    ):
        app.state.earthx_cache_pool = pool
        # Only with a pool: without a database this process still starts and serves
        # federated datasets as before (E5); a materialized item is then a 503.
        if pool is not None:
            async with pool.connection() as conn:
                await check_item_holdings(app.state.earthx_registry, conn)
        # The registry `build_app` was actually given, not the module-wide default
        # (M3-11a §2.2): before this field existed the two never diverged in a test,
        # because nothing here read from pgstac at all — a materialized item does.
        app.state.earthx_item_source = build_item_source(
            app.state.earthx_registry, app.state.earthx_adapters, gateway, pool
        )
        app.state.earthx_item_batches = build_item_batch_source(
            app.state.earthx_registry, app.state.earthx_adapters, gateway, pool
        )
        app.state.earthx_mosaic_selections = None if pool is None else SelectionStore(pool)
        app.state.earthx_results = _result_sources()
        yield


def _result_sources() -> ResultSources | None:
    """The tiles of job results (M4-13c-5), or ``None`` when this process has no key for the store.

    A tiler without the `S3_*` environment still serves every source; the result routes then answer
    ``503``, with a line in the log that names the missing setting and never its value. Compose gives
    this process the read-only key `earthx-tiler`.
    """
    try:
        return ResultSources(Store.from_environ(), clock=time.monotonic)
    except StoreConfigError as error:
        LOGGER.warning("job results are not served: %s", error)
        return None


def build_app(
    registry: DatasetRegistry | None = None, *, adapters: AdapterSpecs = ADAPTER_SPECS, lifespan=_lifespan
) -> FastAPI:
    """The tiler application, with everything the factory needs hung on it.

    ``registry``, ``adapters`` and ``lifespan`` are arguments so that a test can build
    the same app against a registry of its own and without a database — not so that
    a deployment can: the process entrypoint below takes none of them. A registry
    entry that asks an adapter for something ``adapters`` lacks stops the build
    (M4-01b F1). Without ``registry`` it is the one of the process (:func:`~earthx.catalog.datasets.registry`).
    """
    registry = dataset_registry() if registry is None else registry
    check_adapter_specs(registry, adapters)
    # M3-16: this process's own JSON logging, before anything can log a line
    # (K-01/K-02) — the compose command starts it with `--no-access-log`, so
    # `RequestIdMiddleware` below is this process's only access log.
    configure_logging()
    policy = policy_from_registry(registry)
    app = FastAPI(title="earthx-tiler", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    # The headers of a mosaic tile that shows a part of its scenes (adr/0032 §6.2): known only once it is read.
    app.add_middleware(mosaic_tiles.TileOutcomeHeaders)
    # Read at request time through the two small dependencies above, so a route
    # never closes over something a test cannot replace.
    app.state.earthx_policy = policy
    # Two profiles, because GDAL reads the size of its `/vsicurl/` cache once per
    # process but `MULTIRANGE` at every call, in the calling thread (NM4-26 §13, §18):
    # the tile routes, statistics, TileJSON, mosaic and result tiles read under the
    # first, the crop of the download route under the second.
    app.state.earthx_gdal_options = tile_gdal_options(policy)
    app.state.earthx_crop_gdal_options = crop_gdal_options(policy)
    # One resolver for the process, shared by the path dependency and the gateway:
    # a tile batch resolves the asset host once instead of once per tile (M2-14).
    # It caches the resolver's answer only — every address is checked again on
    # every request, by `check_url` as before.
    app.state.earthx_resolver = CachingResolver()
    app.state.earthx_item_source = None
    # The scenes of a mosaic selection are fetched by id in batches, and the selections are kept in the database (M5-30b).
    app.state.earthx_item_batches = None
    app.state.earthx_mosaic_selections = None
    # The download route (M2-06) needs the dataset's licence, title and terms —
    # nothing the path dependency above already carries.
    app.state.earthx_registry = registry
    # The item source fetches federated items through this table (adr/0011 F1).
    app.state.earthx_adapters = adapters

    factory = EarthxTilerFactory(
        path_dependency=dataset_asset_path,
        layer_dependency=BidxParams,
        process_dependency=operator_post_process,
        reader=_open_reader,
        environment_dependency=gdal_environment,
        stats_cache_dependency=statistics_cache,
        viewer_zoom_dependency=_viewer_zoom_range,
        router_prefix=ROUTER_PREFIX,
        name="tiles",
    )
    app.include_router(factory.router, prefix=ROUTER_PREFIX, tags=["Tiles"])
    # The scenes of one overpass as one tile (M4-17b): the ids travel in the URL, the process keeps
    # nothing but the item fetches that are running.
    app.state.earthx_item_fetches = mosaic_tiles.ItemFetches()
    mosaic_factory = EarthxMosaicTilerFactory(
        path_dependency=mosaic_scenes,
        layer_dependency=BidxParams,
        process_dependency=mosaic_post_process,
        reader=_open_mosaic_reader,
        environment_dependency=gdal_environment,
        viewer_zoom_dependency=_mosaic_zoom_range,
        router_prefix=MOSAIC_ROUTER_PREFIX,
        name="mosaic-tiles",
    )
    app.include_router(mosaic_factory.router, prefix=MOSAIC_ROUTER_PREFIX, tags=["Mosaic tiles"])
    app.add_api_route(
        MOSAIC_SELECTION_ROUTE,
        create_mosaic_selection,
        methods=["POST"],
        status_code=201,
        tags=["Mosaic tiles"],
        summary="Create the selection of a mosaic; its id goes into the tile URL",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": mosaic_tiles.SelectionRequest.model_json_schema()}},
            }
        },
    )
    # The picture a dataset shows below its first level where another dataset stands in (plan M5-30b §4.8): one tile route.
    overview_factory = EarthxOverviewTilerFactory(
        path_dependency=overview_scenes,
        layer_dependency=BidxParams,
        process_dependency=overview_post_process,
        environment_dependency=gdal_environment,
        router_prefix=OVERVIEW_ROUTER_PREFIX,
        name="overview-tiles",
    )
    app.include_router(overview_factory.router, prefix=OVERVIEW_ROUTER_PREFIX, tags=["Overview tiles"])
    # The tiles of a finished job (M4-13c-5): read from the object store, not through the registry.
    app.state.earthx_results = None
    app.include_router(build_result_factory().router, prefix=RESULT_ROUTER_PREFIX, tags=["Results"])
    app.add_api_route(
        SCENE_ORDER_ROUTE,
        scene_order,
        methods=["POST"],
        tags=["Mosaic tiles"],
        summary="The order a mosaic reads the scenes of a pass in",
    )
    app.add_api_route(
        BANDS_ROUTE,
        bands_of_items,
        methods=["POST"],
        tags=["Download"],
        summary="The bands the download dialog offers for some scenes",
    )
    app.add_api_route(
        DOWNLOAD_ROUTE,
        download_crop,
        methods=["POST"],
        tags=["Download"],
    )
    # The statistics of an order's area, as its result would carry them (NM4-19): the AOI in the body only.
    app.add_api_route(
        AREA_STATISTICS_ROUTE,
        area_statistics_endpoint(area_statistics_cache),
        methods=["POST"],
        tags=["Statistics"],
        summary="The statistics of an order's area, as its result would carry them",
    )

    @app.exception_handler(TileOutsideBounds)
    async def _tile_outside(request: Request, error: TileOutsideBounds):
        return _problem(404, "the tile does not touch this item")

    @app.exception_handler(RioTilerError)
    async def _rio_tiler_error(request: Request, error: RioTilerError):
        # Band names, expressions, colormaps: what the caller asked for cannot be
        # rendered from this asset. The message is rio-tiler's own and names no address.
        # An operator tile's refusals (`processing.tile.TileRefused`) carry their own status.
        return _problem(getattr(error, "status_code", 400), str(error))

    # Module-level, not a closure like the others above: a test builds its own
    # bare app around `EarthxTilerFactory` (`access.tiles`, no registry, no
    # gateway) and needs the same two handlers on it to check the mapping below
    # without a real `build_app()` (backend/tests/earthx/api/test_statistics_read_errors.py).
    app.add_exception_handler(RasterioIOError, _rasterio_io_error)
    app.add_exception_handler(RasterioError, _rasterio_error)

    @app.exception_handler(GeoreferenceMismatch)
    async def _georeference_mismatch(request: Request, error: GeoreferenceMismatch):
        # The file is placed differently from what the registry names (DS-04a): the source's side of the line. The
        # text names neither dataset nor address.
        LOGGER.warning("an asset is not placed the way the registry names")
        return _problem(502, "the asset is not placed the way the platform expects")

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

    @app.get("/colormaps", tags=["Colormaps"])
    def colormaps() -> JSONResponse:
        """The colormaps every tile route takes as ``colormap_name``, by group, each with a preview and its reversed name.

        The same answer for everyone and every time this version runs: a day in the browser's cache (UI-03d).
        """
        return JSONResponse(colormap_catalog(), headers={"Cache-Control": "public, max-age=86400"})

    return app


def _problem(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _may_log_detail(request: Request) -> bool:
    """Whether the traceback of a read error may go to the log.

    Not for a result's tiles: GDAL's message names the path it opened, which for a result is the signed
    URL — the `result_id`, the id of the tiler's key and a signature good for 15 minutes.
    """
    return RESULT_PATH_START not in request.url.path


async def _rasterio_io_error(request: Request, error: RasterioIOError) -> JSONResponse:
    """A genuine read failure: GDAL could not get bytes from the source.

    Applies to every route on this dependency, not only `/statistics` — the one
    place this actually fired is what led here (M3-03 review). Logged with the
    traceback, which the single handler this replaced discarded outright.
    `RasterioIOError` is `rasterio.errors`' one subclass of `OSError`; every other
    `RasterioError` goes to :func:`_rasterio_error` below instead of here.
    """
    LOGGER.warning("could not read the asset from the source", exc_info=_may_log_detail(request))
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
    LOGGER.error("the asset could not be processed", exc_info=_may_log_detail(request))
    return _problem(500, "the asset could not be processed")


app = build_app()


__all__ = [
    "BANDS_ROUTE",
    "DOWNLOAD_ROUTE",
    "MOSAIC_ROUTER_PREFIX",
    "MOSAIC_SELECTION_ROUTE",
    "OVERVIEW_ROUTER_PREFIX",
    "ROUTER_PREFIX",
    "DownloadRequest",
    "app",
    "build_app",
    "dataset_asset_path",
    "download_crop",
    "mosaic_scenes",
]
