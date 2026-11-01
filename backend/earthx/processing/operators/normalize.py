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
they are, so that a raw band that nobody converts can be dropped from the stock (adr/0020 §4, §15a).

**Version 3 (NM4-11)** adds ``method`` on the same field: ``linear`` (as before), ``percentile`` (the line through two
percentiles), ``zscore`` and ``robust`` (median and interquartile range). Every method is a line per band, and the
numbers of a statistical one are *in the recipe*, measured before the run over the area by the route of NM4-19
(``measured``, adr/0014 §15 Nachtrag NM4-11): the step stays a pure pixel step, the tile and the job give the same
bytes, and the runner measures nothing. Where the span of a band is 0 the divisor is 1, as in scikit-learn.

**Version 4 (NM4-71)** takes the numbers out of the recipe again, for the job only: the same fields without ``measured``,
and the run measures the bands of a statistical method over the AOI at full resolution, exactly (adr/0014
Nachtrag NM4-71). The step says so with ``measures``; the planner ends the pass before it, the core counts the bands in that
pass, refines the percentiles from the work file it left (:mod:`earthx.processing.statistics`) and hands the step its numbers
(``with_measured``, the internal :class:`MeasuredNormalizeV4`). From there the kernel is version 3's, so version 4 with the
numbers it measured gives the bytes of version 3 with the same numbers; ``linear`` measures nothing and gives those of
versions 1 to 3. Version 3 stays accepted (the tile, old recipes, "⚙" on a result) and is no longer listed.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Mapping
from typing import Any, Literal

import numpy
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from rio_tiler.models import ImageData

from earthx.catalog.registry import LicenseTier
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators.base import BandMeta, BandUse, Operator, RasterMeta, Requirement, Tier

__all__ = [
    "NORMALIZE",
    "NORMALIZE_V2",
    "NORMALIZE_V3",
    "NORMALIZE_V4",
    "MEASURED_PROPERTY",
    "BandValues",
    "Measured",
    "MeasuredNormalizeV4",
    "NormalizeParams",
    "NormalizeParamsV2",
    "NormalizeParamsV3",
    "NormalizeParamsV4",
]

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
        return _checked_names(value)


def _checked_names(value: list[str]) -> list[str]:
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


def _finish(scaled: numpy.ndarray, mask: numpy.ndarray) -> numpy.ma.MaskedArray:
    """``scaled`` as float32 with NaN where it was masked or is not finite (an overflow)."""
    result = scaled.astype("float32")
    mask = mask | ~numpy.isfinite(result)
    return numpy.ma.MaskedArray(numpy.where(mask, numpy.float32("nan"), result), mask=mask)


def _line(
    values: numpy.ndarray,
    mask: numpy.ndarray,
    start: float,
    span: float,
    out_min: float,
    out_max: float,
    clip: bool,
) -> numpy.ma.MaskedArray:
    """``(x - start) / span * (out_max - out_min) + out_min``, as float32, NaN where masked; each step its own numpy operation.

    The kernel of every method that maps a range onto a range: the fixed range of version 1 and 2 (``start`` =
    ``in_min``, ``span`` = ``in_max - in_min``) and the percentiles of version 3. With ``clip`` the result is limited to
    the target range, whichever way round it runs.
    """
    with numpy.errstate(over="ignore", invalid="ignore"):
        scaled = numpy.subtract(values, start)
        scaled = numpy.divide(scaled, span)
        scaled = numpy.multiply(scaled, out_max - out_min)
        scaled = numpy.add(scaled, out_min)
        if clip:
            scaled = numpy.clip(scaled, min(out_min, out_max), max(out_min, out_max))
        return _finish(scaled, mask)


def _centred(values: numpy.ndarray, mask: numpy.ndarray, centre: float, divisor: float) -> numpy.ma.MaskedArray:
    """``(x - centre) / divisor``, as float32, NaN where masked: the z-score and the robust scaling."""
    with numpy.errstate(over="ignore", invalid="ignore"):
        scaled = numpy.divide(numpy.subtract(values, centre), divisor)
        return _finish(scaled, mask)


