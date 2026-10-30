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

**Version 2 (NM4-43c)** names the bands it converts (``bands``, always given) and leaves the others of the stock as
they are, so that a raw band that nobody converts can be dropped from the stock (adr/0020 §4, §15a). The
methods (percentiles and the like) come with NM4-11 on the same field.
"""

from __future__ import annotations

import dataclasses
import math

import numpy
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from rio_tiler.models import ImageData

from earthx.catalog.registry import LicenseTier
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators.base import BandMeta, BandUse, Operator, RasterMeta, Requirement, Tier

__all__ = ["NORMALIZE", "NORMALIZE_V2", "NormalizeParams", "NormalizeParamsV2"]

_MAX_BANDS = 256
_MAX_BAND_CHARS = 64


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


class NormalizeParamsV2(NormalizeParams):
    """Version 2: the two ranges and the bands the step converts, always given (B10)."""

    bands: list[str] = Field(
        min_length=1,
        max_length=_MAX_BANDS,
        description="Names of the bands to convert, each once; the others of the stock are left as they are.",
    )

    @field_validator("bands")
    @classmethod
    def _names(cls, value: list[str]) -> list[str]:
        if any(not 1 <= len(name) <= _MAX_BAND_CHARS for name in value):
            raise ValueError(f"a band name has 1 to {_MAX_BAND_CHARS} characters")
        if len({name.casefold() for name in value}) != len(value):
            raise ValueError("bands names each band once, case ignored")
        return value


def _run(image: ImageData, params: BaseModel) -> ImageData:
    assert isinstance(params, NormalizeParams)
    values = numpy.ma.getdata(image.array).astype("float64")
    data = _convert(values, numpy.ma.getmaskarray(image.array), params)
    return ImageData(data, bounds=image.bounds, crs=image.crs, band_names=list(image.band_names), nodata=None)


def _transform(meta: RasterMeta, params: BaseModel) -> RasterMeta:
    bands = tuple(BandMeta(name=band.name, data_type="float32", nodata=float("nan")) for band in meta.bands)
    return RasterMeta(meta.crs, meta.transform, meta.width, meta.height, bands, meta.resampled)


def _convert(values: numpy.ndarray, mask: numpy.ndarray, params: NormalizeParams) -> numpy.ma.MaskedArray:
    """The kernel of both versions: ``values`` mapped onto the target range, as float32, NaN where masked."""
    with numpy.errstate(over="ignore", invalid="ignore"):
        scaled = numpy.subtract(values, params.in_min)
        scaled = numpy.divide(scaled, params.in_max - params.in_min)
        scaled = numpy.multiply(scaled, params.out_max - params.out_min)
        scaled = numpy.add(scaled, params.out_min)
        if params.clip:
            scaled = numpy.clip(scaled, min(params.out_min, params.out_max), max(params.out_min, params.out_max))
        result = scaled.astype("float32")
    mask = mask | ~numpy.isfinite(result)
    return numpy.ma.MaskedArray(numpy.where(mask, numpy.float32("nan"), result), mask=mask)


def _listed(names: list[str], wanted: list[str]) -> list[int]:
    missing = [name for name in wanted if name not in names]
    if missing:
        raise RecipeInvalid(f"normalize names unknown band(s): {', '.join(missing)}; the input has: {', '.join(names)}")
    return [names.index(name) for name in wanted]


def _run_v2(image: ImageData, params: BaseModel) -> ImageData:
    """The stock with the listed bands converted to float32 and the others untouched."""
    assert isinstance(params, NormalizeParamsV2)
    names = list(image.band_names)
    chosen = set(_listed(names, params.bands))
    kept = numpy.ma.getdata(image.array)
    # One array for the stock: the common type holds the converted bands (float32) and every type the sources give.
    dtype = numpy.promote_types(kept.dtype, "float32")
    array = numpy.ma.MaskedArray(kept.astype(dtype, copy=True), mask=numpy.ma.getmaskarray(image.array).copy())
    for index in chosen:
        band = image.array[index]
        converted = _convert(numpy.ma.getdata(band).astype("float64"), numpy.ma.getmaskarray(band), params)
        array[index] = converted
    return ImageData(array, bounds=image.bounds, crs=image.crs, band_names=names, nodata=image.nodata)


def _transform_v2(meta: RasterMeta, params: BaseModel) -> RasterMeta:
    assert isinstance(params, NormalizeParamsV2)
    chosen = set(_listed([band.name for band in meta.bands], params.bands))
    bands = tuple(
        BandMeta(name=band.name, data_type="float32", nodata=float("nan"), resampled=band.resampled)
        if index in chosen
        else band
        for index, band in enumerate(meta.bands)
    )
    return RasterMeta(meta.crs, meta.transform, meta.width, meta.height, bands, meta.resampled)


def _restrict_v2(params: BaseModel, kept: frozenset[str]) -> BaseModel:
    """The step for a stock without the bands nobody needs: it converts the ones of its list that are still there."""
    assert isinstance(params, NormalizeParamsV2)
    return params.model_copy(update={"bands": [name for name in params.bands if name in kept]})


def _bands_used_v2(params: BaseModel) -> BandUse:
    assert isinstance(params, NormalizeParamsV2)
    return BandUse(acts_on=frozenset(params.bands))


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
    stock=False,
)


def _lineage_v2(params: BaseModel) -> str:
    assert isinstance(params, NormalizeParamsV2)
    return f"{_lineage(params)} of {', '.join(params.bands)}"


def _method_v2(params: BaseModel) -> str:
    assert isinstance(params, NormalizeParamsV2)
    outside = "limited to the target range" if params.clip else "continued along the same line"
    return (
        f"The bands {', '.join(params.bands)} were mapped linearly from the range {params.in_min:g} to "
        f"{params.in_max:g} onto the range {params.out_min:g} to {params.out_max:g}, values outside the source "
        f"range {outside}, in 32-bit floating point."
    )


#: Version 2 (NM4-43c): converts the bands it names. Not listed until the panel sends it; the tile runs it since NM4-43d.
NORMALIZE_V2 = dataclasses.replace(
    NORMALIZE,
    op_version=2,
    params=NormalizeParamsV2,
    description="Map a fixed range of values linearly onto another range, for the bands named.",
    transform=_transform_v2,
    run=_run_v2,
    lineage=_lineage_v2,
    method=_method_v2,
    bands_used=_bands_used_v2,
    restrict=_restrict_v2,
    stock=True,
    listed=False,
)
