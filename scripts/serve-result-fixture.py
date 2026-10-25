#!/usr/bin/env python3
"""Serves the real tiler over one synthetic job result, for the browser checks in ``frontend/e2e`` (UI-01a).

    PYTHONPATH=backend python scripts/serve-result-fixture.py [--port 8001] [--size 3072] [--cog result.tif]

The tiler is the real app (``earthx.api.tiler.build_app``) with its result routes; the object store is an in-process
S3 (``moto``) the result was uploaded to the way the supervisor does it, and the only seam is the one the tests use too
(``result_tiles.gdal_path`` hands GDAL the local file instead of the signed URL). Without ``--cog`` the result is a
10 m float32 raster of per-pixel noise in UTM 32N, with overviews, so that every pixel is visible when zoomed in. The
first line printed is JSON: the ``result_id``, the center and the bounds in WGS 84. Run the dev server of the frontend
with ``VITE_TILER_PROXY=http://127.0.0.1:<port>``: ``/results`` is proxied there.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

import numpy
import rasterio
import uvicorn
from moto import mock_aws
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from earthx.api import result_tiles
from earthx.api.result_tiles import ResultSources
from earthx.api.tiler import build_app
from earthx.objectstore.results import Store, new_result_id, upload_result

ENDPOINT = "http://objectstore:3900"
BUCKET = "earthx"
REGION = "garage"
CRS = "EPSG:32632"
ORIGIN = (600000.0, 5700000.0)
RESOLUTION = 10.0


def make_cog(root: Path, size: int) -> Path:
    plain, target = root / "plain.tif", root / "result.tif"
    noise = numpy.random.default_rng(7).uniform(-1, 1, (size, size)).astype("float32")
    with rasterio.open(
        plain, "w", driver="GTiff", width=size, height=size, count=1, dtype="float32", crs=CRS,
        transform=from_origin(*ORIGIN, RESOLUTION, RESOLUTION), nodata=-9999.0,
    ) as destination:
        destination.write(noise, 1)
    cog_translate(str(plain), str(target), cog_profiles.get("deflate"), quiet=True)
    return target


def make_mask(root: Path, source: Path) -> Path:
    """1 everywhere, on the grid of the result (the ``mask.tif`` of a job without an AOI cut)."""
    path = root / "mask.tif"
    with rasterio.open(source) as result, rasterio.open(
        path, "w", driver="GTiff", width=result.width, height=result.height, count=1, dtype="uint8", crs=result.crs,
        transform=result.transform, tiled=True, blockxsize=1024, blockysize=1024, compress="deflate",
    ) as destination:
        for row in range(0, result.height, 1024):
            height = min(1024, result.height - row)
            destination.write(
                numpy.ones((height, result.width), "uint8"), 1, window=rasterio.windows.Window(0, row, result.width, height)
            )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--size", type=int, default=3072)
    parser.add_argument("--cog", type=Path, default=None)
    arguments = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="earthx-result-fixture-"))
    for name in ("access_key", "secret_key"):
        (root / name).write_text("GKtestaccesskey0001\n" if name == "access_key" else "test-secret-key-0000000000000000\n")
    os.environ["MOTO_S3_CUSTOM_ENDPOINTS"] = ENDPOINT
    environ = {
        "S3_ENDPOINT": ENDPOINT,
        "S3_PUBLIC_ENDPOINT": "http://localhost:3900",
        "S3_REGION": REGION,
        "S3_BUCKET": BUCKET,
        "S3_ACCESS_KEY_FILE": str(root / "access_key"),
        "S3_SECRET_KEY_FILE": str(root / "secret_key"),
    }
    result_file = arguments.cog or make_cog(root, arguments.size)
    mask_file = make_mask(root, result_file)
    with rasterio.open(result_file) as dataset:
        west, south, east, north = transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds)

    with mock_aws():
        store = Store.from_environ(environ)
        store.s3._internal.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
        result_id = new_result_id()
        upload_result(store, result_id, "result.tif", result_file)
        upload_result(store, result_id, "mask.tif", mask_file)
        result_tiles.gdal_path = lambda url: str(mask_file if url.split("?")[0].endswith("mask.tif") else result_file)

        @asynccontextmanager
        async def lifespan(app):
            app.state.earthx_results = ResultSources(store, clock=time.monotonic)
            yield

        print(
            json.dumps({"result_id": result_id, "center": [(west + east) / 2, (south + north) / 2], "bounds": [west, south, east, north]}),
            flush=True,
        )
        uvicorn.run(build_app(lifespan=lifespan), host="127.0.0.1", port=arguments.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
