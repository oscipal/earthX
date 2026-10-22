"""``normalize``: a fixed range of values onto another, linearly (plan M4-18, adr/0014 §15m).

An operator for ``T1`` and ``T2``. Both ranges come from the recipe: no statistic of the scene or the AOI enters
(F5), which is why the tile and the job give the same bytes. A panel may *suggest* the input range from a
statistic; the recipe then holds plain numbers.

Per band, in ``float64``, in this order, each step its own numpy operation::

    (x - in_min) / (in_max - in_min) * (out_max - out_min) + out_min

and with ``clip`` limited to the output range afterwards. Only IEEE-exact operations, no function whose result
depends on the CPU, so the result is bit-stable across machines (R5, §15c). The result is ``float32`` with NaN as
nodata; a pixel is masked where it was masked or the result is not finite (an overflow). One range for all bands
in version 1 (F4).
"""

from __future__ import annotations

import math

import numpy
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rio_tiler.models import ImageData

from earthx.catalog.registry import LicenseTier
from earthx.processing.operators.base import BandMeta, Operator, RasterMeta, Requirement, Tier

__all__ = ["NORMALIZE", "NormalizeParams"]


class NormalizeParams(BaseModel):
    """The panel's form (K8): both ranges and whether to clip, always given (B10)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    in_min: float = Field(allow_inf_nan=False, description="Value that becomes out_min.")
    in_max: float = Field(allow_inf_nan=False, description="Value that becomes out_max; above in_min.")
    out_min: float = Field(allow_inf_nan=False, description="Start of the target range.")
    out_max: float = Field(
        allow_inf_nan=False, description="End of the target range; below out_min reverses the values."
    )
    clip: bool = Field(description="Limit the result to the target range instead of continuing the line.")

    @model_validator(mode="after")
    def _ranges(self) -> NormalizeParams:
        if not self.in_min < self.in_max:
            raise ValueError("in_min is below in_max")
        if self.out_min == self.out_max:
            raise ValueError("out_min and out_max differ")
        if not (math.isfinite(self.in_max - self.in_min) and math.isfinite(self.out_max - self.out_min)):
            raise ValueError("the ranges are too wide")
        return self


def _run(image: ImageData, params: BaseModel) -> ImageData:
    assert isinstance(params, NormalizeParams)
    values = numpy.ma.getdata(image.array).astype("float64")
    mask = numpy.ma.getmaskarray(image.array)
    with numpy.errstate(over="ignore", invalid="ignore"):
        scaled = numpy.subtract(values, params.in_min)
        scaled = numpy.divide(scaled, params.in_max - params.in_min)
        scaled = numpy.multiply(scaled, params.out_max - params.out_min)
        scaled = numpy.add(scaled, params.out_min)
        if params.clip:
            scaled = numpy.clip(scaled, min(params.out_min, params.out_max), max(params.out_min, params.out_max))
        result = scaled.astype("float32")
    mask = mask | ~numpy.isfinite(result)
    data = numpy.ma.MaskedArray(numpy.where(mask, numpy.float32("nan"), result), mask=mask)
    return ImageData(data, bounds=image.bounds, crs=image.crs, band_names=list(image.band_names), nodata=None)


def _transform(meta: RasterMeta, params: BaseModel) -> RasterMeta:
    bands = tuple(BandMeta(name=band.name, data_type="float32", nodata=float("nan")) for band in meta.bands)
    return RasterMeta(meta.crs, meta.transform, meta.width, meta.height, bands, meta.resampled)


def _lineage(params: BaseModel) -> str:
    assert isinstance(params, NormalizeParams)
    clipped = ", clipped" if params.clip else ""
    return (
        f"normalize: [{params.in_min:g}, {params.in_max:g}] to [{params.out_min:g}, {params.out_max:g}]{clipped}"
    )


def _method(params: BaseModel) -> str:
    assert isinstance(params, NormalizeParams)
    outside = (
        "limited to the target range" if params.clip else "continued along the same line"
    )
    return (
        f"Every band was mapped linearly from the range {params.in_min:g} to {params.in_max:g} onto the range "
        f"{params.out_min:g} to {params.out_max:g}, values outside the source range {outside}, "
        "in 32-bit floating point."
    )


NORMALIZE = Operator(
    op="normalize",
    op_version=1,
    category="bands",
    title="Normalize",
    description="Map a fixed range of values linearly onto another range, for all bands alike.",
    citation=None,
    params=NormalizeParams,
    requires=Requirement(
        capabilities=frozenset({"normalization"}), data_classes=frozenset(), license_tier=LicenseTier.PROCESSING
    ),
    tiers=frozenset({Tier.T1, Tier.T2}),
    kind="pixel",
    cost_factor=lambda params: 0.3,
    transform=_transform,
    run=_run,
    lineage=_lineage,
    method=_method,
)
