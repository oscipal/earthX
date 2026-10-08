"""One export in a process of its own, for its peak memory with one and with two items (M4-11a).

Called by ``test_memory_export.py`` as ``python -m tests.earthx.processing.memory_export
<cog> <workdir> <size> <items>``. Every item is the same scene behind its own address;
the scene has a nodata stripe in every block, so the mosaic never fills a block from the
first item alone and reads each item for every block. It enters ``worker_environment()``
as a `jobs` child does and prints one JSON line: peak resident memory (``VmHWM``) in MB,
seconds, blocks and the size of ``export.zip``. Nothing here opens a socket; ``boto3`` is
hidden as in ``memory_run.py``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from tests.earthx.processing.memory_run import high_water_mb


def main(cog: Path, workdir: Path, size: int, items: int) -> None:
    import earthx.readers.access as read_access
    import earthx.readers.cog as cog_reader
    from earthx.processing import run, worker_environment
    from earthx.processing.export import Attachments
    from earthx.processing.recipe import recipe_from_data
    from tests.earthx.processing import sources
    from tests.earthx.processing.recipes import CROP
    from tests.earthx.processing.testops import OPERATORS

    cog_reader.vsicurl_path = lambda checked: str(cog)
    read_access.resolve_host = lambda host, port=443: ("93.184.216.34",)
    names = [f"ITEM_{index}" for index in range(items)]
    aoi = sources.whole(size, size)
    data = {
        "recipe_version": 1,
        "inputs": [
            {
                "name": "input",
                "dataset": "synthetic",
                "groups": [names],
                "assets": ["visual"],
                "resolved": [
                    {
                        "asset": {
                            "dataset_id": "synthetic", "item_id": name, "asset": "visual", "reader": "cog",
                            "href": sources.url(name.lower()), "variable": None, "crs": sources.CRS,
                        },
                        "version": None,
                        "bands": [{"data_type": "uint8", "nodata": 0, "scale": None, "offset": None}] * 3,
                        "scaling": "none",
                        "gsd": sources.RESOLUTION,
                    }  # fmt: skip
                    for name in names
                ],
                "footprints": {name: aoi for name in names},
            }
        ],
        "aoi": aoi,
        "steps": [],
        "output": CROP,
    }
    recipe = recipe_from_data(data, OPERATORS)
    attachments = Attachments(
        files={"ATTRIBUTION.txt": "synthetic\n", "citation.bib": "@misc{synthetic}\n", "aoi.geojson": json.dumps(aoi)},
        attribution=(),
    )
    started = time.monotonic()
    with worker_environment():
        result = run(recipe, workdir=workdir, progress=lambda done, total: None, attachments=attachments)
    print(
        json.dumps(
            {
                "peak_mb": round(high_water_mb(), 1),
                "seconds": round(time.monotonic() - started, 2),
                "blocks": result.blocks,
                "zip_bytes": result.path.stat().st_size,
            }
        )
    )


if __name__ == "__main__":
    sys.modules["boto3"] = None  # type: ignore[assignment]
    main(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
