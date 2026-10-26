#!/usr/bin/env python3
"""A SHA-256 per tile for a fixed set of tiles (NM4-26), to compare the bytes of two GDAL settings.

    python scripts/tile-bench/hashes.py <out.txt>

Three neighbouring tiles each for NDVI and ``visual`` on z11/256, z10/512 and z14/256 of the first synthetic scene.
Run it against two tilers and ``diff`` the files.
"""

import hashlib
import sys

import httpx
import morecantile
from view import CENTRE, NDVI, scene_ids


def main() -> None:
    lines = []
    scene = scene_ids(1)[0]
    for mode, query in (("ndvi", NDVI), ("visual", "asset=visual")):
        for z, size in ((11, 256), (10, 512), (14, 256)):
            centre = morecantile.tms.get("WebMercatorQuad").tile(*CENTRE, z)
            for dx in (-1, 0, 1):
                url = (f"http://127.0.0.1:8101/collections/sentinel-2-c1-l2a/items/{scene}/tiles/WebMercatorQuad/"
                       f"{z}/{centre.x + dx}/{centre.y}.png?{query}" + ("&tilesize=512" if size == 512 else ""))
                response = httpx.get(url, timeout=120)
                digest = hashlib.sha256(response.content).hexdigest()[:16]
                lines.append(f"{mode} z{z} {size}px dx={dx} {response.status_code} {digest}")
    with open(sys.argv[1], "w") as file:
        file.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