def _convert(values: numpy.ndarray, mask: numpy.ndarray, params: NormalizeParams) -> numpy.ma.MaskedArray:
    """The kernel of versions 1 and 2: ``values`` mapped onto the target range, as float32, NaN where masked."""
    return _line(
        values,
        mask,
        params.in_min,
        params.in_max - params.in_min,
        params.out_min,
        params.out_max,
        params.clip,
    )


def _listed(names: list[str], wanted: list[str]) -> list[int]:
    missing = [name for name in wanted if name not in names]
    if missing:
        raise RecipeInvalid(f"normalize names unknown band(s): {', '.join(missing)}; the input has: {', '.join(names)}")
    return [names.index(name) for name in wanted]


def _convert_listed(
    image: ImageData,
    wanted: list[str],
    convert: Callable[[str, numpy.ndarray, numpy.ndarray], numpy.ma.MaskedArray],
) -> ImageData:
    """The stock with the listed bands converted to float32 by ``convert`` and the others untouched."""
    names = list(image.band_names)
    chosen = _listed(names, wanted)
    kept = numpy.ma.getdata(image.array)
    # One array for the stock: the common type holds the converted bands (float32) and every type the sources give.
    dtype = numpy.promote_types(kept.dtype, "float32")
    array = numpy.ma.MaskedArray(kept.astype(dtype, copy=True), mask=numpy.ma.getmaskarray(image.array).copy())
    for index in sorted(chosen):
        band = image.array[index]
        array[index] = convert(names[index], numpy.ma.getdata(band).astype("float64"), numpy.ma.getmaskarray(band))
    return ImageData(array, bounds=image.bounds, crs=image.crs, band_names=names, nodata=image.nodata)


def _converted_meta(meta: RasterMeta, wanted: list[str]) -> RasterMeta:
    chosen = set(_listed([band.name for band in meta.bands], wanted))
    bands = tuple(
        BandMeta(name=band.name, data_type="float32", nodata=float("nan"), resampled=band.resampled)
        if index in chosen
        else band
        for index, band in enumerate(meta.bands)
    )
    return RasterMeta(meta.crs, meta.transform, meta.width, meta.height, bands, meta.resampled)


def _run_v2(image: ImageData, params: BaseModel) -> ImageData:
    """The stock with the listed bands converted to float32 and the others untouched."""
    assert isinstance(params, NormalizeParamsV2)
    return _convert_listed(image, params.bands, lambda name, values, mask: _convert(values, mask, params))


def _transform_v2(meta: RasterMeta, params: BaseModel) -> RasterMeta:
    assert isinstance(params, NormalizeParamsV2)
    return _converted_meta(meta, params.bands)


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
    return f"normalize: [{params.in_min:g}, {params.in_max:g}] to [{params.out_min:g}, {params.out_max:g}]{clipped}"


def _method(params: BaseModel) -> str:
    assert isinstance(params, NormalizeParams)
    outside = "limited to the target range" if params.clip else "continued along the same line"
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
    listed=False,
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


#: Version 2 (NM4-43c): converts the bands it names. Accepted, not listed since NM4-11b: the panel sends version 3.
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


# --- Version 3 (NM4-11): the methods -------------------------------------------------------------------------------

Method = Literal["linear", "percentile", "zscore", "robust"]

#: The ends of a percentile stretch the panel offers (plan NM4-11 KE1): 0 and 100 are the minimum and the maximum.
LOW_PERCENTS = (0, 1, 2, 5)
HIGH_PERCENTS = (95, 98, 99, 100)

#: What a measure reports and how many times coarser than the result it read (``factor`` 1 is exact, NM4-19).
_MAX_FACTOR = 10_000

#: Fields of the parameters that belong to a method, and the numbers it needs of every band.
_FIELDS = {
    "linear": ("in_min", "in_max", "out_min", "out_max", "clip"),
    "percentile": ("low", "high", "out_min", "out_max", "clip"),
    "zscore": (),
    "robust": (),
}
_VALUES = {
    "linear": (),
    "percentile": ("p_low", "p_high"),
    "zscore": ("mean", "stddev"),
    "robust": ("p25", "median", "p75"),
}
_ALL_FIELDS = frozenset(name for names in _FIELDS.values() for name in names)
_ALL_VALUES = tuple(dict.fromkeys(name for names in _VALUES.values() for name in names))


