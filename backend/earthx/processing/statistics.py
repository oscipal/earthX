"""Statistics of one band of a result, gathered block by block in the pass that writes it (M4-32).

What is counted are the valid, finite values as they are written. Every block becomes a
:class:`BlockSummary`, and summaries merge: the statistics of the mask (AOI) and of the
whole file come from the same summaries, without reading anything twice
(plan M4-32 §6.2, §7).

* ``minimum``, ``maximum`` and ``count`` are exact.
* ``mean`` is the exact mean, rounded once: the sum is taken in integers over the bit
  patterns, per sign and exponent, so it depends on neither the order of the values nor
  the machine.
* ``stddev`` merges blocks as GDAL does (``GDALRasterBand::ComputeStatistics``): within a
  block the mean, then the sum of squared deviations (numpy's pairwise sums); across blocks
  Chan's parallel formula; divided by ``count``. Deterministic for a fixed order of blocks,
  not exact. GDAL reads stored statistics only with it (plan §6.1).
* ``percentile_2`` and ``percentile_98`` come from a fixed histogram: one bin per value
  for integers of up to 16 bits (exact), otherwise the upper 16 bits of the
  order-preserving pattern of the ``float32`` value — 65 536 bins of relative width
  2⁻⁷. The rank is the nearest rank; the 2 % value is the lower edge of its bin, the
  98 % value the upper edge, both clamped to the range, so ``[p2, p98]`` holds the true
  values. Values of other types reach float32 rounded down, and the 98 % value moves one
  float32 step up, so this holds for them too; integers of 32 bits round outwards to whole
  numbers.
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
_FLOAT32_MAX = numpy.finfo(numpy.float32).max

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
    #: Exact sum: an int for integer types; for float32 the fraction sums per histogram bin (int64), for
    #: float64 int partial sums keyed by sign and exponent.
    total: Any
    mean: float
    m2: float
    histogram: numpy.ndarray


def _histogram_size(dtype: numpy.dtype) -> int:
    return 1 << (8 * dtype.itemsize) if _kind(dtype) == "small" else 1 << _KEY_BITS


def _float_keys(values: numpy.ndarray) -> numpy.ndarray:
    """The bin of each value: its float32 pattern made order-preserving (negatives flipped), upper 16 bits.

    A value of another type becomes the largest float32 not above it, so its bin's lower edge is never
    above it; below the float32 range that is ``-inf``, whose bin lies under every finite one.
    """
    if values.dtype != numpy.float32:
        wide = values.astype(numpy.float64)
        with numpy.errstate(over="ignore"):  # below the float32 range nextafter gives -inf, on purpose
            narrow = numpy.clip(wide, -_FLOAT32_MAX, _FLOAT32_MAX).astype(numpy.float32)
            values = numpy.where(narrow > wide, numpy.nextafter(narrow, numpy.float32(-numpy.inf)), narrow)
    bits = values.view(numpy.uint32)
    flip = (values.view(numpy.int32) >> 31).view(numpy.uint32) | _SIGN32
    return ((bits ^ flip) >> _KEY_SHIFT).astype(numpy.intp)


def _float32_total(values: numpy.ndarray, keys: numpy.ndarray) -> numpy.ndarray:
    """The fraction bits summed per histogram bin: sign and exponent are the bin's upper bits (:func:`_float32_sum`)."""
    fractions = values.view(numpy.uint32) & numpy.uint32((1 << 23) - 1)
    total = numpy.zeros(1 << _KEY_BITS, dtype=numpy.int64)
    for start in range(0, values.size, _CHUNK):
        part = numpy.bincount(keys[start : start + _CHUNK], weights=fractions[start : start + _CHUNK], minlength=total.size)
        total += part.astype(numpy.int64)
    return total


def _float32_sum(total: numpy.ndarray, histogram: numpy.ndarray) -> Fraction:
    """The exact sum from the bins: each bin holds one sign and one exponent, the implicit bit counts once a value."""
    keys = numpy.flatnonzero(histogram)
    upper = numpy.where(keys >= 1 << (_KEY_BITS - 1), keys & 0x7FFF, ~keys & 0xFFFF)  # the pattern's upper 16 bits
    exponents = (upper >> 7) & 0xFF
    scaled = 0  # the sum times 2¹⁴⁹, the smallest float32 step, so every term is an integer
    for key, sign_bit, exponent in zip(keys.tolist(), (upper >> 15).tolist(), exponents.tolist(), strict=True):
        implicit = 1 << 23 if exponent else 0
        significands = int(histogram[key]) * implicit + int(total[key])
        scaled += (-1 if sign_bit else 1) * (significands << (max(exponent, 1) - 1))
    return Fraction(scaled, 1 << 149)


