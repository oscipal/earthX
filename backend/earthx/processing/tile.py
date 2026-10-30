"""The tile of an operator or of a chain of them (T1): the same inputs, scaling and kernels as the job (adr/0014 §6.2).

`api` builds an :class:`OperatorInput` from the path of a tile URL — the assets named
in it, already cleared through the gateway policy, with the bands and the scaling
source the item describes — and TiTiler's factory opens :class:`OperatorTileReader` on
it. The reader reads each asset's tile through :class:`~earthx.processing.source.Source`
(physical values, named bands, the grid rule of the core) and merges them into one
image; the kernels of the chain then run as TiTiler's ``process_dependency``, one after the other, the very
functions a job calls on a block.

The same reader measures the whole extent for the colour scale of a preview (:meth:`OperatorTileReader.preview`,
M4-19c): each source over the same bounds onto the same grid, at most :data:`MAX_PREVIEW_SIDE` pixels on the long side.

The mosaic tile with steps (NM4-04) reads as the mosaic job reads: per band and pixel the first valid
element of the scenes, in physical values, and only then the kernels (:class:`MosaicOperatorTileReader`).

Steps of version 2 work on a stock of named bands, and a picture shows one of them (NM4-43d, adr/0020 §10): the URL
names the band (:func:`plan_band`), and the tile reads and runs what that band needs, as the planner of a job does.

The tile is a *preview* below the native level: rio-tiler reads an overview there, and
only on the native level is the tile bit-identical with the job (§6.3, F9).
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Protocol

import morecantile
import rasterio
from pydantic import BaseModel
from rasterio.transform import Affine
from rasterio.warp import transform_bounds
from rio_tiler.constants import WGS84_CRS
from rio_tiler.errors import EmptyMosaicError, RioTilerError, TileOutsideBounds
from rio_tiler.models import ImageData
from rio_tiler.mosaic import mosaic_reader
from rio_tiler.mosaic.methods.defaults import FirstMethod

from earthx.access.mosaic_tiles import MOSAIC_THREADS
from earthx.processing.errors import GridMismatch, RecipeInvalid, ScalingMismatch, UnsupportedRecipe
from earthx.processing.mosaic import check_alike
from earthx.processing.operators.base import BandMeta, Operator, RasterMeta
from earthx.processing.plan import PlannedStep, needed_source_bands, stock_steps
from earthx.processing.recipe import ResolvedInput, Step
from earthx.processing.source import Source, common_grid, expected_band_names, merge_images, units_of
from earthx.readers.cog import AssetPath
from earthx.readers.zarr_reader import ZarrAsset

__all__ = [
    "MAX_PREVIEW_SIDE",
    "BandPlan",
    "MosaicOperatorTileReader",
    "MosaicTileInputs",
    "OperatorTileReader",
    "TileInputs",
    "TileOptionRefused",
    "TileRefused",
    "judge_described_bands",
    "judge_steps",
    "plan_band",
]

#: The longest side, in pixels, of the read a measurement of an operator takes (the size of the statistics of one asset).
MAX_PREVIEW_SIDE = 1024


class TileRefused(RioTilerError):
    """A refusal of an operator tile, with the HTTP status `api` answers it with (rio-tiler's handler reads it)."""

    status_code = 400


class TileOptionRefused(TileRefused):
    """A tile option that has no meaning for an operator's tile (`400`)."""


class TileInputs(Protocol):
    """What `api` hands the reader: the assets of the tile and the steps (operator, validated parameters).

    ``band`` is the band the steps leave for the picture (:func:`plan_band`); ``None`` for steps of version 1, which
    leave the bands they leave.
    """

    inputs: tuple[tuple[ResolvedInput, AssetPath | ZarrAsset], ...]
    steps: tuple[tuple[Operator, BaseModel], ...]
    band: str | None


class MosaicTileInputs(Protocol):
    """What `api` hands the mosaic reader: per scene, in the order of the mosaic, its assets; the steps; the extent.

    ``bounds`` is west, south, east, north in EPSG:4326 over every scene of the URL, not only those of the tile.
    ``band`` as for :class:`TileInputs`.
    """

    scenes: tuple[tuple[tuple[ResolvedInput, AssetPath | ZarrAsset], ...], ...]
    steps: tuple[tuple[Operator, BaseModel], ...]
    bounds: tuple[float, float, float, float]
    band: str | None


def _as_refusal(error: BaseException) -> BaseException:
    """The error as a :class:`TileRefused` with its status, or itself where it is none of the four below."""
    for kind, status in ((RecipeInvalid, 422), (GridMismatch, 422), (UnsupportedRecipe, 422), (ScalingMismatch, 502)):
        if isinstance(error, kind):
            refused = TileRefused(str(error))
            refused.status_code = status
            return refused
    return error


def judge_steps(meta: RasterMeta, steps: Sequence[tuple[Operator, BaseModel]]) -> RasterMeta:
    """The bands the steps leave, each judged on the bands the one before leaves, as in a job.

    In a chain the refusal says which step it is, counted from 0 like the order's.
    """
    for index, (operator, params) in enumerate(steps):
        try:
            meta = operator.transform(meta, params)
        except RecipeInvalid as error:
            if len(steps) == 1:
                raise
            raise RecipeInvalid(f"step {index}: {error}") from error
    return meta


def judge_described_bands(entries: Sequence[ResolvedInput], steps: Sequence[tuple[Operator, BaseModel]]) -> None:
    """:func:`judge_steps` on the bands the item describes, before any file is opened (NM4-04 KE1).

    Where the item does not say how many bands an asset has, only the file knows, and the reader judges
    again before the first pixel; nothing is judged here then.
    """
    bands = []
    for entry in entries:
        names = expected_band_names(entry)
        if names is None:
            return
        units = units_of(entry, len(names))
        bands += [BandMeta(name, "float32", None, unit) for name, unit in zip(names, units, strict=True)]
    judge_steps(RasterMeta(entries[0].asset.crs or "EPSG:4326", Affine.identity(), 1, 1, tuple(bands)), steps)


@dataclass(frozen=True, slots=True)
class BandPlan:
    """What a tile of steps of version 2 reads and runs to show one band (adr/0020 §10)."""

    #: The band the picture shows: the one the URL names, else the last that a ``band_math`` step added, else the first.
    band: str
    #: The assets the band needs, in the order of the URL; the tile opens no other.
    assets: tuple[str, ...]
    #: The steps to run on what is read: the planner's (dead steps left out, ``normalize`` narrowed, the bands nobody needs
    #: dropped), ending in the selection of ``band``, so that the picture has this one band.
    steps: tuple[tuple[Operator, BaseModel], ...]


def plan_band(
    entries: Sequence[ResolvedInput], steps: Sequence[tuple[Operator, BaseModel]], band: str | None
) -> BandPlan | None:
    """The plan of a tile that shows ``band`` of what ``steps`` leave of ``entries``, judged before any file is opened.

    The same planner as a job's (:func:`~earthx.processing.plan.stock_steps`) with ``[band]`` as the output, so the
    values of the band are those of a job that asks for it alone (adr/0020 §4). Where the item does not say how many
    bands an asset has, the asset counts as one band named like it, as the estimate of a job counts it; the reader
    judges again on the file.

    ``None`` for steps one of which is of version 1 (it replaces or removes bands): nothing is dropped and no band
    is chosen, the picture is what the steps leave. ``TileOptionRefused`` (`400`) if a ``band`` is named then, and
    :class:`~earthx.processing.errors.RecipeInvalid` (`422`, with the name) for a band the steps do not leave.
    """
    if any(not operator.stock for operator, _ in steps):
        if band is not None:
            raise TileOptionRefused("band is for steps of version 2; a step of version 1 replaces or removes bands")
        return None
    names_of = [expected_band_names(entry) or [entry.asset.asset] for entry in entries]
    meta = RasterMeta(
        entries[0].asset.crs or "EPSG:4326",
        Affine.identity(),
        1,
        1,
        tuple(
            BandMeta(name, "float32", None, unit)
            for entry, names in zip(entries, names_of, strict=True)
            for name, unit in zip(names, units_of(entry, len(names)), strict=True)
        ),
    )
    planned = [
        PlannedStep(
            Step(op=operator.op, op_version=operator.op_version, params=params.model_dump(mode="json")), operator, params
        )
        for operator, params in steps
    ]
    held = [band_meta.name for band_meta in meta.bands]
    added = [use.adds for step in planned if (use := step.operator.bands_used(step.params)).adds is not None]
    held += added
    shown = band if band is not None else (added[-1] if added else held[0])
    if shown not in held:
        raise RecipeInvalid(f"band {shown!r} is not among the bands the steps leave: {', '.join(held)}")
    run = stock_steps(meta, planned, [shown])
    needed = needed_source_bands(planned, [shown])
    return BandPlan(
        band=shown,
        assets=tuple(entry.asset.asset for entry, names in zip(entries, names_of, strict=True) if needed & set(names)),
        steps=tuple((step.operator, step.params) for step in run),
    )


def _tile_options(
    tilesize: int | None,
    resampling_method: str | None,
    buffer: float | None,
    padding: int | None,
    refused: dict[str, Any],
) -> dict[str, Any]:
    """The reader options of an operator tile; options that would change the values are refused."""
    if refused:
        raise TileOptionRefused(
            f"{', '.join(sorted(refused))} cannot be used with op: the tile is computed in physical values"
        )
    if resampling_method not in (None, "nearest"):
        raise TileOptionRefused("an operator tile is read with nearest resampling")
    options: dict[str, Any] = {"resampling_method": "nearest"}
    for name, value in (("tilesize", tilesize), ("buffer", buffer), ("padding", padding)):
        if value is not None:
            options[name] = value
    return options


def _meta_of(sources: list[Source], steps: Sequence[tuple[Operator, BaseModel]]) -> tuple[Source, RasterMeta]:
    """The grid the sources are read onto, and the bands the steps leave of them; refusals before the first pixel."""
    finest, resampled = common_grid(sources)
    bands = tuple(
        BandMeta(name, "float32", None, unit)
        for source in sources
        for name, unit in zip(source.names, source.units, strict=True)
    )
    meta = RasterMeta(finest.crs.to_string(), finest.transform, finest.width, finest.height, bands, resampled)
    return finest, judge_steps(meta, steps)


class OperatorTileReader:
    """Opens the assets of an :class:`OperatorInput` and reads the merged tile in physical values."""

    def __init__(self, source: TileInputs, *, tms: Any = None, **options: Any) -> None:
        if options:
            raise TileOptionRefused("this reader takes no reader options")
        self._input = source
        self._tms = tms
        self._stack = ExitStack()
        self._sources: list[Source] = []
        self._grid: Source | None = None
        self._units: tuple[str | None, ...] = ()

    def __enter__(self) -> OperatorTileReader:
        try:
            self._sources = [Source.open(entry, target, self._stack) for entry, target in self._input.inputs]
            # The names and the syntax are judged before the first pixel, as in a job.
            self._grid, meta = _meta_of(self._sources, self._input.steps)
            self._units = tuple(band.unit for band in meta.bands)
        except BaseException as error:
            self._stack.close()
            raise _as_refusal(error) from error
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self._stack.close()

    @property
    def _first(self) -> Source:
        return self._sources[0]

    @property
    def band(self) -> str | None:
        """The band the picture shows (:func:`plan_band`); ``None`` for steps of version 1."""
        return self._input.band

    @property
    def minzoom(self) -> int:
        return self._first.reader.minzoom

    @property
    def maxzoom(self) -> int:
        return self._first.reader.maxzoom

    def get_geographic_bounds(self, crs: Any) -> tuple[float, float, float, float]:
        return self._first.reader.get_geographic_bounds(crs)

    @property
    def units(self) -> tuple[str | None, ...]:
        """The unit of each band the steps leave, in order; ``None`` where it is not known."""
        return self._units

    @property
    def unit(self) -> str | None:
        """The one unit all bands share, or ``None`` where it is unknown or the bands differ."""
        return self._units[0] if self._units and len(set(self._units)) == 1 else None

    def info(self) -> SimpleNamespace:
        return SimpleNamespace(band_descriptions=None, dtype="float32", minmax=None)

    def tile(
        self,
        x: int,
        y: int,
        z: int,
        *,
        tilesize: int | None = None,
        resampling_method: str | None = None,
        buffer: float | None = None,
        padding: int | None = None,
        **refused: Any,
    ) -> ImageData:
        """The merged tile, in physical values; options that would change the values are refused."""
        options = _tile_options(tilesize, resampling_method, buffer, padding, refused)
        return merge_images([source.read_tile(x, y, z, **options) for source in self._sources])

    def preview(
        self,
        *,
        max_size: int | None = None,
        resampling_method: str | None = None,
        **refused: Any,
    ) -> ImageData:
        """The whole extent in physical values, at most ``max_size`` pixels on its long side (default and limit 1024).

        Every source is read over the same bounds onto the same size, so the bands of two assets of
        different resolution stay one grid. The steps of the chain are not applied: that is the caller's.
        """
        if refused:
            raise TileOptionRefused(
                f"{', '.join(sorted(refused))} cannot be used with op: the measure is computed in physical values"
            )
        if resampling_method not in (None, "nearest"):
            raise TileOptionRefused("an operator measure is read with nearest resampling")
        if max_size is not None and not 1 <= max_size <= MAX_PREVIEW_SIDE:
            raise TileOptionRefused(f"max_size is at most {MAX_PREVIEW_SIDE}")
        assert self._grid is not None  # set by __enter__
        grid = self._grid
        scale = min(1.0, (max_size or MAX_PREVIEW_SIDE) / max(grid.width, grid.height))
        left, top = grid.transform @ (0, 0)
        right, bottom = grid.transform @ (grid.width, grid.height)
        width, height = max(1, round(grid.width * scale)), max(1, round(grid.height * scale))
        return merge_images([source.read_preview((left, bottom, right, top), width, height) for source in self._sources])


class MosaicOperatorTileReader:
    """The scenes of one overpass read into one tile as the mosaic job reads them, for the steps that follow (NM4-04).

    The job mosaics each asset on its own — per band and pixel the first valid element, in physical values — and
    only then merges the assets and runs the kernels (`processing.mosaic`, `processing.core`). rio-tiler's
    ``FirstMethod`` chooses per band and pixel too, so one ``mosaic_reader`` over scenes that each carry all their
    assets gives the same image. Read in portions of :data:`MOSAIC_THREADS`, done once every band of every pixel
    is filled, like the mosaic tile without steps.

    Only the first scene is opened on entering: it names the bands the steps are judged on. Every other scene is
    opened in the thread that reads it, under the GDAL configuration of the route, and has to agree with the
    first as the job's scenes do (:func:`~earthx.processing.mosaic.check_alike`).
    """

    def __init__(
        self,
        source: MosaicTileInputs,
        *,
        tms: morecantile.TileMatrixSet | None = None,
        gdal_config: dict[str, Any] | None = None,
        **options: Any,
    ) -> None:
        if options:
            raise TileOptionRefused("this reader takes no reader options")
        if not source.scenes:
            raise ValueError("a mosaic has at least one scene")
        self._input = source
        self.tms = tms or morecantile.tms.get("WebMercatorQuad")
        self.gdal_config = dict(gdal_config or {})
        self._stack = ExitStack()
        self._first: list[Source] = []
        self._units: tuple[str | None, ...] = ()

    def __enter__(self) -> MosaicOperatorTileReader:
        try:
            self._first = [Source.open(entry, target, self._stack) for entry, target in self._input.scenes[0]]
            _, meta = _meta_of(self._first, self._input.steps)
            self._units = tuple(band.unit for band in meta.bands)
        except BaseException as error:
            self._stack.close()
            raise _as_refusal(error) from error
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self._stack.close()

    @property
    def minzoom(self) -> int:
        return self.tms.minzoom

    @property
    def maxzoom(self) -> int:
        return self.tms.maxzoom

    @property
    def order(self) -> tuple[str, ...]:
        """The item ids in the order the tile reads them."""
        return tuple(assets[0][0].asset.item_id for assets in self._input.scenes)

    @property
    def band(self) -> str | None:
        """The band the picture shows (:func:`plan_band`); ``None`` for steps of version 1."""
        return self._input.band

    @property
    def units(self) -> tuple[str | None, ...]:
        return self._units

    @property
    def unit(self) -> str | None:
        return self._units[0] if self._units and len(set(self._units)) == 1 else None

    def get_geographic_bounds(self, crs: Any) -> tuple[float, float, float, float]:
        if crs == WGS84_CRS:
            return self._input.bounds
        return transform_bounds(WGS84_CRS, crs, *self._input.bounds, densify_pts=21)

    def info(self) -> SimpleNamespace:
        return SimpleNamespace(band_descriptions=None, dtype="float32", minmax=None)

    def _scene(self, index: int, x: int, y: int, z: int, options: dict[str, Any]) -> ImageData:
        """One scene's assets as one image in physical values; the first scene from what ``__enter__`` opened."""
        with rasterio.Env(**self.gdal_config):
            if index == 0:
                return merge_images([source.read_tile(x, y, z, **options) for source in self._first])
            with ExitStack() as stack:
                sources = [Source.open(entry, target, stack) for entry, target in self._input.scenes[index]]
                for first, source in zip(self._first, sources, strict=True):
                    check_alike(first.entry.asset.asset, [first, source])
                return merge_images([source.read_tile(x, y, z, **options) for source in sources])

    def tile(
        self,
        x: int,
        y: int,
        z: int,
        *,
        tilesize: int | None = None,
        resampling_method: str | None = None,
        buffer: float | None = None,
        padding: int | None = None,
        **refused: Any,
    ) -> ImageData:
        """The mosaic of the scenes in physical values, before the steps. Only ``TileOutsideBounds`` skips a scene."""
        options = _tile_options(tilesize, resampling_method, buffer, padding, refused)
        try:
            image, _ = mosaic_reader(
                list(range(len(self._input.scenes))),
                lambda index, *tile, **_: self._scene(index, *tile, options),
                x,
                y,
                z,
                pixel_selection=FirstMethod(),
                threads=MOSAIC_THREADS,
                chunk_size=MOSAIC_THREADS,
                allowed_exceptions=(TileOutsideBounds,),
            )
        except EmptyMosaicError:
            raise TileOutsideBounds("the tile does not touch these scenes") from None
        except (RecipeInvalid, GridMismatch, UnsupportedRecipe, ScalingMismatch) as error:
            raise _as_refusal(error) from error
        return image
