"""``sar_db``: a band of radar backscatter in decibels, added to the bands (DS-05a, adr/0030 F2, §5.2.1).

``20·log10`` of an amplitude, ``10·log10`` of an intensity, for whole numbers from 1 to 65 535 (the digital numbers of
Sentinel-1 GRD) through a table. ``log10`` of numpy or numexpr differs in the last bit between machines (adr/0014
§15c), the table does not: each entry is the value Python's ``decimal`` gives, rounded to ``float32`` (:func:`db_table`),
so the tile, the job and the runner agree to the bit on any machine. An intensity takes half the entry, which in
``float32`` is exact. 0 is no data at GRD and has no logarithm: it is left empty.

Whole numbers only (DS-05a A2): a value with a fraction, below 0 or above 65 535 refuses the step. The check is on the
values of each block, not on the type of the band, because the tile does not know the types of the file and a stock
that holds a ``float32`` band holds every band as ``float32``. dB of floating point values (after a filter or a
calibration) comes later with a tolerance of its own (adr/0030 F2).
"""

from __future__ import annotations

import decimal
from functools import lru_cache
from typing import Any, Literal

import numpy
from pydantic import BaseModel, ConfigDict, Field, field_validator
from rio_tiler.models import ImageData

from earthx.catalog.registry import DatasetConfig, LicenseTier, Look
from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators.band_math import MAX_NAME_CHARS, check_name
from earthx.processing.operators.base import BandMeta, BandUse, Looks, Operator, RasterMeta, Requirement, Tier

__all__ = ["DB_UNIT", "SAR_DB", "SarDbParams", "db_table", "exact_db_table"]

#: The unit of the band the step adds.
DB_UNIT = "dB"
#: The largest whole number the table holds: the digital numbers of a ``uint16`` file.
MAX_NUMBER = 65535

_FACTORS = {"amplitude": 20, "intensity": 10}
# A float64 value this close, relatively, to the middle between two float32 numbers is taken again with decimal: numpy's
# log10 is off by far less (about 1e-16), so every other value rounds to the float32 that decimal's value rounds to.
_MARGIN = 1e-12
_DECIMAL = decimal.Context(prec=40)


