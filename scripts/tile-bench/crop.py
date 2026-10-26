#!/usr/bin/env python3
"""One AOI crop through the tiler's download route (NM4-26): its time, and a hash of each raster in the ZIP.

    python scripts/tile-bench/crop.py [--size 0.1] [--assets red nir]

The AOI is a square of ``--size`` degrees around the middle of the synthetic scene, read at native resolution. The
hashes cover the raster files only: the recipe and the texts carry the time of the request.
"""

import argparse
import hashlib
import io
import json
import time
import zipfile

import httpx
from view import CENTRE, scene_ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8101")
    parser.add_argument("--size", type=float, default=0.1)
    parser.add_argument("--assets", nargs="+", default=["red", "nir"])
    args = parser.parse_args()
    lon, lat = CENTRE
    half = args.size / 2
    ring = [[lon - half, lat - half], [lon + half, lat - half], [lon + half, lat + half], [lon - half, lat + half],
            [lon - half, lat - half]]
    body = {"groups": [scene_ids(1)], "assets": args.assets, "aoi": {"type": "Polygon", "coordinates": [ring]},
            "resolution": 1}
    started = time.perf_counter()
    response = httpx.post(f"{args.base}/collections/sentinel-2-c1-l2a/download", json=body, timeout=600)
    seconds = time.perf_counter() - started
    hashes = {}
    if response.status_code == 200:
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            hashes = {name: hashlib.sha256(archive.read(name)).hexdigest()[:16]
                      for name in archive.namelist() if name.endswith(".tif")}
    print(json.dumps({"status": response.status_code, "s": round(seconds, 2), "bytes": len(response.content),
                      "rasters": hashes}))


if __name__ == "__main__":
    main()
