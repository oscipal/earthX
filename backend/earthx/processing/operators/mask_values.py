"""``mask_values``: hide the pixels where one band holds a value the recipe names (DS-06, adr/0014 §15 Nachtrag DS-06).

An operator for ``T1`` and ``T2``, a sibling of ``mask``: that one hides the classes of a classification layer, this
one hides by the value of any band of the stock — a band of the data (``height > 2000``) or the result of an earlier
step (``NDVI < 0.2``). Like ``mask`` it hides in **every** band of the stock, the band it looks at included, and it adds
none (adr/0020 §12), so the planner treats it like ``mask`` version 2: it reads the band, and the band stays where it was.

The condition is one of four, on the values as the stock holds them:

* ``lt``: ``x < v`` and ``gt``: ``x > v``, one value;
* ``between``: ``lo <= x <= hi``, both ends included (as openEO's ``between``), ``lo < hi``;
* ``eq``: ``x`` is one of the values, ascending and each once (one mask, one way to write it, K3).

**The comparison is made in the data type of the band.** A floating-point band gets the values rounded to its own type
first, so that ``NDVI`` read as ``float32`` 0.2 is equal to 0.2, which is what the statistics and the tooltips show; in
``float64`` it would not be. An integer band is compared exactly, in ``float64`` (every integer of up to 32 bits is exact
there). A value that does not fit the type of the band (``float32``) is refused with the parameters.

A pixel is hidden where the condition holds **or** the band has no value there (masked, or NaN): a pixel the condition
cannot judge does not stay as a valid one (DS-06 question 4; ``mask`` does the same, M4-18 F3).

Nothing here is a float computation, only comparisons and combinations of masks, which is why the result is bit-stable
across machines (§15c) and the tile and the job give the same bytes.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

import numpy
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from rio_tiler.models import ImageData

from earthx.catalog.registry import LicenseTier
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators.base import BandUse, Operator, RasterMeta, Requirement, Tier

__all__ = ["MASK_VALUES", "MAX_VALUES", "MaskValuesParams"]

MAX_VALUES = 64

_MAX_BAND_CHARS = 64

#: The largest value that stays finite in ``float32``; a bigger one would round to infinity in a band of that type.
_MAX_MAGNITUDE = float(numpy.finfo("float32").max)

#: How many numbers each condition takes (``eq`` takes 1 to :data:`MAX_VALUES`).
_COUNTS = {"lt": 1, "gt": 1, "between": 2}

Condition = Literal["lt", "gt", "between", "eq"]


class MaskValuesParams(BaseModel):
    """The panel's form (K8): the band to look at, the condition and its numbers, all always given (B10)."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    # No `pattern` here: the Rust `regex` of pydantic and ECMA-262 read it differently (§5.1).
    band: str = Field(
        min_length=1,
        max_length=_MAX_BAND_CHARS,
        description="Name of the band whose values decide: a band of the data or the result of an earlier step.",
    )
    condition: Condition = Field(
        description=(
            "lt: hide where the band is below the value. gt: above the value. between: from the first value to the "
            "second, both included. eq: equal to one of the values."
        )
    )
    values: list[Annotated[float, Field(allow_inf_nan=False, ge=-_MAX_MAGNITUDE, le=_MAX_MAGNITUDE)]] = Field(
        min_length=1,
        max_length=MAX_VALUES,
        description=(
            "The numbers of the condition, in physical values: one for lt and gt, two for between (low, high), "
            "one to 64 for eq (ascending, each once). Compared in the data type of the band."
        ),
    )

    @field_validator("band")
    @classmethod
    def _printable(cls, value: str) -> str:
        if not all("!" <= char <= "~" for char in value):
            raise ValueError("band is printable ASCII without spaces")
        return value

    @model_validator(mode="after")
    def _fits_the_condition(self) -> MaskValuesParams:
        wanted = _COUNTS.get(self.condition)
        if wanted is not None and len(self.values) != wanted:
            raise ValueError(f"values: {self.condition} takes {wanted} number{'s' if wanted > 1 else ''}")
        if self.condition == "between" and not self.values[0] < self.values[1]:
            raise ValueError("values: between takes the low end first, and it is below the high end")
        if self.condition == "eq" and self.values != sorted(set(self.values)):
            # One mask, one way to write it: two orders would be two recipes with two hashes (K3).
            raise ValueError("values: eq lists them ascending, each value once")
        return self


def _index(names: list[str], band: str) -> int:
    if band not in names:
        raise RecipeInvalid(f"mask_values band {band!r} is not among the bands: {', '.join(names)}")
    return names.index(band)


