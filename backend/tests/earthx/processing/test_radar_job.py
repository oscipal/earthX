"""A job over a dataset placed by GCPs stays in radar geometry (DS-04d): one scene or the joined slices of a pass, the
source's pixels in their own rows and columns, the GCPs shifted onto the window, no CRS; and the map shows the result
through the spline of its GCPs (A3). Synthetic slices (`mini_pass`), read through the real readers."""

from __future__ import annotations

import copy
import warnings
from pathlib import Path
from typing import Any

import numpy
import pytest
import rasterio
from rasterio.errors import NotGeoreferencedWarning
from rio_tiler.constants import WEB_MERCATOR_TMS

from earthx.access.radar import gcp_key, item_line_times
from earthx.api.result_tiles import ResultPath, ResultReader, result_statistics
from earthx.processing import run
from earthx.processing.core import area_statistics
from earthx.processing.errors import AoiOutsideInputs, GridMismatch
from earthx.processing.recipe import recipe_from_data
from earthx.readers.cog import AS_WRITTEN, AssetPath
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import recipe_data, resolved
from tests.earthx.processing.testops import OPERATORS
from tests.earthx.readers import mini_pass

ITEMS = ["slice-0", "slice-1"]


def area(line0: float, col0: float, line1: float, col1: float) -> dict[str, Any]:
    ring = [list(mini_pass.position(line, col)) for line, col in ((line0, col0), (line0, col1), (line1, col1), (line1, col0))]
    return {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}


ACROSS = area(50, 10, 80, 50)


@pytest.fixture(scope="module")
def slices(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    directory = tmp_path_factory.mktemp("pass")
    return {name: mini_pass.build_slice(directory / f"{name}.tif", index) for index, name in enumerate(ITEMS)}


@pytest.fixture
def served(slices: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    sources.serve({sources.url(name): path for name, path in slices.items()}, monkeypatch)


def recipe(
    group: list[str], aoi: dict[str, Any] = ACROSS, *, gap_lines: int = 0, times: bool = True, steps: list | None = None
) -> Any:
    entries = []
    for name in group:
        entry = resolved(name, "vv", scale=None, offset=None, href=sources.url(name))
        entry["asset"].update(crs=None, georeferencing="gcp_tps")
        entries.append(entry)
    line_times = {}
    for name in group:
        index = ITEMS.index(name)
        stac = mini_pass.item(index, gap_lines=gap_lines if index else 0, item_id=name)
        first, last = item_line_times(stac, mini_pass.FIRST_LINE, mini_pass.LAST_LINE)
        line_times[name] = {"first": first.isoformat(), "last": last.isoformat()}
    data = recipe_data(
        inputs=[
            {
                "name": "s1", "dataset": "synthetic", "groups": [list(group)], "assets": ["vv"], "resolved": entries,
                **({"line_times": line_times} if times else {}),
            }
        ],
        aoi=copy.deepcopy(aoi),
        steps=steps or [],
        output={"kind": "raster", "format": "cog", "dtype": "uint16" if not steps else "float32", "bands": ["vv"]},
    )  # fmt: skip
    return recipe_from_data(data, OPERATORS)


def lines_and_cols(path: Path) -> tuple[numpy.ndarray, numpy.ndarray]:
    with rasterio.open(path) as dataset:
        return numpy.vectorize(mini_pass.value_at)(dataset.read(1))


@pytest.mark.usefixtures("served")
def test_a_job_joins_the_slices_of_a_pass_in_radar_geometry(tmp_path: Path) -> None:
    result = run(recipe(ITEMS), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)
    with rasterio.open(result.path) as out, rasterio.open(result.mask_path) as mask:
        assert out.crs is None and out.transform.is_identity
        assert gcp_key(out) == gcp_key(mask)
        assert len(out.gcps[0]) == 2 * len(mini_pass.gcps(0, mini_pass.WIDTHS[0]))
        assert mask.read(1).any()
    lines, cols = lines_and_cols(result.path)
    # One row of the result is one line of the pass, across the seam: nothing warped, nothing flipped.
    assert (numpy.diff(lines, axis=0) == 1).all() and (numpy.diff(cols, axis=1) == 1).all()
    assert lines.min() < mini_pass.HEIGHT <= lines.max()
    assert result.properties["earthx:georeferencing"] == "gcp_tps"
    assert "proj:code" not in result.properties and "gsd" not in result.properties
    assert result.properties["processing:lineage"].startswith("mosaic of 2 scenes")


@pytest.mark.usefixtures("served")
def test_two_runs_of_a_pass_give_the_same_bytes(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = run(recipe(ITEMS), workdir=tmp_path / "a", progress=lambda *_: None, operators=OPERATORS)
    second = run(recipe(ITEMS), workdir=tmp_path / "b", progress=lambda *_: None, operators=OPERATORS)
    assert Path(first.path).read_bytes() == Path(second.path).read_bytes()


@pytest.mark.usefixtures("served")
@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"gap_lines": mini_pass.HEIGHT}, "missing"),
        ({"gap_lines": -2}, "overlap"),
        ({"times": False}, "no times"),
    ],
    ids=["a missing slice", "an overlap", "no line times"],
)
def test_slices_that_do_not_join_fail_the_job_with_the_reason(tmp_path: Path, changes: dict, reason: str) -> None:
    with pytest.raises(GridMismatch, match=reason):
        run(recipe(ITEMS, **changes), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)
    assert not any(tmp_path.iterdir())


