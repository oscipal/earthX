"""The nodata of a file the core writes, and a valid value kept off it (plan M5-28, adr/0014 Nachtrag M5-28).

- A float type takes NaN: no measured value is NaN (R1).
- An integer type takes the nodata of the source where the chain only passes the source's integer values on, for
  then no valid value can be it (R2); otherwise an edge of the type, ``max`` for an unsigned type and ``min`` for a
  signed one, as ``gdal_calc.py`` chooses, so that 0 always stays a value (R3).
- A source nodata the integer type cannot hold is refused before a block is read (Otto, 11.11.2026, F7).
- A valid value that lands on the nodata after rounding and clamping is moved one step towards the middle of the
  type, as GDAL's warper does (``AvoidNoData`` in ``alg/gdalwarpkernel.cpp``) (R4).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy

from earthx.processing.errors import UnsupportedRecipe
from earthx.processing.operators.base import BandMeta


def is_integer(dtype: str) -> bool:
    return numpy.issubdtype(numpy.dtype(dtype), numpy.integer)


def edge(dtype: str) -> int:
    """The nodata of an integer type whose source gives none it can keep: ``max`` if unsigned, else ``min``."""
    limits = numpy.iinfo(numpy.dtype(dtype))
    return int(limits.max) if limits.min == 0 else int(limits.min)


def output_nodata(dtype: str, bands: Sequence[BandMeta], passes_values: bool) -> float:
    """The nodata of a file of ``dtype`` holding ``bands``; ``passes_values`` says the steps only pass values on.

    :class:`UnsupportedRecipe` where a band carries a source nodata the integer type cannot hold.
    """
    target = numpy.dtype(dtype)
    if numpy.issubdtype(target, numpy.floating):
        return math.nan
    if not numpy.issubdtype(target, numpy.integer):
        raise UnsupportedRecipe(f"no nodata for the output type {dtype}")
    limits = numpy.iinfo(target)
    declared = {band.nodata for band in bands if band.nodata is not None and not math.isnan(band.nodata)}
    for value in sorted(declared):
        if not (math.isfinite(value) and value == int(value) and limits.min <= value <= limits.max):
            raise UnsupportedRecipe(
                f"the source's nodata {value:g} does not fit the output type {dtype}; "
                "choose a type that holds it, or a float type"
            )
    keeps = (
        passes_values
        and len(declared) == 1
        and all(band.nodata is not None for band in bands)
        and all(is_integer(band.data_type) for band in bands)
    )
    return float(declared.pop()) if keeps else float(edge(dtype))


def avoid_nodata(values: numpy.ndarray, valid: numpy.ndarray, nodata: float) -> list[int]:
    """Move every valid integer value equal to ``nodata`` one step towards the middle of its type, in place.

    Down by one, up by one where ``nodata`` is the lowest value of the type, as GDAL's ``AvoidNoData``. Returns the
    number of pixels moved per band (axis 0).
    """
    hit = valid & (values == nodata)
    counts = [int(band.sum()) for band in hit]
    if any(counts):
        lowest = numpy.iinfo(values.dtype).min
        values[hit] = nodata + 1 if nodata == lowest else nodata - 1
    return counts
