#!/usr/bin/env python3
"""Does the number of bands in a file change what ``reproject`` gives for one band? (NM4-43, adr/0020 §3.4)

    PYTHONPATH=backend python scripts/nm4-43-bands/warp_bands.py [--op-version 3|4] [--size 2048] [--counts 1,2,3,4,18,34]
    PYTHONPATH=backend python scripts/nm4-43-bands/warp_bands.py --measure [--op-version 3|4] [--size 4096] [--counts 1,4,17] [--interleave band|pixel]

Writes synthetic ``float64`` files in the core's intermediate form (1024 px tiles, NaN as nodata) with
``count`` bands whose first band is always the same, runs the ``reproject`` operator block by block onto
EPSG:3035 with ``bilinear`` as the core does, and compares the first band bit by bit with the first count
given and with the count before it. ``--op-version 3`` is the operator before NM4-43b (all bands in one
warp, adr/0020 §3.4), ``4`` the one that warps each band for itself (default 4).
With ``--measure`` each count runs in a process of its own, in the worker's GDAL environment
(``GDAL_CACHEMAX`` 64 MB), and prints seconds and peak memory (``VmHWM``) of the warp pass.
No source is read; the files live in a temporary directory.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy
import rasterio
from rasterio.transform import Affine
from rasterio.windows import Window

from earthx.processing.core import BLOCK_SIZE, _profile, worker_environment
from earthx.processing.operators import REPROJECT, REPROJECT_V3, ReprojectParams
from earthx.processing.operators.base import BandMeta, RasterMeta

TRANSFORM = Affine(10, 0, 600000, 0, -10, 5200000)
OPERATORS = {3: REPROJECT_V3, 4: REPROJECT}
PARAMS = ReprojectParams.model_validate(
    {"crs": "EPSG:3035", "resolution": 10.0, "resampling": "bilinear", "align": False}
)


def _write(path: Path, base: numpy.ndarray, count: int, interleave: str | None = None) -> None:
    """A pass file as the core writes it (``core._profile``: 1024 px tiles, deflate, NaN as nodata).

    ``interleave`` adds GDAL's ``INTERLEAVE`` to the profile; ``None`` leaves it to GDAL, as the core does.
    """
    size = base.shape[0]
    bands = tuple(BandMeta(f"b{index}", "float64", math.nan) for index in range(count))
    profile = _profile(RasterMeta("EPSG:32632", TRANSFORM, size, size, bands), "float64", math.nan)
    if interleave is not None:
        profile["interleave"] = interleave
    with rasterio.open(path, "w", **profile) as dst:
        for band in range(1, count + 1):
            dst.write(base + (band - 1) * 0.01, band)


def _warp(path: Path, size: int, count: int, operator, keep: bool = True) -> numpy.ndarray | None:
    """The first band of ``path`` after ``operator``; ``keep=False`` only runs the warp."""
    bands = tuple(BandMeta(f"b{index}", "float64", math.nan) for index in range(count))
    target = operator.transform(RasterMeta("EPSG:32632", TRANSFORM, size, size, bands), PARAMS)
    out = numpy.empty((target.height, target.width), dtype="float64") if keep else None
    with rasterio.open(path) as src:
        for row in range(0, target.height, BLOCK_SIZE):
            for col in range(0, target.width, BLOCK_SIZE):
                window = Window(col, row, min(BLOCK_SIZE, target.width - col), min(BLOCK_SIZE, target.height - row))
                data = operator.run(src, target, window, PARAMS)
                if out is not None:
                    out[row : row + int(window.height), col : col + int(window.width)] = numpy.ma.filled(
                        data[0], math.nan
                    )
    return out


def _peak_mb() -> float:
    with open("/proc/self/status") as status:
        return next(int(line.split()[1]) for line in status if line.startswith("VmHWM:")) / 1024


def _make(path: Path, size: int, count: int, interleave: str | None) -> None:
    """Child process: only writes the pass file, so that its own peak is not the one measured."""
    _write(path, numpy.random.default_rng(1).random((size, size)) * 0.5, count, interleave)


def _measure_one(size: int, count: int, op_version: int, interleave: str | None) -> None:
    """Child process: one warp pass over ``count`` bands, printed as JSON."""
    with tempfile.TemporaryDirectory() as directory, worker_environment():
        path = Path(directory) / f"bands-{count}.tif"
        command = [sys.executable, __file__, "--make", str(path), "--size", str(size), "--counts", str(count)]
        subprocess.run([*command, *(["--interleave", interleave] if interleave else [])], check=True)
        before = _peak_mb()
        started = time.perf_counter()
        _warp(path, size, count, OPERATORS[op_version], keep=False)
        seconds = time.perf_counter() - started
    result = {"op_version": op_version, "interleave": interleave or "gdal default", "bands": count}
    result["seconds"] = round(seconds, 1)
    print(json.dumps({**result, "peak_mb": round(_peak_mb()), "peak_mb_before_warp": round(before)}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=2048)
    parser.add_argument("--counts", default="1,2,3,4,18,34")
    parser.add_argument("--op-version", type=int, choices=sorted(OPERATORS), default=4)
    parser.add_argument("--measure", action="store_true")
    parser.add_argument("--interleave", choices=["band", "pixel"], help="for --measure: the file's INTERLEAVE")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--make", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    counts = [int(count) for count in args.counts.split(",")]
    if args.make:
        return _make(args.make, args.size, counts[0], args.interleave)
    if args.child:
        return _measure_one(args.size, counts[0], args.op_version, args.interleave)
    if args.measure:
        for count in counts:
            command = [sys.executable, __file__, "--child", "--size", str(args.size), "--counts", str(count)]
            interleave = ["--interleave", args.interleave] if args.interleave else []
            subprocess.run([*command, "--op-version", str(args.op_version), *interleave], check=True)
        return
    base = numpy.random.default_rng(1).random((args.size, args.size)) * 0.5
    with tempfile.TemporaryDirectory() as directory:
        results = {}
        for count in counts:
            path = Path(directory) / f"bands-{count}.tif"
            _write(path, base, count)
            results[count] = _warp(path, args.size, count, OPERATORS[args.op_version])
    for index, count in enumerate(counts):
        compared = [counts[0]] if index < 2 else [counts[0], counts[index - 1]]
        for other in compared if index else []:
            print(f"{count} against {other} bands: {_difference(results[other], results[count])}")


def _difference(reference: numpy.ndarray, out: numpy.ndarray) -> str:
    """How band 1 of ``out`` differs from ``reference``: pixels, valid/NaN swaps, largest difference."""
    same = (numpy.isnan(reference) & numpy.isnan(out)) | (reference.view("uint64") == out.view("uint64"))
    valid = ~numpy.isnan(reference) & ~numpy.isnan(out)
    delta = numpy.abs(reference - out)[valid]
    return (
        f"band 1 differs in {int((~same).sum())} of {reference.size} pixels, "
        f"valid/NaN swapped in {int((numpy.isnan(reference) != numpy.isnan(out)).sum())}, "
        f"largest difference {float(delta.max()) if delta.size else 0.0:.3g}"
    )


if __name__ == "__main__":
    main()