class BandValues(BaseModel):
    """The numbers measured for one band; which are given depends on the method (:class:`Measured`)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    p_low: float | None = Field(default=None, allow_inf_nan=False, description="Value at the low percentile.")
    p_high: float | None = Field(default=None, allow_inf_nan=False, description="Value at the high percentile.")
    mean: float | None = Field(default=None, allow_inf_nan=False, description="Mean of the band.")
    stddev: float | None = Field(default=None, allow_inf_nan=False, description="Population standard deviation.")
    p25: float | None = Field(default=None, allow_inf_nan=False, description="First quartile.")
    median: float | None = Field(default=None, allow_inf_nan=False, description="Median.")
    p75: float | None = Field(default=None, allow_inf_nan=False, description="Third quartile.")


class Measured(BaseModel):
    """What the route of NM4-19 measured before the run, per band, and how coarsely (``factor`` 1 is exact)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    factor: int = Field(
        ge=1, le=_MAX_FACTOR, description="1 when read at the resolution of the result, else how many times coarser."
    )
    bands: dict[str, BandValues] = Field(min_length=1, max_length=_MAX_BANDS, description="Numbers by band name.")


class _MethodFields(BaseModel):
    """``method``, the ``bands`` it converts, and the fields of that method, all given (B10): versions 3 and 4 alike.

    One model for all four methods; the fields of the others stay out (:meth:`_check_fields`), so a recipe says exactly
    what its method needs. The numbers a statistical method measures are not here: version 3 carries them in the recipe
    (``measured``), version 4 measures them in the run.
    """

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    method: Method = Field(
        description="linear: a fixed range; percentile: two percentiles; zscore; robust: median and IQR."
    )
    bands: list[str] = Field(
        min_length=1,
        max_length=_MAX_BANDS,
        description="Names of the bands to convert, each once; the others of the stock are left as they are.",
    )
    in_min: float | None = Field(default=None, allow_inf_nan=False, description="linear: value that becomes out_min.")
    in_max: float | None = Field(default=None, allow_inf_nan=False, description="linear: value that becomes out_max.")
    low: Literal[0, 1, 2, 5] | None = Field(default=None, description="percentile: percent that becomes out_min.")
    high: Literal[95, 98, 99, 100] | None = Field(default=None, description="percentile: percent that becomes out_max.")
    out_min: float | None = Field(
        default=None, allow_inf_nan=False, description="linear, percentile: target range start."
    )
    out_max: float | None = Field(
        default=None, allow_inf_nan=False, description="linear, percentile: target range end; below out_min reverses."
    )
    clip: bool | None = Field(default=None, description="linear, percentile: limit the result to the target range.")

    @field_validator("bands")
    @classmethod
    def _names(cls, value: list[str]) -> list[str]:
        return _checked_names(value)

    def _check_fields(self) -> None:
        given = {name for name in _ALL_FIELDS if getattr(self, name) is not None}
        wanted = set(_FIELDS[self.method])
        if missing := sorted(wanted - given):
            raise ValueError(f"method {self.method} needs {', '.join(missing)}")
        if foreign := sorted(given - wanted):
            raise ValueError(f"method {self.method} takes no {', '.join(foreign)}")

    def _check_ranges(self) -> None:
        if self.method in ("linear", "percentile"):
            assert self.out_min is not None and self.out_max is not None
            if self.out_min == self.out_max:
                raise ValueError("out_min and out_max differ")
            if not math.isfinite(self.out_max - self.out_min):
                raise ValueError("the ranges are too wide")
        if self.method == "linear":
            assert self.in_min is not None and self.in_max is not None
            if not self.in_min < self.in_max:
                raise ValueError("in_min is below in_max")
            if not math.isfinite(self.in_max - self.in_min):
                raise ValueError("the ranges are too wide")

    def _check_measured(self, measured: Measured) -> None:
        if set(measured.bands) != set(self.bands):
            raise ValueError("measured names exactly the bands of the step")
        wanted = _VALUES[self.method]
        for name, values in measured.bands.items():
            for field in _ALL_VALUES:
                value = getattr(values, field)
                if field in wanted and value is None:
                    raise ValueError(f"measured of {name} needs {field} for method {self.method}")
                if field not in wanted and value is not None:
                    raise ValueError(f"measured of {name} takes no {field} for method {self.method}")
            if self.method == "percentile":
                assert values.p_low is not None and values.p_high is not None
                if not values.p_low <= values.p_high:
                    raise ValueError(f"measured of {name}: p_low is at most p_high")
                if not math.isfinite(values.p_high - values.p_low):
                    raise ValueError(f"measured of {name}: the range is too wide")
            elif self.method == "zscore":
                assert values.stddev is not None
                if values.stddev < 0:
                    raise ValueError(f"measured of {name}: stddev is not negative")
            else:
                assert values.p25 is not None and values.median is not None and values.p75 is not None
                if not values.p25 <= values.median <= values.p75:
                    raise ValueError(f"measured of {name}: p25 is at most the median, which is at most p75")
                if not math.isfinite(values.p75 - values.p25):
                    raise ValueError(f"measured of {name}: the range is too wide")


