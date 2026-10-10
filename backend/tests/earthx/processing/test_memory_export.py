"""Peak memory of an export: below the limit, and a second item does not add a second scene (M4-11a).

Otto, 08.10.2026: the export reads the items of a group one after the other, and the
memory limit holds per item, shown with a test over two items. The scene is a
three-band ``uint8`` ``visual`` of ``SIZE``² with a nodata stripe in every block, so the
mosaic reads both items for every block. Each run happens in a fresh process
(``memory_export.py``) that measures its own ``VmHWM``, as ``test_memory_8192.py`` does.
"""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
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

SIZE = 6144

#: The limit of a whole worker child that M4-07a set for a raster run (F11), held by the export too.
PEAK_LIMIT_MB = 500

#: What the second item may add to the peak: its open dataset and warp, never a second
#: scene or a second read cache. Measured +4 to +8 MB in the session (one item 355–357 MB, two 361–364,
#: eight 375); before the items of a group shared one item's ``VSI_CACHE_SIZE`` it was
#: +64 MB per item (plan M4-11 §11).
SECOND_ITEM_LIMIT_MB = 16


def build_scene(path: Path, size: int) -> Path:
    generator = numpy.random.default_rng(seed=20261008)
    profile = {
        "driver": "GTiff", "dtype": "uint8", "count": 3, "width": size, "height": size, "crs": sources.CRS,
        "transform": from_origin(sources.ORIGIN_X, sources.ORIGIN_Y, sources.RESOLUTION, sources.RESOLUTION),
        "nodata": 0, "tiled": True, "blockxsize": 512, "blockysize": 512,
    }  # fmt: skip
    plain = path.with_suffix(".plain.tif")
    stripe = (numpy.arange(size) % 512) < 6
    with rasterio.open(plain, "w", **profile) as destination:
        for row in range(0, size, 512):
            block = generator.integers(1, 255, (3, 512, size), dtype="uint8")
            block[:, :, stripe] = 0
            destination.write(block, window=Window(0, row, size, 512))
    cog_profile = cog_profiles.get("deflate")
    cog_profile.update({"blockxsize": 512, "blockysize": 512})
    cog_translate(plain, path, cog_profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path


@pytest.fixture(scope="module")
def scene(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_scene(tmp_path_factory.mktemp("export-memory") / "scene.tif", SIZE)


def measure(scene: Path, workdir: Path, items: int) -> dict:
    command = [
        sys.executable, "-m", "tests.earthx.processing.memory_export", str(scene), str(workdir), str(SIZE), str(items),
    ]  # fmt: skip
    output = subprocess.run(command, cwd=BACKEND, capture_output=True, text=True, check=True, timeout=900)
    return json.loads(output.stdout.strip().splitlines()[-1])


def test_two_items_stay_below_the_limit_and_cost_about_what_one_costs(
    scene: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    measured = {}
    for items in (1, 2):
        workdir = tmp_path / str(items)
        workdir.mkdir()
        measured[items] = measure(scene, workdir, items)
        with zipfile.ZipFile(workdir / "export.zip") as archive:
            assert archive.namelist()[:2] == ["visual.tif", "visual_mask.tif"]
    growth = measured[2]["peak_mb"] - measured[1]["peak_mb"]
    with capsys.disabled():
        for items in (1, 2):
            print(f"\nexport memory, {items} item(s), {SIZE}²: {measured[items]}")
        print(f"export memory, second item: {growth:+.1f} MB")
    assert measured[1]["blocks"] == measured[2]["blocks"]
    assert max(entry["peak_mb"] for entry in measured.values()) < PEAK_LIMIT_MB
    assert growth <= SECOND_ITEM_LIMIT_MB
