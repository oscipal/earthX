"""Statistics of one band of a result, gathered block by block in the pass that writes it (M4-32).

What is counted are the valid, finite values as they are written. Every block becomes a
:class:`BlockSummary`, and summaries merge: the statistics of the mask (AOI) and of the
whole file come from the same summaries, without reading anything twice
(plan M4-32 §6.2, §7).

* ``minimum``, ``maximum`` and ``count`` are exact.
* ``mean`` is the exact mean, rounded once: the sum is taken in integers over the bit
  patterns, per sign and exponent, so it depends on neither the order of the values nor
  the machine.
* ``stddev`` is GDAL's way (``GDALRasterBand::ComputeStatistics``): Welford within a
  block, Chan's parallel formula across blocks, divided by ``count``. Deterministic for a
  fixed order of blocks, not exact. GDAL reads stored statistics only with it (plan §6.1).
* ``percentile_2`` and ``percentile_98`` come from a fixed histogram: one bin per value
  for integers of up to 16 bits (exact), otherwise the upper 16 bits of the
  order-preserving pattern of the ``float32`` value — 65 536 bins of relative width
  2⁻⁷. The rank is the nearest rank; the 2 % value is the lower edge of its bin, the
  98 % value the upper edge, both clamped to the range, so ``[p2, p98]`` holds the true
  values. Integers of 32 bits round outwards to whole numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

import numpy

__all__ = ["BandStatistics", "BlockSummary", "PERCENTILES", "gdal_tags", "summarize"]

PERCENTILES = (2, 98)

#: Bins of the float histogram: the upper 16 bits of the order-preserving float32 pattern.
_KEY_BITS = 16
_KEY_SHIFT = numpy.uint32(32 - _KEY_BITS)
_SIGN32 = numpy.uint32(0x80000000)

#: Values per exact partial sum: a significand below 2²⁶ times 2²⁰ values stays below
#: 2⁴⁶, which float64 (the type of ``bincount``'s weighted sums) holds exactly.
_CHUNK = 1 << 20

_FLOAT_LAYOUT = {
    # dtype: (unsigned view, fraction bits, exponent bits, exponent bias)
    numpy.dtype("float32"): (numpy.uint32, 23, 8, 127),
    numpy.dtype("float64"): (numpy.uint64, 52, 11, 1023),
}
_LIMB_BITS = 26


def _kind(dtype: numpy.dtype) -> str:
    if dtype in _FLOAT_LAYOUT:
        return "float"
    if dtype.kind in "iu" and dtype.itemsize <= 2:
        return "small"
    if dtype.kind in "iu" and dtype.itemsize == 4:
        return "int"
    raise TypeError(f"no statistics for values of type {dtype}")


@dataclass(slots=True)
class BlockSummary:
    """What one block of values contributes; summaries of one ``dtype`` merge."""

    dtype: numpy.dtype
    count: int
    minimum: Any
    maximum: Any
    #: Exact sum: an int for integer types, otherwise int partial sums keyed by sign and exponent.
    total: Any
    mean: float
    m2: float
    histogram: numpy.ndarray


def _histogram_size(dtype: numpy.dtype) -> int:
    return 1 << (8 * dtype.itemsize) if _kind(dtype) == "small" else 1 << _KEY_BITS


def _float_keys(values: numpy.ndarray) -> numpy.ndarray:
    """The bin of each value: its float32 pattern made order-preserving (negatives flipped), upper 16 bits."""
    if values.dtype != numpy.float32:
        limit = float(numpy.finfo(numpy.float32).max)
        values = numpy.clip(values, -limit, limit).astype(numpy.float32)
    bits = values.view(numpy.uint32)
    flip = (values.view(numpy.int32) >> 31).view(numpy.uint32) | _SIGN32
    return ((bits ^ flip) >> _KEY_SHIFT).astype(numpy.intp)


def _float_total(values: numpy.ndarray) -> dict[int, int]:
    """The exact sum, as integer significand sums keyed by ``sign << exponent bits | exponent``."""
    unsigned, fraction_bits, exponent_bits, _ = _FLOAT_LAYOUT[values.dtype]
    total: dict[int, int] = {}
    for start in range(0, values.size, _CHUNK):
        bits = values[start : start + _CHUNK].view(unsigned)
        index = (bits >> unsigned(fraction_bits)).astype(numpy.intp)
        fraction = bits & unsigned((1 << fraction_bits) - 1)
        size = 1 << (exponent_bits + 1)
        counts = numpy.bincount(index, minlength=size)
        high = numpy.bincount(index, weights=fraction >> unsigned(_LIMB_BITS), minlength=size)
        low = numpy.bincount(index, weights=fraction & unsigned((1 << _LIMB_BITS) - 1), minlength=size)
        for key in numpy.flatnonzero(counts):
            implicit = 1 << fraction_bits if key & ((1 << exponent_bits) - 1) else 0
            part = int(counts[key]) * implicit + (int(high[key]) << _LIMB_BITS) + int(low[key])
            total[int(key)] = total.get(int(key), 0) + part
    return total


def _float_sum(total: dict[int, int], dtype: numpy.dtype) -> Fraction:
    _, fraction_bits, exponent_bits, bias = _FLOAT_LAYOUT[dtype]
    exact = Fraction(0)
    for key, significands in total.items():
        exponent = key & ((1 << exponent_bits) - 1)
        sign = -1 if key >> exponent_bits else 1
        exact += sign * significands * Fraction(2) ** (max(exponent, 1) - bias - fraction_bits)
    return exact


def summarize(values: numpy.ndarray) -> BlockSummary:
    """The summary of ``values``, the valid values of one block (one dimension, the band's type).

    Values that are not finite do not count: in a result they can only be an overflow on
    the way into ``float32``.
    """
    if values.ndim != 1:
        raise ValueError("summarize() takes the valid values of a block as one dimension")
    dtype = values.dtype
    kind = _kind(dtype)
    if kind == "float":
        values = values[numpy.isfinite(values)]
    histogram = numpy.zeros(_histogram_size(dtype), dtype=numpy.int64)
    if values.size == 0:
        return BlockSummary(dtype, 0, None, None, {} if kind == "float" else 0, 0.0, 0.0, histogram)
    wide = values.astype(numpy.float64)
    with numpy.errstate(over="ignore", invalid="ignore"):  # near the float64 limits: no stddev (summary())
        mean = float(wide.sum()) / values.size
        deviation = wide - mean
        m2 = float((deviation * deviation).sum())
    if kind == "small":
        histogram += numpy.bincount(values.astype(numpy.intp) - int(numpy.iinfo(dtype).min), minlength=histogram.size)
    else:
        histogram += numpy.bincount(_float_keys(values), minlength=histogram.size)
    if kind == "float":
        total: Any = _float_total(values)
    else:
        total = sum(int(values[start : start + _CHUNK].sum(dtype=numpy.int64)) for start in range(0, values.size, _CHUNK))
    return BlockSummary(dtype, int(values.size), values.min(), values.max(), total, mean, m2, histogram)


def _unkey(key: int) -> float:
    """The float32 whose order-preserving pattern is ``key`` (32 bits)."""
    bits = key & 0x7FFFFFFF if key & 0x80000000 else ~key & 0xFFFFFFFF
    return float(numpy.array([bits], dtype=numpy.uint32).view(numpy.float32)[0])


class BandStatistics:
    """The statistics of one band, merged from the summaries of its blocks in a fixed order."""

    def __init__(self, dtype: str | numpy.dtype) -> None:
        self.dtype = numpy.dtype(dtype)
        self._kind = _kind(self.dtype)
        self.count = 0
        self._minimum: Any = None
        self._maximum: Any = None
        self._total: Any = {} if self._kind == "float" else 0
        self._mean = 0.0
        self._m2 = 0.0
        self._histogram = numpy.zeros(_histogram_size(self.dtype), dtype=numpy.int64)

    def add(self, values: numpy.ndarray) -> None:
        self.merge(summarize(values))

    def merge(self, block: BlockSummary) -> None:
        if block.dtype != self.dtype:
            raise ValueError(f"a summary of {block.dtype} does not merge into statistics of {self.dtype}")
        if block.count == 0:
            return
        before, count = self.count, self.count + block.count
        # Chan et al.: GDAL's merge of the block means and sums of squared deviations.
        delta = block.mean - self._mean
        self._mean += delta * (block.count / count)
        self._m2 += block.m2 + delta * delta * before * block.count / count
        self.count = count
        self._minimum = block.minimum if self._minimum is None else min(self._minimum, block.minimum)
        self._maximum = block.maximum if self._maximum is None else max(self._maximum, block.maximum)
        if self._kind == "float":
            for key, part in block.total.items():
                self._total[key] = self._total.get(key, 0) + part
        else:
            self._total += block.total
        self._histogram += block.histogram

    def _percentile(self, percent: int, minimum: Any, maximum: Any) -> Any:
        rank = max(1, -(-percent * self.count // 100))
        index = int(numpy.searchsorted(numpy.cumsum(self._histogram), rank))
        if self._kind == "small":
            return index + int(numpy.iinfo(self.dtype).min)
        upper = percent > 50
        edge = _unkey((((index + 1) << (32 - _KEY_BITS)) - 1) if upper else (index << (32 - _KEY_BITS)))
        if self._kind == "int":
            edge = math.ceil(edge) if upper else math.floor(edge)
        return min(edge, maximum) if upper else max(edge, minimum)

    def summary(self, pixels: int) -> dict[str, Any]:
        """The STAC statistics object (1.1, extended by the two percentiles) over ``pixels`` in all."""
        if pixels <= 0:
            raise ValueError("statistics need at least one pixel")
        if self.count > pixels:
            raise ValueError("more valid values than pixels")
        valid_percent = 100.0 * self.count / pixels
        if self.count == 0:
            return {"count": 0, "valid_percent": valid_percent}
        if self._kind == "float":
            minimum, maximum = float(self._minimum), float(self._maximum)
            mean = float(_float_sum(self._total, self.dtype) / self.count)
        else:
            minimum, maximum = int(self._minimum), int(self._maximum)
            mean = float(Fraction(self._total, self.count))
        result: dict[str, Any] = {"minimum": minimum, "maximum": maximum, "mean": mean}
        stddev = math.sqrt(self._m2 / self.count) if math.isfinite(self._m2) else math.nan
        if math.isfinite(stddev):
            result["stddev"] = stddev
        result["count"] = self.count
        result["valid_percent"] = valid_percent
        for percent in PERCENTILES:
            result[f"percentile_{percent}"] = self._percentile(percent, minimum, maximum)
        return result


#: STAC name → GDAL band tag. The percentiles have no GDAL name, hence a prefix of our own.
_TAGS = {
    "minimum": "STATISTICS_MINIMUM",
    "maximum": "STATISTICS_MAXIMUM",
    "mean": "STATISTICS_MEAN",
    "stddev": "STATISTICS_STDDEV",
    "valid_percent": "STATISTICS_VALID_PERCENT",
    "percentile_2": "EARTHX_PERCENTILE_2",
    "percentile_98": "EARTHX_PERCENTILE_98",
}


def gdal_tags(summary: dict[str, Any]) -> dict[str, str]:
    """The band tags of a summary, each value as ``repr``: the shortest text that reads back as the same number."""
    return {tag: repr(summary[name]) for name, tag in _TAGS.items() if name in summary}
