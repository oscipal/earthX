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
  type, the same way ``access.download.plan_outputs`` estimates a crop (F8).
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy
from rasterio.transform import Affine
from rasterio.warp import transform_geom
from rasterio.windows import Window
from shapely.geometry import box
from shapely.geometry import shape as shapely_shape

from earthx.access.download import MAX_OUTPUT_SIDE_PX, estimate_output_dims
from earthx.processing.errors import AoiOutsideInputs, UnsupportedRecipe
from earthx.processing.operators import BandMeta, Operator, OperatorRegistry, RasterMeta, Tier
from earthx.processing.recipe import Band, Recipe, Step

__all__ = [
    "EXPORT_FACTOR",
    "SECONDS_PER_ASSET",
    "SECONDS_PER_INPUT_MB",
    "CostEstimate",
    "PlannedStep",
    "Segment",
    "crop_window",
    "estimate",
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


def estimate(recipe: Recipe, operators: OperatorRegistry) -> CostEstimate:
    """The cost of a job from AOI, ``gsd`` and data types (§5.5); reads nothing."""
    aoi = shapely_shape(recipe.aoi.model_dump(mode="json"))
    input_pixels = input_bytes = assets = 0
    first: RasterMeta | None = None
    for item in recipe.inputs:
        for entry in item.resolved:
            assets += 1
            if entry.gsd is not None:
                height, width = estimate_output_dims(aoi, entry.gsd)
            else:
                height = width = MAX_OUTPUT_SIDE_PX
            input_pixels += height * width
            input_bytes += height * width * _band_bytes(entry.bands)
            if first is None:
                gsd = entry.gsd or 1.0
                bands = tuple(
                    BandMeta(name=f"b{index + 1}", data_type=band.data_type or "float64", nodata=None)
                    for index, band in enumerate(entry.bands)
                ) or (BandMeta(name="b1", data_type="float64", nodata=None),)
                first = RasterMeta(entry.asset.crs or "EPSG:4326", Affine(gsd, 0, 0, 0, -gsd, 0), width, height, bands)
    assert first is not None  # a recipe has at least one resolved input
    planned = plan_steps(recipe.steps, operators)
    meta = first
    for step in planned:
        meta = step.operator.transform(meta, step.params)
    output_pixels = meta.width * meta.height
    dtype = getattr(recipe.output, "dtype", None)
    output_bytes = output_pixels * len(meta.bands) * _value_bytes(dtype)
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
