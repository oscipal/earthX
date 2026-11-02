"""``run``: one recipe, computed block by block into a COG in the work directory (adr/0014 §7).

The worker core (KLAERUNGEN B9): no database, no queue, no object store, no internal
API, no import of `gateway`. Everything it needs comes in the recipe; everything it
produces lands in ``workdir``. `jobs` uploads it (adr/0013, adr/0015); the local
runner keeps it (adr/0016).

**How it reads (L1, F10).** Each input asset is opened once per run through
``access.open_asset_ref``, so every address has passed ``check_url`` in `readers`
(§7.3 point 1). The first pass reads 1024 px blocks with ``part()`` in the input's
own grid (the finest of its assets) — an exact window, no warp — applies the scaling of
§5.4 and the ``pixel`` kernels, and writes a tiled GeoTIFF. A ``grid`` step is a pass of its own over the
previous file (approved F3). Reading happens on the calling thread, under the GDAL
options of `readers` entered on that thread (§7.3 point 2); there is no second
reading thread.

**What it writes (approved F9, as M3-18 §11/§13).** ``result.tif``, a deflate COG
over ``bbox(AOI ∩ raster bounds)`` that keeps every value inside that box, and
``mask.tif``, ``uint8`` on the same grid, ``1`` inside the AOI polygon. The bands of ``result.tif`` are those of
``output.bands``, in that order, each with its name as band description (NM4-43c, adr/0020 §8; the unit is in the
STAC properties, see :meth:`_Run.write_pass`). The steps run on a stock of named bands that the planner narrows to
what the output needs (:func:`~earthx.processing.plan.stock_steps`).

**Statistics (M4-32).** The last pass counts every band as it writes it
(:mod:`earthx.processing.statistics`): over the whole file into GDAL's ``STATISTICS_*``
band tags of ``result.tif``, as ``gdalinfo -stats`` would, and over the pixels the mask
marks into ``statistics`` of the band in the properties, which the map's colour scale
is taken from. The mask is written first, so that pass reads it block by block.

**Measuring steps (NM4-71, adr/0014 Nachtrag NM4-71).** A step that measures (``Operator.measures``, ``normalize`` version 4
with a statistical method) needs numbers over the AOI before it runs. The planner ends the
pass before it; that pass counts the bands of the step over the mask as it writes its ``float64`` work file
(:class:`_Measure`), a local pass over that file makes the percentiles exact
(:class:`~earthx.processing.statistics.PercentileRefinement`), and the step runs in the next pass with its numbers
(``Operator.with_measured``). The sources are read once. The numbers are reported in the property ``earthx:normalize``. A
work file is deleted as soon as the pass that reads it is done; ``cleanup`` does the rest after an error or a cancel.

**Progress and cancel (approved F5).** ``progress(done, total)`` after every block.
To stop, the callback raises :class:`~earthx.processing.errors.RunCancelled`; the
core removes every file it wrote and re-raises, as it does for any other failure.

**Scope (F2).** One input and one group; several assets of an item when they share one
grid or are nested (the coarser read onto the finest with ``nearest``, the result marked
resampled; :mod:`earthx.processing.source`). A group of several items is the mosaic of one
overpass (M4-12a, :mod:`earthx.processing.mosaic`): the same passes over one raster in the
CRS most scenes share. Several groups are :class:`UnsupportedRecipe`. The output ``crop`` is
the export of M4-11a (:mod:`earthx.processing.export`): several groups and items, one after
the other.
"""

from __future__ import annotations

import ctypes
import logging
import math
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy
import rasterio
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.transform import Affine
from rasterio.warp import transform_geom
from rasterio.windows import Window
from rasterio.windows import bounds as window_bounds
from rasterio.windows import transform as window_transform
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from rio_tiler.models import ImageData

from earthx.access.resolve import open_asset_ref
from earthx.processing.errors import UnsupportedRecipe
from earthx.processing.export import Attachments, ExportResult, check_export, export
from earthx.processing.mosaic import open_mosaic
from earthx.processing.operators import REGISTRY, BandMeta, OperatorRegistry, RasterMeta
from earthx.processing.operators.normalize import MEASURED_PROPERTY
from earthx.processing.plan import PlannedStep, Segment, crop_window, live_steps, plan_steps, segments, stock_steps
from earthx.processing.recipe import AppliedScaling, CropOutput, RasterOutput, Recipe, engine_versions
from earthx.processing.source import Source, common_grid, merge_images
from earthx.processing.statistics import BandStatistics, PercentileRefinement, gdal_tags, summarize
from earthx.processing.workfile import open_workfile, workfile_path
from earthx.readers import process_gdal_options, read_access_for