class SarDbParams(BaseModel):
    """The panel's form (K8): the band in digital numbers, what it measures and the name of the band in dB."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    bands: list[str] = Field(min_length=1, max_length=1, description="The band of uncalibrated digital numbers (DN).")
    quantity: Literal["amplitude", "intensity"] = Field(
        description="What the band measures: 20·log10 of an amplitude, 10·log10 of an intensity."
    )
    name: str = Field(
        min_length=1,
        max_length=MAX_NAME_CHARS,
        description="Name of the new band: a letter, then letters, digits or _; free in the data and the other results.",
    )

    @field_validator("name")
    @classmethod
    def _free_name(cls, value: str) -> str:
        check_name(value)
        return value


def _params(params: BaseModel) -> SarDbParams:
    assert isinstance(params, SarDbParams)
    return params


def _exact(number: int) -> numpy.float32:
    return numpy.float32(float(_DECIMAL.multiply(20, _DECIMAL.log10(decimal.Decimal(number)))))


def exact_db_table() -> numpy.ndarray:
    """``20·log10(n)`` for ``n`` from 0 to 65 535, every entry with ``decimal`` (2 to 3 s); entry 0 is NaN. For the tests."""
    table = numpy.full(MAX_NUMBER + 1, numpy.nan, dtype="float32")
    table[1:] = [_exact(number) for number in range(1, MAX_NUMBER + 1)]
    return table


@lru_cache(maxsize=1)
def db_table() -> numpy.ndarray:
    """:func:`exact_db_table` in milliseconds: numpy's values, and decimal's where a float32 rounding could differ."""
    numbers = numpy.arange(1, MAX_NUMBER + 1, dtype="float64")
    values = 20 * numpy.log10(numbers)
    low, high = (values * (1 - _MARGIN)).astype("float32"), (values * (1 + _MARGIN)).astype("float32")
    table = numpy.full(MAX_NUMBER + 1, numpy.nan, dtype="float32")
    table[1:] = low
    for at in numpy.flatnonzero(low != high):
        table[at + 1] = _exact(int(at) + 1)
    table.setflags(write=False)
    return table


def _whole_numbers(band: numpy.ma.MaskedArray, name: str) -> numpy.ndarray:
    """The values of ``band`` as indices into the table, 0 where masked; refuses any other than whole numbers 0 to 65 535."""
    values = numpy.ma.getdata(band)
    valid = ~numpy.ma.getmaskarray(band)
    if values.dtype.kind == "u" and values.dtype.itemsize <= 2:
        return numpy.where(valid, values, 0).astype("intp")
    taken = values[valid]
    if taken.size and not (
        numpy.all(numpy.isfinite(taken))
        and numpy.all(taken >= 0)
        and numpy.all(taken <= MAX_NUMBER)
        and numpy.all(taken == numpy.floor(taken))
    ):
        raise RecipeInvalid(f"sar_db reads whole numbers from 0 to {MAX_NUMBER} (digital numbers); {name} holds others")
    return numpy.where(valid, values, 0).astype("intp")


def _run(image: ImageData, params: BaseModel) -> ImageData:
    """The stock and one band more, in dB; the bands that were there are the very same values."""
    step = _params(params)
    names = list(image.band_names)
    if step.bands[0] not in names:
        raise RecipeInvalid(f"sar_db reads {step.bands[0]}, which the input does not have: {', '.join(names)}")
    numbers = _whole_numbers(image.array[names.index(step.bands[0])], step.bands[0])
    values = db_table()[numbers]
    if step.quantity == "intensity":
        values = values / numpy.float32(2)
    added = numpy.ma.MaskedArray(values[None], mask=numpy.isnan(values)[None])
    stock = numpy.ma.concatenate([image.array, added.astype(numpy.promote_types(image.array.dtype, "float32"))])
    return ImageData(stock, bounds=image.bounds, crs=image.crs, band_names=[*names, step.name], nodata=image.nodata)


def _transform(meta: RasterMeta, params: BaseModel) -> RasterMeta:
    """The bands and one more in dB; also the check, before any block is read, that the band is there and the name free."""
    step = _params(params)
    bands = {band.name: band for band in meta.bands}
    source = bands.get(step.bands[0])
    if source is None:
        raise RecipeInvalid(f"sar_db reads {step.bands[0]}, which the input does not have: {', '.join(bands)}")
    if step.name.casefold() in {name.casefold() for name in bands}:
        raise RecipeInvalid(f"{step.name} is used twice")
    band = BandMeta(name=step.name, data_type="float32", nodata=float("nan"), unit=DB_UNIT, resampled=source.resampled)
    return RasterMeta(meta.crs, meta.transform, meta.width, meta.height, (*meta.bands, band), meta.resampled)


def _dataset_check(config: DatasetConfig, params: BaseModel) -> list[str]:
    """The band is a radar band of the entry and the quantity is the one the entry states (adr/0030 §8)."""
    step = _params(params)
    stated = config.sar_quantity.get(step.bands[0])
    if stated is None:
        return [f"{step.bands[0]} is no radar band of {config.dataset_id} with a stated quantity"]
    if stated != step.quantity:
        return [f"{step.bands[0]} of {config.dataset_id} is an {stated}, not an {step.quantity}"]
    return []


def _dataset_schema(config: DatasetConfig, schema: dict[str, Any]) -> None:
    """Where the entry states one quantity for all its radar bands, the form takes it as fixed (DS-05a A4)."""
    quantities = set(config.sar_quantity.values())
    field = schema.get("properties", {}).get("quantity")
    if len(quantities) == 1 and isinstance(field, dict):
        field.pop("enum", None)
        field.pop("type", None)
        field["const"] = quantities.pop()


def _bands_used(params: BaseModel) -> BandUse:
    step = _params(params)
    return BandUse(reads=frozenset(step.bands), adds=step.name)


def _formula(step: SarDbParams) -> str:
    return f"{_FACTORS[step.quantity]}·log10({step.bands[0]})"


def _lineage(params: BaseModel) -> str:
    step = _params(params)
    return f"sar_db: {step.name} = {_formula(step)} ({step.quantity})"


def _method(params: BaseModel) -> str:
    step = _params(params)
    return (
        f"A band named {step.name} was computed as {_formula(step)}, the {step.quantity} in {step.bands[0]} in decibels, "
        "from a table of exact values for whole numbers; pixels of value 0 were left empty."
    )


def _properties(params: BaseModel) -> dict[str, Any]:
    return {"earthx:sar_db": _params(params).model_dump(mode="json")}


# Grey from the 2nd to the 98th percentile, as the digital numbers it comes from (DS-05a F4): dB changes how the brightness
# is spread, not its colour, and a fixed range of dB would mean nothing on uncalibrated values.
_LOOK = Look(colormap="greys_r")

SAR_DB = Operator(
    op="sar_db",
    op_version=1,
    category="radar",
    title="SAR dB",
    # Says what v1 reads (Otto, 27.11.2026): whole numbers are digital numbers, never σ⁰; the calibration (DS-05d) changes it.
    description=(
        "Add a radar band in decibels, computed from its uncalibrated digital numbers (DN), not calibrated "
        "backscatter (σ⁰)."
    ),
    citation=None,
    params=SarDbParams,
    requires=Requirement(
        capabilities=frozenset({"sar_backscatter"}), data_classes=frozenset(), license_tier=LicenseTier.PROCESSING
    ),
    tiers=frozenset({Tier.T1, Tier.T2}),
    kind="pixel",
    # adr/0030 §7 guessed 0.2 for the look-up alone; measured with the stock it joins, 0.77 of band math's kernel on
    # 4 Mpx (DS-05a §8), and the statistics of the result as band math (§15k): 1.0.
    cost_factor=lambda params: 1.0,
    transform=_transform,
    run=_run,
    lineage=_lineage,
    method=_method,
    properties=_properties,
    dataset_check=_dataset_check,
    dataset_schema=_dataset_schema,
    bands_used=_bands_used,
    looks=Looks(param="quantity", by_value={"amplitude": _LOOK, "intensity": _LOOK}),
)
