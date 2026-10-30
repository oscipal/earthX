"""Peak memory of a job with many bands stays below the estimate that guards it (NM4-43c PR 2, adr/0020 §7).

The scene has 17 bands, the width of Sentinel-2's data assets; the job applies real ``band_math`` steps (version 2),
each adding a band, so the stock grows as it does for a user, and keeps every band. Each run is a process of its own
(``memory_bands.py``) that measures ``VmHWM`` and prints the estimate of ``plan.memory_needed`` for the same recipe.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.earthx.processing.test_memory_8192 import BACKEND, build_scene

BANDS = 17


@pytest.fixture(scope="module")
def scenes_by_size(tmp_path_factory: pytest.TempPathFactory) -> dict[int, Path]:
    root = tmp_path_factory.mktemp("scenes")
    return {size: build_scene(root / f"scene-{size}.tif", size, bands=BANDS) for size in (1024, 2048)}


def measure(scene: Path, workdir: Path, size: int, results: int, scenes: int) -> dict:
    command = [
        sys.executable,
        "-m",
        "tests.earthx.processing.memory_bands",
        str(scene),
        str(workdir),
        str(size),
        str(BANDS),
        str(results),
        "all",
        str(scenes),
    ]
    output = subprocess.run(command, cwd=BACKEND, capture_output=True, text=True, check=True, timeout=900)
    return json.loads(output.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(
    ("size", "results", "scenes"),
    [(2048, 0, 1), (1024, 16, 1), (1024, 0, 5)],
    ids=["17 bands, whole blocks", "17 bands and 16 results", "5 scenes"],
)
def test_the_peak_stays_below_the_estimate(
    scenes_by_size: dict[int, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    size: int,
    results: int,
    scenes: int,
) -> None:
    measured = measure(scenes_by_size[size], tmp_path, size, results, scenes)
    # Printed before the check: the CI log is where the numbers behind the constants are read off.
    with capsys.disabled():
        print(f"\nT2 memory {BANDS} bands + {results} results, {scenes} scene(s), {size}²: {measured}")
    assert measured["out_bands"] == BANDS + results
    assert measured["peak_mb"] < measured["est_memory_mb"]
