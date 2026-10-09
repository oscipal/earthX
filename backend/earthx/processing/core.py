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
``mask.tif``, ``uint8`` on the same grid, ``1`` inside the AOI polygon.

**Progress and cancel (approved F5).** ``progress(done, total)`` after every block.
To stop, the callback raises :class:`~earthx.processing.errors.RunCancelled`; the
core removes every file it wrote and re-raises, as it does for any other failure.

**Scope (F2).** One input, one group, one item; several assets of that item when
they share one grid or are nested (the coarser read onto the finest with ``nearest``,
the result marked resampled; :mod:`earthx.processing.source`). More is
:class:`UnsupportedRecipe` until M4-11 and M4-12.
"""

from __future__ import annotations

import ctypes
import logging
import math
import threading
import time
from collections.abc import Callable, Iterator
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
from earthx.processing.operators import REGISTRY, BandMeta, OperatorRegistry, RasterMeta
from earthx.processing.plan import PlannedStep, Segment, crop_window, plan_steps, segments
from earthx.processing.recipe import AppliedScaling, RasterOutput, Recipe, engine_versions
from earthx.processing.source import Source, common_grid, merge_images
from earthx.processing.workfile import open_workfile, workfile_path
from earthx.readers import process_gdal_options, read_access_for

__all__ = ["BLOCK_SIZE", "MASK_NAME", "RESULT_NAME", "Progress", "RunResult", "run", "worker_environment"]

LOGGER = logging.getLogger("earthx.processing")

#: Block size of every pass: the block size of the Sentinel-2 COGs (adr/0014 §3.11,
#: §7.2) and of the windowed crop (M3-18 §10.3). Part of the result for a grid
#: step (§3.4), so a change raises ``earthx.__version__``.
BLOCK_SIZE = 1024

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


def _open_sources(recipe: Recipe, stack: ExitStack) -> list[Source]:
    access = read_access_for(recipe.hrefs())
    sources = []
    for entry in recipe.inputs[0].resolved:
        target = open_asset_ref(
            entry.asset.to_asset(), access.policy, access.resolve, decode_cf=entry.scaling == "store-cf"
        )
        sources.append(Source.open(entry, target, stack))
    return sources


def check_scope(recipe: Recipe) -> RasterOutput:
    """The raster output of a recipe this core can run, or :class:`UnsupportedRecipe`.

    ``run`` calls it first; `api` calls it before a job is queued, so that a recipe the core
    would turn away does not wait its turn first (M4-08b K3).
    """
    if not isinstance(recipe.output, RasterOutput):
        raise UnsupportedRecipe("the core computes a raster output; a crop is described, not run")
    if len(recipe.inputs) != 1 or len(recipe.inputs[0].groups) != 1 or len(recipe.inputs[0].groups[0]) != 1:
        raise UnsupportedRecipe("a run reads one item of one input; mosaics and several groups come with M4-11/M4-12")
    return recipe.output


def _nodata_for(dtype: str, meta: RasterMeta) -> float:
    if numpy.issubdtype(numpy.dtype(dtype), numpy.floating):
        return float("nan")
    values = {band.nodata for band in meta.bands}
    if len(values) != 1 or None in values or any(math.isnan(value) for value in values):
        raise UnsupportedRecipe("an integer output needs one nodata value shared by every band")
    return float(values.pop())


def _profile(meta: RasterMeta, dtype: str, nodata: float) -> dict[str, Any]:
    return {
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


class _Run:
    """The state of one run: the files it wrote, the blocks done, the valid pixels counted."""

    def __init__(self, workdir: Path, progress: Progress) -> None:
        self.workdir = workdir
        self.progress = progress
        self.written: list[str] = []
        self.done = 0
        self.total = 0
        self.valid_pixels = 0

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

    def write_pass(
        self,
        name: str,
        meta: RasterMeta,
        dtype: str,
        nodata: float,
        block: Callable[[Window], numpy.ma.MaskedArray],
        count_valid: bool,
    ) -> None:
        with open_workfile(self.workdir, self.new_file(name), "w", **_profile(meta, dtype, nodata)) as dst:
            for window in _blocks(meta.width, meta.height):
                data = block(window)
                if count_valid:
                    self.valid_pixels += int((~numpy.ma.getmaskarray(data)).any(axis=0).sum())
                dst.write(numpy.ma.filled(data.astype(dtype, casting="unsafe"), nodata), window=window)
                self.tick()


def _pixel_kernels(image: ImageData, steps: tuple[PlannedStep, ...]) -> ImageData:
    for step in steps:
        image = step.operator.run(image, step.params)
    return image


def _transform_meta(meta: RasterMeta, steps: tuple[PlannedStep, ...]) -> RasterMeta:
    for step in steps:
        meta = step.operator.transform(meta, step.params)
    return meta


def _source_meta(
    sources: list[Source], finest: Source, resampled: bool, window: Window, transform: Affine
) -> RasterMeta:
    bands = []
    for source in sources:
        for name, data_type, nodata in zip(source.names, source.data_types, source.nodata, strict=True):
            data_type = "float32" if source.scaling.applied_by_core else data_type
            bands.append(BandMeta(name=name, data_type=data_type, nodata=nodata))
    return RasterMeta(
        finest.crs.to_string(), transform, int(window.width), int(window.height), tuple(bands), resampled
    )


def _properties(meta: RasterMeta, planned: list[PlannedStep], engine: dict[str, str]) -> dict[str, Any]:
    """The STAC properties of the result (§5.6): projection, bands, software, lineage, honesty flag."""
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
        }
        for band in meta.bands
    ]
    properties["processing:software"] = {name: engine[name] for name in ("earthx", "gdal", "rasterio", "numexpr")}
    properties["processing:lineage"] = "; ".join(step.operator.lineage(step.params) for step in planned) or "crop"
    added = [step.operator.properties(step.params) for step in planned]
    for key in sorted({key for entry in added for key in entry}):
        values = [entry[key] for entry in added if key in entry]
        properties[key] = values[0] if len(values) == 1 else values
    properties["earthx:resampled"] = meta.resampled
    return properties


def _write_mask(state: _Run, meta: RasterMeta, aoi: dict) -> None:
    geometry = transform_geom("EPSG:4326", meta.crs, aoi)
    profile = {**_profile(meta, "uint8", 0), "count": 1, "nodata": None}
    with open_workfile(state.workdir, state.new_file(MASK_NAME), "w", **profile) as dst:
        for window in _blocks(meta.width, meta.height):
            inside = rasterize(
                [geometry],
                out_shape=(int(window.height), int(window.width)),
                transform=window_transform(window, meta.transform),
                all_touched=True,
                default_value=1,
                fill=0,
                dtype="uint8",
            )
            dst.write(inside, 1, window=window)


def run(recipe: Recipe, *, workdir: Path, progress: Progress, operators: OperatorRegistry = REGISTRY) -> RunResult:
    """Compute ``recipe`` into ``workdir`` and describe the result; a pure function of its inputs."""
    output = check_scope(recipe)
    planned = plan_steps(recipe.steps, operators)
    passes = segments(planned)
    state = _Run(workdir, progress)
    started = time.monotonic()
    dataset = recipe.inputs[0].dataset
    LOGGER.info("processing run started", extra={"dataset": dataset, "operators": [s.operator.op for s in planned]})
    try:
        with ExitStack() as stack:
            stack.enter_context(rasterio.Env(**process_gdal_options()))
            sources = _open_sources(recipe, stack)
            finest, resampled = common_grid(sources)
            window, transform = crop_window(
                recipe.aoi.model_dump(mode="json"), finest.crs.to_string(), finest.transform, finest.width, finest.height
            )
            metas = [_source_meta(sources, finest, resampled, window, transform)]
            for segment in passes:
                metas.append(_transform_meta(metas[-1], segment.steps))
            state.total = sum(_block_count(meta) for meta in metas[1:])
            previous: str | None = None
            for index, segment in enumerate(passes):
                last = index == len(passes) - 1
                previous = _run_pass(
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
                )
            nodata = _nodata_for(output.dtype, metas[-1])
            final = replace(
                metas[-1],
                bands=tuple(replace(band, data_type=output.dtype, nodata=nodata) for band in metas[-1].bands),
            )
            _write_mask(state, final, recipe.aoi.model_dump(mode="json"))
            result = state.new_file(RESULT_NAME)
            with open_workfile(workdir, previous) as plain:
                cog_translate(
                    plain,
                    str(workfile_path(workdir, result)),
                    cog_profiles.get(_COG_PROFILE),
                    in_memory=False,
                    quiet=True,
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
        properties=_properties(final, planned, engine),
        scaling=scaling,
        blocks=state.done,
        valid_pixels=state.valid_pixels,
        engine=engine,
    )


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
) -> str:
    """One pass into a new file in the work directory; returns its name."""
    name = f"pass-{len(state.written)}.tif"
    dtype = output.dtype if last else _INTERMEDIATE_DTYPE
    nodata = _nodata_for(dtype, target_meta)
    if segment.kind == "grid":
        step = segment.steps[0]
        with open_workfile(state.workdir, previous) as src:
            state.write_pass(
                name, target_meta, dtype, nodata, lambda w: step.operator.run(src, target_meta, w, step.params), last
            )
        return name
    if sources is not None:

        def block(w: Window) -> numpy.ma.MaskedArray:
            absolute = Window(window.col_off + w.col_off, window.row_off + w.row_off, w.width, w.height)
            image = merge_images([source.read(absolute, grid) for source in sources])
            return _pixel_kernels(image, segment.steps).array

        state.write_pass(name, target_meta, dtype, nodata, block, last)
        return name
    with open_workfile(state.workdir, previous) as src:

        def local_block(w: Window) -> numpy.ma.MaskedArray:
            data = src.read(window=w, masked=True)
            bounds = window_bounds(w, src.transform)
            image = ImageData(data, bounds=bounds, crs=src.crs, band_names=[band.name for band in source_meta.bands])
            return _pixel_kernels(image, segment.steps).array

        state.write_pass(name, target_meta, dtype, nodata, local_block, last)
    return name
