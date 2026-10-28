"""The estimate of a job on a geographic grid against the run itself (M4-25).

A synthetic DEM tile like ``cop-dem-glo-30``: one degree in EPSG:4326 at one arc second, a smooth
ramp. The recipe reprojects it to EPSG:3035 at 30 m. The estimate sizes the target grid from the
recipe alone; the run does it from the file. They have to agree within a fifth, for every AOI from
0.01° to the whole tile. Everything is synthetic and offline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy
import pytest
import rasterio
from rasterio.transform import from_origin
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

from earthx.processing import run
from earthx.processing.errors import UnsupportedRecipe
from earthx.processing.operators import REGISTRY
from earthx.processing.plan import estimate
from earthx.processing.recipe import recipe_from_data
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved

WEST, NORTH = 9.0, 48.0
PIXELS = 3600  # one degree at one arc second
CENTRE = (WEST + 0.5, NORTH - 0.5)


@pytest.fixture(scope="module")
def tile(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("dem")
    rows, cols = numpy.indices((PIXELS, PIXELS))
    data = ((rows + cols) % 3000).astype("int16")
    plain, path = root / "dem.plain.tif", root / "dem.tif"
    with rasterio.open(
        plain,
        "w",
        driver="GTiff",
        dtype="int16",
        count=1,
        height=PIXELS,
        width=PIXELS,
        crs="EPSG:4326",
        transform=from_origin(WEST, NORTH, 1 / PIXELS, 1 / PIXELS),
        nodata=-32768,
    ) as destination:
        destination.write(data, 1)
    profile = cog_profiles.get("deflate")
    profile.update({"blockxsize": 256, "blockysize": 256})
    cog_translate(plain, path, profile, overview_resampling="nearest", quiet=True)
    plain.unlink()
    return path


def _recipe(
    aoi_degrees: float,
    resolution: float = 30.0,
    *,
    gsd: float | None = 30.0,
    crs: str = "EPSG:4326",
    target: str | None = "EPSG:3035",
    also: float | None = None,
):
    """``target=None`` leaves out the ``reproject`` step; ``also`` adds a second asset of that ``gsd`` after the first."""
    half = aoi_degrees / 2
    west, south, east, north = CENTRE[0] - half, CENTRE[1] - half, CENTRE[0] + half, CENTRE[1] + half
    entry = resolved("DEM", "data", scale=None, offset=None, href=sources.url("dem"))
    entry["asset"]["crs"], entry["gsd"] = crs, gsd
    entry["bands"] = [{"data_type": "int16", "nodata": -32768, "scale": None, "offset": None}]
    steps = (
        []
        if target is None
        else [
            {
                "op": "reproject",
                "op_version": 2,
                "params": {"crs": target, "resolution": resolution, "resampling": "bilinear"},
            }
        ]
    )
    entries = [entry]
    if also is not None:
        second = resolved("DEM", "second", scale=None, offset=None, href=sources.url("dem"))
        second["asset"]["crs"], second["gsd"], second["bands"] = crs, also, entry["bands"]
        entries.append(second)
    data: dict[str, Any] = {
        "recipe_version": 1,
        "inputs": [
            {
                "name": "dem",
                "dataset": "synthetic",
                "groups": [["DEM"]],
                "assets": [e["asset"]["asset"] for e in entries],
                "resolved": entries,
            }
        ],
        "aoi": {
            "type": "Polygon",
            "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
        },
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }
    return recipe_from_data(data, REGISTRY)


@pytest.mark.parametrize("target", ["EPSG:3035", "EPSG:3857"])
@pytest.mark.parametrize("aoi", [0.01, 0.1, 0.5, 1.0])
def test_the_estimated_target_grid_is_the_one_the_run_makes(
    tmp_path: Path, tile: Path, monkeypatch: pytest.MonkeyPatch, aoi: float, target: str
) -> None:
    """EPSG:3857 stretches by 1/cos(latitude) in both directions: a box in the wrong place is off by a factor of two there."""
    sources.serve({sources.url("dem"): tile}, monkeypatch)
    recipe = _recipe(aoi, target=target)
    estimated = estimate(recipe, REGISTRY).output_pixels
    result = run(recipe, workdir=tmp_path, progress=lambda done, total: None)
    actual = result.meta.width * result.meta.height
    assert 0.8 < estimated / actual < 1.2, (estimated, actual)


@pytest.mark.parametrize("gsds", [(90.0, 30.0), (30.0, 90.0)])
def test_assets_of_two_pixel_sizes_are_sized_on_the_finest_in_degrees(gsds: tuple[float, float]) -> None:
    """A geographic asset at 90 m beside one at 30 m: the grid is the 30 m one, whichever stands first (adr/0020 §3.3)."""
    mixed = estimate(_recipe(0.5, gsd=gsds[0], also=gsds[1], target=None), REGISTRY).output_pixels
    fine = estimate(_recipe(0.5, gsd=30.0, target=None), REGISTRY).output_pixels
    coarse = estimate(_recipe(0.5, gsd=90.0, target=None), REGISTRY).output_pixels
    assert mixed == fine
    assert 8 < mixed / coarse < 10


class TestTheSideCapOfTheTargetGrid:
    """32 768 px is the core's limit for the grid it makes; the estimate applies it only where the grid is that big."""

    def test_a_degree_at_4_m_is_under_it(self) -> None:
        # About 18 600 x 27 900 px: the old estimate called this one UnsupportedRecipe whatever the AOI.
        assert estimate(_recipe(1.0, 4.0), REGISTRY).output_pixels > 400_000_000

    def test_a_degree_at_3_m_is_over_it(self) -> None:
        with pytest.raises(UnsupportedRecipe, match="longest side is 32768"):
            estimate(_recipe(1.0, 3.0), REGISTRY)

    def test_a_small_area_is_far_under_it_at_any_resolution_that_makes_sense(self) -> None:
        assert estimate(_recipe(0.01, 3.0), REGISTRY).output_pixels < 10_000_000


class TestWhatTheEstimateCannotSize:
    def test_a_missing_gsd_is_named_not_guessed(self) -> None:
        with pytest.raises(UnsupportedRecipe, match=r"pixel size of asset 'data'.*no gsd"):
            estimate(_recipe(0.1, gsd=None), REGISTRY)

    def test_a_crs_nobody_knows_is_not_a_crash(self) -> None:
        with pytest.raises(UnsupportedRecipe, match="cannot be placed in the CRS"):
            estimate(_recipe(0.1, crs="EPSG:0"), REGISTRY)