@pytest.mark.usefixtures("served")
def test_an_aoi_beside_the_scene_fails_the_job(tmp_path: Path) -> None:
    with pytest.raises(AoiOutsideInputs):
        run(recipe(["slice-0"], area(400, 400, 420, 420)), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)


@pytest.mark.usefixtures("served")
def test_a_pixel_step_runs_on_the_radar_grid(tmp_path: Path) -> None:
    steps = [{"op": "scale", "op_version": 1, "params": {"factor": 2.0}}]
    plain = run(recipe(ITEMS), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)
    (tmp_path / "scaled").mkdir()
    scaled = run(recipe(ITEMS, steps=steps), workdir=tmp_path / "scaled", progress=lambda *_: None, operators=OPERATORS)
    with rasterio.open(plain.path) as a, rasterio.open(scaled.path) as b:
        assert b.crs is None and gcp_key(a) == gcp_key(b)
        values, doubled = a.read(1).astype("float64"), b.read(1).astype("float64")
    valid = values != mini_pass.NODATA
    assert numpy.allclose(doubled[valid], 2 * values[valid])


@pytest.mark.usefixtures("served")
@pytest.mark.parametrize("max_pixels", [1_000_000, 200], ids=["on the job's grid", "on a coarser grid"])
def test_the_statistics_of_the_area_are_read_in_radar_geometry(tmp_path: Path, max_pixels: int) -> None:
    measured = area_statistics(recipe(ITEMS), operators=OPERATORS, max_pixels=max_pixels)
    (band,) = measured.bands
    lines_min = (band["statistics"]["minimum"] - 1) // mini_pass.WIDTH
    lines_max = (band["statistics"]["maximum"] - 1) // mini_pass.WIDTH
    assert lines_min < mini_pass.HEIGHT <= lines_max
    if max_pixels > 200:
        result = run(recipe(ITEMS), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)
        assert measured.factor == 1
        assert band["statistics"] == result.properties["bands"][0]["statistics"]
    else:
        assert measured.factor > 1


@pytest.mark.usefixtures("served")
def test_the_map_shows_a_radar_result_through_its_spline(tmp_path: Path) -> None:
    result = run(recipe(ITEMS), workdir=tmp_path, progress=lambda *_: None, operators=OPERATORS)
    mask = AssetPath(str(result.mask_path), dataset_id="", item_id="", asset="mask.tif", georeferencing=AS_WRITTEN)
    path = ResultPath(str(result.path), mask=mask)
    lon, lat = mini_pass.position(mini_pass.HEIGHT, 30)
    tile = WEB_MERCATOR_TMS.tile(lon, lat, 16)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with ResultReader(path) as reader:
            assert reader.dataset.crs is not None
            image = reader.tile(tile.x, tile.y, tile.z, indexes=(1,))
        statistics = result_statistics(path, {})
    assert (~numpy.ma.getmaskarray(image.array)).any()
    assert statistics[0]["statistics"]["count"] > 0
