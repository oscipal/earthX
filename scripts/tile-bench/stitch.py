#!/usr/bin/env python3
"""A 512 px tile against the four 256 px tiles of the same area (NM4-29), through the tiler of ``bench.sh``.

    CLIENT=stitch.py scripts/tile-bench/bench.sh <tag> [--scenes 2]

Tile ``z/x/y`` at 512 px covers what ``z+1`` covers with ``2x/2y`` to ``2x+1/2y+1`` at 256 px, at the same pixel
size. Per level and mode the four are put together and compared with the large one, as GeoTIFF (the values, not the
PNG): NDVI and ``visual`` of one scene, and the NDVI mosaic of ``--scenes`` scenes (the scenes of ``view.py`` share
one footprint, so the first fills it). Levels: 10 (overview), 13 (the native level of 10 m at 47° N for 512 px, z14
for 256 px) and 15 (above it). Prints one line per comparison: pixels compared and how many differ.
"""

import argparse
import json

import httpx
import numpy
from rasterio.io import MemoryFile
from view import CENTRE, NDVI, TMS, scene_ids

BASE = "http://127.0.0.1:8101/collections/sentinel-2-c1-l2a"


def read(client: httpx.Client, url: str) -> numpy.ma.MaskedArray:
    response = client.get(url)
    response.raise_for_status()
    with MemoryFile(response.content) as memory, memory.open() as dataset:
        data = dataset.read()
    *bands, alpha = data
    return numpy.ma.masked_array(numpy.stack(bands), mask=numpy.broadcast_to(alpha <= 0, (len(bands), *alpha.shape)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=int, default=2)
    args = parser.parse_args()
    scene = scene_ids(1)[0]
    items = "&".join(f"item={item}" for item in sorted(scene_ids(args.scenes)))
    paths = {
        "ndvi": (f"{BASE}/items/{scene}/tiles/WebMercatorQuad", NDVI),
        "visual": (f"{BASE}/items/{scene}/tiles/WebMercatorQuad", "asset=visual"),
        "ndvi-mosaic": (f"{BASE}/mosaic/tiles/WebMercatorQuad", f"{items}&{NDVI}"),
    }
    with httpx.Client(timeout=300) as client:
        for mode, (path, query) in paths.items():
            for z in (10, 13, 15):
                tile = TMS.tile(*CENTRE, z)
                large = read(client, f"{path}/{z}/{tile.x}/{tile.y}.tif?{query}&tilesize=512")
                small = numpy.ma.zeros(large.shape, dtype=large.dtype)
                for dy in (0, 1):
                    for dx in (0, 1):
                        part = read(client, f"{path}/{z + 1}/{2 * tile.x + dx}/{2 * tile.y + dy}.tif?{query}")
                        small[:, dy * 256:(dy + 1) * 256, dx * 256:(dx + 1) * 256] = part
                mask_differs = numpy.ma.getmaskarray(large) != numpy.ma.getmaskarray(small)
                valid = ~numpy.ma.getmaskarray(large) & ~numpy.ma.getmaskarray(small)
                value_differs = valid & (numpy.ma.getdata(large) != numpy.ma.getdata(small))
                print(json.dumps({"mode": mode, "z512": z, "z256": z + 1, "pixels": int(valid.sum()),
                                  "mask_differs": int(mask_differs.sum()), "value_differs": int(value_differs.sum())}))


if __name__ == "__main__":
    main()