def _float_total(values: numpy.ndarray) -> dict[int, int]:
    """The exact sum of float64 values, as integer significand sums keyed by ``sign << 11 | exponent``."""
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
    scaled = 0  # the sum times the smallest step of the type, so every term is an integer
    for key, significands in total.items():
        exponent = key & ((1 << exponent_bits) - 1)
        sign = -1 if key >> exponent_bits else 1
        scaled += sign * (significands << (max(exponent, 1) - 1))
    return Fraction(scaled, 1 << (bias + fraction_bits - 1))


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
        finite = numpy.isfinite(values)
        if not finite.all():
            values = values[finite]
    if values.size == 0:
        histogram = numpy.zeros(_histogram_size(dtype), dtype=numpy.int64)
        return BlockSummary(dtype, 0, None, None, _empty_total(dtype), 0.0, 0.0, histogram)
    wide = values.astype(numpy.float64)
    with numpy.errstate(over="ignore", invalid="ignore"):  # near the float64 limits: no stddev (summary())
        mean = float(wide.sum()) / values.size
        # In place, so a block costs one float64 copy of its values, not three.
        wide -= mean
        numpy.multiply(wide, wide, out=wide)
        m2 = float(wide.sum())
    size = _histogram_size(dtype)
    if kind == "small":
        histogram = numpy.bincount(values.astype(numpy.intp) - int(numpy.iinfo(dtype).min), minlength=size)
    else:
        keys = _float_keys(values)
        histogram = numpy.bincount(keys, minlength=size)
    total: Any
    if dtype == numpy.float32:
        total = _float32_total(values, keys)
    elif kind == "float":
        total = _float_total(values)
    else:
        total = sum(int(values[start : start + _CHUNK].sum(dtype=numpy.int64)) for start in range(0, values.size, _CHUNK))
    return BlockSummary(dtype, int(values.size), values.min(), values.max(), total, mean, m2, histogram.astype(numpy.int64))


def _empty_total(dtype: numpy.dtype) -> Any:
    if dtype == numpy.float32:
        return numpy.zeros(1 << _KEY_BITS, dtype=numpy.int64)
    return {} if dtype in _FLOAT_LAYOUT else 0


def _unkey(key: int) -> numpy.float32:
    """The float32 whose order-preserving pattern is ``key`` (32 bits)."""
    bits = key & 0x7FFFFFFF if key & 0x80000000 else ~key & 0xFFFFFFFF
    return numpy.array([bits], dtype=numpy.uint32).view(numpy.float32)[0]


#: The bins of the most negative and the most positive finite float32.
_LOWEST_BIN = int(_float_keys(numpy.array([-_FLOAT32_MAX], dtype=numpy.float32))[0])
_HIGHEST_BIN = int(_float_keys(numpy.array([_FLOAT32_MAX], dtype=numpy.float32))[0])


class BandStatistics:
    """The statistics of one band, merged from the summaries of its blocks in a fixed order."""

    def __init__(self, dtype: str | numpy.dtype) -> None:
        self.dtype = numpy.dtype(dtype)
        self._kind = _kind(self.dtype)
        self.count = 0
        self._minimum: Any = None
        self._maximum: Any = None
        self._total: Any = _empty_total(self.dtype)
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
        if isinstance(self._total, dict):
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
        # At the ends of the float32 range (a float64 beyond it) the bin says nothing: the range does.
        if upper and index >= _HIGHEST_BIN:
            return maximum
        if not upper and index <= _LOWEST_BIN:
            return minimum
        edge = _unkey((((index + 1) << (32 - _KEY_BITS)) - 1) if upper else (index << (32 - _KEY_BITS)))
        if upper and self.dtype != numpy.float32:
            edge = numpy.nextafter(edge, numpy.float32(numpy.inf))  # the value may lie just above its float32
        if self._kind == "int":
            return min(math.ceil(edge), maximum) if upper else max(math.floor(edge), minimum)
        edge = float(edge) + 0.0  # no -0.0 from a bin edge
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
            exact = (
                _float32_sum(self._total, self._histogram)
                if self.dtype == numpy.float32
                else _float_sum(self._total, self.dtype)
            )
            mean = float(exact / self.count)
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
