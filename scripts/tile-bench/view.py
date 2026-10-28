#!/usr/bin/env python3
"""One map view as the browser asks for it (NM4-26): S scenes, a block of tiles each, over at most C connections.

    python scripts/tile-bench/view.py [--mode ndvi|visual] [--scenes 13] [--z 11] [--side 5] [--tilesize 256]
        [--viewport 1280x800 --map-zoom 10] [--mosaic] [--conns 6] [--out view.jsonl]

The default is the NDVI preview Otto measured on 25.10.2026: 13 scenes x 5 x 5 tiles of 256 px = 325 requests, each
scene its own layer as ``processingPreview.ts`` builds them. ``--conns 6`` is the browser's limit per host on HTTP/1.1;
the requests are all issued at once and wait for a connection, as they do in the browser. Prints one JSON line:
wall time and the client-side times (waiting for a connection included, as DevTools shows them).

``--viewport WxH --map-zoom Z`` (NM4-29) replaces the block of ``--z``/``--side``: the tiles MapLibre asks for a map
of W x H CSS pixels at map zoom Z, centred on the scene, for a raster source of ``--tilesize`` px. MapLibre's world
is 512 px at zoom 0 and a raster source rounds, so the level is ``round(Z + log2(512 / tilesize))``; tiles outside
the scene's footprint are not asked, as a source with ``bounds`` does not. ``--mosaic`` asks one mosaic tile of all
scenes per position (``/mosaic/tiles/...``) instead of one tile per scene.
"""

import argparse
import asyncio
import json
import math
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
FOOTPRINT = (10.3119, 46.8326, 11.8028, 47.8459)  # run_tiler.py
TMS = morecantile.tms.get("WebMercatorQuad")


def scene_ids(count: int) -> list[str]:
    return [f"SYNTH_T32TPT_202608{day:02d}T102039_L2A" for day in range(1, count + 1)]


def block_tiles(z: int, side: int) -> list[tuple[int, int, int]]:
    centre = TMS.tile(*CENTRE, z)
    half = side // 2
    return [(z, centre.x + dx, centre.y + dy) for dy in range(-half, half + 1) for dx in range(-half, half + 1)]


def viewport_tiles(width: int, height: int, map_zoom: float, tilesize: int) -> list[tuple[int, int, int]]:
    """The tiles of a north-up map of ``width`` x ``height`` px at ``map_zoom``, as MapLibre covers them."""
    z = math.floor(map_zoom + math.log2(512 / tilesize) + 0.5)
    n = 2**z
    on_screen = 512 * 2**map_zoom / n  # CSS px of one tile
    lon, lat = CENTRE
    cx = (lon + 180) / 360 * n
    cy = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    hx, hy = width / 2 / on_screen, height / 2 / on_screen
    inside = {(t.x, t.y) for t in TMS.tiles(*FOOTPRINT, [z])}
    return [(z, x, y) for y in range(math.floor(cy - hy), math.ceil(cy + hy))
            for x in range(math.floor(cx - hx), math.ceil(cx + hx)) if (x, y) in inside]


def tile_urls(tiles: list[tuple[int, int, int]], base: str, mode: str, scenes: int, tilesize: int,
              mosaic: bool = False) -> list[str]:
    query = (NDVI if mode == "ndvi" else "asset=visual") + (f"&tilesize={tilesize}" if tilesize != 256 else "")
    ids = scene_ids(scenes)
    if mosaic:
        items = "&".join(f"item={scene}" for scene in sorted(ids))
        return [f"{base}/collections/sentinel-2-c1-l2a/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}.png?{items}&{query}"
                for z, x, y in tiles]
    return [f"{base}/collections/sentinel-2-c1-l2a/items/{scene}/tiles/WebMercatorQuad/{z}/{x}/{y}.png?{query}"
            for z, x, y in tiles for scene in ids]


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
    parser.add_argument("--viewport", help="WxH in CSS px, with --map-zoom instead of --z/--side")
    parser.add_argument("--map-zoom", type=float)
    parser.add_argument("--mosaic", action="store_true")
    parser.add_argument("--conns", type=int, default=6)
    parser.add_argument("--out", default="view.jsonl")
    args = parser.parse_args()
    if args.viewport:
        width, height = map(int, args.viewport.split("x"))
        tiles = viewport_tiles(width, height, args.map_zoom, args.tilesize)
    else:
        tiles = block_tiles(args.z, args.side)
    urls = tile_urls(tiles, args.base, args.mode, args.scenes, args.tilesize, args.mosaic)
    result = asyncio.run(run(urls, args.conns, args.out))
    print(json.dumps({"level": tiles[0][0], "positions": len(tiles), **result}))


if __name__ == "__main__":
    main()
