"""Peak memory of a T2 run with ``mask`` and ``normalize``: below 500 MB at 4096², and not growing with the scene (M4-18a).

The limit and the method are those of ``test_memory_8192.py`` and ``test_memory_reproject.py``: the whole
child process, ``VmHWM`` in a process of its own, ``GDAL_CACHEMAX`` 64 MB. The scene is the same two-band
``uint16`` COG at 2048² and 4096²; for ``mask`` a 20 m classification layer of ``uint8`` classes 0 to 11
comes with it, read onto the 10 m grid of the bands (half the side, nested). Both operators run in the pass
that reads the scene, one block at a time, so the peak follows the block size and not the scene.
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
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from tests.earthx.processing import sources
from tests.earthx.processing.test_memory_8192 import BACKEND, PEAK_LIMIT_MB, build_scene

SMALL, LARGE = 2048, 4096

#: How much the peak may grow from 2048² to 4096², 4 times the pixels. Measured 69 MB (mask) and 80 MB
#: (normalize) in the session, with the statistics pass of M4-32a; 100 MB keeps a fifth in reserve and stays below the 192 MB by which a core
#: holding the float64 scene would grow (plan M4-07a §9.5).
GROWTH_LIMIT_MB = 100


def build_layer(path: Path, size: int) -> Path:
    """Classes 0 to 11 in blobs on a 20 m grid over the scene of ``size``² 10 m pixels, class 0 along a strip."""
    side = size // 2
    rows, cols = numpy.indices((side, side))
    classes = (1 + (rows // 37 + cols // 53 + (rows * cols) // 4096) % 11).astype("uint8")
    classes[:, side // 2 : side // 2 + 20] = 0
    plain = path.with_suffix(".plain.tif")
    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "count": 1,
        "width": side,
        "height": side,
        "crs": sources.CRS,
        "transform": from_origin(sources.ORIGIN_X, sources.ORIGIN_Y, 2 * sources.RESOLUTION, 2 * sources.RESOLUTION),
        "nodata": 0,
    }
    with rasterio.open(plain, "w", **profile) as destination:
        destination.write(classes, 1)
    cog_profile = cog_profiles.get("deflate")
    cog_profile.update({"blockxsize": 512, "blockysize": 512})
    cog_translate(plain, path, cog_profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path


@pytest.fixture(scope="module")
def scenes(tmp_path_factory: pytest.TempPathFactory) -> dict[int, tuple[Path, Path]]:
    root = tmp_path_factory.mktemp("mask-scenes")
    return {
        size: (build_scene(root / f"scene-{size}.tif", size), build_layer(root / f"layer-{size}.tif", size))
        for size in (SMALL, LARGE)
    }


def measure(scene: Path, layer: Path | None, workdir: Path, size: int, step: str) -> dict:
    command = [sys.executable, "-m", "tests.earthx.processing.memory_run", str(scene), str(workdir), str(size), "64", step]
    if layer is not None:
        command.append(str(layer))
    output = subprocess.run(command, cwd=BACKEND, capture_output=True, text=True, check=True, timeout=600)
    return json.loads(output.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("step", ["mask", "normalize"])
def test_a_pixel_operator_stays_below_the_limit_and_does_not_follow_the_scene_size(
    scenes: dict[int, tuple[Path, Path]], tmp_path: Path, capsys: pytest.CaptureFixture[str], step: str
) -> None:
    measured = {}
    for size in (SMALL, LARGE):
        scene, layer = scenes[size]
        (tmp_path / str(size)).mkdir()
        measured[size] = measure(scene, layer if step == "mask" else None, tmp_path / str(size), size, step)
    growth = measured[LARGE]["peak_mb"] - measured[SMALL]["peak_mb"]
    # Printed before any check: the CI log is where the numbers behind the limits are read off.
    with capsys.disabled():
        for size in (SMALL, LARGE):
            print(f"\nT2 memory {step} {size}²: {measured[size]}")
        print(f"T2 memory {step} growth {SMALL}² → {LARGE}²: {growth:.1f} MB")
    for size in (SMALL, LARGE):
        assert measured[size]["blocks"] == (size // 1024) ** 2
        with rasterio.open(tmp_path / str(size) / "result.tif") as result:
            assert (result.width, result.height, result.count) == (size, size, 2)
    assert measured[LARGE]["peak_mb"] < PEAK_LIMIT_MB
    assert growth <= GROWTH_LIMIT_MB

