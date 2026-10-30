#!/usr/bin/env python3
"""Peak memory and time of a raster job by bands, area and scenes, on synthetic data (NM4-43c PR 2, adr/0020 §7).

    PYTHONPATH=backend python scripts/nm4-43-bands/memory.py scene <file.tif> --size 4096 --bands 17
    PYTHONPATH=backend python scripts/nm4-43-bands/memory.py run <file.tif> <workdir> --size 4096 --bands 17 \\
        [--results 16] [--output all|results] [--scenes 25]

``scene`` writes the synthetic scene of ``tests/earthx/processing/test_memory_8192.py`` with ``--bands`` bands
(``uint16``, a nodata strip, 512 px blocks). ``run`` computes one raster job on it in this process, as a `jobs` child
does, and prints one line of JSON (``tests/earthx/processing/memory_bands.py``): the peak resident memory (``VmHWM``,
not ``ru_maxrss``, which survives ``exec``), the time, the bands in the result and the estimate of the platform for the
same recipe. Start each ``run`` from a shell of its own: the peak is that of the process.

The job reads the scene as the asset ``big`` (``big_1`` … ``big_<n>``) and applies ``--results`` real ``band_math``
steps (version 2), each adding a band, so the stock grows as it does for a user. ``--output all`` keeps every band
(``--bands`` + ``--results``), ``results`` only the results. With ``--scenes`` more than one the same file stands behind
that many addresses, one overpass in one mosaic; the nodata strip of the scene keeps its blocks from being filled by the
first scene alone, so every scene is read for them, the worst case of a mosaic.

Nothing here opens a socket or names a place: the host is reserved and the seam is the one the memory tests use.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["scene", "run"])
    parser.add_argument("path", type=Path, help="the scene: written by `scene`, read by `run`")
    parser.add_argument("workdir", type=Path, nargs="?")
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--bands", type=int, required=True)
    parser.add_argument("--results", type=int, default=0)
    parser.add_argument("--output", choices=["all", "results"], default="all")
    parser.add_argument("--scenes", type=int, default=1)
    args = parser.parse_args()
    if args.mode == "scene":
        from tests.earthx.processing.test_memory_8192 import build_scene

        build_scene(args.path, args.size, bands=args.bands)
        print(json.dumps({"scene": args.path.name, "size": args.size, "bands": args.bands}))
        return
    if args.workdir is None:
        parser.error("run needs a work directory")
    from tests.earthx.processing.memory_bands import main as measure

    args.workdir.mkdir(parents=True, exist_ok=True)
    print(json.dumps(measure(args.path, args.workdir, args.size, args.bands, args.results, args.output, args.scenes)))


if __name__ == "__main__":
    sys.modules["boto3"] = None  # type: ignore[assignment]
    main()
