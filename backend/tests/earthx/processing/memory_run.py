"""One T2 run in a process of its own, for the peak memory of adr/0014 §3.5 (plan M4-07a §3.8, F10).

Called by ``test_memory_8192.py`` as ``python -m tests.earthx.processing.memory_run
<cog> <workdir> <size> [<GDAL_CACHEMAX in MB> [<step> [<layer>]]]``, ``size`` being the side of the
square scene in pixels. It puts the COG behind the same two
seams the tests use — ``vsicurl_path`` and the resolver — enters
``worker_environment()`` in its main thread as a `jobs` child does (adr/0013 §5.3),
runs one step over every band of the COG (two, or more since NM4-43b) — the test operator ``scale``, or with ``step`` set to
``reproject`` the platform's ``reproject`` to EPSG:3035 with ``bilinear`` at 10 m, with
``reproject-lanczos`` with ``lanczos`` at 30 m, with ``normalize`` the platform's
``normalize`` over its bands (``normalize-zscore``, ``-percentile`` and ``-robust``: version 3, NM4-11), with ``mask-values`` the platform's ``mask_values`` (DS-06), with ``mask`` its ``mask`` over its bands and the 20 m
classification layer ``layer`` (a second COG, M4-18) — and prints one JSON line: peak
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
        "op_version": 4,
        "params": {"crs": "EPSG:3035", "resolution": 10.0, "resampling": "bilinear"},
    },
    # The highest peak of plan M4-24 §7.5: lanczos, coarsening by 3.
    "reproject-lanczos": {
        "op": "reproject",
        "op_version": 4,
        "params": {"crs": "EPSG:3035", "resolution": 30.0, "resampling": "lanczos"},
    },
    # M4-18: the two pixel operators, in the pass that reads the scene.
    "normalize": {
        "op": "normalize",
        "op_version": 1,
        "params": {"in_min": 0.0, "in_max": 0.5, "out_min": 0.0, "out_max": 255.0, "clip": True},
    },
    "mask": {"op": "mask", "op_version": 1, "params": {"source": "scl", "classes": [3, 8, 9, 10]}},
}

#: NM4-11: the methods of ``normalize`` version 3 over the two bands of the scene (``big_1``, ``big_2``). A recipe of
#: version 2, because only it names the bands the step converts.
_V3_BANDS = ["big_1", "big_2"]
STEPS_V3 = {
    "normalize-zscore": {
        "method": "zscore",
        "bands": _V3_BANDS,
        "measured": {
            "factor": 1,
            "bands": {"big_1": {"mean": 0.3, "stddev": 0.1}, "big_2": {"mean": 0.5, "stddev": 0.2}},
        },
    },
    "normalize-percentile": {
        "method": "percentile",
        "bands": _V3_BANDS,
        "low": 2,
        "high": 98,
        "out_min": 0.0,
        "out_max": 1.0,
        "clip": True,
        "measured": {
            "factor": 1,
            "bands": {"big_1": {"p_low": 0.1, "p_high": 0.6}, "big_2": {"p_low": 0.2, "p_high": 0.9}},
        },
    },
    "normalize-robust": {
        "method": "robust",
        "bands": _V3_BANDS,
        "measured": {
            "factor": 1,
            "bands": {
                "big_1": {"p25": 0.2, "median": 0.3, "p75": 0.4},
                "big_2": {"p25": 0.3, "median": 0.5, "p75": 0.7},
            },
        },
    },
}

#: DS-06: ``mask_values`` over the two bands of the scene, in a recipe of version 2 like the methods above.
STEPS_V2 = {
    "mask-values": {
        "op": "mask_values",
        "op_version": 1,
        "params": {"band": "big_1", "condition": "between", "values": [0.2, 0.6]},
    },
}


def _step(name: str) -> dict:
    if name in STEPS:
        return STEPS[name]
    if name in STEPS_V2:
        return STEPS_V2[name]
    return {"op": "normalize", "op_version": 3, "params": STEPS_V3[name]}


def main(
    cog: Path, workdir: Path, size: int, cachemax_mb: int | None, step: str = "scale", layer: Path | None = None
) -> None:
    # Imported here, after `boto3` is hidden (module docstring), not at the top.
    import rasterio

    import earthx.readers.access as read_access
    import earthx.readers.cog as cog_reader
    from earthx.processing import run, worker_environment
    from tests.earthx.processing import sources
    from tests.earthx.processing.recipes import resolved
    from tests.earthx.processing.testops import OPERATORS

    address = sources.url("big")
    layer_address = sources.url("scl")
    files = {address: str(cog)} | ({layer_address: str(layer)} if layer is not None else {})
    cog_reader.vsicurl_path = lambda checked: files[getattr(checked, "url", str(checked))]
    read_access.resolve_host = lambda host, port=443: ("93.184.216.34",)
    if cachemax_mb is not None:
        read_access.GDAL_CACHEMAX_BYTES = cachemax_mb * 1024 * 1024
    with rasterio.open(cog) as scene:
        bands = scene.count
    entry = resolved("ITEM_BIG", "big", href=address)
    entry["bands"] = entry["bands"] * bands
    entries, assets = [entry], ["big"]
    if layer is not None:
        classes = resolved("ITEM_BIG", "scl", href=layer_address, scale=None, offset=None)
        classes["bands"] = [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}]
        entries.append(classes)
        assets.append("scl")
    data = {
        "recipe_version": 1,
        "inputs": [
            {"name": "s2", "dataset": "synthetic", "groups": [["ITEM_BIG"]], "assets": assets, "resolved": entries}
        ],
        "aoi": sources.whole(size, size),
        "steps": [_step(step)],
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }
    if step in STEPS_V3 or step in STEPS_V2:
        data["recipe_version"] = 2
        data["output"]["bands"] = _V3_BANDS
    from tests.earthx.processing.recipes import recipe_of_data

    recipe = recipe_of_data(data, OPERATORS)
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
        Path(sys.argv[6]) if len(sys.argv) > 6 else None,
    )
