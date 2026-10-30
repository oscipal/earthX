#!/usr/bin/env python3
"""Synthetic Sentinel-2 L2A COGs in the layout of Earth Search's (NM4-26).

    python -I scripts/tile-bench/make_cogs.py <cog-dir>

10980 x 10980 pixels in UTM 32N, internal blocks of 1024, DEFLATE, overviews 2 to 16: what ``TCI``, ``B04`` and
``B08`` of a real scene carry (read on 25.10.2026). The content is noise over a gradient, so that the compressed
size, and with it the bytes a tile reads, comes close to the real files (TCI 308 MB, B04 225 MB at the source). No
pixel comes from a real scene. About 850 MB on disk, half a minute.

``SCL`` (NM4-62) is the 20 m scene classification the ``mask`` step reads: 5490 x 5490, uint8, the classes of
Sen2Cor drawn at random, a quarter of them cloud (8, 9, 10).
"""

import sys
from pathlib import Path

import numpy as np
import rasterio
import rasterio.shutil
from rasterio.transform import from_origin

SIZE = 10980
BLOCK = 1024
TRANSFORM = from_origin(600000, 5300040, 10, 10)
SCL_SIZE = SIZE // 2
SCL_TRANSFORM = from_origin(600000, 5300040, 20, 20)


def write(out: Path, name: str, count: int, dtype: str, make, size: int = SIZE, transform=TRANSFORM) -> None:
    raw = out / f"{name}.raw.tif"
    profile = dict(driver="GTiff", width=size, height=size, count=count, dtype=dtype, crs="EPSG:32632",
                   transform=transform, nodata=0, tiled=True, blockxsize=BLOCK, blockysize=BLOCK)
    with rasterio.open(raw, "w", **profile) as dst:
        for row in range(0, size, BLOCK):
            height = min(BLOCK, size - row)
            dst.write(make(height, row), window=((row, row + height), (0, size)))
    with rasterio.open(raw) as src:
        rasterio.shutil.copy(src, out / f"{name}.tif", driver="COG", BLOCKSIZE=BLOCK, COMPRESS="DEFLATE",
                             OVERVIEW_RESAMPLING="AVERAGE", NUM_THREADS="ALL_CPUS")
    raw.unlink()


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)

    def rgb(height: int, row: int) -> np.ndarray:
        base = (np.linspace(40, 200, SIZE)[None, :] + row / SIZE * 30).astype(np.int16)
        bands = [np.clip(base + rng.integers(0, 56, (height, SIZE)), 1, 255) for _ in range(3)]
        return np.stack(bands).astype(np.uint8)

    def reflectance(level: int):
        def make(height: int, row: int) -> np.ndarray:
            base = np.linspace(level - 800, level + 800, SIZE)[None, :]
            return np.clip(base + rng.normal(0, 300, (height, SIZE)), 1, 10000).astype(np.uint16)[None]
        return make

    def classes(height: int, row: int) -> np.ndarray:
        drawn = rng.choice([4, 5, 6, 7, 8, 9, 10], size=(height, SCL_SIZE), p=[0.3, 0.2, 0.15, 0.1, 0.1, 0.1, 0.05])
        return drawn.astype(np.uint8)[None]

    write(out, "TCI", 3, "uint8", rgb)
    write(out, "B04", 1, "uint16", reflectance(1500))
    write(out, "B08", 1, "uint16", reflectance(3500))
    write(out, "SCL", 1, "uint8", classes, SCL_SIZE, SCL_TRANSFORM)
    for path in sorted(out.glob("*.tif")):
        print(path.name, path.stat().st_size)


if __name__ == "__main__":
    main()
