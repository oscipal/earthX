"""Planning a recipe before anything is read: tiers, segments, output grid, cost (adr/0014 §5.5, §6.1).

* :func:`split_tiers` — the longest leading run of ``pixel`` steps that all run in
  ``T1`` becomes tile parameters; everything after it is a job (§6.1).
* :func:`segments` — the steps of a job as the core runs them: a run of ``pixel``
  steps is computed block by block in one pass, a ``grid`` step is a pass of its
  own over a file in the work directory (approved F3). A step that measures
  (``Operator.measures``, NM4-71) opens a pass: the pass before it counts its bands.
* :func:`stock_steps` — the steps of a job on a stock of named bands (recipe version 2, adr/0020 §4): the
  planner works from the end, drops what no later step and not ``output.bands`` needs, and puts the result
  in the order of the output.
* :func:`crop_window` — the output grid of the first pass: ``bbox(AOI ∩ raster
  bounds)`` in the input's own grid, snapped outward to its pixels (approved F9;
  the raster bounds stand in for the footprints, which the core does not see).
* :func:`estimate` — the cost shown before a run, from AOI, ``gsd`` and data
  type, with the rules the crop uses (``access.crop_rules``, F8).
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

import numpy
from rasterio.crs import CRS
from rasterio.errors import CRSError, RasterioError
from rasterio.transform import Affine
from rasterio.warp import transform_geom
from rasterio.windows import Window
from shapely.geometry import box
from shapely.geometry import shape as shapely_shape

from earthx.access.crop_rules import (
    BLOCK_SIZE,
    FALLBACK_BYTES_PER_PIXEL,
    MAX_JOB_BYTES,
    MAX_OUTPUT_SIDE_PX,
    AoiOutsideItems,
    PlannedOutput,
    bytes_per_pixel,
    compute_crop_region,
    estimate_output_dims,
    target_crs,
)
from earthx.processing.errors import AoiOutsideInputs, ExportTooLarge, JobTooLarge, RecipeInvalid, UnsupportedRecipe
from earthx.processing.operators import BandMeta, Operator, OperatorRegistry, RasterMeta, Tier
from earthx.processing.operators.select import SELECT_BANDS, SelectParams
from earthx.processing.recipe import Band, CropOutput, RasterOutput, Recipe, ResolvedInput, Step
from earthx.processing.source import expected_band_names, units_of

__all__ = [
    "EXPORT_FACTOR",
    "MAX_JOB_MEMORY_BYTES",
    "RASTER_WITHOUT_STEP_FACTOR",
    "RESAMPLING_METHOD",
    "SECONDS_PER_ASSET",
    "SECONDS_PER_EXPORT_MB",
    "SECONDS_PER_EXPORT_MB_PER_ITEM",
    "SECONDS_PER_INPUT_MB",
    "SECONDS_PER_MEASURE_BAND_MPIXEL",
    "SECONDS_PER_OUTPUT_BAND_MPIXEL",
    "DISK_RESERVE_BYTES",
    "BandOnOtherGrid",
    "CostEstimate",
    "GridFacts",
    "PlannedStep",
    "ResamplingFacts",
    "ScenesInOtherZone",
    "Segment",
    "check_bands",
    "crop_window",
    "describe_resampling",
    "disk_needed",
    "estimate",
    "export_outputs",
    "live_steps",
    "memory_needed",
    "needed_source_bands",
    "plan_steps",
    "segments",
    "split_tiers",
    "stock_steps",
]

#: Seconds per MB of raw input for band math, measured locally on 1024 px blocks
#: (adr/0014 §3.5: 9.8 s for 2 × 134 MB). A bound for the display ("about"), no promise.
SECONDS_PER_INPUT_MB = 0.034

#: Seconds per output band and million pixels of the output: writing, statistics and the COG of each band, which the
#: input term does not see (adr/0020 §3.2 Befund 9). Measured on synthetic scenes with up to three runs at a time on four
#: cores, as a worker with two slots runs: 0.42–0.72 s per band and million pixels, 0.57 with 16 `band_math` steps at 5632²;
#: the real runs of adr/0020 §3.2 give 0.55–0.7. The limit of a run is twice the estimate.
SECONDS_PER_OUTPUT_BAND_MPIXEL = 0.75

#: Seconds per million pixels and band of the stock at a cut where a step measures: the extra pass over the local
#: ``float64`` file (read, convert, write, count) and the refinement of the percentiles. Measured, plan NM4-71 §8.3:
#: 0.20–0.21 s (whole scene, one band 25 s, four bands 98 s).
SECONDS_PER_MEASURE_BAND_MPIXEL = 0.2

#: First open of an asset over the network (adr/0006 §3.4).
SECONDS_PER_ASSET = 1.0

#: Units of an export, the crop alone (adr/0014 §5.5, M3-18 §10.3). It writes no statistics.
EXPORT_FACTOR = 0.9

#: Units of a raster run without any step: the crop as one pass of the core, which counts the
#: statistics as it writes (M4-32, +9.3 % measured, rounded up; adr/0014 §15k).
RASTER_WITHOUT_STEP_FACTOR = 1.0

#: Seconds per MB of an export's output (data and mask, as ``PlannedOutput.total_bytes``
#: counts) for writing, the COG, reading it back and packing, plus per item of the group for
#: reading it — in a mosaic every item may be read for every block. Measured locally in
#: M4-11a (``test_memory_export.py``, 160 MB planned, items read fully): one item 8.2–9.6 s,
#: two 12.4–13.5 s, eight 36.6 s, so 0.030 + 0.025 per item. The network is not in it; the
#: runtime limit's factor 2 is the reserve.
SECONDS_PER_EXPORT_MB = 0.030
SECONDS_PER_EXPORT_MB_PER_ITEM = 0.025

#: What one child process of a job may hold at its peak (adr/0020 §7.2, F5; a starting value, Otto, 28.10.2026): a
#: worker with two slots needs up to twice this. Over it `estimate` refuses the job with the number, a `413`.
MAX_JOB_MEMORY_BYTES = 1_500_000_000

#: The peak memory of a run, measured on synthetic scenes (`scripts/nm4-43-bands/memory.py`, the Nachtrag NM4-43c PR 2 of
#: adr/0014): a base, a share for every band the widest pass holds, and for a mosaic a share for every scene beyond the
#: first (an open file) and for each of its bands. It follows the 1024 px block and not the area: 17 bands peak at
#: 727 MB from 2048² to 5632². Each constant lies above every measurement.
MEMORY_BASE_BYTES = 300_000_000
MEMORY_BYTES_PER_BAND = 33_000_000
MEMORY_BYTES_PER_SCENE = 4_000_000
MEMORY_BYTES_PER_SCENE_BAND = 1_200_000

#: Added for every band a step measures, measured NM4-71 (`test_memory_mask_normalize.py`, `normalize` version 4 with a
#: percentile stretch over every band of a 4096² scene, ``VmHWM`` with ``GDAL_CACHEMAX`` 64 MB): 1 band 347 MB, 2 bands
#: 433 MB, 4 bands 516 MB, against 333, 366 and 432 MB of base and share per band alone. The least share that covers all
#: three is 34 MB (2 bands). The CI runner measured 457 MB for 2 bands, which needs 46 MB; 60 MB keeps a margin on both
#: machines, and the sum stays above every measured peak.
MEMORY_BYTES_PER_MEASURED_BAND = 60_000_000

#: Bytes per value where an item names no data type, as the download estimate assumes.
_FALLBACK_BYTES_PER_VALUE = 8


@dataclass(frozen=True, slots=True)
class PlannedStep:
    """One step with its operator looked up and its parameters validated."""

    step: Step
    operator: Operator
    params: object


@dataclass(frozen=True, slots=True)
class Segment:
    """One pass over the raster: a run of ``pixel`` steps, or exactly one ``grid`` step."""

    kind: Literal["pixel", "grid"]
    steps: tuple[PlannedStep, ...]

    @property
    def measuring(self) -> PlannedStep | None:
        """The step that opens this pass and needs its bands counted in the pass before it, or ``None`` (NM4-71).

        :func:`segments` puts such a step first in its pass and never inside a run, so this is the only place one can be.
        """
        if self.kind == "pixel" and self.steps and _measures(self.steps[0]):
            return self.steps[0]
        return None


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """What a run is expected to cost (§5.5), computed before any read."""

    input_pixels: int
    input_bytes: int
    assets: int
    output_pixels: int
    output_bytes: int
    seconds: float
    units: float
    #: The peak memory of the child process that runs the job; zero for an export, which streams.
    memory_bytes: int = 0


def memory_needed(bands: int, scenes: int = 1, measured_bands: int = 0) -> int:
    """The peak memory of a run whose widest pass holds ``bands`` bands, over ``scenes`` scenes of one mosaic.

    A band is held several times per block (read, scaled, masked, written), so the share is per band; a scene beyond
    the first is an open file whose pieces are merged one at a time. Nothing here depends on the area. A step that
    measures (NM4-71) adds :data:`MEMORY_BYTES_PER_MEASURED_BAND` for each band it measures: the pass after the count
    reads the ``float64`` work file, which holds twice the bytes per value of the scene.
    """
    extra_scenes = scenes - 1
    return (
        MEMORY_BASE_BYTES
        + MEMORY_BYTES_PER_BAND * bands
        + extra_scenes * (MEMORY_BYTES_PER_SCENE + MEMORY_BYTES_PER_SCENE_BAND * bands)
        + MEMORY_BYTES_PER_MEASURED_BAND * measured_bands
    )


def plan_steps(steps: Sequence[Step], operators: OperatorRegistry) -> list[PlannedStep]:
    """Every step with its operator and validated parameters; unknown ones are named errors."""
    planned = []
    for step in steps:
        operator = operators.operator(step.op, step.op_version)
        params = operator.params.model_validate_json(json.dumps(step.params), strict=True)
        planned.append(PlannedStep(step, operator, params))
    return planned


def _refuse_chain_of_version_1(planned: Sequence[PlannedStep]) -> None:
    for index, step in enumerate(planned):
        if not step.operator.stock:
            raise RecipeInvalid(
                f"step {index}: {step.step.op} version {step.step.op_version} replaces or removes bands, as a recipe "
                f"of version 1 did; a recipe of version 2 takes version {step.step.op_version + 1} or later"
            )


def _trace(planned: Sequence[PlannedStep], output: Sequence[str]) -> tuple[list[frozenset[str]], list[bool]]:
    """The names the stock has to hold before each step, from the end, and which steps change nothing the output keeps.

    ``needed[i]`` is what step ``i`` is given (``needed[len(planned)]`` the output itself); a step is ``dead`` where
    it adds a band nobody needs or changes none that is needed (:class:`~earthx.processing.operators.BandUse`).
    """
    needed = [frozenset[str]()] * (len(planned) + 1)
    needed[-1] = frozenset(output)
    dead = [False] * len(planned)
    for index in reversed(range(len(planned))):
        use = planned[index].operator.bands_used(planned[index].params)
        after = needed[index + 1]
        if use.adds is not None:
            dead[index] = use.adds not in after
            needed[index] = after if dead[index] else (after - {use.adds}) | use.reads
        elif use.acts_on is not None and not use.acts_on & after:
            dead[index] = True
            needed[index] = after
        else:
            needed[index] = after | use.reads
    return needed, dead


def needed_source_bands(planned: Sequence[PlannedStep], output: Sequence[str]) -> frozenset[str]:
    """The names the first step needs from the data: what `api` reads the assets for (adr/0020 §5).

    Names a step adds are not among them; a name that no band of the data has is, and the caller refuses it.
    """
    _refuse_chain_of_version_1(planned)
    return _trace(planned, output)[0][0]


def _select(names: Sequence[str]) -> PlannedStep:
    return PlannedStep(
        Step(op=SELECT_BANDS.op, op_version=SELECT_BANDS.op_version, params={"names": list(names)}),
        SELECT_BANDS,
        SelectParams(names=tuple(names)),
    )


def stock_steps(meta: RasterMeta, planned: Sequence[PlannedStep], output: Sequence[str]) -> list[PlannedStep]:
    """The steps a job runs on ``meta``'s stock: the recipe's without the dead ones, plus the planner's selections.

    Every step that is run is judged first on the whole stock (:class:`RecipeInvalid`, the place of the step in the
    text as in :func:`check_bands`), and so is an output band the stock does not hold at the end. A step that changes
    nothing the output keeps is not run and not judged: the bands it names are not read, so they need not be there.

    Then the plan: bands that no later step and not the output needs are dropped before the step that follows, so a
    ``grid`` step warps only what is kept. The bands that stay have the values they would have had in a stock with the
    others, because a step works per band or per pixel, and ``reproject`` since version 4 for each band alone
    (adr/0020 §3.4). The stock is ordered like ``output`` as soon as it is narrowed, so that a last ``grid`` step needs
    no pass of its own to sort the bands.
    """
    _refuse_chain_of_version_1(planned)
    needed, dead = _trace(planned, output)
    full = meta
    for index, step in enumerate(planned):
        if dead[index]:
            continue
        try:
            full = step.operator.transform(full, step.params)
        except RecipeInvalid as error:
            if len(planned) == 1:
                raise
            raise RecipeInvalid(f"step {index}: {error}") from error
    held = [band.name for band in full.bands]
    missing = [name for name in output if name not in held]
    if missing:
        raise RecipeInvalid(
            f"output.bands names unknown band(s): {', '.join(missing)}; the stock has: {', '.join(held)}"
        )
    position = {name: index for index, name in enumerate(output)}
    steps: list[PlannedStep] = []
    current = meta

    def narrow(wanted: frozenset[str]) -> None:
        nonlocal current
        present = [band.name for band in current.bands]
        rank = {name: (position.get(name, len(position)), index) for index, name in enumerate(present)}
        kept = sorted((name for name in present if name in wanted), key=rank.__getitem__)
        if kept != present:
            steps.append(_select(kept))
            current = SELECT_BANDS.transform(current, steps[-1].params)

    narrow(needed[0])
    for index, step in enumerate(planned):
        if dead[index]:
            continue
        if step.operator.restrict is not None:
            # The bands of the step that the planner dropped are not converted; the others are, as before.
            step = replace(step, params=step.operator.restrict(step.params, needed[index + 1]))
        steps.append(step)
        current = step.operator.transform(current, step.params)
        narrow(needed[index + 1])
    return steps


def live_steps(planned: Sequence[PlannedStep], output: Sequence[str]) -> list[PlannedStep]:
    """The steps of a recipe that run: those whose result the output keeps. What a result reports (lineage,
    expressions, methods text) is these steps and no other."""
    _, dead = _trace(planned, output)
    return [step for step, is_dead in zip(planned, dead, strict=True) if not is_dead]


def split_tiers(steps: Sequence[Step], operators: OperatorRegistry) -> tuple[list[Step], list[Step]]:
    """``(tile steps, job steps)`` by the rule of §6.1."""
    cut = 0
    for planned in plan_steps(steps, operators):
        if planned.operator.kind != "pixel" or Tier.T1 not in planned.operator.tiers:
            break
        cut += 1
    return list(steps[:cut]), list(steps[cut:])


def _measures(step: PlannedStep) -> frozenset[str]:
    return step.operator.measures(step.params)


def segments(planned: Sequence[PlannedStep]) -> list[Segment]:
    """The passes of a job, in order.

    The first pass is always ``pixel``: it is the one that reads the inputs, and with
    no ``pixel`` step before a ``grid`` step it is empty, a plain native crop into the
    work directory for the grid step to read (F3). No step at all is that crop alone.

    A ``pixel`` step that measures (``Operator.measures``) ends the run before it and opens the next pass, so that the
    pass before it can count its bands (NM4-71). As with a ``grid`` step, a measuring first step is preceded by an empty
    pass that reads the inputs; one that follows a ``grid`` step needs no pass of its own, the pass of the grid step
    counts. Two measuring steps are two cuts. A measuring step before a ``grid`` step is fine: the pass before it counts on
    the grid of the stock, with the AOI on that grid.
    """
    result: list[Segment] = []
    run: list[PlannedStep] = []
    for step in planned:
        if step.operator.kind == "pixel":
            if _measures(step) and (run or not result):
                result.append(Segment("pixel", tuple(run)))
                run = []
            run.append(step)
            continue
        if run or not result:
            result.append(Segment("pixel", tuple(run)))
            run = []
        result.append(Segment("grid", (step,)))
    if run or not result:
        result.append(Segment("pixel", tuple(run)))
    return result


def crop_window(aoi: dict, crs: str, transform: Affine, width: int, height: int) -> tuple[Window, Affine]:
    """The window of ``bbox(AOI ∩ raster bounds)`` in this grid, snapped outward to whole pixels.

    ``aoi`` is GeoJSON in EPSG:4326. Raises :class:`AoiOutsideInputs` when the two
    do not overlap, and :class:`UnsupportedRecipe` for a rotated grid.
    """
    if transform.b != 0 or transform.d != 0 or transform.a <= 0 or transform.e >= 0:
        raise UnsupportedRecipe("only north-up grids without rotation are processed")
    left, top = transform.c, transform.f
    right, bottom = transform @ (width, height)
    footprint = shapely_shape(transform_geom("EPSG:4326", crs, aoi)).intersection(box(left, bottom, right, top))
    if footprint.is_empty or footprint.area == 0:
        raise AoiOutsideInputs("the AOI does not overlap the input raster")
    minx, miny, maxx, maxy = footprint.bounds
    col0 = max(0, math.floor((minx - left) / transform.a))
    col1 = min(width, math.ceil((maxx - left) / transform.a))
    row0 = max(0, math.floor((top - maxy) / -transform.e))
    row1 = min(height, math.ceil((top - miny) / -transform.e))
    window = Window(col0, row0, col1 - col0, row1 - row0)
    return window, transform @ Affine.translation(col0, row0)


def _value_bytes(data_type: str | None) -> int:
    try:
        return numpy.dtype(data_type).itemsize if data_type and data_type != "other" else _FALLBACK_BYTES_PER_VALUE
    except TypeError:
        return _FALLBACK_BYTES_PER_VALUE


def _band_bytes(bands: Sequence[Band]) -> int:
    return sum(_value_bytes(band.data_type) for band in bands) or _FALLBACK_BYTES_PER_VALUE


#: Metres a degree of latitude is worth, only to size the placeholder raster of an estimate (no promise).
_METRES_PER_DEGREE = 111_320.0

#: Floor for the cosine of the latitude, so that a pole does not divide by zero.
_MIN_COSINE = 0.01


def _pixel_size(crs: str, gsd: float, latitude: float) -> tuple[float, float]:
    """``gsd`` (metres) as ``(x, y)`` pixel size in the units of ``crs``.

    A projected CRS gives the metres in its own unit. A geographic CRS gives degrees, the
    east-west one stretched by the cosine of ``latitude``: a degree of longitude is that much shorter.
    """
    try:
        parsed = CRS.from_user_input(crs)
        if not parsed.is_geographic:
            size = gsd / parsed.linear_units_factor[1]
            return size, size
    except CRSError:
        raise UnsupportedRecipe(f"the CRS {crs!r} of the input is not one this platform can size a raster in") from None
    y = gsd / _METRES_PER_DEGREE
    return y / max(math.cos(math.radians(latitude)), _MIN_COSINE), y


def _no_pixel_size(entry: ResolvedInput) -> UnsupportedRecipe:
    return UnsupportedRecipe(
        f"the item does not give the pixel size of asset {entry.asset.asset!r} (no gsd), so the job cannot be estimated"
    )


def _finest(entries: Sequence[ResolvedInput]) -> ResolvedInput:
    """The entry the core reads the others onto: the smallest ``gsd``, the first of equals (``source.common_grid``).

    Whatever the order of the assets in the job, this is the same entry. A missing ``gsd`` is
    refused with the reason, not guessed (``UnsupportedRecipe``, a ``422``).
    """
    for entry in entries:
        if entry.gsd is None:
            raise _no_pixel_size(entry)
    return min(entries, key=lambda entry: entry.gsd)


def _input_grid(recipe: Recipe, finest: ResolvedInput) -> tuple[Affine, int, int]:
    """The box of the AOI in the CRS of ``finest``'s asset, with the pixel size of its ``gsd``: ``(transform, width, height)``.

    The box is where the first pass would read, the AOI's bounds in the CRS of the asset, not the
    origin of that CRS; the pixel size is ``gsd`` in the units of the CRS, a geographic one at the
    latitude of the middle of the AOI. A missing ``gsd`` is not guessed: the estimate is refused
    with the reason (``UnsupportedRecipe``, a ``422``).
    """
    if finest.gsd is None:
        raise _no_pixel_size(finest)
    crs = finest.asset.crs or "EPSG:4326"
    aoi = recipe.aoi.model_dump(mode="json")
    try:
        _, south, _, north = shapely_shape(aoi).bounds
        left, bottom, right, top = shapely_shape(transform_geom("EPSG:4326", crs, aoi)).bounds
    except (CRSError, RasterioError, ValueError, TypeError):
        raise UnsupportedRecipe(f"the AOI cannot be placed in the CRS {crs!r} of the input") from None
    if not all(math.isfinite(value) for value in (left, bottom, right, top)):
        raise UnsupportedRecipe(f"the AOI has no finite extent in the CRS {crs!r} of the input")
    size_x, size_y = _pixel_size(crs, finest.gsd, (south + north) / 2)
    width = max(1, math.ceil((right - left) / size_x))
    height = max(1, math.ceil((top - bottom) / size_y))
    return Affine(size_x, 0, left, 0, -size_y, top), width, height


def _asset_entries(recipe: Recipe) -> list[ResolvedInput]:
    """One resolved entry per asset of each input: the first item's.

    The scenes of a mosaic (M4-12a) carry the same bands; the raster they make has them once.
    For an input of one item these are all its entries.
    """
    entries: list[ResolvedInput] = []
    for item in recipe.inputs:
        seen: set[str] = set()
        for entry in item.resolved:
            if entry.asset.asset not in seen:
                seen.add(entry.asset.asset)
                entries.append(entry)
    return entries


def _input_meta(recipe: Recipe, *, names_known: bool, sized: bool) -> RasterMeta | None:
    """The raster the first pass would read, as far as the recipe says (no read).

    The bands of every input asset, in order, named as the core names them. Where an
    asset's names are only in the file, ``names_known`` decides: ``False`` falls back to
    the asset key (an estimate does not care), ``True`` gives up and returns ``None``
    (a check against the names would reject what the file may well offer). CRS and pixel
    size are those of the asset with the finest ``gsd`` (:func:`_finest`), the grid the core
    reads all assets onto (adr/0020 §3.3). With ``sized`` the raster is the AOI's box in that CRS
    at that pixel size (:func:`_input_grid`, which refuses a missing ``gsd``); without it, one
    pixel at the corner of that box, or at the origin where the size is not known: the names
    are all a check wants.
    """
    bands: list[BandMeta] = []
    resolved = _asset_entries(recipe)
    for entry in resolved:
        names = expected_band_names(entry)
        if names is None:
            if names_known:
                return None
            names = [entry.asset.asset]
        types = [band.data_type for band in entry.bands] if len(entry.bands) == len(names) else [None] * len(names)
        units = units_of(entry, len(names))
        bands.extend(
            BandMeta(name, data_type or "float64", None, unit)
            for name, data_type, unit in zip(names, types, units, strict=True)
        )
    if sized:
        finest = _finest(resolved)
        transform, width, height = _input_grid(recipe, finest)
    else:
        finest = resolved[0]
        try:
            finest = _finest(resolved)
            transform, _, _ = _input_grid(recipe, finest)
        except UnsupportedRecipe:
            transform = Affine(1, 0, 0, 0, -1, 0)
        width = height = 1
    return RasterMeta(finest.asset.crs or "EPSG:4326", transform, width, height, tuple(bands))


def check_bands(recipe: Recipe, operators: OperatorRegistry) -> None:
    """Run every step's ``transform`` on the bands the inputs will carry; ``RecipeInvalid`` for a wrong name.

    With several steps the refusal begins with the place of the step (``step 1: …`` for the second, counted from 0 like the other refusals of an order), as the tile of a chain says it.
    A raster recipe also has to find every band of ``output.bands`` in the stock after the last step
    (:func:`stock_steps`).

    Where the item does not say how many bands an asset has, the file does, and the
    core checks again before it reads the first block (plan M4-09 §3.3). Nothing is read.
    """
    meta = _input_meta(recipe, names_known=True, sized=False)
    if meta is None:
        return
    planned = plan_steps(recipe.steps, operators)
    if isinstance(recipe.output, RasterOutput):
        stock_steps(meta, planned, recipe.output.bands)
        return
    for index, step in enumerate(planned):
        try:
            meta = step.operator.transform(meta, step.params)
        except RecipeInvalid as error:
            if len(planned) == 1:
                raise
            raise RecipeInvalid(f"step {index}: {error}") from error


@dataclass(frozen=True, slots=True)
class _Stock:
    """What a raster job is made of: the raster it writes, its steps, the widest stock and the work its bands cost."""

    meta: RasterMeta
    steps: list[PlannedStep]
    #: The most bands the job holds at once.
    widest: int
    #: Bands weighted by factor: each step counts its factor for the bands it adds or changes (``band_math`` its result,
    #: the others the bands they act on), and an output band no step touches counts as written (adr/0014 Nachtrag
    #: NM4-43c PR 2, Otto 30.10.2026).
    weighted_bands: float
    #: The pixels times the bands of the stock at every cut where a step measures, summed: each is written once more and
    #: read again (NM4-71). The raster at a cut before a ``grid`` step is not the one of the result.
    measure_band_pixels: int = 0
    #: The most bands one step measures; the count of the pass holds their statistics and the second look their values.
    measured_bands: int = 0


def _planned_stock(recipe: Recipe, operators: OperatorRegistry) -> _Stock:
    """The raster a raster job writes, its steps without the planner's selections, and what its bands cost.

    Every band of the assets is read together, whatever a step drops after it, and a ``band_math`` step adds one: the
    widest stock decides the memory of a pass and the float64 file it leaves in the work directory.
    """
    meta = _input_meta(recipe, names_known=False, sized=True)
    assert meta is not None  # a recipe has at least one resolved input
    steps = stock_steps(meta, plan_steps(recipe.steps, operators), recipe.output.bands)
    widest = len(meta.bands)
    weighted, touched = 0.0, set[str]()
    measure_band_pixels = measured_bands = 0
    for step in steps:
        if measured := _measures(step):
            measure_band_pixels += meta.width * meta.height * len(meta.bands)
            measured_bands = max(measured_bands, len(measured))
        if step.operator is not SELECT_BANDS:
            names = {band.name for band in meta.bands}
            use = step.operator.bands_used(step.params)
            changed = {use.adds} if use.adds is not None else names if use.acts_on is None else names & use.acts_on
            weighted += step.operator.cost_factor(step.params) * len(changed)
            touched |= changed
        meta = step.operator.transform(meta, step.params)
        widest = max(widest, len(meta.bands))
    weighted += RASTER_WITHOUT_STEP_FACTOR * len({band.name for band in meta.bands} - touched)
    return _Stock(
        meta,
        [step for step in steps if step.operator is not SELECT_BANDS],
        widest,
        weighted,
        measure_band_pixels,
        measured_bands,
    )


def estimate(recipe: Recipe, operators: OperatorRegistry) -> CostEstimate:
    """The cost of a job from AOI, ``gsd`` and data types (§5.5); reads nothing.

    An export (output ``crop``) is estimated as the crop estimates itself and refused
    with :class:`ExportTooLarge` above ``MAX_JOB_BYTES`` (M4-11 F5); a raster job is refused
    with :class:`JobTooLarge` above it, counting its output and its mask (M4-12 F7), and above the memory one child
    process may use (:func:`memory_needed`, adr/0020 §7). A raster job needs the pixel size of every asset (``gsd``);
    without it :class:`UnsupportedRecipe` says so (M4-25). Seconds count the bands of the output; units count each step's factor for the bands it adds or
    changes (:class:`_Stock`). Each cut where a step measures (NM4-71) adds :data:`SECONDS_PER_MEASURE_BAND_MPIXEL` for
    every band of the stock at that cut.
    """
    if isinstance(recipe.output, CropOutput):
        return _export_estimate(recipe)
    aoi = shapely_shape(recipe.aoi.model_dump(mode="json"))
    input_pixels = input_bytes = 0
    #: Every scene of a mosaic is opened, but each output pixel comes from about one of them.
    assets = sum(len(item.resolved) for item in recipe.inputs)
    for entry in _asset_entries(recipe):
        if entry.gsd is None:
            raise _no_pixel_size(entry)
        rows, columns = estimate_output_dims(aoi, entry.gsd)
        input_pixels += rows * columns
        input_bytes += rows * columns * _band_bytes(entry.bands)
    stock = _planned_stock(recipe, operators)
    meta, widest = stock.meta, stock.widest
    output_pixels = meta.width * meta.height
    dtype = getattr(recipe.output, "dtype", None)
    output_bytes = output_pixels * len(meta.bands) * _value_bytes(dtype)
    if output_bytes + output_pixels > MAX_JOB_BYTES:
        raise JobTooLarge(
            f"This job would write about {(output_bytes + output_pixels) / 1_000_000:.0f} MB, more than the "
            f"{MAX_JOB_BYTES / 1_000_000:.0f} MB a job may write. Draw a smaller area or choose fewer assets."
        )
    memory = memory_needed(widest, len(recipe.inputs[0].groups[0]), stock.measured_bands)
    if memory > MAX_JOB_MEMORY_BYTES:
        raise JobTooLarge(
            f"This job would need about {memory / 1_000_000_000:.1f} GB of memory, more than the "
            f"{MAX_JOB_MEMORY_BYTES / 1_000_000_000:.1f} GB a job may use. Put fewer bands in the output."
        )
    band_megapixels = output_pixels / 1_000_000 * len(meta.bands)
    return CostEstimate(
        input_pixels=input_pixels,
        input_bytes=input_bytes,
        assets=assets,
        output_pixels=output_pixels,
        output_bytes=output_bytes,
        seconds=SECONDS_PER_INPUT_MB * input_bytes / 1_000_000
        + SECONDS_PER_ASSET * assets
        + SECONDS_PER_OUTPUT_BAND_MPIXEL * band_megapixels
        + SECONDS_PER_MEASURE_BAND_MPIXEL * stock.measure_band_pixels / 1_000_000,
        units=output_pixels / 1_000_000 * stock.weighted_bands,
        memory_bytes=memory,
    )


#: How the core brings a value band of a coarser asset, or a scene of another zone, onto the grid of the finest
#: asset: read with ``nearest`` (``source.common_grid``, ``mosaic``, which warps with the constants of ``reproject``).
RESAMPLING_METHOD = "nearest"

#: Two pixel sizes are the same grid up to this (``source._GRID_TOLERANCE``).
_SAME_SIZE = 1e-6


@dataclass(frozen=True, slots=True)
class GridFacts:
    """The grid the values of a job lie on: the finest pixel size (metres, the item's ``gsd``) and the CRS, if the item names one."""

    resolution: float
    crs: str | None


@dataclass(frozen=True, slots=True)
class BandOnOtherGrid:
    """A band of the data that reaches the result and whose source does not lie on the grid of the job."""

    band: str
    resolution: float
    crs: str | None


@dataclass(frozen=True, slots=True)
class ScenesInOtherZone:
    """``count`` of the ``of`` scenes of a mosaic lie in another CRS than ``crs``, the one most scenes share."""

    count: int
    of: int
    crs: str


@dataclass(frozen=True, slots=True)
class ResamplingFacts:
    """What a raster job converts silently, from the recipe alone (no read): the values of ``bands`` and of ``scenes``."""

    grid: GridFacts
    method: str
    bands: tuple[BandOnOtherGrid, ...]
    scenes: ScenesInOtherZone | None


def _crs_by_asset(recipe: Recipe) -> dict[str, str | None]:
    """The CRS each asset is read in: the one most of its scenes are in, as the mosaic picks its target (``target_crs``)."""
    scenes: dict[str, dict[str, str | None]] = {}
    for entry in recipe.inputs[0].resolved:
        scenes.setdefault(entry.asset.asset, {})[entry.asset.item_id] = entry.asset.crs
    return {asset: target_crs(crs_by_item) for asset, crs_by_item in scenes.items()}


def _feeding_bands(live: Sequence[PlannedStep], output: Sequence[str]) -> frozenset[str]:
    """The bands of the data whose values reach the output.

    Worked from the end through the steps that run. A step that adds a band (``band_math``) hands on what it reads;
    what a step that adds none reads is the layer it decides by (``mask``, ``mask_values``, :class:`BandUse`): it
    hides pixels and gives no value, so it does not feed the result.
    """
    feeding = frozenset(output)
    for step in reversed(live):
        use = step.operator.bands_used(step.params)
        if use.adds is not None and use.adds in feeding:
            feeding = (feeding - {use.adds}) | use.reads
    return feeding


def describe_resampling(recipe: Recipe, operators: OperatorRegistry) -> ResamplingFacts | None:
    """What a raster job converts onto a common grid without being asked to, or ``None``; reads nothing.

    The rule of the job (:func:`~earthx.processing.source.common_grid` and ``_source_meta`` of the core): the grid is
    that of the asset with the finest ``gsd`` (:func:`_finest`); a band is converted where its asset has another pixel
    size or CRS, and a scene of a mosaic where it lies in another CRS than most (:func:`target_crs`). Like the flag
    ``earthx:resampled`` of the result, only a band that reaches the output counts (:func:`_feeding_bands`): a
    classification layer that only masks is read onto the grid and does not appear.

    ``None`` as well for an export (native values), for an order with a ``grid`` step (``reproject``: the person chose
    the target and the method, that step describes it) and where an asset has no ``gsd`` (the estimate refuses that
    before). A CRS the item does not name is ``None`` in the facts: it is neither compared nor guessed.
    """
    if not isinstance(recipe.output, RasterOutput):
        return None
    live = live_steps(plan_steps(recipe.steps, operators), recipe.output.bands)
    entries = _asset_entries(recipe)
    if any(step.operator.kind == "grid" for step in live) or not entries or any(e.gsd is None for e in entries):
        return None
    finest = _finest(entries)
    crs_of = _crs_by_asset(recipe)
    grid = GridFacts(finest.gsd, crs_of[finest.asset.asset])

    def on_grid(entry: ResolvedInput) -> bool:
        crs = crs_of[entry.asset.asset]
        return math.isclose(entry.gsd, grid.resolution, rel_tol=_SAME_SIZE) and (
            crs is None or grid.crs is None or crs == grid.crs
        )

    feeding = _feeding_bands(live, recipe.output.bands)
    bands = tuple(
        BandOnOtherGrid(name, entry.gsd, crs_of[entry.asset.asset])
        for entry in entries
        if not on_grid(entry)
        for name in expected_band_names(entry) or [entry.asset.asset]
        if name in feeding
    )
    scenes = None
    crs_by_scene = {e.asset.item_id: e.asset.crs for e in recipe.inputs[0].resolved if e.asset.asset == finest.asset.asset}
    if len(crs_by_scene) > 1 and (target := target_crs(crs_by_scene)) is not None:
        apart = sum(1 for crs in crs_by_scene.values() if crs is not None and crs != target)
        scenes = ScenesInOtherZone(apart, len(crs_by_scene), target) if apart else None
    return ResamplingFacts(grid, RESAMPLING_METHOD, bands, scenes) if bands or scenes else None


def export_outputs(recipe: Recipe) -> list[PlannedOutput]:
    """The files an export writes, per group and asset, as ``access.download.plan_outputs`` plans a crop.

    The region of a group is AOI ∩ its footprints (``compute_crop_region``); per asset the
    finest ``gsd`` and the largest bytes per pixel of the group's items, both read off the
    item at acceptance. Reads nothing.
    """
    aoi = shapely_shape(recipe.aoi.model_dump(mode="json"))
    planned = []
    for entry in recipe.inputs:
        footprints = entry.footprints or {}
        resolved = {(item.asset.item_id, item.asset.asset): item for item in entry.resolved}
        for group in entry.groups:
            geometries = [footprints.get(item_id) for item_id in group]
            items = [{"geometry": None if g is None else g.model_dump(mode="json")} for g in geometries]
            try:
                region = compute_crop_region(items, aoi)
            except AoiOutsideItems:
                raise AoiOutsideInputs("the AOI does not touch the footprint of a group") from None
            for asset in entry.assets:
                entries = [resolved[(item_id, asset)] for item_id in group]
                gsds = [item.gsd for item in entries if item.gsd is not None]
                if gsds:
                    height, width = estimate_output_dims(region, min(gsds))
                else:
                    height = width = MAX_OUTPUT_SIDE_PX
                per_pixel = max(
                    (bytes_per_pixel([band.data_type for band in item.bands], asset) for item in entries),
                    default=FALLBACK_BYTES_PER_PIXEL,
                )
                planned.append(PlannedOutput(label=asset, width=width, height=height, bytes_per_pixel=per_pixel))
    return planned


def _export_estimate(recipe: Recipe) -> CostEstimate:
    planned = export_outputs(recipe)
    pixels = sum(output.width * output.height for output in planned)
    raw = sum(output.width * output.height * output.bytes_per_pixel for output in planned)
    total = sum(output.total_bytes for output in planned)
    if total > MAX_JOB_BYTES:
        raise ExportTooLarge(
            f"This export would be about {total / 1_000_000:.0f} MB, more than the "
            f"{MAX_JOB_BYTES / 1_000_000:.0f} MB an export job may write. "
            "Draw a smaller area or choose fewer assets."
        )
    assets = sum(len(entry.resolved) for entry in recipe.inputs)
    items = [len(group) for entry in recipe.inputs for group in entry.groups for _ in entry.assets]
    seconds = sum(
        output.total_bytes / 1_000_000 * (SECONDS_PER_EXPORT_MB + SECONDS_PER_EXPORT_MB_PER_ITEM * count)
        for output, count in zip(planned, items, strict=True)
    )
    return CostEstimate(
        input_pixels=pixels,
        input_bytes=raw,
        assets=assets,
        output_pixels=pixels,
        output_bytes=total,
        seconds=seconds + SECONDS_PER_ASSET * assets,
        units=pixels / 1_000_000 * EXPORT_FACTOR,
    )


#: What a run keeps free beyond its estimated need (Otto, 08.10.2026; a starting value [A]):
#: the recipe and side files, GDAL's and rio-cogeo's small files, slack for a COG's header.
DISK_RESERVE_BYTES = 256 * 1024 * 1024

#: A COG's overviews add at most a third of its full resolution (each level a quarter of the one before).
_WITH_OVERVIEWS = 4 / 3

#: Bytes per value of the core's intermediate passes (``core._INTERMEDIATE_DTYPE``, float64).
_PASS_BYTES = 8


def _tiles_px(pixels: int) -> int:
    """``pixels`` filled up to whole blocks: a tiled GeoTIFF stores every block in full."""
    return -(-pixels // BLOCK_SIZE) * BLOCK_SIZE


def disk_needed(recipe: Recipe, operators: OperatorRegistry) -> int:
    """The bytes a run needs in its work directory, judged before it starts (Otto, 08.10.2026).

    **Finished files + 2 × raw size of the largest output + reserve**, from the recipe alone:

    * finished files: the planned output, data and mask, raw, with room for COG overviews
      (× 4/3); deflate only makes the files smaller;
    * the raw size of the largest output: its plain GeoTIFF, uncompressed and filled up to
      whole 1024 px blocks — for an export the data file of one group and asset, for a raster
      run the float64 pass over all bands; twice, because ``cog_translate`` keeps a temporary
      file of the same order beside it (measured, plan m4-11 §11 Punkt 8);
    * the work file of a measure (NM4-71) is that same float64 pass: the pass before a step that measures writes it and
      counts into it, the next pass reads it. At most two pass files lie in the work directory at once (the one read and
      the one written, each deleted as soon as the pass that reads it is done), and a deflate file is not larger than its
      raw size by more than a fraction of a percent, so the term covers it; a test holds the highest level measured in
      a run below this number;
    * :data:`DISK_RESERVE_BYTES`.

    An estimate like :func:`estimate`, conservative where it has to guess (``gsd`` missing,
    data type unknown). Reads nothing.
    """
    if isinstance(recipe.output, CropOutput):
        planned = export_outputs(recipe)
        finished = sum(output.total_bytes for output in planned)
        largest = max(
            _tiles_px(output.width) * _tiles_px(output.height) * output.bytes_per_pixel for output in planned
        )
    else:
        cost = estimate(recipe, operators)
        finished = cost.output_bytes + cost.output_pixels
        rows, columns = estimate_output_dims(
            shapely_shape(recipe.aoi.model_dump(mode="json")), _finest(_asset_entries(recipe)).gsd
        )
        bands = _planned_stock(recipe, operators).widest
        largest = _tiles_px(rows) * _tiles_px(columns) * bands * _PASS_BYTES  # the work file of a pass, measured or not
    return math.ceil(finished * _WITH_OVERVIEWS) + 2 * largest + DISK_RESERVE_BYTES
