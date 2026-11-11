"""The nodata of a job's result, through the real core and readers (plan M5-28, Otto 11.11.2026).

Synthetic COGs: ``counts`` (``uint16``, nodata 0, unscaled, like Sentinel-1 DN or WorldCover classes), ``heights``
(``float32``, nodata −9999, like swissALTI3D) and ``dem`` (``float32`` without nodata, like the Copernicus DEM). Each
holds 0 as a real value where its kind allows it: 0 m is sea level.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy
import pytest
import rasterio

from earthx.processing import run
from earthx.processing.core import NODATA_MOVED_PROPERTY
from earthx.processing.errors import UnsupportedRecipe
from earthx.processing.operators import REGISTRY
from earthx.processing.plan import estimate
from earthx.processing.recipe import recipe_from_data
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved

WIDTH, HEIGHT = 96, 64

SOURCES = {
    "counts": ("uint16", 0),
    "heights": ("float32", -9999),
    "dem": ("float32", None),
}


def _heights() -> numpy.ndarray:
    rows, cols = numpy.indices((HEIGHT, WIDTH))
    data = (rows * 10.0 - 200.0 + cols * 0.25).astype("float32")  # below and above 0 m, 0 m itself in row 20
    data[20, :] = 0.0
    data[:8, :8] = -9999.0
    return data


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("nodata")
    dem = _heights()
    dem[:8, :8] = 0.0
    return {
        "counts": sources.build_band_cog(root / "counts.tif", sources.ramp(WIDTH, HEIGHT, 100), scale=None, offset=None),
        "heights": sources.build_band_cog(root / "heights.tif", _heights(), scale=None, offset=None, nodata=-9999),
        "dem": sources.build_band_cog(root / "dem.tif", dem, scale=None, offset=None, nodata=None),
    }


@pytest.fixture(autouse=True)
def served(files: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    sources.serve({sources.url(name): path for name, path in files.items()}, monkeypatch)


def _recipe(asset: str, steps: list, bands: list[str], dtype: str) -> dict:
    data_type, nodata = SOURCES[asset]
    entry = resolved("ITEM_A", asset, href=sources.url(asset), scale=None, offset=None)
    entry["bands"] = [{"data_type": data_type, "nodata": nodata, "scale": None, "offset": None}]
    return {
        "recipe_version": 2,
        "inputs": [
            {"name": "in", "dataset": "synthetic", "groups": [["ITEM_A"]], "assets": [asset], "resolved": [entry]}
        ],
        "aoi": sources.whole(WIDTH, HEIGHT),
        "steps": steps,
        "output": {"kind": "raster", "format": "cog", "dtype": dtype, "bands": bands},
    }


def _run(data: dict, workdir: Path):
    return run(recipe_from_data(data, REGISTRY), workdir=workdir, progress=lambda done, total: None, operators=REGISTRY)


def _file(path: Path) -> tuple[numpy.ndarray, float | None]:
    with rasterio.open(path) as dataset:
        return dataset.read(1), dataset.nodata


def _math(expression: str, name: str = "x") -> dict:
    return {"op": "band_math", "op_version": 2, "params": {"expression": expression, "name": name}}


def _reproject(resampling: str) -> dict:
    params = {"crs": "EPSG:32632", "resolution": 10.0, "resampling": resampling, "align": True}
    return {"op": "reproject", "op_version": 4, "params": params}


class TestTheSourceNodataIsKept:
    def test_where_the_steps_only_pass_integers_on(self, tmp_path: Path) -> None:
        result = _run(_recipe("counts", [], ["counts"], "uint16"), tmp_path)
        values, nodata = _file(result.path)
        assert nodata == 0
        assert result.properties["bands"][0]["nodata"] == 0
        assert NODATA_MOVED_PROPERTY not in result.properties

    def test_and_after_nearest(self, tmp_path: Path) -> None:
        assert _file(_run(_recipe("counts", [_reproject("nearest")], ["counts"], "uint16"), tmp_path).path)[1] == 0


class TestTheEdgeOfTheType:
    def test_an_interpolating_step_takes_it_so_an_overshoot_to_0_stays_a_value(self, tmp_path: Path) -> None:
        result = _run(_recipe("counts", [_reproject("cubic")], ["counts"], "uint16"), tmp_path)
        assert _file(result.path)[1] == 65535

    def test_band_math_into_a_signed_type_keeps_0_as_a_value(self, tmp_path: Path) -> None:
        result = _run(_recipe("counts", [_math("counts * 0")], ["x"], "int16"), tmp_path)
        values, nodata = _file(result.path)
        assert nodata == -32768
        valid = values != nodata
        assert valid.sum() == result.valid_pixels == WIDTH * HEIGHT - 64
        assert set(numpy.unique(values[valid]).tolist()) == {0}

    def test_a_float_source_into_an_integer_type_takes_it_and_0_m_stays_a_value(self, tmp_path: Path) -> None:
        result = _run(_recipe("heights", [], ["heights"], "int16"), tmp_path)
        values, nodata = _file(result.path)
        assert nodata == -32768
        assert (values[20, 8:] == 0).all()
        assert (values[:8, :8] == -32768).all()


class TestAValueOnTheNodataIsMoved:
    def test_down_by_one_counted_per_band_and_counted_as_valid(self, tmp_path: Path) -> None:
        result = _run(_recipe("counts", [_math("counts * 0 + 70000", "top")], ["top"], "uint16"), tmp_path)
        values, nodata = _file(result.path)
        assert nodata == 65535
        valid = WIDTH * HEIGHT - 64
        assert (values == 65534).sum() == valid == result.valid_pixels
        assert result.properties[NODATA_MOVED_PROPERTY] == {"top": valid}
        statistics = result.properties["bands"][0]["statistics"]
        assert statistics["maximum"] == 65534

    def test_an_integer_into_a_narrower_type_is_clamped_not_wrapped(self, tmp_path: Path) -> None:
        result = _run(_recipe("counts", [], ["counts"], "uint8"), tmp_path)
        values, nodata = _file(result.path)
        assert nodata == 0
        assert (values[:8, :8] == 0).all()
        assert values[8:, :].min() >= 1 and values.max() == 255


class TestRefusal:
    def test_a_source_nodata_the_type_cannot_hold_fails_before_the_first_block(self, tmp_path: Path) -> None:
        ticks: list[int] = []
        with pytest.raises(UnsupportedRecipe, match="nodata -9999 does not fit the output type uint16"):
            run(
                recipe_from_data(_recipe("heights", [], ["heights"], "uint16"), REGISTRY),
                workdir=tmp_path,
                progress=lambda done, total: ticks.append(done),
                operators=REGISTRY,
            )
        assert ticks == [] and list(tmp_path.iterdir()) == []

    def test_the_estimate_refuses_it_from_the_item_before_the_job_waits(self) -> None:
        with pytest.raises(UnsupportedRecipe, match="-9999 does not fit the output type uint8"):
            estimate(recipe_from_data(_recipe("heights", [], ["heights"], "uint8"), REGISTRY), REGISTRY)

    def test_after_band_math_the_source_nodata_is_not_in_the_result_and_nothing_is_refused(self) -> None:
        recipe = recipe_from_data(_recipe("heights", [_math("heights * 2")], ["x"], "uint16"), REGISTRY)
        assert estimate(recipe, REGISTRY).output_pixels > 0


class TestFloat:
    def test_a_float_source_without_nodata_keeps_0_m_and_marks_nothing(self, tmp_path: Path) -> None:
        result = _run(_recipe("dem", [], ["dem"], "float32"), tmp_path)
        values, nodata = _file(result.path)
        assert nodata is not None and math.isnan(nodata)
        assert (values[:8, :8] == 0).all() and result.valid_pixels == WIDTH * HEIGHT
