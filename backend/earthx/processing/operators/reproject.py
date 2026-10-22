"""``reproject``: a new CRS, pixel size and resampling for the whole raster (adr/0014 §3.4, §5.2, §5.3).

A ``grid`` operator for ``T2`` only (Q6): it computes each block of a new grid from
the previous pass's file in the work directory (approved F3), through a
``WarpedVRT`` read window by window.

**The plan is part of the operator.** The result of a warp depends on the block size
(the core's ``BLOCK_SIZE``), the approximation threshold ``tolerance`` and
``warp_mem_limit`` (§3.4); the number of threads changes nothing. So the two are
constants here, not parameters, and a change to either raises ``op_version`` (E2,
§6.3 row 1): :data:`TOLERANCE` and :data:`WARP_MEM_LIMIT_MB` belong to versions 2 and 3.

**One warp per block (version 2, M4-10b).** A pixel is masked where the warp left
NaN. Version 1 read with ``masked=True``: GDAL then derived the mask from a second
read of the warped band, which did not always agree with the first and masked a
few pixels at the edge of the data that had values (3 per band of 4.3 million at
2048²). The second read cost time and buffers of its own.

**Version 3 (M4-24)** adds ``cubicspline``, ``lanczos``, ``average`` and ``mode``, each
measured against §6.3 (plan M4-24 §7). The block plan and the three methods of
version 2 are unchanged, so version 2 is still accepted for them and gives the same
bytes; only version 3 is listed (Otto, 20.10.2026).

**What the caller has to allow.** ``reprojection`` always (R3); ``interpolation``
for every resampling that makes values the source does not have, all but ``nearest``
and ``mode`` (§5.3, F6). The resampling has no default (B10): the order names it.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Annotated, Literal

import numpy
from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, field_validator
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.errors import CRSError
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from rasterio.windows import Window

from earthx.catalog.registry import LicenseTier
from earthx.processing.errors import UnsupportedRecipe
from earthx.processing.operators.base import BandMeta, Operator, RasterMeta, Requirement, Tier

__all__ = [
    "MAX_SIDE_PX",
    "REPROJECT",
    "REPROJECT_V2",
    "TOLERANCE",
    "WARP_MEM_LIMIT_MB",
    "ReprojectParams",
    "ReprojectParamsV2",
]

#: Approximation threshold of the warp, in source pixels; GDAL's own default and what
#: the measurements of §3.4 used. ``WarpedVRT`` refuses ``0``.
TOLERANCE = 0.125

#: Working memory of one warp, in MB; it steers how GDAL splits a block internally.
WARP_MEM_LIMIT_MB = 64.0

#: Longest side of the target grid. Not a promise of the platform, only a guard
#: against a resolution that would make the plan itself the problem.
MAX_SIDE_PX = 32768

#: Each method with GDAL's resampling, its cost factor relative to band math (§5.5;
#: the four of M4-24 relative to ``bilinear``, plan §7.4) and the panel's one sentence.
#: Since M4-32 each factor carries the statistics pass, +7.7 % measured, rounded up (adr/0014 §15k).
_METHODS = {
    "nearest": (Resampling.nearest, 0.5, "Value of the nearest source pixel; for class data and masks."),
    "bilinear": (Resampling.bilinear, 1.1, "Distance-weighted mean of the 2x2 nearest pixels; for continuous data."),
    "cubic": (Resampling.cubic, 1.2, "Cubic convolution over 4x4 pixels; sharper than bilinear, for continuous data."),
    "cubicspline": (Resampling.cubic_spline, 1.9, "Cubic B-spline over 4x4 pixels; smoothest, for continuous data."),
    "lanczos": (Resampling.lanczos, 2.4, "Lanczos windowed sinc over 6x6 pixels; sharpest, may overshoot at edges."),
    "average": (Resampling.average, 1.3, "Mean of all source pixels per target pixel; for coarsening continuous data."),
    "mode": (Resampling.mode, 1.2, "Most frequent source value per target pixel; for class data."),
}

#: The methods that only ever pick a value of the source, and so need no ``interpolation``.
_PICKING = frozenset({"nearest", "mode"})

_Method = Annotated[
    Literal["nearest", "bilinear", "cubic", "cubicspline", "lanczos", "average", "mode"],
    WithJsonSchema(
        {
            "type": "string",
            "oneOf": [{"const": name, "title": name, "description": text} for name, (_, _, text) in _METHODS.items()],
        }
    ),
]


class ReprojectParams(BaseModel):
    """The panel's form (K8); names follow openEO ``resample_spatial``."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    crs: str = Field(pattern=r"^EPSG:[0-9]{4,6}$", description="Target CRS as an EPSG code, e.g. EPSG:3035.")
    resolution: float = Field(
        gt=0, allow_inf_nan=False, description="Pixel size in the units of the target CRS, square pixels."
    )
    resampling: _Method = Field(
        description="No default: the choice changes the values. Anything but nearest and mode interpolates."
    )
    align: bool = Field(
        default=False, description="Snap the target grid to whole multiples of the resolution in the target CRS."
    )

    @field_validator("crs")
    @classmethod
    def _known_crs(cls, value: str) -> str:
        try:
            CRS.from_user_input(value)
        except CRSError:
            raise ValueError(f"{value} is not a known EPSG code") from None
        return value


