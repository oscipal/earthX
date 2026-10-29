"""``reproject`` against one whole ``reproject``, per method and case (adr/0014 §6.3 row 4 and §15j; M4-24).

Otto's condition of 20.10.2026: every method, old and new, is checked in all three
cases — coarsening, about the same pixel size, refining — against its own row of
§6.3 or its addendum, and a row made too tight makes the check fail.

The block side is the operator itself over the core's blocks (``core._blocks``), on a
float64 file as the core hands it over, NaN where masked. The whole side is one
``rasterio.warp.reproject`` over the same array onto the same grid, as in §3.4. Both
are compared as float32, the type the result is written in, where both are valid.
The data are synthetic and small versions of plan M4-24 §7.2: a DEM in EPSG:4326,
an NDVI and a class raster in EPSG:32632, the last two with a nodata strip and corner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject as warp_reproject

from earthx.processing.core import BLOCK_SIZE, _blocks
from earthx.processing.operators import REPROJECT, BandMeta, RasterMeta, ReprojectParams
from earthx.processing.operators import reproject as reproject_module

METHODS = ("nearest", "bilinear", "cubic", "cubicspline", "lanczos", "average", "mode")
CASES = ("coarse", "same", "fine")

#: dataset → case → (target CRS, pixel size). Plan M4-24 §7.2: coarsening by about 3,
#: about the same size, refining by about 2.
GRIDS = {
    "heights": {"coarse": ("EPSG:32632", 90.0), "same": ("EPSG:32632", 30.0), "fine": ("EPSG:32632", 10.0)},
    "ndvi": {"coarse": ("EPSG:3035", 30.0), "same": ("EPSG:3035", 10.0), "fine": ("EPSG:3035", 5.0)},
    "classes": {"coarse": ("EPSG:3035", 30.0), "same": ("EPSG:3035", 10.0), "fine": ("EPSG:3035", 5.0)},
}


@dataclass(frozen=True)
class Measured:
    identical: float
    p99: float
    worst: float


@dataclass(frozen=True)
class Row:
    """One tolerance of §6.3 as the test reads it; ``None`` is a bound the row does not set."""

    min_identical: float | None = None
    p99: float | None = None
    worst: float | None = None

    def check(self, measured: Measured) -> None:
        if self.min_identical is not None:
            assert measured.identical >= self.min_identical, f"{measured.identical:.4%} identical"
        if self.p99 is not None:
            assert measured.p99 <= self.p99, f"p99 {measured.p99:.4g}"
        if self.worst is not None:
            assert measured.worst <= self.worst, f"max {measured.worst:.4g}"

    def tightened(self, measured: Measured) -> Row:
        """The same row with every bound it sets halfway past what was measured."""
        return Row(
            None if self.min_identical is None else (measured.identical + 1) / 2,
            None if self.p99 is None else measured.p99 / 2,
            None if self.worst is None else measured.worst / 2,
        )


#: Heights in m, §15j (Otto, answer 8): every interpolating method, average when the
#: target is not finer. Replaces §6.3's 0.3 m and 1 m: the whole reproject the block
#: plan is compared with splits the raster by its size, measured over 13 sizes.
HEIGHTS = Row(p99=0.6, worst=4.0)
#: Heights, §15j: average when the target is finer than the source (Otto, answers 4 and 8).
HEIGHTS_AVERAGE_FINE = Row(p99=1.0, worst=4.0)
NDVI = Row(p99=0.01)
PICKING = Row(min_identical=0.97)
CLASSES = Row(min_identical=0.999)


def row(method: str, dataset: str, case: str) -> Row:
    """The row of §6.3 or §15j that holds for ``method`` on ``dataset`` in ``case``."""
    if method == "mode" and dataset == "classes":
        return CLASSES
    if method in ("nearest", "mode"):
        return PICKING
    if dataset == "ndvi":
        return NDVI
    if method == "average" and case == "fine":
        return HEIGHTS_AVERAGE_FINE
    return HEIGHTS


#: Class rasters are only resampled by the methods that keep their values.
COMBINATIONS = [
    (method, dataset, case)
    for dataset in GRIDS
    for method in METHODS
    if dataset != "classes" or method in ("nearest", "mode")
    for case in CASES
]
IDS = ["-".join(combination) for combination in COMBINATIONS]


def _no_data(data: numpy.ndarray) -> None:
    """A strip and a corner without data, as plan §7.2."""
    rows, cols = data.shape
    data[:, cols // 2 : cols // 2 + 40] = numpy.nan
    data[: rows // 8, : cols // 8] = numpy.nan


def _write(path: Path, data: numpy.ndarray, crs: str, transform) -> Path:
    profile = {
        "driver": "GTiff",
        "dtype": "float64",
        "count": 1,
        "width": data.shape[1],
        "height": data.shape[0],
        "crs": crs,
        "transform": transform,
        "nodata": math.nan,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(path, "w", **profile) as destination:
        destination.write(data, 1)
    return path


def _heights(path: Path, rows: int, cols: int) -> Path:
    generator = numpy.random.default_rng(seed=20261020)
    y, x = numpy.mgrid[0:rows, 0:cols] / 3600  # a window of plan §7.2's 3600² DEM, same slopes
    terrain = 1500 + 1100 * numpy.sin(3.1 * x + 1.3) * numpy.cos(2.3 * y) + 500 * numpy.sin(11 * x * y + 0.4)
    terrain += 120 * numpy.sin(37 * x) * numpy.sin(29 * y) + generator.normal(0, 2, (rows, cols))
    return _write(path, terrain, "EPSG:4326", from_origin(9.0, 48.0, 1 / 3600, 1 / 3600))


def _ndvi(path: Path, rows: int, cols: int) -> Path:
    generator = numpy.random.default_rng(seed=20261021)
    y, x = numpy.mgrid[0:rows, 0:cols] / 4096  # a window of plan §7.2's 4096² NDVI
    field = 0.35 + 0.3 * numpy.sin(17 * x) * numpy.cos(13 * y) + 0.15 * numpy.sin(61 * x + 47 * y)
    field = numpy.clip(field + generator.normal(0, 0.02, (rows, cols)), -0.2, 0.9)
    _no_data(field)
    return _write(path, field, "EPSG:32632", from_origin(600000.0, 5700000.0, 10.0, 10.0))


def _classes(path: Path, rows: int, cols: int) -> Path:
    """Six classes as Voronoi areas, about 30 px of 10 m across, as plan §7.2."""
    generator = numpy.random.default_rng(seed=20261022)
    count = rows * cols // 30000
    seeds, labels = generator.uniform(0, (rows, cols), (count, 2)), generator.integers(1, 7, count)
    y, x = numpy.mgrid[0:rows, 0:cols]
    nearest = numpy.zeros((rows, cols), dtype=int)
    best = numpy.full((rows, cols), numpy.inf)
    for index, (seed_y, seed_x) in enumerate(seeds):
        distance = (y - seed_y) ** 2 + (x - seed_x) ** 2
        closer = distance < best
        best[closer], nearest[closer] = distance[closer], index
    classes = labels[nearest].astype("float64")
    _no_data(classes)
    return _write(path, classes, "EPSG:32632", from_origin(600000.0, 5700000.0, 10.0, 10.0))


#: Rows and columns of the source per case: big enough that every target spans more
#: than one block of the core, small enough for a quick run.
SIZES = {
    "heights": {"coarse": (1100, 4600), "same": (1100, 1600), "fine": (600, 800)},
    "ndvi": {"coarse": (1100, 3300), "same": (1100, 1100), "fine": (700, 700)},
    "classes": {"coarse": (1100, 3300), "same": (1100, 1100), "fine": (700, 700)},
}
_BUILD = {"heights": _heights, "ndvi": _ndvi, "classes": _classes}


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[tuple[str, str], Path]:
    root = tmp_path_factory.mktemp("tolerance")
    return {
        (dataset, case): _BUILD[dataset](root / f"{dataset}-{case}.tif", *SIZES[dataset][case])
        for dataset in GRIDS
        for case in CASES
    }


def _params(method: str, crs: str, resolution: float) -> ReprojectParams:
    return ReprojectParams(crs=crs, resolution=resolution, resampling=method)


def _blockwise(source, target: RasterMeta, params: ReprojectParams, band: int = 0) -> numpy.ndarray:
    out = numpy.full((target.height, target.width), numpy.nan)
    for window in _blocks(target.width, target.height):
        block = REPROJECT.run(source, target, window, params)
        rows, cols = window.toslices()
        out[rows, cols] = block.filled(numpy.nan)[band]
    return out


def _whole(source, target: RasterMeta, method: str, band: int = 0) -> numpy.ndarray:
    out = numpy.full((target.height, target.width), numpy.nan)
    warp_reproject(
        source.read(band + 1),
        out,
        src_transform=source.transform,
        src_crs=source.crs,
        src_nodata=numpy.nan,
        dst_transform=target.transform,
        dst_crs=target.crs,
        dst_nodata=numpy.nan,
        resampling=reproject_module._METHODS[method][0],
    )
    return out


_MEASURED: dict[tuple[str, str, str], Measured] = {}


def measure(files: dict[tuple[str, str], Path], method: str, dataset: str, case: str) -> Measured:
    """Whole against blockwise for one combination, computed once per test session."""
    key = (method, dataset, case)
    if key not in _MEASURED:
        crs, resolution = GRIDS[dataset][case]
        params = _params(method, crs, resolution)
        with rasterio.open(files[dataset, case]) as source:
            meta = RasterMeta(
                source.crs.to_string(),
                source.transform,
                source.width,
                source.height,
                (BandMeta("b", "float64", math.nan),),
            )
            target = REPROJECT.transform(meta, params)
            assert target.width > BLOCK_SIZE or target.height > BLOCK_SIZE
            block = _blockwise(source, target, params).astype("float32").astype("float64")
            whole = _whole(source, target, method).astype("float32").astype("float64")
        both = ~numpy.isnan(block) & ~numpy.isnan(whole)
        assert both.sum() > 0.9 * (~numpy.isnan(whole)).sum()
        difference = numpy.abs(block - whole)[both]
        _MEASURED[key] = Measured(
            float((difference == 0).mean()), float(numpy.percentile(difference, 99)), float(difference.max())
        )
    return _MEASURED[key]


@pytest.mark.parametrize(("method", "dataset", "case"), COMBINATIONS, ids=IDS)
def test_the_block_plan_stays_inside_the_row_of_its_method(
    files: dict[tuple[str, str], Path], method: str, dataset: str, case: str
) -> None:
    row(method, dataset, case).check(measure(files, method, dataset, case))


@pytest.mark.parametrize(("method", "dataset", "case"), COMBINATIONS, ids=IDS)
def test_a_row_made_too_tight_fails(files: dict[tuple[str, str], Path], method: str, dataset: str, case: str) -> None:
    measured = measure(files, method, dataset, case)
    with pytest.raises(AssertionError):
        row(method, dataset, case).tightened(measured).check(measured)


def test_every_band_of_a_multi_band_file_stays_inside_the_row(files: dict[tuple[str, str], Path], tmp_path: Path) -> None:
    """Version 4 warps each band for itself; each stays within the row of its single-band run (NM4-43b)."""
    crs, resolution = GRIDS["ndvi"]["same"]
    params = _params("bilinear", crs, resolution)
    with rasterio.open(files["ndvi", "same"]) as single:
        data = single.read(1)
        profile = {**single.profile, "count": 4}
    path = tmp_path / "ndvi-four-bands.tif"
    with rasterio.open(path, "w", **profile) as destination:
        for band in range(4):
            destination.write(data + band * 0.01, band + 1)
    with rasterio.open(path) as source:
        bands = tuple(BandMeta(f"b{index}", "float64", math.nan) for index in range(4))
        target = REPROJECT.transform(
            RasterMeta(source.crs.to_string(), source.transform, source.width, source.height, bands), params
        )
        assert target.width > BLOCK_SIZE or target.height > BLOCK_SIZE
        for band in range(4):
            block = _blockwise(source, target, params, band).astype("float32").astype("float64")
            whole = _whole(source, target, "bilinear", band).astype("float32").astype("float64")
            both = ~numpy.isnan(block) & ~numpy.isnan(whole)
            difference = numpy.abs(block - whole)[both]
            measured = Measured(
                float((difference == 0).mean()), float(numpy.percentile(difference, 99)), float(difference.max())
            )
            row("bilinear", "ndvi", "same").check(measured)
