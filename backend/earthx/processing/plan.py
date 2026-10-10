"""Planning a recipe before anything is read: tiers, segments, output grid, cost (adr/0014 §5.5, §6.1).

* :func:`split_tiers` — the longest leading run of ``pixel`` steps that all run in
  ``T1`` becomes tile parameters; everything after it is a job (§6.1).
* :func:`segments` — the steps of a job as the core runs them: a run of ``pixel``
  steps is computed block by block in one pass, a ``grid`` step is a pass of its
  own over a file in the work directory (approved F3).
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
)
from earthx.processing.errors import AoiOutsideInputs, ExportTooLarge, JobTooLarge, UnsupportedRecipe
from earthx.processing.operators import BandMeta, Operator, OperatorRegistry, RasterMeta, Tier
from earthx.processing.recipe import Band, CropOutput, Recipe, ResolvedInput, Step
from earthx.processing.source import expected_band_names

__all__ = [
    "EXPORT_FACTOR",
    "SECONDS_PER_ASSET",
    "SECONDS_PER_EXPORT_MB",
    "SECONDS_PER_EXPORT_MB_PER_ITEM",
    "SECONDS_PER_INPUT_MB",
    "DISK_RESERVE_BYTES",
    "CostEstimate",
    "PlannedStep",
    "Segment",
    "check_bands",
    "crop_window",
    "disk_needed",
    "estimate",
    "export_outputs",
    "plan_steps",
    "segments",
    "split_tiers",
]

#: Seconds per MB of raw input for band math, measured locally on 1024 px blocks
#: (adr/0014 §3.5: 9.8 s for 2 × 134 MB). A bound for the display ("about"), no promise.
SECONDS_PER_INPUT_MB = 0.034

#: First open of an asset over the network (adr/0006 §3.4).
SECONDS_PER_ASSET = 1.0

#: Units of a run without any step, the crop alone (adr/0014 §5.5, M3-18 §10.3).
EXPORT_FACTOR = 0.9

#: Seconds per MB of an export's output (data and mask, as ``PlannedOutput.total_bytes``
#: counts) for writing, the COG, reading it back and packing, plus per item of the group for
#: reading it — in a mosaic every item may be read for every block. Measured locally in
#: M4-11a (``test_memory_export.py``, 160 MB planned, items read fully): one item 8.2–9.6 s,
#: two 12.4–13.5 s, eight 36.6 s, so 0.030 + 0.025 per item. The network is not in it; the
#: runtime limit's factor 2 is the reserve.
SECONDS_PER_EXPORT_MB = 0.030
SECONDS_PER_EXPORT_MB_PER_ITEM = 0.025

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


def plan_steps(steps: Sequence[Step], operators: OperatorRegistry) -> list[PlannedStep]:
    """Every step with its operator and validated parameters; unknown ones are named errors."""
    planned = []
    for step in steps:
        operator = operators.operator(step.op, step.op_version)
        params = operator.params.model_validate_json(json.dumps(step.params), strict=True)
        planned.append(PlannedStep(step, operator, params))
    return planned


def split_tiers(steps: Sequence[Step], operators: OperatorRegistry) -> tuple[list[Step], list[Step]]:
    """``(tile steps, job steps)`` by the rule of §6.1."""
    cut = 0
    for planned in plan_steps(steps, operators):
        if planned.operator.kind != "pixel" or Tier.T1 not in planned.operator.tiers:
            break
        cut += 1
    return list(steps[:cut]), list(steps[cut:])


def segments(planned: Sequence[PlannedStep]) -> list[Segment]:
    """The passes of a job, in order.

    The first pass is always ``pixel``: it is the one that reads the inputs, and with
    no ``pixel`` step before a ``grid`` step it is empty, a plain native crop into the
    work directory for the grid step to read (F3). No step at all is that crop alone.
    """
    result: list[Segment] = []
    run: list[PlannedStep] = []
    for step in planned:
        if step.operator.kind == "pixel":
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


def _input_meta(recipe: Recipe, *, names_known: bool) -> RasterMeta | None:
    """The raster the first pass would read, as far as the recipe says (no read).

    The bands of every input asset, in order, named as the core names them. Where an
    asset's names are only in the file, ``names_known`` decides: ``False`` falls back to
    the asset key (an estimate does not care), ``True`` gives up and returns ``None``
    (a check against the names would reject what the file may well offer). CRS, pixel
    size and extent are those of the first asset; the size is set by the caller.
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
        bands.extend(BandMeta(name, data_type or "float64", None) for name, data_type in zip(names, types, strict=True))
    first = resolved[0]
    gsd = first.gsd or 1.0
    return RasterMeta(first.asset.crs or "EPSG:4326", Affine(gsd, 0, 0, 0, -gsd, 0), 1, 1, tuple(bands))