class NormalizeParamsV3(_MethodFields):
    """The step of version 3: ``method``, the ``bands`` it converts, and the fields of that method, all given (B10).

    One model for all four methods; the fields of the others stay out (:meth:`_method`), so a recipe says exactly
    what its method needs.
    """

    measured: Measured | None = Field(
        default=None, description="percentile, zscore, robust: the numbers of each band, measured before the run."
    )

    @model_validator(mode="after")
    def _method(self) -> NormalizeParamsV3:
        self._check_fields()
        if (self.measured is None) != (not _VALUES[self.method]):
            raise ValueError(
                f"method {self.method} takes no measured numbers"
                if self.measured is not None
                else f"method {self.method} needs measured numbers"
            )
        self._check_ranges()
        if self.measured is not None:
            self._check_measured(self.measured)
        return self


def _divisor(span: float) -> float:
    """A span of 0 (the band is constant over the area) divides by 1, as scikit-learn's scalers do (plan KE10)."""
    return span if span != 0 else 1.0


def _kernel(
    params: _MethodFields, measured: Measured | None
) -> Callable[[str, numpy.ndarray, numpy.ndarray], numpy.ma.MaskedArray]:
    """The conversion of one named band: ``(name, values as float64, mask) → float32 with NaN``.

    ``measured`` holds the numbers of a statistical method: those of the recipe (version 3) or those the run measured
    (version 4). The kernel is the same for both, which is why version 4 gives the bytes of version 3 with its numbers.
    """
    method = params.method

    def kernel(name: str, values: numpy.ndarray, mask: numpy.ndarray) -> numpy.ma.MaskedArray:
        if method == "linear":
            assert params.in_min is not None and params.in_max is not None
            assert params.out_min is not None and params.out_max is not None and params.clip is not None
            return _line(
                values, mask, params.in_min, params.in_max - params.in_min, params.out_min, params.out_max, params.clip
            )
        assert measured is not None
        numbers = measured.bands[name]
        if method == "percentile":
            assert numbers.p_low is not None and numbers.p_high is not None
            assert params.out_min is not None and params.out_max is not None and params.clip is not None
            span = _divisor(numbers.p_high - numbers.p_low)
            return _line(values, mask, numbers.p_low, span, params.out_min, params.out_max, params.clip)
        if method == "zscore":
            assert numbers.mean is not None and numbers.stddev is not None
            return _centred(values, mask, numbers.mean, _divisor(numbers.stddev))
        assert numbers.p25 is not None and numbers.median is not None and numbers.p75 is not None
        return _centred(values, mask, numbers.median, _divisor(numbers.p75 - numbers.p25))

    return kernel


def _run_v3(image: ImageData, params: BaseModel) -> ImageData:
    """The stock with the named bands converted by the method and the others untouched."""
    assert isinstance(params, NormalizeParamsV3)
    return _convert_listed(image, params.bands, _kernel(params, params.measured))


def _transform_v3(meta: RasterMeta, params: BaseModel) -> RasterMeta:
    assert isinstance(params, _MethodFields)
    return _converted_meta(meta, params.bands)


