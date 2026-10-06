"""Physical values for band math: which scaling applies, the check against the file, and applying it.

adr/0014 §5.4 with F7, F7a and the reading of 05.10.2026:

* **The item carries a scaling** (``scaling="item"``): its values apply. The reader
  reads raw — a Zarr store with ``decode_cf=False`` — and where the file or store
  carries a scaling too, both must agree, or the run fails with
  :class:`ScalingMismatch` instead of computing on the wrong numbers.
* **No scaling on the item, Zarr** (``store-cf``): the reader's generic CF decoding
  applies, whatever the store says; the values it used are reported.
* **No scaling on the item, COG** (``none``): nothing is scaled — but a file whose
  own tags say otherwise fails the run, because nothing declared that scaling.

:func:`apply_scaling` computes exactly as rio-tiler's ``unscale`` does (float32,
multiply, then add; ``rio_tiler/reader.py`` lines 281–288), so the tile path (T1,
M4-09) can call this very function and stay bit-identical with a job (§6.3).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy
from rio_tiler.models import ImageData

from earthx.processing.errors import ScalingMismatch
from earthx.processing.recipe import Band

__all__ = ["Scaling", "apply_scaling", "scaling_for_cog", "scaling_for_zarr"]

Source = Literal["item", "store-cf", "none"]


@dataclass(frozen=True, slots=True)
class Scaling:
    """What one input asset's values are scaled with, per band, and where that came from."""

    source: Source
    scales: tuple[float, ...]
    offsets: tuple[float, ...]
    #: Whether the core multiplies and adds; ``False`` where the reader already did or nothing applies.
    applied_by_core: bool


def _same(a: float, b: float) -> bool:
    # Decimal text in an item against a double in a file: equal up to representation.
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def _trivial(scales: Sequence[float], offsets: Sequence[float]) -> bool:
    return all(_same(scale, 1.0) for scale in scales) and all(_same(offset, 0.0) for offset in offsets)


def _from_item(bands: Sequence[Band]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    scales = tuple(1.0 if band.scale is None else band.scale for band in bands)
    offsets = tuple(0.0 if band.offset is None else band.offset for band in bands)
    return scales, offsets


def _compare(
    item: tuple[tuple[float, ...], tuple[float, ...]], file: tuple[Sequence[float], Sequence[float]], what: str
) -> None:
    if len(item[0]) != len(file[0]):
        raise ScalingMismatch(f"{what}: the item describes {len(item[0])} bands, the file has {len(file[0])}")
    for index, (a, b, c, d) in enumerate(zip(item[0], file[0], item[1], file[1], strict=True)):
        if not (_same(a, b) and _same(c, d)):
            raise ScalingMismatch(f"{what}: band {index + 1} is scaled differently in the item and in the file")


def scaling_for_cog(
    source: Source, bands: Sequence[Band], scales: Sequence[float], offsets: Sequence[float], what: str
) -> Scaling:
    """The scaling of a COG asset, checked against the file's own ``scales``/``offsets`` tags."""
    if source == "item":
        item = _from_item(bands)
        if not _trivial(scales, offsets):
            _compare(item, (scales, offsets), what)
        elif len(item[0]) != len(scales):
            raise ScalingMismatch(f"{what}: the item describes {len(item[0])} bands, the file has {len(scales)}")
        return Scaling("item", item[0], item[1], applied_by_core=True)
    if source == "none":
        if not _trivial(scales, offsets):
            raise ScalingMismatch(f"{what}: the file carries a scaling that neither item nor store declares")
        return Scaling("none", tuple(1.0 for _ in scales), tuple(0.0 for _ in scales), applied_by_core=False)
    raise ScalingMismatch(f"{what}: a COG has no store CF attributes to decode")


def scaling_for_zarr(source: Source, bands: Sequence[Band], attributes: Sequence[dict], what: str) -> Scaling:
    """The scaling of a Zarr asset, from the item or the CF attributes of each variable.

    ``attributes`` holds, per variable, its attributes when read raw
    (``decode_cf=False``) or its encoding when decoded — the two places xarray
    leaves ``scale_factor`` and ``add_offset``.
    """
    store_scales = tuple(float(entry.get("scale_factor", 1.0)) for entry in attributes)
    store_offsets = tuple(float(entry.get("add_offset", 0.0)) for entry in attributes)
    if source == "item":
        item = _from_item(bands)
        if not _trivial(store_scales, store_offsets):
            _compare(item, (store_scales, store_offsets), what)
        return Scaling("item", item[0], item[1], applied_by_core=True)
    if source == "store-cf":
        return Scaling("store-cf", store_scales, store_offsets, applied_by_core=False)
    raise ScalingMismatch(f"{what}: a Zarr asset without item scaling is decoded by the store's CF attributes")


def apply_scaling(image: ImageData, scaling: Scaling) -> ImageData:
    """``image`` in physical values, computed as rio-tiler's ``unscale`` does; the mask is kept."""
    if not scaling.applied_by_core:
        return image
    if image.count != len(scaling.scales):
        raise ScalingMismatch(f"the scaling names {len(scaling.scales)} bands, the data has {image.count}")
    data = image.array.astype("float32", casting="unsafe")
    numpy.multiply(data, numpy.array(scaling.scales).reshape((-1, 1, 1)), out=data, casting="unsafe")
    numpy.add(data, numpy.array(scaling.offsets).reshape((-1, 1, 1)), out=data, casting="unsafe")
    return ImageData(
        data,
        bounds=image.bounds,
        crs=image.crs,
        band_names=list(image.band_names),
        nodata=image.nodata,
    )
