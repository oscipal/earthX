"""One mosaic job in a process of its own, for its peak memory and time with one, two and eight scenes (M4-12a).

Called by ``test_memory_mosaic.py`` as ``python -m tests.earthx.processing.memory_mosaic <cog>
<workdir> <size> <scenes> [<cog in another zone>]``. Every scene is the same file behind its own
address; the file has a nodata stripe in every block, so the mosaic never fills a block from the
first scene alone and reads each scene for every block. With a file in another zone the last
scene is that one, warped onto the grid of the others. It enters ``worker_environment()`` as a
`jobs` child does and prints one JSON line: peak resident memory (``VmHWM``) in MB, seconds,
blocks and the seconds the estimate gave. Nothing here opens a socket; ``boto3`` is hidden as in
``memory_run.py``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from tests.earthx.processing.memory_run import high_water_mb


def main(cog: Path, workdir: Path, size: int, scenes: int, other_zone: Path | None) -> None:
    import earthx.readers.access as read_access
    import earthx.readers.cog as cog_reader
    from earthx.processing import run, worker_environment
    from earthx.processing.plan import estimate
    from earthx.processing.recipe import recipe_from_data
    from tests.earthx.processing import sources
    from tests.earthx.processing.testops import OPERATORS

    files = {sources.url(f"scene_{index}"): cog for index in range(scenes)}
    if other_zone is not None:
        files[sources.url(f"scene_{scenes - 1}")] = other_zone
    cog_reader.vsicurl_path = lambda checked: str(files[getattr(checked, "url", str(checked))])
    read_access.resolve_host = lambda host, port=443: ("93.184.216.34",)
    names = [f"ITEM_{index}" for index in range(scenes)]
    entries = []
    for index, name in enumerate(names):
        crs = "EPSG:32633" if other_zone is not None and index == scenes - 1 else sources.CRS
        entries.append(
            {
                "asset": {
                    "dataset_id": "synthetic", "item_id": name, "asset": "visual", "reader": "cog",
                    "href": sources.url(f"scene_{index}"), "variable": None, "crs": crs,
                },
                "version": None,
                "bands": [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}] * 3,
                "scaling": "none",
                "gsd": sources.RESOLUTION,
            }  # fmt: skip
        )
    data = {
        "recipe_version": 1,
        "inputs": [{"name": "input", "dataset": "synthetic", "groups": [names], "assets": ["visual"], "resolved": entries}],
        "aoi": sources.whole(size, size),
        "steps": [],
        "output": {"kind": "raster", "format": "cog", "dtype": "uint8"},
    }
    recipe = recipe_from_data(data, OPERATORS)
    estimate_seconds = estimate(recipe, OPERATORS).seconds
    started = time.monotonic()
    with worker_environment():
        result = run(recipe, workdir=workdir, progress=lambda done, total: None, operators=OPERATORS)
    print(
        json.dumps(
            {
                "peak_mb": round(high_water_mb(), 1),
                "seconds": round(time.monotonic() - started, 2),
                "blocks": result.blocks,
                "estimate_seconds": round(estimate_seconds, 2),
                "width": result.meta.width,
                "height": result.meta.height,
            }
        )
    )


if __name__ == "__main__":
    sys.modules["boto3"] = None  # type: ignore[assignment]
    main(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), Path(sys.argv[5]) if len(sys.argv) > 5 else None)