def _restrict_v3(params: BaseModel, kept: frozenset[str]) -> BaseModel:
    """The step for a stock without the bands nobody needs: the ones of its list that are still there, with their numbers."""
    assert isinstance(params, NormalizeParamsV3)
    bands = [name for name in params.bands if name in kept]
    measured = (
        None
        if params.measured is None
        else params.measured.model_copy(update={"bands": {name: params.measured.bands[name] for name in bands}})
    )
    return params.model_copy(update={"bands": bands, "measured": measured})


def _bands_used_v3(params: BaseModel) -> BandUse:
    assert isinstance(params, _MethodFields)
    return BandUse(acts_on=frozenset(params.bands))


def _clipped(params: _MethodFields) -> str:
    return "limited to the target range" if params.clip else "continued along the same line"


def _how_measured(params: NormalizeParamsV3) -> str:
    assert params.measured is not None
    factor = params.measured.factor
    coarser = "" if factor == 1 else f", on a read {factor} times coarser than the result"
    return f"as measured before the run{coarser}"


def _per_band(params: _MethodFields, measured: Measured, show: Callable[[BandValues], str]) -> str:
    return "; ".join(f"{name}: {show(measured.bands[name])}" for name in params.bands)


def _ordinal(percent: int) -> str:
    """``1st``, ``2nd``, ``5th``, ``95th`` and so on, for the percents a stretch offers."""
    if percent % 100 in (11, 12, 13):
        return f"{percent}th"
    return f"{percent}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(percent % 10, 'th') }"


def _number(value: float | None) -> str:
    assert value is not None
    return f"{value:g}"


def _lineage_v3(params: BaseModel) -> str:
    assert isinstance(params, _MethodFields)
    bands = ", ".join(params.bands)
    if params.method == "linear":
        assert params.in_min is not None and params.in_max is not None
        assert params.out_min is not None and params.out_max is not None
        clipped = ", clipped" if params.clip else ""
        return f"normalize: [{params.in_min:g}, {params.in_max:g}] to [{params.out_min:g}, {params.out_max:g}]{clipped} of {bands}"
    if params.method == "percentile":
        assert params.out_min is not None and params.out_max is not None
        clipped = ", clipped" if params.clip else ""
        return f"normalize: percentiles {params.low} to {params.high} to [{params.out_min:g}, {params.out_max:g}]{clipped} of {bands}"
    return f"normalize: {params.method} of {bands}"


def _method_text(params: _MethodFields, measured: Measured | None, how: str) -> str:
    """The methods sentence of version 3 and 4: ``how`` says where the numbers come from, ``measured`` shows them.

    Without ``measured`` (version 4 as the recipe has it, before the run) the numbers are left out; the
    constant-band sentence needs them and is left out too.
    """
    bands = ", ".join(params.bands)
    noun = "band" if len(params.bands) == 1 else "bands"
    verb = "was" if len(params.bands) == 1 else "were"
    if params.method == "linear":
        assert params.in_min is not None and params.in_max is not None
        assert params.out_min is not None and params.out_max is not None
        return (
            f"The {noun} {bands} {verb} mapped linearly from the range {params.in_min:g} to {params.in_max:g} onto "
            f"the range {params.out_min:g} to {params.out_max:g}, values outside the source range {_clipped(params)}, "
            "in 32-bit floating point."
        )

    def shown(show: Callable[[BandValues], str]) -> str:
        return how if measured is None else f"{_per_band(params, measured, show)}; {how}"

    if params.method == "percentile":
        assert params.out_min is not None and params.out_max is not None
        assert params.low is not None and params.high is not None
        where = shown(lambda v: f"{_number(v.p_low)} to {_number(v.p_high)}")
        return (
            f"The {noun} {bands} {verb} stretched from the {_ordinal(params.low)} to the {_ordinal(params.high)} percentile "
            f"({where}) onto the range {params.out_min:g} to {params.out_max:g}, values outside "
            f"{_clipped(params)}, in 32-bit floating point."
        )
    if params.method == "zscore":
        where = shown(lambda v: f"mean {_number(v.mean)}, standard deviation {_number(v.stddev)}")
        text = (
            f"The {noun} {bands} {verb} standardised, (x - mean) / standard deviation, with the mean and the population "
            f"standard deviation of the {noun} ({where}), in 32-bit floating point."
        )
        if measured is not None and any(v.stddev == 0 for v in measured.bands.values()):
            text += " A band that is constant (standard deviation 0) was only centred."
        return text
    where = shown(lambda v: f"median {_number(v.median)}, interquartile range {_number(_iqr(v))}")
    text = (
        f"The {noun} {bands} {verb} scaled robustly, (x - median) / interquartile range, with the median and the "
        f"interquartile range (75th minus 25th percentile) of the {noun} ({where}), in 32-bit floating point."
    )
    if measured is not None and any(_iqr(v) == 0 for v in measured.bands.values()):
        text += " A band that is constant (interquartile range 0) was only centred."
    return text


