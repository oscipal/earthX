#!/usr/bin/env python3
"""What a mosaic tile costs with and without an operator, on synthetic local COGs, CPU only (NM4-04 §7.5).

    PYTHONPATH=backend python -W ignore scripts/tile-bench/mosaic_op_cost.py

Scenes like Sentinel-2: 10 m, ``uint16`` with scale and offset, blocks of 1024, 2048 x 2048 pixels, one UTM grid, and
a 20 m ``scl``. Per number of scenes N two cases: ``best`` (the first scene fills the tile, the portion of four is read
and nothing after it) and ``worst`` (scene i is valid only in a stripe of rows, so all N are read). Three variants:

* ``raw``   the mosaic tile of M4-17: one asset, raw values, ``FirstMethod``, portions of four;
* ``op``    per scene ``red`` and ``nir`` in physical values (``float32``), ``FirstMethod`` over the scenes, then the
            ``band_math`` kernel (NDVI);
* ``chain`` as ``op`` with ``scl``, then ``mask`` and ``band_math``.

A z14 tile of 256 px, median and minimum of 15 runs in ms, warm file cache, no PNG encoding. ``boto3`` is set aside as
in the image (NM4-26 §8.1). The COGs go to a temporary directory, about 300 MB; the run takes about ten minutes.
"""

import statistics
import tempfile
import time
from pathlib import Path

import morecantile
import numpy
import rasterio
import rasterio.session
from rasterio.transform import from_origin
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles
from rio_tiler.io import Reader
from rio_tiler.models import ImageData
from rio_tiler.mosaic import mosaic_reader
from rio_tiler.mosaic.methods.defaults import FirstMethod

from earthx.processing.operators import REGISTRY

rasterio.session.boto3 = None

SIZE, RES, X0, Y0, CRS = 2048, 10.0, 500000.0, 5300000.0, "EPSG:32632"
SCALE, OFFSET = 0.0001, -0.1
ROOT = Path(tempfile.mkdtemp())
RNG = numpy.random.default_rng(0)
TMS = morecantile.tms.get("WebMercatorQuad")

BAND_MATH = REGISTRY.operator("band_math", 1)
NDVI = BAND_MATH.params.model_validate({"expression": "(nir - red) / (nir + red)"})
MASK = REGISTRY.operator("mask", 1)
CLOUDS = MASK.params.model_validate({"source": "scl", "classes": [8, 9]})


def cog(name: str, data: numpy.ndarray, res: float, *, scaled: bool = True) -> str:
    plain, path = ROOT / f"{name}.plain.tif", ROOT / f"{name}.tif"
    profile = {
        "driver": "GTiff", "dtype": str(data.dtype), "count": 1, "height": data.shape[0], "width": data.shape[1],
        "crs": CRS, "transform": from_origin(X0, Y0, res, res), "nodata": 0,
    }  # fmt: skip
    with rasterio.open(plain, "w", **profile) as dst:
        dst.write(data, 1)
        if scaled:
            dst.scales, dst.offsets = (SCALE,), (OFFSET,)
    cog_profile = cog_profiles.get("deflate")
    cog_profile.update(blockxsize=1024, blockysize=1024)
    cog_translate(plain, path, cog_profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return str(path)


def stripe(data: numpy.ndarray, index: int, count: int) -> numpy.ndarray:
    """``data`` valid only in the ``index``-th of ``count`` stripes of rows."""
    rows = numpy.arange(data.shape[0])
    data[(rows * count // data.shape[0]) != index, :] = 0
    return data


def scenes(count: int, worst: bool) -> list[dict[str, str]]:
    made = []
    for index in range(count):
        files = {}
        for band, base in (("red", 800), ("nir", 3000)):
            data = (base + RNG.integers(0, 2000, (SIZE, SIZE))).astype("uint16")
            files[band] = cog(f"{count}{worst}{index}{band}", stripe(data, index, count) if worst else data, RES)
        scl = RNG.integers(4, 7, (SIZE // 2, SIZE // 2)).astype("uint8")
        files["scl"] = cog(f"{count}{worst}{index}scl", stripe(scl, index, count) if worst else scl, RES * 2, scaled=False)
        made.append(files)
    return made


def read_raw(files: dict[str, str], x: int, y: int, z: int, **_: object) -> ImageData:
    with Reader(files["red"]) as reader:
        return reader.tile(x, y, z, resampling_method="nearest")


def read_assets(bands: tuple[str, ...]):
    def read(files: dict[str, str], x: int, y: int, z: int, **_: object) -> ImageData:
        arrays = []
        for band in bands:
            with Reader(files[band]) as reader:
                image = reader.tile(x, y, z, resampling_method="nearest")
            data = image.array.astype("float32")
            arrays.append(data if band == "scl" else data * numpy.float32(SCALE) + numpy.float32(OFFSET))
        return ImageData(numpy.ma.concatenate(arrays, axis=0), bounds=image.bounds, crs=image.crs, band_names=list(bands))

    return read


def tile_of(variant: str, files: list[dict[str, str]], tile: morecantile.Tile) -> ImageData:
    options = {"pixel_selection": FirstMethod(), "threads": 4, "chunk_size": 4}
    if variant == "raw":
        return mosaic_reader(files, read_raw, tile.x, tile.y, tile.z, **options)[0]
    bands = ("red", "nir") if variant == "op" else ("red", "nir", "scl")
    image = mosaic_reader(files, read_assets(bands), tile.x, tile.y, tile.z, **options)[0]
    if variant == "chain":
        image = MASK.run(image, CLOUDS)
    return BAND_MATH.run(image, NDVI)


def main() -> None:
    with Reader(scenes(1, False)[0]["red"]) as reader:
        west, south, east, north = reader.get_geographic_bounds("EPSG:4326")
    tile = TMS.tile((west + east) / 2, (south + north) / 2, 14)
    print("N case  variant median_ms min_ms")
    for count in (1, 2, 4, 8, 12):
        for worst in (False, True):
            if count == 1 and worst:
                continue
            files = scenes(count, worst)
            for variant in ("raw", "op", "chain"):
                tile_of(variant, files, tile)
                times = []
                for _ in range(15):
                    started = time.perf_counter()
                    tile_of(variant, files, tile)
                    times.append((time.perf_counter() - started) * 1000)
                case = "worst" if worst else "best"
                print(f"{count:2d} {case:5s} {variant:6s} {statistics.median(times):9.1f} {min(times):7.1f}")


if __name__ == "__main__":
    main()
