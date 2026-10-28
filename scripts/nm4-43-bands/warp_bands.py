#!/usr/bin/env python3
"""Does the number of bands in a file change what ``reproject`` gives for one band? (NM4-43, adr/0020 §3.5)

    PYTHONPATH=backend python scripts/nm4-43-bands/warp_bands.py [--size 2048] [--counts 1,2,3,4,18,34]

Writes synthetic ``float64`` files in the core's intermediate form (1024 px tiles, NaN as nodata) with
``count`` bands whose first band is always the same, runs the ``reproject`` operator block by block onto
EPSG:3035 with ``bilinear`` as the core does, and compares the first band bit by bit with the one-band file.
No source is read; the files live in a temporary directory.
"""

from __future__ import annotations

import argparse
import math
import tempfile
from pathlib import Path

import numpy
import rasterio
from rasterio.transform import Affine
from rasterio.windows import Window

from earthx.processing.core import BLOCK_SIZE
from earthx.processing.operators.base import BandMeta, RasterMeta
from earthx.processing.operators.reproject import REPROJECT, ReprojectParams

TRANSFORM = Affine(10, 0, 600000, 0, -10, 5200000)
PARAMS = ReprojectParams.model_validate(
    {"crs": "EPSG:3035", "resolution": 10.0, "resampling": "bilinear", "align": False}
)


def _write(path: Path, base: numpy.ndarray, count: int) -> None:
    size = base.shape[0]
    profile = {
        "driver": "GTiff", "dtype": "float64", "count": count, "width": size, "height": size, "crs": "EPSG:32632",
        "transform": TRANSFORM, "nodata": math.nan, "tiled": True, "blockxsize": BLOCK_SIZE, "blockysize": BLOCK_SIZE,
    }  # fmt: skip
    with rasterio.open(path, "w", **profile) as dst:
        for band in range(1, count + 1):
            dst.write(base + (band - 1) * 0.01, band)


def _warp_first_band(path: Path, size: int, count: int) -> numpy.ndarray:
    bands = tuple(BandMeta(f"b{index}", "float64", math.nan) for index in range(count))
    target = REPROJECT.transform(RasterMeta("EPSG:32632", TRANSFORM, size, size, bands), PARAMS)
    out = numpy.empty((target.height, target.width), dtype="float64")
    with rasterio.open(path) as src:
        for row in range(0, target.height, BLOCK_SIZE):
            for col in range(0, target.width, BLOCK_SIZE):
                window = Window(col, row, min(BLOCK_SIZE, target.width - col), min(BLOCK_SIZE, target.height - row))
                data = REPROJECT.run(src, target, window, PARAMS)
                out[row : row + int(window.height), col : col + int(window.width)] = numpy.ma.filled(data[0], math.nan)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=2048)
    parser.add_argument("--counts", default="1,2,3,4,18,34")
    args = parser.parse_args()
    base = numpy.random.default_rng(1).random((args.size, args.size)) * 0.5
    counts = [int(count) for count in args.counts.split(",")]
    with tempfile.TemporaryDirectory() as directory:
        results = {}
        for count in counts:
            path = Path(directory) / f"bands-{count}.tif"
            _write(path, base, count)
            results[count] = _warp_first_band(path, args.size, count)
    reference = results[counts[0]]
    for count, out in results.items():
        both_nan = numpy.isnan(reference) & numpy.isnan(out)
        same = both_nan | (reference.view("uint64") == out.view("uint64"))
        valid = ~numpy.isnan(reference) & ~numpy.isnan(out)
        delta = numpy.abs(reference - out)[valid]
        print(
            f"{count} bands: band 1 differs in {int((~same).sum())} of {reference.size} pixels, "
            f"valid/NaN swapped in {int((numpy.isnan(reference) != numpy.isnan(out)).sum())}, "
            f"largest difference {float(delta.max()) if delta.size else 0.0:.3g}"
        )


if __name__ == "__main__":
    main()
