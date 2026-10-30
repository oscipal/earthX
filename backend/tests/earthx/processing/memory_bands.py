"""One raster job with many bands in a process of its own, for its peak memory against the estimate (NM4-43c, adr/0020 §7).

Called by ``test_memory_bands.py`` and by ``scripts/nm4-43-bands/memory.py`` as ``python -m tests.earthx.processing.memory_bands
<scene> <workdir> <size> <bands> <results> <output> <scenes>``. The scene is one COG with ``bands`` bands, read as the
asset ``big`` (``big_1`` … ``big_<n>``) behind ``scenes`` addresses, one overpass in one mosaic. The job applies
``results`` real ``band_math`` steps (version 2) that each add a band, so the stock grows as it does in a run, and keeps
all bands (``output`` ``all``) or only the results. It prints one JSON line: peak resident memory (``VmHWM``), the
estimate of the same recipe and the time. Nothing here opens a socket; ``boto3`` is hidden as in ``memory_run.py``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from tests.earthx.processing.memory_run import high_water_mb


def main(scene: Path, workdir: Path, size: int, bands: int, results: int, output: str, scenes: int) -> dict:
    # Imported here, after `boto3` is hidden, as in `memory_run.py`.
    import earthx.readers.access as read_access
    import earthx.readers.cog as cog_reader
    from earthx.processing import plan, run, worker_environment
    from earthx.processing.operators import REGISTRY
    from tests.earthx.processing import sources
    from tests.earthx.processing.recipes import recipe_of_data, resolved

    files = {sources.url(f"scene_{index}"): str(scene) for index in range(scenes)}
    cog_reader.vsicurl_path = lambda checked: files[getattr(checked, "url", str(checked))]
    read_access.resolve_host = lambda host, port=443: ("93.184.216.34",)
    read_access.GDAL_CACHEMAX_BYTES = 64 * 1024 * 1024
    names = [f"ITEM_{index}" for index in range(scenes)]
    entries = []
    for index, name in enumerate(names):
        entry = resolved(name, "big", href=sources.url(f"scene_{index}"))
        entry["bands"] = entry["bands"] * bands
        entries.append(entry)
    steps = []
    for index in range(results):
        first, second = (2 * index) % bands + 1, (2 * index + 1) % bands + 1
        expression = f"(big_{second} - big_{first}) / (big_{second} + big_{first})"
        steps.append(
            {"op": "band_math", "op_version": 2, "params": {"expression": expression, "name": f"Result_{index + 1}"}}
        )
    made = [f"Result_{index + 1}" for index in range(results)]
    held = [f"big_{index + 1}" for index in range(bands)] if bands > 1 else ["big"]
    data = {
        "recipe_version": 2,
        "inputs": [{"name": "s2", "dataset": "synthetic", "groups": [names], "assets": ["big"], "resolved": entries}],
        "aoi": sources.whole(size, size),
        "steps": steps,
        "output": {
            "kind": "raster",
            "format": "cog",
            "dtype": "float32",
            "bands": made if output == "results" else [*held, *made],
        },
    }
    recipe = recipe_of_data(data, REGISTRY)
    imports_mb = high_water_mb()
    # The peak is what is measured, so the cap that would refuse a wide job does not apply to the estimate printed with it.
    plan.MAX_JOB_MEMORY_BYTES = 1 << 62
    cost = plan.estimate(recipe, REGISTRY)
    started = time.monotonic()
    with worker_environment():
        result = run(recipe, workdir=workdir, progress=lambda done, total: None, operators=REGISTRY)
    seconds = time.monotonic() - started
    return {
        "size": size,
        "bands": bands,
        "results": results,
        "scenes": scenes,
        "out_bands": len(result.meta.bands),
        "pixels": result.meta.width * result.meta.height,
        "peak_mb": round(high_water_mb(), 1),
        "imports_mb": round(imports_mb, 1),
        "seconds": round(seconds, 2),
        "blocks": result.blocks,
        "result_mb": round(result.path.stat().st_size / 1e6, 1),
        "est_memory_mb": round(cost.memory_bytes / 1e6, 1),
        "est_seconds": round(cost.seconds, 2),
        "est_units": round(cost.units, 2),
    }


if __name__ == "__main__":
    sys.modules["boto3"] = None  # type: ignore[assignment]
    scene, workdir, *numbers, output, scenes = sys.argv[1:]
    size, bands, results = (int(number) for number in numbers)
    print(json.dumps(main(Path(scene), Path(workdir), size, bands, results, output, int(scenes))))