__all__ = [
    "BLOCK_SIZE",
    "MASK_NAME",
    "MAX_AREA_PIXELS",
    "RESULT_NAME",
    "AreaStatistics",
    "Progress",
    "RunResult",
    "area_factor",
    "area_statistics",
    "run",
    "worker_environment",
]

LOGGER = logging.getLogger("earthx.processing")

#: Block size of every pass: the block size of the Sentinel-2 COGs (adr/0014 §3.11,
#: §7.2) and of the windowed crop (M3-18 §10.3). Part of the result for a grid
#: step (§3.4), so a change raises ``earthx.__version__``.
BLOCK_SIZE = 1024

#: The most pixels of the window ``bbox(AOI ∩ raster)`` a measure of the area counts on the job's own grid
#: (NM4-19, Otto's answer 2): 2048², about 20 by 20 km at 10 m. A larger window is counted on a coarser grid.
MAX_AREA_PIXELS = 2048 * 2048

RESULT_NAME = "result.tif"
MASK_NAME = "mask.tif"

_COG_PROFILE = "deflate"

#: Between passes every value is kept exactly, whatever the input type, and NaN marks
#: what is masked: float64 holds every integer type a source here delivers.
_INTERMEDIATE_DTYPE = "float64"

Progress = Callable[[int, int], None]

#: glibc's ``M_MMAP_THRESHOLD`` for ``mallopt``.
_M_MMAP_THRESHOLD = -3

#: Buffers from this size on get pages of their own and give them back when freed.
#: Left alone, glibc raises the threshold to the largest buffer freed so far (up to
#: 32 MB), so the block buffers of a pass end up in the heap, where GDAL's small
#: allocations pin them; the peak then depends on the order of frees (M4-10b).
MMAP_THRESHOLD_BYTES = 128 * 1024


@dataclass(frozen=True, slots=True)
class RunResult:
    """What a run leaves in the work directory, and what it says about it."""

    path: Path
    mask_path: Path
    meta: RasterMeta
    #: STAC properties of the result (§5.6); links with our own URLs come with M4-08b.
    properties: dict[str, Any]
    scaling: tuple[AppliedScaling, ...]
    blocks: int
    valid_pixels: int
    engine: dict[str, str]


@dataclass(frozen=True, slots=True)
class AreaStatistics:
    """What :func:`area_statistics` found: the statistics of the area a result would carry, without the result."""

    #: Per band of the result: ``name``, ``unit`` where known, and ``statistics`` as in the result's properties.
    bands: list[dict[str, Any]]
    #: ``1`` on the job's own grid (the very statistics of the result), else how many times coarser.
    factor: int
    pixels_read: int

    @property
    def exact(self) -> bool:
        return self.factor == 1


@contextmanager
def worker_environment() -> Iterator[None]:
    """The GDAL options of `readers` for the whole process (§7.3 point 2, adr/0013 §5.3).

    Entered once, in the main thread of the process that reads: only there does
    rasterio set them process-wide; from any other thread they would hold for that
    thread alone (§3.6), which is why this refuses to be entered elsewhere. It also
    fixes the allocator's mmap threshold for the process (:func:`_fix_mmap_threshold`).
    """
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("worker_environment() is entered in the main thread of the worker process")
    if not _fix_mmap_threshold():
        LOGGER.warning("mmap threshold left to the C library", extra={"threshold_bytes": MMAP_THRESHOLD_BYTES})
    with rasterio.Env(**process_gdal_options()):
        yield


def _fix_mmap_threshold() -> bool:
    """Fix glibc's mmap threshold at :data:`MMAP_THRESHOLD_BYTES` for the rest of the process.

    No effect on any value computed, only on where the buffers live. Without glibc
    (another C library) it does nothing and returns ``False``; the peak memory
    measured in M4-10b then no longer holds, which is why the caller logs it.
    """
    try:
        mallopt = ctypes.CDLL("libc.so.6").mallopt
    except (OSError, AttributeError):
        return False
    return mallopt(_M_MMAP_THRESHOLD, MMAP_THRESHOLD_BYTES) == 1


def _blocks(width: int, height: int) -> Iterator[Window]:
    for row in range(0, height, BLOCK_SIZE):
        for col in range(0, width, BLOCK_SIZE):
            yield Window(col, row, min(BLOCK_SIZE, width - col), min(BLOCK_SIZE, height - row))