def check_bands(recipe: Recipe, operators: OperatorRegistry) -> None:
    """Run every step's ``transform`` on the bands the inputs will carry; ``RecipeInvalid`` for a wrong name.

    Where the item does not say how many bands an asset has, the file does, and the
    core checks again before it reads the first block (plan M4-09 §3.3). Nothing is read.
    """
    meta = _input_meta(recipe, names_known=True)
    if meta is None:
        return
    for step in plan_steps(recipe.steps, operators):
        meta = step.operator.transform(meta, step.params)


def estimate(recipe: Recipe, operators: OperatorRegistry) -> CostEstimate:
    """The cost of a job from AOI, ``gsd`` and data types (§5.5); reads nothing.

    An export (output ``crop``) is estimated as the crop estimates itself and refused
    with :class:`ExportTooLarge` above ``MAX_JOB_BYTES`` (M4-11 F5); a raster job is refused
    with :class:`JobTooLarge` above it, counting its output and its mask (M4-12 F7).
    """
    if isinstance(recipe.output, CropOutput):
        return _export_estimate(recipe)
    aoi = shapely_shape(recipe.aoi.model_dump(mode="json"))
    input_pixels = input_bytes = 0
    width = height = 0
    #: Every scene of a mosaic is opened, but each output pixel comes from about one of them.
    assets = sum(len(item.resolved) for item in recipe.inputs)
    for entry in _asset_entries(recipe):
        if entry.gsd is not None:
            rows, columns = estimate_output_dims(aoi, entry.gsd)
        else:
            rows = columns = MAX_OUTPUT_SIDE_PX
        if not width:
            height, width = rows, columns
        input_pixels += rows * columns
        input_bytes += rows * columns * _band_bytes(entry.bands)
    meta = _input_meta(recipe, names_known=False)
    assert meta is not None  # a recipe has at least one resolved input
    meta = replace(meta, width=width, height=height)
    planned = plan_steps(recipe.steps, operators)
    for step in planned:
        meta = step.operator.transform(meta, step.params)
    output_pixels = meta.width * meta.height
    dtype = getattr(recipe.output, "dtype", None)
    output_bytes = output_pixels * len(meta.bands) * _value_bytes(dtype)
    if output_bytes + output_pixels > MAX_JOB_BYTES:
        raise JobTooLarge(
            f"This job would write about {(output_bytes + output_pixels) / 1_000_000:.0f} MB, more than the "
            f"{MAX_JOB_BYTES / 1_000_000:.0f} MB a job may write. Draw a smaller area or choose fewer assets."
        )
    factor = sum(step.operator.cost_factor(step.params) for step in planned) if planned else EXPORT_FACTOR
    return CostEstimate(
        input_pixels=input_pixels,
        input_bytes=input_bytes,
        assets=assets,
        output_pixels=output_pixels,
        output_bytes=output_bytes,
        seconds=SECONDS_PER_INPUT_MB * input_bytes / 1_000_000 + SECONDS_PER_ASSET * assets,
        units=output_pixels / 1_000_000 * factor,
    )


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
        aoi = shapely_shape(recipe.aoi.model_dump(mode="json"))
        largest = 0
        for entry in _asset_entries(recipe):
            if entry.gsd is not None:
                rows, columns = estimate_output_dims(aoi, entry.gsd)
            else:
                rows = columns = MAX_OUTPUT_SIDE_PX
            largest += _tiles_px(rows) * _tiles_px(columns) * max(len(entry.bands), 1) * _PASS_BYTES
    return math.ceil(finished * _WITH_OVERVIEWS) + 2 * largest + DISK_RESERVE_BYTES