def _method_v3(params: BaseModel) -> str:
    assert isinstance(params, NormalizeParamsV3)
    return _method_text(params, params.measured, _how_measured(params) if params.measured else "")


def _iqr(values: BandValues) -> float:
    assert values.p75 is not None and values.p25 is not None
    return values.p75 - values.p25


#: Version 3 (NM4-11): the methods, with the numbers in the recipe. Accepted since NM4-71, no longer listed: the panel sends
#: version 4 for a job; this is the form of the tile, of recipes written before and of "⚙" on a result.
NORMALIZE_V3 = dataclasses.replace(
    NORMALIZE_V2,
    op_version=3,
    params=NormalizeParamsV3,
    tiers=frozenset({Tier.T1, Tier.T2}),
    description=(
        "Rescale the values of the bands named: a fixed range, two percentiles, a z-score, or the median and the "
        "interquartile range."
    ),
    transform=_transform_v3,
    run=_run_v3,
    lineage=_lineage_v3,
    method=_method_v3,
    bands_used=_bands_used_v3,
    restrict=_restrict_v3,
    listed=False,
)


# --- Version 4 (NM4-71): measured in the run ----------------------------------------------------------------------

#: What the methods text says of the numbers of version 4 (plan NM4-71 KE4).
_MEASURED_IN_THE_RUN = "measured in the run over the AOI at full resolution"

#: The property of the result that holds the numbers each measuring step used (adr/0014 Nachtrag NM4-71).
MEASURED_PROPERTY = "earthx:normalize"


class NormalizeParamsV4(_MethodFields):
    """The step of version 4: ``method``, the ``bands`` it converts, and the fields of that method, all given (B10).

    The fields of version 3 without ``measured``. A statistical method (``percentile``, ``zscore``, ``robust``) is not
    given its numbers: the job counts the bands over the AOI at full resolution and takes the exact numbers
    from that count (NM4-71). ``linear`` measures nothing. Only a job runs this version.
    """

    @model_validator(mode="after")
    def _method(self) -> NormalizeParamsV4:
        self._check_fields()
        self._check_ranges()
        return self


class MeasuredNormalizeV4(NormalizeParamsV4):
    """Version 4 after the run measured it: the same step with its numbers (``factor`` 1, full resolution).

    Internal: no operator names this model, so no recipe can carry it. :func:`_with_measured` makes it; the kernel, the
    lineage and the methods text read it.
    """

    measured: Measured

    @model_validator(mode="after")
    def _numbers(self) -> MeasuredNormalizeV4:
        if self.method == "linear":
            raise ValueError("method linear measures nothing")
        if self.measured.factor != 1:
            raise ValueError("version 4 measures at full resolution")
        self._check_measured(self.measured)
        return self


def _measures_v4(params: BaseModel) -> frozenset[str]:
    assert isinstance(params, NormalizeParamsV4)
    return frozenset() if params.method == "linear" else frozenset(params.bands)


def _measure_percents_v4(params: BaseModel) -> tuple[int, ...]:
    """The percents the method needs exactly; the minimum and the maximum (0 and 100) come with the count."""
    assert isinstance(params, NormalizeParamsV4)
    if params.method == "percentile":
        return tuple(percent for percent in (params.low, params.high) if percent is not None and 0 < percent < 100)
    return (25, 50, 75) if params.method == "robust" else ()


