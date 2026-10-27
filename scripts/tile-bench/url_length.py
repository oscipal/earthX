#!/usr/bin/env python3
"""The length of a mosaic tile URL with steps (NM4-04 §7.7), encoded as the frontend's ``URLSearchParams`` does.

    python -I scripts/tile-bench/url_length.py

Item ids are placeholders of the length the sources give theirs (Earth Search 30 characters, the Zarr collection
about 60); the length is all that counts. The parameters are canonical JSON, as ``processing.ts`` sends them.
"""

import json
from urllib.parse import urlencode

PATH = "/api/tiler/collections/sentinel-2-l2a-zarr3/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}?"
DISPLAY = "&rescale=-1%2C1&colormap_name=rdylgn"

NDVI = ("band_math", {"expression": "(nir - red) / (nir + red)"})
NDVI_ZARR = ("band_math", {"expression": "(b08 - b04) / (b08 + b04)"})
MASK = ("mask", {"source": "scl", "classes": [0, 1, 3, 8, 9, 10]})
NORMALIZE = ("normalize", {"in_min": -1, "in_max": 1, "out_min": 0, "out_max": 1, "clip": True})


def length(items: int, id_length: int, assets: list[str], steps: list[tuple[str, dict]]) -> int:
    query = [("item", "x" * id_length) for _ in range(items)] + [("asset", asset) for asset in assets]
    for op, params in steps:
        query += [("op", op), ("op_version", "1"), ("params", json.dumps(params, separators=(",", ":"), sort_keys=True))]
    return len(PATH) + len(urlencode(query)) + len(DISPLAY)


def main() -> None:
    print("Sentinel-2 C1, 64 x 30, red+nir, NDVI:", length(64, 30, ["red", "nir"], [NDVI]))
    print("same with scl, mask -> NDVI -> normalize:", length(64, 30, ["red", "nir", "scl"], [MASK, NDVI, NORMALIZE]))
    zarr = ["SR_10m:b04", "SR_10m:b08", "SCL_20m:scl"]
    print("Zarr, 64 x 60, 3 assets, the same chain:", length(64, 60, zarr, [MASK, NDVI_ZARR, NORMALIZE]))
    escaped = urlencode([("params", "(" * 2048)])
    worst = len(PATH) + 64 * len("item=" + "x" * 60 + "&") + 16 * len("asset=" + "x" * 30 + "&")
    worst += 4 * (len("op=band_math&op_version=1&") + len(escaped) + 1) + len(DISPLAY)
    print("worst: 64 x 60, 16 assets of 30, 4 x params of 2048 characters, all escaped:", worst)


if __name__ == "__main__":
    main()