def _block_count(meta: RasterMeta) -> int:
    return -(-meta.width // BLOCK_SIZE) * -(-meta.height // BLOCK_SIZE)


def _scenes(recipe: Recipe) -> int:
    return len(recipe.inputs[0].groups[0])


def _open_sources(recipe: Recipe, stack: ExitStack) -> list[Source]:
    if _scenes(recipe) > 1:
        return open_mosaic(recipe, stack)
    access = read_access_for(recipe.hrefs())
    sources = []
    for entry in recipe.inputs[0].resolved:
        target = open_asset_ref(
            entry.asset.to_asset(), access.policy, access.resolve, decode_cf=entry.scaling == "store-cf"
        )
        sources.append(Source.open(entry, target, stack))
    return sources


def check_scope(recipe: Recipe) -> RasterOutput | CropOutput:
    """The output of a recipe this core can run, or :class:`UnsupportedRecipe`.

    ``run`` calls it first; `api` calls it before a job is queued, so that a recipe the core
    would turn away does not wait its turn first (M4-08b K3). A crop is an export
    (:func:`~earthx.processing.export.check_export`) and may read several groups and items;
    a raster output still reads exactly one item (M4-07a F2).
    """
    if isinstance(recipe.output, CropOutput):
        return check_export(recipe)
    if len(recipe.inputs) != 1 or len(recipe.inputs[0].groups) != 1:
        raise UnsupportedRecipe("a raster run reads one group of one input: one scene, or the scenes of one overpass")
    entry = recipe.inputs[0]
    if len(entry.groups[0]) > 1 and any(asset.asset.reader == "zarr" for asset in entry.resolved):
        if len({asset.asset.crs for asset in entry.resolved}) > 1:
            raise UnsupportedRecipe("a mosaic of Zarr scenes needs all scenes in one CRS; warping Zarr is not done yet")
    return recipe.output


def _nodata_for(dtype: str, meta: RasterMeta) -> float:
    if numpy.issubdtype(numpy.dtype(dtype), numpy.floating):
        return float("nan")
    values = {band.nodata for band in meta.bands}
    if len(values) != 1 or None in values or any(math.isnan(value) for value in values):
        raise UnsupportedRecipe("an integer output needs one nodata value shared by every band")
    return float(values.pop())


def _profile(meta: RasterMeta, dtype: str, nodata: float, interleave: str | None = None) -> dict[str, Any]:
    """The profile of a work file; ``interleave`` is GDAL's ``INTERLEAVE``, ``None`` leaves it to GDAL (pixel)."""
    profile = {
        "driver": "GTiff",
        "dtype": dtype,
        "count": len(meta.bands),
        "width": meta.width,
        "height": meta.height,
        "crs": meta.crs,
        "transform": meta.transform,
        "nodata": nodata,
        "tiled": True,
        "blockxsize": BLOCK_SIZE,
        "blockysize": BLOCK_SIZE,
        "compress": "deflate",
    }
    return {**profile, "interleave": interleave} if interleave else profile


def _cast(data: numpy.ma.MaskedArray, dtype: str) -> numpy.ma.MaskedArray:
    """``data`` as ``dtype``; a float written to an integer type is rounded and clamped, not cut off.

    The rule of GDAL's ``GDALCopyWords`` (gdal_priv_templates.hpp): add 0.5 to the magnitude and drop the
    fraction, so x.5 goes away from zero, then clamp to the range of the type. Unlike GDAL, which turns NaN
    into 0, NaN stays what it marks, a masked pixel, and ends up as nodata. The sum is taken in float64,
    where every float32 is exact, so no value just below x.5 is pushed over it.
    """
    target = numpy.dtype(dtype)
    if not (numpy.issubdtype(target, numpy.integer) and numpy.issubdtype(data.dtype, numpy.floating)):
        return data.astype(target, casting="unsafe")
    values = numpy.ma.getdata(data).astype("float64")
    nan = numpy.isnan(values)
    rounded = numpy.sign(values) * numpy.floor(numpy.abs(values) + 0.5)
    limits = numpy.iinfo(target)
    clamped = numpy.clip(numpy.where(nan, 0.0, rounded), limits.min, limits.max)
    return numpy.ma.MaskedArray(clamped.astype(target), mask=numpy.ma.getmaskarray(data) | nan)


class _Run:
    """The state of one run: the files it wrote, the blocks done, the valid pixels counted, the statistics."""

    def __init__(self, workdir: Path, progress: Progress) -> None:
        self.workdir = workdir
        self.progress = progress
        self.written: list[str] = []
        self.done = 0
        self.total = 0
        self.valid_pixels = 0
        #: Per band, over the pixels the mask marks (M4-32).
        self.statistics: list[dict[str, Any]] = []
        #: The pass files named so far; a name is never used twice, whatever has been deleted since.
        self.passes = 0
        #: The parameters of each step that ran with measured numbers, by ``id`` of the recipe's step they belong to
        #: (what lineage reads).
        self.resolved: dict[int, Any] = {}
        #: The report of each step that measured, in the order they ran, for the property ``earthx:normalize``.
        self.measured: list[dict[str, Any]] = []

    def tick(self) -> None:
        self.done += 1
        self.progress(self.done, self.total)

    def new_file(self, name: str) -> str:
        workfile_path(self.workdir, name)
        self.written.append(name)
        return name

    def cleanup(self) -> None:
        for name in self.written:
            workfile_path(self.workdir, name).unlink(missing_ok=True)

    def drop(self, name: str) -> None:
        """Delete a work file that no pass reads any more."""
        workfile_path(self.workdir, name).unlink(missing_ok=True)
        if name in self.written:
            self.written.remove(name)

    def write_pass(
        self,
        name: str,
        meta: RasterMeta,
        dtype: str,
        nodata: float,
        block: Callable[[Window], numpy.ma.MaskedArray],
        count_valid: bool,
        measure: _Measure | None = None,
    ) -> None:
        """One pass into the new file ``name``; the last pass (``count_valid``) counts the statistics of the result,
        a pass before a measuring step counts the bands of that step (``measure``, NM4-71)."""
        with ExitStack() as files:
            # A pass that a later pass reads is stored band by band: reading one band of a pixel-interleaved
            # tile unpacks all its bands, which a per-band warp does once per band (NM4-43b). The last pass,
            # the source of ``result.tif``, and the mask keep GDAL's layout, so the files of a job stay as they were.
            interleave = None if count_valid else "band"
            dst = files.enter_context(
                open_workfile(self.workdir, self.new_file(name), "w", **_profile(meta, dtype, nodata, interleave))
            )
            mask = files.enter_context(open_workfile(self.workdir, MASK_NAME)) if count_valid else None
            if count_valid:
                # The name of the band, which rio-cogeo carries into the COG; the unit stays in the properties:
                # ``cog_translate`` drops it, and GDAL's COG driver, which keeps it, holds memory that grows with the
                # area (adr/0014 Nachtrag NM4-43c).
                for index, band in enumerate(meta.bands, start=1):
                    dst.set_band_description(index, band.name)
            whole = [BandStatistics(dtype) for _ in meta.bands] if count_valid else []
            area = [BandStatistics(dtype) for _ in meta.bands] if count_valid else []
            inside_pixels = 0
            for window in _blocks(meta.width, meta.height):
                data = _cast(block(window), dtype)
                if mask is not None or measure is not None:
                    values, valid, written = _written(data, nodata)
                    if measure is not None:
                        measure.count(values, written, window)
                    if mask is not None:
                        self.valid_pixels += int(valid.any(axis=0).sum())
                        inside = mask.read(1, window=window) == 1
                        inside_pixels += int(inside.sum())
                        _count(values, written, inside, whole, area)
                dst.write(numpy.ma.filled(data, nodata), window=window)
                self.tick()
            if count_valid:
                for index, statistics in enumerate(whole, start=1):
                    dst.update_tags(index, **gdal_tags(statistics.summary(meta.width * meta.height)))
                self.statistics = [statistics.summary(max(inside_pixels, 1)) for statistics in area]


class _Measure:
    """The count of the bands a measuring step needs, made in the pass that writes them (NM4-71).

    The values are those the pass writes into its ``float64`` file (after :func:`_cast`): valid, finite, inside the AOI.
    ``indices`` are the places of the bands in that file. The AOI is rasterised on the grid of that file with the rule of
    ``mask.tif`` (``all_touched``): behind a ``grid`` step that is the grid of the result and the mask is the same,
    before it the grid of the stock, which the mask file does not cover (plan NM4-71, Otto's decision of 01.11.2026).
    """

    def __init__(self, step: PlannedStep, meta: RasterMeta, aoi: dict) -> None:
        self.step = step
        self.transform = meta.transform
        self.geometry = transform_geom("EPSG:4326", meta.crs, aoi)
        wanted = step.operator.measures(step.params)
        self.indices = [index for index, band in enumerate(meta.bands) if band.name in wanted]
        self.names = [meta.bands[index].name for index in self.indices]
        self.statistics = [BandStatistics(_INTERMEDIATE_DTYPE) for _ in self.indices]
        self.inside_pixels = 0

    def inside(self, window: Window) -> numpy.ndarray:
        return _mask_block(self.geometry, window, self.transform) == 1

    def count(self, values: numpy.ndarray, valid: numpy.ndarray, window: Window) -> None:
        inside = self.inside(window)
        self.inside_pixels += int(inside.sum())
        for band, statistics in zip(self.indices, self.statistics, strict=True):
            statistics.add(values[band][valid[band] & inside])


def _written(data: numpy.ma.MaskedArray, nodata: float) -> tuple[numpy.ndarray, numpy.ndarray, numpy.ndarray]:
    """The values of a block as written, the valid ones, and those the file keeps as values.

    A valid value rounded onto an integer nodata reads back as nodata: the statistics count what the file says
    (adr/0014 §15h, "Kollision mit nodata").
    """
    valid = ~numpy.ma.getmaskarray(data)
    values = numpy.ma.getdata(data)
    return values, valid, valid if math.isnan(nodata) else valid & (values != nodata)


def _count(
    values: numpy.ndarray,
    valid: numpy.ndarray,
    inside: numpy.ndarray,
    whole: list[BandStatistics] | None,
    area: list[BandStatistics],
) -> None:
    """One block into the statistics: what lies inside the mask counts for both, the rest for the file only.

    Without ``whole`` (a measure of the area alone, :func:`area_statistics`) only the area is counted.
    """
    everywhere = bool(inside.all())
    for index, (band, valid_band, area_statistics) in enumerate(zip(values, valid, area, strict=True)):
        within = summarize(band[valid_band & inside])
        area_statistics.merge(within)
        if whole is None:
            continue
        whole[index].merge(within)
        if not everywhere:
            whole[index].merge(summarize(band[valid_band & ~inside]))


def _pixel_kernels(image: ImageData, steps: tuple[PlannedStep, ...]) -> ImageData:
    for step in steps:
        image = step.operator.run(image, step.params)
    return image


def _transform_meta(meta: RasterMeta, steps: tuple[PlannedStep, ...]) -> RasterMeta:
    for step in steps:
        meta = step.advance(meta)
    return meta


def _source_meta(sources: list[Source], finest: Source, window: Window, transform: Affine) -> RasterMeta:
    """The bands the sources give, on the grid of the finest.

    A band counts as resampled where its own source is not on that grid or warps its scenes. The flag of the
    whole raster is for a step that resamples all of it (a ``grid`` step); the result is marked where that or a band
    in it is (backlog 51, adr/0014 Nachtrag NM4-43c).
    """
    bands = []
    for source in sources:
        moved = source.warps or not finest.same_grid(source)
        for name, data_type, nodata, unit in zip(
            source.names, source.data_types, source.nodata, source.units, strict=True
        ):
            data_type = "float32" if source.scaling.applied_by_core else data_type
            bands.append(BandMeta(name=name, data_type=data_type, nodata=nodata, unit=unit, resampled=moved))
    return RasterMeta(finest.crs.to_string(), transform, int(window.width), int(window.height), tuple(bands))


def _properties(
    meta: RasterMeta,
    planned: list[PlannedStep],
    engine: dict[str, str],
    scenes: int,
    statistics: list[dict[str, Any]],
    measured: list[dict[str, Any]],
) -> dict[str, Any]:
    """The STAC properties of the result (§5.6): projection, bands with the statistics of the area, software,
    lineage, honesty flag, and where steps measured (NM4-71) the numbers they used.

    ``planned`` holds a measuring step with the numbers it ran with, so lineage names what was converted."""
    crs = CRS.from_user_input(meta.crs)
    epsg = crs.to_epsg()
    properties: dict[str, Any] = {"proj:code": f"EPSG:{epsg}"} if epsg is not None else {"proj:wkt2": crs.to_wkt()}
    if crs.is_projected:
        properties["gsd"] = meta.resolution[0]
    properties["bands"] = [
        {
            "name": band.name,
            "data_type": band.data_type,
            "nodata": "nan" if band.nodata is not None and math.isnan(band.nodata) else band.nodata,
            **({} if band.unit is None else {"unit": band.unit}),
            "statistics": band_statistics,
        }
        for band, band_statistics in zip(meta.bands, statistics, strict=True)
    ]
    properties["processing:software"] = {name: engine[name] for name in ("earthx", "gdal", "rasterio", "numexpr")}
    lineage = [f"mosaic of {scenes} scenes"] if scenes > 1 else []
    lineage += [step.operator.lineage(step.params) for step in planned]
    properties["processing:lineage"] = "; ".join(lineage) or "crop"
    added = [step.operator.properties(step.params) for step in planned]
    for key in sorted({key for entry in added for key in entry}):
        values = [entry[key] for entry in added if key in entry]
        properties[key] = values[0] if len(values) == 1 else values
    properties["earthx:resampled"] = meta.resampled
    if measured:
        properties[MEASURED_PROPERTY] = measured
    return properties


def _mask_block(geometry: dict, window: Window, transform: Affine) -> numpy.ndarray:
    """``1`` where a pixel of ``window`` touches the AOI (in the grid's CRS), else ``0``; ``uint8``."""
    return rasterize(
        [geometry],
        out_shape=(int(window.height), int(window.width)),
        transform=window_transform(window, transform),
        all_touched=True,
        default_value=1,
        fill=0,
        dtype="uint8",
    )


def _write_mask(state: _Run, meta: RasterMeta, aoi: dict) -> None:
    geometry = transform_geom("EPSG:4326", meta.crs, aoi)
    profile = {**_profile(meta, "uint8", 0), "count": 1, "nodata": None}
    with open_workfile(state.workdir, state.new_file(MASK_NAME), "w", **profile) as dst:
        for window in _blocks(meta.width, meta.height):
            dst.write(_mask_block(geometry, window, meta.transform), 1, window=window)


def run(
    recipe: Recipe,
    *,
    workdir: Path,
    progress: Progress,
    operators: OperatorRegistry = REGISTRY,
    attachments: Attachments | None = None,
) -> RunResult | ExportResult:
    """Compute ``recipe`` into ``workdir`` and describe the result; a pure function of its inputs.

    The output ``crop`` is the export (:func:`~earthx.processing.export.export`): its groups
    and items one after the other into ``export.zip``, with the ``attachments`` `api` built.
    """
    output = check_scope(recipe)
    if isinstance(output, CropOutput):
        if attachments is None:
            raise UnsupportedRecipe("an export needs the attachments api builds for it")
        return export(recipe, workdir=workdir, progress=progress, attachments=attachments)
    planned = plan_steps(recipe.steps, operators)
    state = _Run(workdir, progress)
    started = time.monotonic()
    dataset = recipe.inputs[0].dataset
    LOGGER.info(
        "processing run started",
        extra={"dataset": dataset, "operators": [s.operator.op for s in planned], "scenes": _scenes(recipe)},
    )
    try:
        with ExitStack() as stack:
            stack.enter_context(rasterio.Env(**process_gdal_options()))
            sources = _open_sources(recipe, stack)
            finest, _ = common_grid(sources)  # refuses assets that are neither one grid nor nested
            aoi = recipe.aoi.model_dump(mode="json")
            window, transform = crop_window(aoi, finest.crs.to_string(), finest.transform, finest.width, finest.height)
            metas = [_source_meta(sources, finest, window, transform)]
            passes = segments(stock_steps(metas[0], planned, output.bands))
            for segment in passes:
                metas.append(_transform_meta(metas[-1], segment.steps))
            state.total = sum(_block_count(meta) for meta in metas[1:])
            for index, segment in enumerate(passes[1:]):
                if (step := segment.measuring) is not None and step.operator.measure_percents(step.params):
                    state.total += _block_count(metas[index + 1])  # the local pass that makes the percentiles exact
            # Before the passes: the last one reads the mask for the statistics of the area.
            _write_mask(state, metas[-1], aoi)
            previous: str | None = None
            for index, segment in enumerate(passes):
                last = index == len(passes) - 1
                upcoming = None if last else passes[index + 1].measuring
                measure = None if upcoming is None else _Measure(upcoming, metas[index + 1], aoi)
                written = _run_pass(
                    state,
                    segment,
                    sources if index == 0 else None,
                    finest.transform,
                    previous,
                    window,
                    metas[index],
                    metas[index + 1],
                    output,
                    last,
                    measure,
                )
                if previous is not None:
                    state.drop(previous)  # the pass that read it is done
                previous = written
                if measure is not None:
                    passes[index + 1] = _measured(state, recipe, passes[index + 1], measure, written, metas[index + 1])
            nodata = _nodata_for(output.dtype, metas[-1])
            # The honesty flag of the result is that of the bands in it, not of every band that was read (backlog 51).
            final = replace(
                metas[-1],
                bands=tuple(replace(band, data_type=output.dtype, nodata=nodata) for band in metas[-1].bands),
                resampled=metas[-1].resampled or any(band.resampled for band in metas[-1].bands),
            )
            result = state.new_file(RESULT_NAME)
            with open_workfile(workdir, previous) as plain:
                cog_translate(
                    plain,
                    str(workfile_path(workdir, result)),
                    cog_profiles.get(_COG_PROFILE),
                    in_memory=False,
                    quiet=True,
                    forward_band_tags=True,
                )
            for name in list(state.written):
                if name not in (RESULT_NAME, MASK_NAME):
                    workfile_path(workdir, name).unlink(missing_ok=True)
                    state.written.remove(name)
    except BaseException:
        state.cleanup()
        LOGGER.warning("processing run failed", extra={"dataset": dataset, "blocks": state.done})
        raise
    engine = engine_versions()
    scaling = tuple(
        AppliedScaling(
            input=recipe.inputs[0].name,
            asset=source.entry.asset.asset,
            source=source.scaling.source,
            scales=list(source.scaling.scales),
            offsets=list(source.scaling.offsets),
        )
        for source in sources
    )
    LOGGER.info(
        "processing run finished",
        extra={
            "dataset": dataset,
            "blocks": state.done,
            "pixels": final.width * final.height,
            "valid_pixels": state.valid_pixels,
            "seconds": round(time.monotonic() - started, 3),
        },
    )
    return RunResult(
        path=workfile_path(workdir, RESULT_NAME),
        mask_path=workfile_path(workdir, MASK_NAME),
        meta=final,
        properties=_properties(
            final,
            [
                replace(step, params=state.resolved.get(id(step.step), step.params))
                for step in live_steps(planned, output.bands)
            ],
            engine,
            _scenes(recipe),
            state.statistics,
            state.measured,
        ),
        scaling=scaling,
        blocks=state.done,
        valid_pixels=state.valid_pixels,
        engine=engine,
    )


def _read_block(sources: list[Source], grid: Affine, window: Window, block: Window) -> ImageData:
    """``block`` of the window ``window`` of the grid ``grid``, every source onto it, merged into one image."""
    absolute = Window(window.col_off + block.col_off, window.row_off + block.row_off, block.width, block.height)
    return merge_images([source.read(absolute, grid) for source in sources])


def area_factor(width: int, height: int, max_pixels: int = MAX_AREA_PIXELS) -> int:
    """The smallest whole ``k`` for which a grid ``k`` times coarser than ``width`` × ``height`` holds ``max_pixels``."""
    if max_pixels < 1:
        raise ValueError("max_pixels is at least 1")
    factor = max(1, math.isqrt(width * height // max_pixels))
    while -(-width // factor) * -(-height // factor) > max_pixels:
        factor += 1
    return factor


def area_statistics(
    recipe: Recipe,
    *,
    operators: OperatorRegistry = REGISTRY,
    max_pixels: int = MAX_AREA_PIXELS,
    extra_percentiles: Sequence[int] = (),
) -> AreaStatistics:
    """The statistics of the AOI the result of ``recipe`` would carry, read and counted as :func:`run` does (NM4-19).

    Nothing is written. While the window ``bbox(AOI ∩ raster)`` holds at most ``max_pixels``, it is read on
    the job's own grid with the same blocks, kernels, cast into the output type and mask, so the answer is the
    ``statistics`` of the result's properties, field for field (``stddev`` too: the blocks come in the same
    order). A larger window is read on a grid :func:`area_factor` times coarser, laid on the job's from the
    window's corner; the reader picks an overview there, and the values are those of that read. A coarse pixel
    of a single scene whose centre lies just past the raster's edge reads the edge value rather than nothing,
    so ``count`` and ``valid_percent`` there are a little higher than the job's. Only ``pixel`` steps: a
    ``grid`` step changes the grid the job counts on, and a step that measures in the run (``Operator.measures``, NM4-71) has
    no place in the start of the chain this measures: the numbers of such a step are the result of this very count.

    The GDAL options are the caller's (:func:`run` enters those of `readers`).
    """
    output = check_scope(recipe)
    if isinstance(output, CropOutput):
        raise UnsupportedRecipe("an export has no statistics of its area; measure a raster order")
    planned = plan_steps(recipe.steps, operators)
    if any(step.operator.kind == "grid" for step in planned):
        raise UnsupportedRecipe("the area is measured for pixel steps only; a grid step changes the grid of the result")
    if any(step.operator.measures(step.params) for step in live_steps(planned, output.bands)):
        raise UnsupportedRecipe(
            "the area is measured at the start of the chain, up to the step; a step that measures its numbers in the run "
            "(normalize version 4 with a statistical method) does not belong in it"
        )
    aoi = recipe.aoi.model_dump(mode="json")
    with ExitStack() as stack:
        sources = _open_sources(recipe, stack)
        finest, _ = common_grid(sources)
        window, transform = crop_window(aoi, finest.crs.to_string(), finest.transform, finest.width, finest.height)
        source_meta = _source_meta(sources, finest, window, transform)
        steps = tuple(stock_steps(source_meta, planned, output.bands))
        meta = _transform_meta(source_meta, steps)
        nodata = _nodata_for(output.dtype, meta)
        factor = area_factor(meta.width, meta.height, max_pixels)
        width, height = -(-meta.width // factor), -(-meta.height // factor)
        coarse = meta.transform @ Affine.scale(factor)
        geometry = transform_geom("EPSG:4326", meta.crs, aoi)
        area = [BandStatistics(output.dtype) for _ in meta.bands]
        inside_pixels = 0
        for block in _blocks(width, height):
            if factor == 1:
                image = _read_block(sources, finest.transform, window, block)
            else:
                image = merge_images([source.read(block, coarse) for source in sources])
            values, _, written = _written(_cast(_pixel_kernels(image, steps).array, output.dtype), nodata)
            inside = _mask_block(geometry, block, coarse) == 1
            inside_pixels += int(inside.sum())
            _count(values, written, inside, None, area)
    bands = [
        {
            "name": band.name,
            **({} if band.unit is None else {"unit": band.unit}),
            "statistics": statistics.summary(max(inside_pixels, 1), extra_percentiles),
        }
        for band, statistics in zip(meta.bands, area, strict=True)
    ]
    return AreaStatistics(bands=bands, factor=factor, pixels_read=width * height)


def _run_pass(
    state: _Run,
    segment: Segment,
    sources: list[Source] | None,
    grid: Affine,
    previous: str | None,
    window: Window,
    source_meta: RasterMeta,
    target_meta: RasterMeta,
    output: RasterOutput,
    last: bool,
    measure: _Measure | None = None,
) -> str:
    """One pass into a new file in the work directory; returns its name.

    ``measure`` counts the bands of the step that follows while the pass writes them (NM4-71)."""
    state.passes += 1
    name = f"pass-{state.passes}.tif"
    dtype = output.dtype if last else _INTERMEDIATE_DTYPE
    nodata = _nodata_for(dtype, target_meta)
    if segment.kind == "grid":
        step = segment.steps[0]
        with open_workfile(state.workdir, previous) as src:
            state.write_pass(
                name,
                target_meta,
                dtype,
                nodata,
                lambda w: step.operator.run(src, target_meta, w, step.params),
                last,
                measure,
            )
        return name
    if sources is not None:

        def block(w: Window) -> numpy.ma.MaskedArray:
            return _pixel_kernels(_read_block(sources, grid, window, w), segment.steps).array

        state.write_pass(name, target_meta, dtype, nodata, block, last, measure)
        return name
    with open_workfile(state.workdir, previous) as src:

        def local_block(w: Window) -> numpy.ma.MaskedArray:
            data = src.read(window=w, masked=True)
            bounds = window_bounds(w, src.transform)
            image = ImageData(data, bounds=bounds, crs=src.crs, band_names=[band.name for band in source_meta.bands])
            return _pixel_kernels(image, segment.steps).array

        state.write_pass(name, target_meta, dtype, nodata, local_block, last, measure)
    return name


def _refine(
    state: _Run, name: str, meta: RasterMeta, measure: _Measure, refinements: list[PercentileRefinement]
) -> None:
    """A local pass over the work file ``name``: the second look that makes the percentiles of the measured bands exact.

    It reads only the bands of the step, one block at a time, and counts the values the pass before counted: valid (not NaN,
    which marks a masked pixel in the file), finite, inside the AOI.
    """
    with open_workfile(state.workdir, name) as src:
        for window in _blocks(meta.width, meta.height):
            inside = measure.inside(window)
            for index, refinement in zip(measure.indices, refinements, strict=True):
                if refinement.needed:
                    values = src.read(index + 1, window=window)
                    refinement.add(values[inside & numpy.isfinite(values)])
            state.tick()


def _measured(state: _Run, recipe: Recipe, segment: Segment, measure: _Measure, name: str, meta: RasterMeta) -> Segment:
    """``segment`` with its first step given the numbers measured in the pass that wrote ``name`` (NM4-71).

    The count of that pass gives the minimum, maximum, count, mean and standard deviation; the percentiles are made exact
    from the work file. The numbers go to the step (``Operator.with_measured``) and to the report of the result. A band
    without a valid value fails the run before the second look (:class:`RecipeInvalid`, from the step).
    """
    step = measure.step
    pixels = max(measure.inside_pixels, 1)
    numbers = {
        band: statistics.summary(pixels) for band, statistics in zip(measure.names, measure.statistics, strict=True)
    }
    percents = step.operator.measure_percents(step.params)
    if percents and all(summary["count"] for summary in numbers.values()):
        refinements = [statistics.refine_targets(percents) for statistics in measure.statistics]
        if any(refinement.needed for refinement in refinements):
            _refine(state, name, meta, measure, refinements)
        else:  # every percentile lay in a bin of one value: the second look is not needed, its blocks count as done
            for _ in _blocks(meta.width, meta.height):
                state.tick()
        for band, refinement in zip(measure.names, refinements, strict=True):
            numbers[band].update({f"percentile_{percent}": value for percent, value in refinement.values().items()})
    assert step.operator.with_measured is not None and step.operator.measured_report is not None
    resolved = step.operator.with_measured(step.params, numbers)
    state.resolved[id(step.step)] = resolved
    state.measured.append(
        {
            "step": next(index for index, recipe_step in enumerate(recipe.steps) if recipe_step is step.step),
            **step.operator.measured_report(resolved),
            "exact": True,
        }
    )
    return Segment(segment.kind, (replace(step, params=resolved), *segment.steps[1:]))