def _hits(data: numpy.ndarray, params: MaskValuesParams) -> numpy.ndarray:
    """Where the condition holds, comparing in the data type of the band (see the module docstring)."""
    kind = data.dtype.kind
    if kind == "f":
        values = numpy.asarray(params.values, dtype=data.dtype)
    elif kind in "iu":
        values = numpy.asarray(params.values, dtype="float64")
    else:
        raise RecipeInvalid(f"mask_values compares numbers; the band holds {data.dtype}")
    if params.condition == "lt":
        return data < values[0]
    if params.condition == "gt":
        return data > values[0]
    if params.condition == "between":
        return (data >= values[0]) & (data <= values[1])
    return numpy.isin(data, values)


def _run(image: ImageData, params: BaseModel) -> ImageData:
    """Every band of the stock, the one looked at included, masked where it meets the condition or has no value."""
    assert isinstance(params, MaskValuesParams)
    names = list(image.band_names)
    layer = image.array[_index(names, params.band)]
    data = numpy.ma.getdata(layer)
    hidden = _hits(data, params) | numpy.ma.getmaskarray(layer)
    if data.dtype.kind == "f":
        hidden |= numpy.isnan(data)
    array = numpy.ma.MaskedArray(
        numpy.ma.getdata(image.array), mask=numpy.ma.getmaskarray(image.array) | hidden[None]
    )
    return ImageData(array, bounds=image.bounds, crs=image.crs, band_names=names, nodata=image.nodata)


def _transform(meta: RasterMeta, params: BaseModel) -> RasterMeta:
    """The same bands; also the check, before any block is read, that the band is there."""
    assert isinstance(params, MaskValuesParams)
    _index([band.name for band in meta.bands], params.band)
    return meta


def _bands_used(params: BaseModel) -> BandUse:
    assert isinstance(params, MaskValuesParams)
    return BandUse(reads=frozenset({params.band}))


def _number(value: float) -> str:
    """The shortest text that reads back as the same number, without ``.0`` on a whole one."""
    return str(int(value)) if value == int(value) and abs(value) < 1e15 else repr(value)


def _numbers(values: list[float]) -> str:
    return ", ".join(map(_number, values))


_SYMBOL = {"lt": "<", "gt": ">"}


def _lineage(params: BaseModel) -> str:
    assert isinstance(params, MaskValuesParams)
    if params.condition in _SYMBOL:
        return f"mask values: {params.band} {_SYMBOL[params.condition]} {_number(params.values[0])}"
    if params.condition == "between":
        return f"mask values: {params.band} from {_number(params.values[0])} to {_number(params.values[1])}"
    return f"mask values: {params.band} = {_numbers(params.values)}"


def _method(params: BaseModel) -> str:
    assert isinstance(params, MaskValuesParams)
    first = _number(params.values[0])
    if params.condition == "lt":
        what = f"below {first}"
    elif params.condition == "gt":
        what = f"above {first}"
    elif params.condition == "between":
        what = f"between {first} and {_number(params.values[1])} (both included)"
    else:
        what = f"equal to {_numbers(params.values)}"
    return f"Pixels were hidden in every band where {params.band} was {what} or had no value."


def _properties(params: BaseModel) -> dict[str, Any]:
    assert isinstance(params, MaskValuesParams)
    return {
        "earthx:mask_values": {"band": params.band, "condition": params.condition, "values": list(params.values)}
    }


MASK_VALUES = Operator(
    op="mask_values",
    op_version=1,
    category="quality",
    title="Mask by value",
    description="Hide the pixels where a band is below, above, between or equal to the values given.",
    citation=None,
    params=MaskValuesParams,
    requires=Requirement(
        capabilities=frozenset({"value_masking"}), data_classes=frozenset(), license_tier=LicenseTier.PROCESSING
    ),
    tiers=frozenset({Tier.T1, Tier.T2}),
    kind="pixel",
    # Measured like mask (adr/0014 §15m): 0.7 to 1.8 ms on a block of 1024², under mask's 2.8 ms; the same factor.
    cost_factor=lambda params: 0.2,
    transform=_transform,
    run=_run,
    lineage=_lineage,
    method=_method,
    properties=_properties,
    bands_used=_bands_used,
    # Accepted by `api`, the tile and the runner, but not offered until the panel sends it (DS-06b flips it, as NM4-11b does
    # for normalize version 3): a listed operator the panel cannot build a form for would show as "not supported".
    listed=False,
)