class ReprojectParamsV2(ReprojectParams):
    """Version 2: the three methods before M4-24, which version 3 computes the same way."""

    resampling: Literal["nearest", "bilinear", "cubic"] = Field(
        description="No default: the choice changes the values. Anything but nearest interpolates."
    )


def _extra_requirements(params: BaseModel) -> frozenset[str]:
    assert isinstance(params, ReprojectParams)
    return frozenset() if params.resampling in _PICKING else frozenset({"interpolation"})


def _target_grid(meta: RasterMeta, params: ReprojectParams) -> tuple[Affine, int, int]:
    left, bottom, right, top = transform_bounds(CRS.from_user_input(meta.crs), params.crs, *meta.bounds, densify_pts=21)
    size = params.resolution
    if not all(math.isfinite(value) for value in (left, bottom, right, top)):
        raise UnsupportedRecipe("the raster has no finite extent in the target CRS")
    if params.align:
        left, right = math.floor(left / size) * size, math.ceil(right / size) * size
        bottom, top = math.floor(bottom / size) * size, math.ceil(top / size) * size
    width = max(1, math.ceil((right - left) / size))
    height = max(1, math.ceil((top - bottom) / size))
    if max(width, height) > MAX_SIDE_PX:
        raise UnsupportedRecipe(f"the target grid would be {width} x {height} px; the longest side is {MAX_SIDE_PX}")
    return Affine(size, 0, left, 0, -size, top), width, height


def _transform(meta: RasterMeta, params: BaseModel) -> RasterMeta:
    assert isinstance(params, ReprojectParams)
    transform, width, height = _target_grid(meta, params)
    bands = tuple(BandMeta(b.name, b.data_type, b.nodata, b.unit, b.scale, b.offset) for b in meta.bands)
    return RasterMeta(params.crs, transform, width, height, bands, resampled=True)


def _run(source, target: RasterMeta, window: Window, params: BaseModel) -> numpy.ma.MaskedArray:
    """One block of the target grid, read from ``source`` (an open file of the work directory)."""
    assert isinstance(params, ReprojectParams)
    with WarpedVRT(
        source,
        crs=target.crs,
        transform=target.transform,
        width=target.width,
        height=target.height,
        resampling=_METHODS[params.resampling][0],
        tolerance=TOLERANCE,
        warp_mem_limit=WARP_MEM_LIMIT_MB,
        src_nodata=math.nan,
        nodata=math.nan,
    ) as vrt:
        data = vrt.read(window=window)
    return numpy.ma.masked_array(data, mask=numpy.isnan(data))


def _lineage(params: BaseModel) -> str:
    assert isinstance(params, ReprojectParams)
    return f"reprojected to {params.crs} at {params.resolution:g} ({params.resampling})"


REPROJECT = Operator(
    op="reproject",
    op_version=3,
    category="geometry",
    title="Reproject and resample",
    description="Bring the raster into another CRS at a chosen pixel size, with a chosen resampling.",
    citation=None,
    params=ReprojectParams,
    requires=Requirement(
        capabilities=frozenset({"reprojection"}), data_classes=frozenset(), license_tier=LicenseTier.PROCESSING
    ),
    tiers=frozenset({Tier.T2}),
    kind="grid",
    cost_factor=lambda params: _METHODS[params.resampling][1],
    transform=_transform,
    run=_run,
    lineage=_lineage,
    extra_requirements=_extra_requirements,
)

#: Accepted for recipes written before M4-24, not listed (Otto, 20.10.2026).
REPROJECT_V2 = dataclasses.replace(REPROJECT, op_version=2, params=ReprojectParamsV2)
