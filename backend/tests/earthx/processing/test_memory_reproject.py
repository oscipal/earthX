"""Peak memory of a T2 run with ``reproject``: 4096² with ``bilinear`` stays below 500 MB (M4-10, Otto 07.10.2026).

The limit is the one of M4-07a (``test_memory_8192.py``): the whole child process,
measured as ``VmHWM`` in a process of its own, ``GDAL_CACHEMAX`` 64 MB. The scene is
the same two-band ``uint16`` COG at 4096². The run has two passes: the pixel pass
that crops and scales into the work directory, and the warp pass that reads it
back through a ``WarpedVRT`` (``warp_mem_limit`` 64 MB, adr/0014 §3.4).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import rasterio

from tests.earthx.processing.test_memory_8192 import BACKEND, PEAK_LIMIT_MB, build_scene

SIZE = 4096


@pytest.fixture(scope="module")
def scene(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_scene(tmp_path_factory.mktemp("scene") / f"scene-{SIZE}.tif", SIZE)


def test_a_bilinear_reprojection_stays_below_the_limit(
    scene: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    command = [sys.executable, "-m", "tests.earthx.processing.memory_run", str(scene), str(tmp_path), str(SIZE), "64"]
    output = subprocess.run(
        [*command, "reproject"], cwd=BACKEND, capture_output=True, text=True, check=True, timeout=600
    )
    measured = json.loads(output.stdout.strip().splitlines()[-1])
    with rasterio.open(tmp_path / "result.tif") as result:
        assert result.crs.to_epsg() == 3035
        assert result.count == 2
        assert result.width >= SIZE * 0.99 and result.height >= SIZE * 0.99
    assert measured["blocks"] >= 2 * (SIZE // 1024) ** 2  # a pixel pass and a warp pass
    with capsys.disabled():
        print(f"\nT2 memory reproject bilinear {SIZE}²: {measured}")
    assert measured["peak_mb"] < PEAK_LIMIT_MB
