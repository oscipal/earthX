"""A T2 run over an 8192² scene stays below 300 MB peak memory (M4-07a acceptance, adr/0014 §3.5).

The scene is the one §17.2 describes: two ``uint16`` bands with Sentinel-2's
``scale``/``offset``, smooth fields with noise (σ 60 and 90 DN), a nodata strip,
512 px blocks, deflate. It is written here, in the test process; the run itself
happens in a fresh process (``memory_run.py``), so its ``ru_maxrss`` counts the run
and nothing the test process did before. Approved F10: part of the normal suite.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from tests.earthx.processing import sources
from tests.earthx.processing.memory_run import SIZE

BACKEND = Path(__file__).resolve().parents[3]

#: The acceptance criterion of M4-07a (plan M4-processing-kern, M4-07a).
PEAK_LIMIT_MB = 300


def build_scene(path: Path) -> Path:
    """§17.2 at 8192², written row strip by row strip so the test process stays small too."""
    generator = numpy.random.default_rng(seed=20261006)
    profile = {
        "driver": "GTiff",
        "dtype": "uint16",
        "count": 2,
        "width": SIZE,
        "height": SIZE,
        "crs": sources.CRS,
        "transform": from_origin(sources.ORIGIN_X, sources.ORIGIN_Y, sources.RESOLUTION, sources.RESOLUTION),
        "nodata": 0,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
    }
    plain = path.with_suffix(".plain.tif")
    cols = numpy.arange(SIZE)
    with rasterio.open(plain, "w", **profile) as destination:
        for row in range(0, SIZE, 512):
            rows = numpy.arange(row, row + 512)[:, None]
            red = (
                1200 + 400 * numpy.sin(rows / 900) + 300 * numpy.cos(cols / 700) + generator.normal(0, 60, (512, SIZE))
            )
            nir = (
                3400 + 900 * numpy.sin(rows / 1300) + 500 * numpy.cos(cols / 500) + generator.normal(0, 90, (512, SIZE))
            )
            block = numpy.stack([red, nir]).clip(1, 60000).astype("uint16")
            block[:, :, 4000:4040] = 0
            destination.write(block, window=Window(0, row, SIZE, 512))
        destination.scales = (sources.SCALE, sources.SCALE)
        destination.offsets = (sources.OFFSET, sources.OFFSET)
    cog_profile = cog_profiles.get("deflate")
    cog_profile.update({"blockxsize": 512, "blockysize": 512})
    cog_translate(plain, path, cog_profile, overview_resampling="average", quiet=True)
    plain.unlink()
    return path


@pytest.fixture(scope="module")
def scene(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_scene(tmp_path_factory.mktemp("scene") / "big.tif")


def measure(scene: Path, workdir: Path, cachemax_mb: int | None = None) -> dict:
    command = [sys.executable, "-m", "tests.earthx.processing.memory_run", str(scene), str(workdir)]
    if cachemax_mb is not None:
        command.append(str(cachemax_mb))
    output = subprocess.run(command, cwd=BACKEND, capture_output=True, text=True, check=True, timeout=600)
    return json.loads(output.stdout.strip().splitlines()[-1])


def test_a_t2_run_over_8192_squared_stays_below_300_mb(scene: Path, tmp_path: Path) -> None:
    measured = measure(scene, tmp_path)
    print(f"\n8192² T2 run: {measured}")
    assert measured["blocks"] == 64
    assert measured["peak_mb"] < PEAK_LIMIT_MB
    with rasterio.open(tmp_path / "result.tif") as result:
        assert (result.width, result.height, result.count) == (SIZE, SIZE, 2)
