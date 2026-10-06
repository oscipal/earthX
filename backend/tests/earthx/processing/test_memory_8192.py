"""Peak memory of a T2 run: below 500 MB at 8192², and not growing with the scene (M4-07a F11).

The scene is the one adr/0014 §17.2 describes: two ``uint16`` bands with
Sentinel-2's ``scale``/``offset``, smooth fields with noise (σ 60 and 90 DN), a
nodata strip, 512 px blocks, deflate. It is written here, in the test process; each
run happens in a fresh process (``memory_run.py``) that measures its own ``VmHWM``,
so nothing the test process did counts (plan M4-07a §9.3).

Otto, 06.10.2026 (F11 option 1, with a condition): the whole child stays below
500 MB at 8192² with ``GDAL_CACHEMAX`` 64 MB, and the same test runs 2048² too and
checks that the peak grows by at most a fixed amount from one to the other — the
evidence that memory follows the block size, not the scene. Part of the normal
suite (F10).
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

BACKEND = Path(__file__).resolve().parents[3]

#: The acceptance of M4-07a after F11 (Otto, 06.10.2026): the whole child process at 8192².
PEAK_LIMIT_MB = 500

#: How much the peak may grow from 2048² to 8192², 16 times the pixels (F11 condition).
#: Measured: SESSION and CI below, see plan M4-07a §9.5 for the reserve.
GROWTH_LIMIT_MB = 200

SMALL, LARGE = 2048, 8192


def build_scene(path: Path, size: int) -> Path:
    """§17.2 at ``size``², written row strip by row strip so the test process stays small too."""
    generator = numpy.random.default_rng(seed=20261006)
    profile = {
        "driver": "GTiff",
        "dtype": "uint16",
        "count": 2,
        "width": size,
        "height": size,
        "crs": sources.CRS,
        "transform": from_origin(sources.ORIGIN_X, sources.ORIGIN_Y, sources.RESOLUTION, sources.RESOLUTION),
        "nodata": 0,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
    }
    plain = path.with_suffix(".plain.tif")
    cols = numpy.arange(size)
    with rasterio.open(plain, "w", **profile) as destination:
        for row in range(0, size, 512):
            rows = numpy.arange(row, row + 512)[:, None]
            red = (
                1200 + 400 * numpy.sin(rows / 900) + 300 * numpy.cos(cols / 700) + generator.normal(0, 60, (512, size))
            )
            nir = (
                3400 + 900 * numpy.sin(rows / 1300) + 500 * numpy.cos(cols / 500) + generator.normal(0, 90, (512, size))
            )
            block = numpy.stack([red, nir]).clip(1, 60000).astype("uint16")
            block[:, :, size // 2 : size // 2 + 40] = 0
            destination.write(block, window=Window(0, row, size, 512))
        destination.scales = (sources.SCALE, sources.SCALE)
        destination.offsets = (sources.OFFSET, sources.OFFSET)
    cog_profile = cog_profiles.get("deflate")
    cog_profile.update({"blockxsize": 512, "blockysize": 512})
    cog_translate(plain, path, cog_profile, overview_resampling="average", quiet=True)
    plain.unlink()
    return path


@pytest.fixture(scope="module")
def scenes(tmp_path_factory: pytest.TempPathFactory) -> dict[int, Path]:
    root = tmp_path_factory.mktemp("scenes")
    return {size: build_scene(root / f"scene-{size}.tif", size) for size in (SMALL, LARGE)}


def measure(scene: Path, workdir: Path, size: int) -> dict:
    command = [sys.executable, "-m", "tests.earthx.processing.memory_run", str(scene), str(workdir), str(size)]
    output = subprocess.run(command, cwd=BACKEND, capture_output=True, text=True, check=True, timeout=600)
    return json.loads(output.stdout.strip().splitlines()[-1])


def test_the_peak_stays_below_the_limit_and_does_not_follow_the_scene_size(
    scenes: dict[int, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    measured = {}
    for size in (SMALL, LARGE):
        workdir = tmp_path / str(size)
        workdir.mkdir()
        measured[size] = measure(scenes[size], workdir, size)
        assert measured[size]["blocks"] == (size // 1024) ** 2
        with rasterio.open(workdir / "result.tif") as result:
            assert (result.width, result.height, result.count) == (size, size, 2)
    growth = measured[LARGE]["peak_mb"] - measured[SMALL]["peak_mb"]
    # Printed even when the test passes: the CI log is where the numbers behind
    # the limits are read off (plan M4-07a §9.5).
    with capsys.disabled():
        for size in (SMALL, LARGE):
            print(f"\nT2 memory {size}²: {measured[size]}")
        print(f"T2 memory growth {SMALL}² → {LARGE}²: {growth:.1f} MB")
    assert measured[LARGE]["peak_mb"] < PEAK_LIMIT_MB
    assert growth <= GROWTH_LIMIT_MB
