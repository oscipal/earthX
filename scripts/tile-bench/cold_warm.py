#!/usr/bin/env python3
"""One mosaic tile asked twice of a fresh tiler (NM4-62): cold, then warm, as P1 and P2 of ``adr/0022`` §8.2.

    python scripts/tile-bench/cold_warm.py [--scenes 4] [--z 10] [--tilesize 512] [--mode ndvi]

The tile is the one at the centre of the synthetic scene; the scenes are those of ``view.py``. Prints one JSON line:
the status of both answers and their times in s.
"""

import argparse
import json
import time

import httpx
from view import block_tiles, tile_urls


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8101")
    parser.add_argument("--mode", choices=("ndvi", "visual"), default="ndvi")
    parser.add_argument("--scenes", type=int, default=4)
    parser.add_argument("--z", type=int, default=10)
    parser.add_argument("--tilesize", type=int, default=512)
    args = parser.parse_args()
    [url] = tile_urls(block_tiles(args.z, 1), args.base, args.mode, args.scenes, args.tilesize, mosaic=True)
    out: dict = {"status": []}
    with httpx.Client(timeout=600) as client:
        for name in ("cold_s", "warm_s"):
            started = time.perf_counter()
            response = client.get(url)
            out[name] = round(time.perf_counter() - started, 3)
            out["status"].append(response.status_code)
            out["bytes"] = len(response.content)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
