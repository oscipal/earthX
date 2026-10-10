"""Peak memory of a mosaic job: below the limit, and a further scene does not add a scene (M4-12a).

As ``test_memory_export.py`` for the export: a three-band ``uint8`` ``visual`` of ``SIZE``² with a
nodata stripe in every block, so the mosaic reads every scene for every block; each run happens in a
fresh process (``memory_mosaic.py``) that measures its own ``VmHWM``. The second file lies in zone 33
(the same array under another CRS), so a run with it warps its last scene.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from tests.earthx.processing import sources
from tests.earthx.processing.test_memory_export import build_scene

BACKEND = Path(__file__).resolve().parents[3]

SIZE = 4096

#: The limit of a whole worker child that M4-07a set for a raster run (F11).
PEAK_LIMIT_MB = 500

#: What further scenes on the grid may add to the peak of one scene: their open datasets and the
#: blocks of the merge, never a second scene (50 MB raw at this size). Measured in the session,
#: 4096², three bands: one scene 374.5 MB, two 391.6 (+17), eight 401.7 (+27); the second scene
#: costs most, the next six +10 together.
SECOND_SCENE_LIMIT_MB = 30
EIGHTH_SCENE_LIMIT_MB = 45

#: What a warped scene may add on top of one on the grid. Measured: 390.1 against 392.8 MB.
WARPED_SCENE_LIMIT_MB = 16


@pytest.fixture(scope="module")
def scene(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_scene(tmp_path_factory.mktemp("mosaic-memory") / "scene.tif", SIZE)


@pytest.fixture(scope="module")
def scene_in_zone_33(scene: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The same array in zone 33, placed where zone 32's scene lies."""
    x, y = Transformer.from_crs(sources.CRS, "EPSG:32633", always_xy=True).transform(sources.ORIGIN_X, sources.ORIGIN_Y)
    path = tmp_path_factory.mktemp("mosaic-memory-33") / "scene33.tif"
    with rasterio.open(scene) as source:
        profile = source.profile | {
            "crs": "EPSG:32633",
            "transform": from_origin(round(x / 10) * 10, round(y / 10) * 10, sources.RESOLUTION, sources.RESOLUTION),
        }
        with rasterio.open(path, "w", **profile) as destination:
            for _, window in source.block_windows(1):
                destination.write(source.read(window=window), window=window)
    return path


def measure(scene: Path, workdir: Path, scenes: int, other_zone: Path | None = None) -> dict:
    command = [sys.executable, "-m", "tests.earthx.processing.memory_mosaic", str(scene), str(workdir), str(SIZE), str(scenes)]
    if other_zone is not None:
        command.append(str(other_zone))
    output = subprocess.run(command, cwd=BACKEND, capture_output=True, text=True, check=True, timeout=1800)
    return json.loads(output.stdout.strip().splitlines()[-1])


def test_further_scenes_stay_below_the_limit_and_cost_about_what_one_costs(
    scene: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    measured = {}
    for scenes in (1, 2, 8):
        workdir = tmp_path / str(scenes)
        workdir.mkdir()
        measured[scenes] = measure(scene, workdir, scenes)
        assert sorted(path.name for path in workdir.iterdir()) == ["mask.tif", "result.tif"]
    with capsys.disabled():
        for scenes, entry in measured.items():
            print(f"\nmosaic, {scenes} scene(s), {SIZE}²: {entry}")
    assert measured[1]["blocks"] == measured[2]["blocks"] == measured[8]["blocks"]
    assert max(entry["peak_mb"] for entry in measured.values()) < PEAK_LIMIT_MB
    assert measured[2]["peak_mb"] - measured[1]["peak_mb"] <= SECOND_SCENE_LIMIT_MB
    assert measured[8]["peak_mb"] - measured[1]["peak_mb"] <= EIGHTH_SCENE_LIMIT_MB


def test_a_warped_scene_stays_below_the_limit_too(
    scene: Path, scene_in_zone_33: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "grid").mkdir()
    (tmp_path / "warp").mkdir()
    on_grid = measure(scene, tmp_path / "grid", 2)
    warped = measure(scene, tmp_path / "warp", 2, scene_in_zone_33)
    with capsys.disabled():
        print(f"\nmosaic, 2 scenes on the grid: {on_grid}\nmosaic, 2 scenes, the last warped: {warped}")
    assert warped["peak_mb"] < PEAK_LIMIT_MB
    assert warped["peak_mb"] - on_grid["peak_mb"] <= WARPED_SCENE_LIMIT_MB