def _band_values(method: str, low: int | None, high: int | None, statistics: Mapping[str, Any]) -> BandValues | str:
    """The numbers of one band from its statistics, or why it has none (KE8)."""
    if not statistics.get("count"):
        return "has no valid value over the AOI"
    if method == "percentile":
        # The ends of the range are the minimum and the maximum as counted, which may be -0.0: never in a report.
        p_low = statistics["minimum"] if low == 0 else statistics[f"percentile_{low}"]
        p_high = statistics["maximum"] if high == 100 else statistics[f"percentile_{high}"]
        return BandValues(p_low=float(p_low) + 0.0, p_high=float(p_high) + 0.0)
    if method == "zscore":
        if "stddev" not in statistics:  # not finite: the values are too large to have a spread
            return "has no finite standard deviation over the AOI"
        return BandValues(mean=float(statistics["mean"]), stddev=float(statistics["stddev"]))
    return BandValues(
        p25=float(statistics["percentile_25"]),
        median=float(statistics["percentile_50"]),
        p75=float(statistics["percentile_75"]),
    )


def _with_measured(params: BaseModel, numbers: Mapping[str, Mapping[str, Any]]) -> BaseModel:
    """The step with the numbers the run measured over the AOI; :class:`RecipeInvalid` for a band without them (KE8)."""
    assert isinstance(params, NormalizeParamsV4)
    values = {}
    for name in params.bands:
        found = _band_values(params.method, params.low, params.high, numbers[name])
        if isinstance(found, str):
            raise RecipeInvalid(f"normalize: band {name} {found}")
        values[name] = found
    try:
        return MeasuredNormalizeV4(
            **params.model_dump(),
            measured=Measured(factor=1, bands=values),
        )
    except ValueError as error:
        raise RecipeInvalid(f"normalize: the numbers measured over the AOI do not fit the step: {error}") from None


def _measured_report(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, MeasuredNormalizeV4)
    wanted = _VALUES[params.method]
    return {
        "method": params.method,
        "bands": {
            name: {field: getattr(params.measured.bands[name], field) for field in wanted} for name in params.bands
        },
    }


def _run_v4(image: ImageData, params: BaseModel) -> ImageData:
    """The stock with the named bands converted. A statistical method runs only with its numbers (:func:`_with_measured`)."""
    assert isinstance(params, NormalizeParamsV4)
    measured = params.measured if isinstance(params, MeasuredNormalizeV4) else None
    if measured is None and params.method != "linear":
        raise RuntimeError("normalize runs a statistical method only with the numbers measured in the run")
    return _convert_listed(image, params.bands, _kernel(params, measured))


def _restrict_v4(params: BaseModel, kept: frozenset[str]) -> BaseModel:
    """The step for a stock without the bands nobody needs; it has no numbers yet, the run measures what is left."""
    assert isinstance(params, NormalizeParamsV4) and not isinstance(params, MeasuredNormalizeV4)
    return params.model_copy(update={"bands": [name for name in params.bands if name in kept]})


def _method_v4(params: BaseModel) -> str:
    """The sentence of the recipe, which holds no numbers; the numbers are in ``earthx:normalize`` of the result."""
    assert isinstance(params, NormalizeParamsV4)
    measured = params.measured if isinstance(params, MeasuredNormalizeV4) else None
    return _method_text(params, measured, _MEASURED_IN_THE_RUN)


#: Version 4 (NM4-71): the numbers of a statistical method are measured in the run, exactly, over the AOI at full resolution
#: (the raster of the pass before the step). A job only (``T2``); ``linear`` is version 3's, bit for bit, and measures nothing.
NORMALIZE_V4 = dataclasses.replace(
    NORMALIZE_V3,
    op_version=4,
    params=NormalizeParamsV4,
    tiers=frozenset({Tier.T2}),
    description=(
        "Rescale the values of the bands named: a fixed range, two percentiles, a z-score, or the median and the "
        "interquartile range. The job measures the numbers of the last three exactly over the AOI."
    ),
    run=_run_v4,
    method=_method_v4,
    restrict=_restrict_v4,
    measures=_measures_v4,
    measure_percents=_measure_percents_v4,
    with_measured=_with_measured,
    measured_report=_measured_report,
    listed=True,
)
