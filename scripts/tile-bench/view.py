#!/usr/bin/env python3
"""One map view as the browser asks for it (NM4-26): S scenes, a block of tiles each, over at most C connections.

    python scripts/tile-bench/view.py [--mode ndvi|visual] [--scenes 13] [--z 11] [--side 5] [--tilesize 256]
        [--conns 6] [--out view.jsonl]

The default is the NDVI preview Otto measured on 25.10.2026: 13 scenes x 5 x 5 tiles of 256 px = 325 requests, each
scene its own layer as ``processingPreview.ts`` builds them. ``--conns 6`` is the browser's limit per host on HTTP/1.1;
the requests are all issued at once and wait for a connection, as they do in the browser. Prints one JSON line:
wall time and the client-side times (waiting for a connection included, as DevTools shows them).
"""

import argparse
import asyncio
import json
import time
import urllib.parse

import httpx
import morecantile

NDVI = "&".join([
    "asset=red", "asset=nir", "op=band_math", "op_version=1",
    "params=" + urllib.parse.quote(json.dumps({"expression": "(nir-red)/(nir+red)"}, separators=(",", ":"))),
    "rescale=-1,1", "colormap_name=rdylgn",
])
CENTRE = (11.05, 47.35)


def scene_ids(count: int) -> list[str]:
    return [f"SYNTH_T32TPT_202608{day:02d}T102039_L2A" for day in range(1, count + 1)]


def tile_urls(base: str, mode: str, scenes: int, z: int, side: int, tilesize: int) -> list[str]:
    query = (NDVI if mode == "ndvi" else "asset=visual") + (f"&tilesize={tilesize}" if tilesize != 256 else "")
    centre = morecantile.tms.get("WebMercatorQuad").tile(*CENTRE, z)
    half = side // 2
    tiles = [(centre.x + dx, centre.y + dy) for dy in range(-half, half + 1) for dx in range(-half, half + 1)]
    return [f"{base}/collections/sentinel-2-c1-l2a/items/{scene}/tiles/WebMercatorQuad/{z}/{x}/{y}.png?{query}"
            for x, y in tiles for scene in scene_ids(scenes)]


async def run(urls: list[str], conns: int, out: str) -> dict:
    limits = httpx.Limits(max_connections=conns, max_keepalive_connections=conns)
    records = []
    async with httpx.AsyncClient(limits=limits, timeout=300) as client:
        t0 = time.perf_counter()

        async def one(url: str) -> None:
            started = time.perf_counter()
            response = await client.get(url)
            records.append({"ms": round((time.perf_counter() - started) * 1000), "status": response.status_code,
                            "bytes": len(response.content)})

        await asyncio.gather(*(one(url) for url in urls))
        wall = time.perf_counter() - t0
    with open(out, "w") as file:
        file.writelines(json.dumps(record) + "\n" for record in records)
    ms = sorted(record["ms"] for record in records)
    ok = sum(record["status"] == 200 for record in records)
    return {"requests": len(records), "ok": ok, "wall_s": round(wall, 1),
            "client_ms_p50": ms[len(ms) // 2], "client_ms_p90": ms[int(len(ms) * 0.9)], "client_ms_max": ms[-1]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8101")
    parser.add_argument("--mode", choices=("ndvi", "visual"), default="ndvi")
    parser.add_argument("--scenes", type=int, default=13)
    parser.add_argument("--z", type=int, default=11)
    parser.add_argument("--side", type=int, default=5)
    parser.add_argument("--tilesize", type=int, default=256)
    parser.add_argument("--conns", type=int, default=6)
    parser.add_argument("--out", default="view.jsonl")
    args = parser.parse_args()
    urls = tile_urls(args.base, args.mode, args.scenes, args.z, args.side, args.tilesize)
    print(json.dumps(asyncio.run(run(urls, args.conns, args.out))))


if __name__ == "__main__":
    main()
