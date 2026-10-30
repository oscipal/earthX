"""Time the kernels of ``normalize`` on one block of 1024² pixels and two bands (NM4-11, adr/0014 §15 Nachtrag NM4-11).

The method of ``adr/0014`` §15m: each kernel 15 times on the same block, the smallest time counts (the least
disturbed run). Version 2 (a fixed range) is the reference the factor 0.3 was set from; version 3 must not cost more.
Synthetic data, no network. Run from the repo root: ``PYTHONPATH=backend python scripts/nm4-11-normalize/measure_kernel.py``.
"""

from __future__ import annotations

import time

import numpy
from rio_tiler.models import ImageData

from earthx.processing.operators import NORMALIZE_V2, NORMALIZE_V3, NormalizeParamsV2, NormalizeParamsV3

BLOCK, RUNS = 1024, 15
BANDS = ["red", "nir"]
NUMBERS = {
    "red": {"p_low": 0.1, "p_high": 0.9, "mean": 0.5, "stddev": 0.2, "p25": 0.3, "median": 0.5, "p75": 0.7},
    "nir": {"p_low": 0.2, "p_high": 1.1, "mean": 0.6, "stddev": 0.3, "p25": 0.4, "median": 0.6, "p75": 0.8},
}


def _measured(*names: str) -> dict:
    return {"factor": 1, "bands": {band: {name: NUMBERS[band][name] for name in names} for band in BANDS}}


STEPS = {
    "v2 fixed range": (
        NORMALIZE_V2,
        NormalizeParamsV2(bands=BANDS, in_min=0.0, in_max=1.0, out_min=0.0, out_max=255.0, clip=True),
    ),
    "v3 linear": (
        NORMALIZE_V3,
        NormalizeParamsV3(
            method="linear", bands=BANDS, in_min=0.0, in_max=1.0, out_min=0.0, out_max=255.0, clip=True
        ),
    ),
    "v3 percentile": (
        NORMALIZE_V3,
        NormalizeParamsV3.model_validate(
            {
                "method": "percentile", "bands": BANDS, "low": 2, "high": 98, "out_min": 0.0, "out_max": 1.0,
                "clip": True, "measured": _measured("p_low", "p_high"),
            }
        ),
    ),
    "v3 zscore": (
        NORMALIZE_V3,
        NormalizeParamsV3.model_validate(
            {"method": "zscore", "bands": BANDS, "measured": _measured("mean", "stddev")}
        ),
    ),
    "v3 robust": (
        NORMALIZE_V3,
        NormalizeParamsV3.model_validate(
            {"method": "robust", "bands": BANDS, "measured": _measured("p25", "median", "p75")}
        ),
    ),
}


def main() -> None:
    rng = numpy.random.default_rng(1)
    data = numpy.ma.masked_array(rng.uniform(-0.2, 1.4, (2, BLOCK, BLOCK)).astype("float32"))
    image = ImageData(data, bounds=(0, 0, 1, 1), crs="EPSG:32632", band_names=BANDS)
    for name, (operator, params) in STEPS.items():
        times = []
        for _ in range(RUNS):
            started = time.perf_counter()
            operator.run(image, params)
            times.append(time.perf_counter() - started)
        print(f"{name:16s} {min(times) * 1000:7.1f} ms (smallest of {RUNS})")


if __name__ == "__main__":
    main()
