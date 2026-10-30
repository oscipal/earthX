"""Time the kernel of ``mask_values`` against ``mask`` and ``band_math`` on a block of 1024² pixels (DS-06, adr/0014 §15 Nachtrag DS-06).

The method of ``adr/0014`` §15m: each kernel 15 times on the same block, the smallest time counts (the least
disturbed run). ``mask`` (factor 0.2) is the reference; ``mask_values`` must not cost more.
Synthetic data, no network. Run from the repo root: ``PYTHONPATH=backend python scripts/ds-06-mask-values/measure_kernel.py``.
"""

from __future__ import annotations

import time

import numpy
from rio_tiler.models import ImageData

from earthx.processing.operators import (
    BAND_MATH_V2,
    MASK_V2,
    MASK_VALUES,
    BandMathParamsV2,
    MaskParams,
    MaskValuesParams,
)

BLOCK, RUNS = 1024, 15
NAMES = ["red", "nir", "scl"]


def _values(condition: str, *values: float, band: str = "red") -> MaskValuesParams:
    return MaskValuesParams(band=band, condition=condition, values=list(values))


STEPS = {
    "band_math v2 NDVI": (BAND_MATH_V2, BandMathParamsV2(expression="(nir-red)/(nir+red)", name="NDVI")),
    "mask v2, 4 classes": (MASK_V2, MaskParams(source="scl", classes=[3, 8, 9, 10])),
    "mask_values lt": (MASK_VALUES, _values("lt", 0.2)),
    "mask_values gt": (MASK_VALUES, _values("gt", 0.8)),
    "mask_values between": (MASK_VALUES, _values("between", 0.2, 0.8)),
    "mask_values eq, 4 values": (MASK_VALUES, _values("eq", 3, 8, 9, 10, band="scl")),
}


def main() -> None:
    rng = numpy.random.default_rng(0)
    data = numpy.ma.masked_array(
        numpy.stack(
            [rng.random((BLOCK, BLOCK)), rng.random((BLOCK, BLOCK)), rng.integers(0, 12, (BLOCK, BLOCK))]
        ).astype("float32")
    )
    image = ImageData(data, bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=NAMES)
    for name, (operator, params) in STEPS.items():
        times = []
        for _ in range(RUNS):
            started = time.perf_counter()
            operator.run(image, params)
            times.append(time.perf_counter() - started)
        print(f"{name:26s} {min(times) * 1000:6.1f} ms")


if __name__ == "__main__":
    main()
