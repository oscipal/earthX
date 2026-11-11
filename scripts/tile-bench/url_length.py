#!/usr/bin/env python3
"""The length of a mosaic tile URL with steps (NM4-04 §7.7), encoded as the frontend's ``URLSearchParams`` does.

    python -I scripts/tile-bench/url_length.py

Since the selection of a mosaic (adr/0032 §10.2) the URL names the selection by an id of 32 characters; the scenes and
the assets are in the body of its creation and no longer count. What is left is the steps and the display. The
parameters are canonical JSON, as ``processing.ts`` sends them.
"""

import json
from urllib.parse import urlencode

PATH = "/api/tiler/collections/sentinel-2-l2a-zarr3/mosaic/" + "0" * 32 + "/tiles/WebMercatorQuad/{z}/{x}/{y}?"
DISPLAY = "&rescale=-1%2C1&colormap_name=rdylgn"

NDVI = ("band_math", {"expression": "(nir - red) / (nir + red)"})
NDVI_ZARR = ("band_math", {"expression": "(b08 - b04) / (b08 + b04)"})
MASK = ("mask", {"source": "scl", "classes": [0, 1, 3, 8, 9, 10]})
NORMALIZE = ("normalize", {"in_min": -1, "in_max": 1, "out_min": 0, "out_max": 1, "clip": True})


def length(steps: list[tuple[str, dict]]) -> int:
    query = []
    for op, params in steps:
        query += [("op", op), ("op_version", "1"), ("params", json.dumps(params, separators=(",", ":"), sort_keys=True))]
    return len(PATH) + len(urlencode(query)) + len(DISPLAY)


def main() -> None:
    print("NDVI:", length([NDVI]))
    print("mask -> NDVI -> normalize:", length([MASK, NDVI, NORMALIZE]))
    print("the Zarr chain:", length([MASK, NDVI_ZARR, NORMALIZE]))
    escaped = urlencode([("params", "(" * 2048)])
    worst = len(PATH) + 4 * (len("op=band_math&op_version=1&") + len(escaped) + 1) + len(DISPLAY)
    print("worst: 4 x params of 2048 characters, all escaped (the number of scenes and assets does not matter):", worst)


if __name__ == "__main__":
    main()
