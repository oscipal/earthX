"""Peak memory of a T2 run with ``reproject``: below 500 MB, and not growing with the scene (M4-10, M4-10b).

The limit is the one of M4-07a (``test_memory_8192.py``): the whole child process,
measured as ``VmHWM`` in a process of its own, ``GDAL_CACHEMAX`` 64 MB. The scenes are
the same two-band ``uint16`` COGs, here at 2048² and 4096², reprojected with
``bilinear`` (Otto, 07.10.2026). The run has two passes: the pixel pass that crops and
scales into the work directory, and the warp pass that reads it back through a
``WarpedVRT`` (``warp_mem_limit`` 64 MB, adr/0014 §3.4).

As in M4-07a F11, the same test checks that the peak grows by at most a fixed amount
from the small scene to the large one: memory follows the block size, not the scene.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import rasterio

from tests.earthx.processing.test_memory_8192 import BACKEND, PEAK_LIMIT_MB, build_scene

SMALL, LARGE = 2048, 4096

#: How much the peak may grow from 2048² to 4096², 4 times the pixels (M4-10b).
#: Measured 79 MB in the session and 79–80 MB in the CI; 120 MB keeps a third in
#: reserve and stays below the 201 MB by which the float64 file of the pixel pass
#: grows, which a warp holding its source would add.
GROWTH_LIMIT_MB = 120


@pytest.fixture(scope="module")
def scenes(tmp_path_factory: pytest.TempPathFactory) -> dict[int, Path]:
    root = tmp_path_factory.mktemp("scenes")
    return {size: build_scene(root / f"scene-{size}.tif", size) for size in (SMALL, LARGE)}


def measure(scene: Path, workdir: Path, size: int) -> dict:
    command = [sys.executable, "-m", "tests.earthx.processing.memory_run", str(scene), str(workdir), str(size), "64"]
    output = subprocess.run(
        [*command, "reproject"], cwd=BACKEND, capture_output=True, text=True, check=True, timeout=600
    )
    return json.loads(output.stdout.strip().splitlines()[-1])


def test_a_bilinear_reprojection_stays_below_the_limit_and_does_not_follow_the_scene_size(
    scenes: dict[int, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    measured = {}
    for size in (SMALL, LARGE):
        workdir = tmp_path / str(size)
        workdir.mkdir()
        measured[size] = measure(scenes[size], workdir, size)
        with rasterio.open(workdir / "result.tif") as result:
            assert result.crs.to_epsg() == 3035
            assert result.count == 2
            assert result.width >= size * 0.99 and result.height >= size * 0.99
        assert measured[size]["blocks"] >= 2 * (size // 1024) ** 2  # a pixel pass and a warp pass
    growth = measured[LARGE]["peak_mb"] - measured[SMALL]["peak_mb"]
    with capsys.disabled():
        for size in (SMALL, LARGE):
            print(f"\nT2 memory reproject bilinear {size}²: {measured[size]}")
        print(f"T2 memory reproject growth {SMALL}² → {LARGE}²: {growth:.1f} MB")
    assert measured[LARGE]["peak_mb"] < PEAK_LIMIT_MB
    assert growth <= GROWTH_LIMIT_MB
