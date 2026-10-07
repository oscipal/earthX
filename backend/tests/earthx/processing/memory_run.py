"""One T2 run in a process of its own, for the peak memory of adr/0014 §3.5 (plan M4-07a §3.8, F10).

Called by ``test_memory_8192.py`` as ``python -m tests.earthx.processing.memory_run
<cog> <workdir> <size> [<GDAL_CACHEMAX in MB> [<step>]]``, ``size`` being the side of the
square scene in pixels. It puts the COG behind the same two
seams the tests use — ``vsicurl_path`` and the resolver — enters
``worker_environment()`` in its main thread as a `jobs` child does (adr/0013 §5.3),
runs one step over both bands — the test operator ``scale``, or with ``step`` set to
``reproject`` the platform's ``reproject`` to EPSG:3035 with ``bilinear`` — and prints one JSON line: peak
resident memory in MB, the resident memory after the imports, seconds and blocks.
Nothing here opens a socket.

**Peak memory is ``VmHWM``, not ``ru_maxrss``.** On Linux ``ru_maxrss`` survives
``exec``: a process started from a parent that once held 1.4 GB reports at least
that much, whatever it did itself (measured: 1494 MB under pytest against 471 MB
for the same run started from a shell). ``VmHWM`` belongs to the address space,
which ``exec`` replaces.

**As in the image, without ``boto3``.** ``rasterio.session`` imports ``boto3`` when
it is installed; only the development environment has it, through ``moto``
(M4-06). It is hidden before the first import, as in ``test_import_is_pure.py``,
so the measured child carries what a child in the image carries.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


def high_water_mb() -> float:
    """Peak resident memory of this address space, from ``/proc/self/status``."""
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1]) / 1024
    raise RuntimeError("no VmHWM in /proc/self/status")


STEPS = {
    "scale": {"op": "scale", "op_version": 1, "params": {"factor": 2.0}},
    "reproject": {
        "op": "reproject",
        "op_version": 1,
        "params": {"crs": "EPSG:3035", "resolution": 10.0, "resampling": "bilinear"},
    },
}


def main(cog: Path, workdir: Path, size: int, cachemax_mb: int | None, step: str = "scale") -> None:
    # Imported here, after `boto3` is hidden (module docstring), not at the top.
    import earthx.readers.access as read_access
    import earthx.readers.cog as cog_reader
    from earthx.processing import run, worker_environment
    from earthx.processing.recipe import recipe_from_data
    from tests.earthx.processing import sources
    from tests.earthx.processing.recipes import resolved
    from tests.earthx.processing.testops import OPERATORS

    address = sources.url("big")
    cog_reader.vsicurl_path = lambda checked: str(cog)
    read_access.resolve_host = lambda host, port=443: ("93.184.216.34",)
    if cachemax_mb is not None:
        read_access.GDAL_CACHEMAX_BYTES = cachemax_mb * 1024 * 1024
    entry = resolved("ITEM_BIG", "big", href=address)
    entry["bands"] = entry["bands"] * 2
    data = {
        "recipe_version": 1,
        "inputs": [
            {"name": "s2", "dataset": "synthetic", "groups": [["ITEM_BIG"]], "assets": ["big"], "resolved": [entry]}
        ],
        "aoi": sources.whole(size, size),
        "steps": [STEPS[step]],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }
    recipe = recipe_from_data(data, OPERATORS)
    imports_mb = high_water_mb()
    started = time.monotonic()
    with worker_environment():
        result = run(recipe, workdir=workdir, progress=lambda done, total: None, operators=OPERATORS)
    seconds = time.monotonic() - started
    measured = {
        "peak_mb": round(high_water_mb(), 1),
        "imports_mb": round(imports_mb, 1),
        "seconds": round(seconds, 2),
        "blocks": result.blocks,
    }
    print(json.dumps(measured))


if __name__ == "__main__":
    sys.modules["boto3"] = None  # type: ignore[assignment]
    main(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        int(sys.argv[3]),
        int(sys.argv[4]) if len(sys.argv) > 4 else None,
        sys.argv[5] if len(sys.argv) > 5 else "scale",
    )
