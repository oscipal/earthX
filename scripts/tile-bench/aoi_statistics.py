#!/usr/bin/env python3
"""What a measure over an AOI costs, exact and coarser, and how far the coarser one lies off (NM4-19 §7.5, §7.6).

    PYTHONPATH=backend python -W ignore scripts/tile-bench/aoi_statistics.py <folder> exact <side>
    PYTHONPATH=backend python -W ignore scripts/tile-bench/aoi_statistics.py <folder> coarse <side> <factor>

``<folder>`` is the folder of a Sentinel-2 C1 L2A item on its open bucket (the part of the ``href`` of ``B04.tif``
before the file name). A square window of ``side`` x ``side`` pixels in the middle of the scene, at 10 m; the AOI is a
circle inscribed in it (64 vertices). ``exact`` reads ``B04`` and ``B08`` on the native grid, ``coarse`` the same
bounds ``factor`` times coarser (GDAL picks the overview). Both scale to reflectance (``scale`` 0.0001, ``offset``
-0.1), compute NDVI in ``float32`` and count the pixels of the AOI mask (``all_touched``) with the statistics of the
job (``earthx.processing.statistics``). GDAL options as the tile routes of the ``tiler`` (NM4-26). One process per
call, so every call is cold; one JSON line out.
"""

import json
import math
import sys
import time

import numpy
import rasterio
from rasterio.features import rasterize
from rasterio.windows import Window
from rasterio.windows import transform as window_transform
from shapely.geometry import Point, mapping

from earthx.processing.statistics import BandStatistics

ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_MULTIRANGE": "SERIAL",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "CPL_VSIL_CURL_CACHE_SIZE": str(256 * 1024 * 1024),
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
}
SCALE, OFFSET = numpy.float32(0.0001), numpy.float32(-0.1)
FIELDS = ("minimum", "maximum", "percentile_2", "percentile_98")


def summary(values: numpy.ndarray, counted: numpy.ndarray, inside: numpy.ndarray) -> dict[str, float]:
    statistics = BandStatistics("float32")
    statistics.add(values[counted].astype(numpy.float32))
    result = statistics.summary(max(int(inside.sum()), 1))
    return {name: result[name] for name in FIELDS if name in result}


def main() -> None:
    folder, mode, side = sys.argv[1].rstrip("/"), sys.argv[2], int(sys.argv[3])
    factor = int(sys.argv[4]) if mode == "coarse" else 1
    started = time.monotonic()
    with rasterio.Env(**ENV):
        with rasterio.open(f"/vsicurl/{folder}/B04.tif") as red_src, rasterio.open(f"/vsicurl/{folder}/B08.tif") as nir_src:
            offset = (red_src.width - side) // 2
            window = Window(offset, offset, side, side)
            grid = window_transform(window, red_src.transform)
            centre_x, centre_y = grid * (side / 2, side / 2)
            aoi = mapping(Point(centre_x, centre_y).buffer(side * grid.a / 2 * 0.95, 16))
            shape = (math.ceil(side / factor), math.ceil(side / factor))
            opened = time.monotonic()
            red = red_src.read(1, window=window, out_shape=shape, masked=True)
            nir = nir_src.read(1, window=window, out_shape=shape, masked=True)
            read = time.monotonic()
    coarse = grid * grid.scale(side / shape[1], side / shape[0])
    inside = rasterize([aoi], out_shape=shape, transform=coarse, all_touched=True, default_value=1, fill=0, dtype="uint8") == 1
    red_values = numpy.ma.getdata(red).astype(numpy.float32) * SCALE + OFFSET
    nir_values = numpy.ma.getdata(nir).astype(numpy.float32) * SCALE + OFFSET
    valid = ~(numpy.ma.getmaskarray(red) | numpy.ma.getmaskarray(nir)) & inside
    with numpy.errstate(divide="ignore", invalid="ignore"):
        ndvi = ((nir_values - red_values) / (nir_values + red_values)).astype(numpy.float32)
    print(
        json.dumps(
            {
                "mode": mode,
                "side": side,
                "factor": factor,
                "pixels_read": shape[0] * shape[1],
                "open_s": round(opened - started, 2),
                "read_s": round(read - opened, 2),
                "red": summary(red_values, valid, inside),
                "ndvi": summary(ndvi, valid & numpy.isfinite(ndvi), inside),
            }
        )
    )


main()
