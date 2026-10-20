"""The ``reproject`` operator (adr/0014 §3.4, §5.2, §5.3; plans M4-10, M4-24).

The plausibility against one whole ``reproject`` per method and case (§6.3 row 4,
§15j) is in ``test_reproject_tolerance.py``.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy
import pytest
import rasterio
from pydantic import ValidationError
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject as warp_reproject
from rasterio.windows import Window
from rio_tiler.io import Reader

from earthx.catalog.datasets import REGISTRY as DATASETS
from earthx.processing import run
from earthx.processing.errors import RecipeInvalid, UnknownOperator, UnsupportedRecipe
from earthx.processing.operators import (
    REGISTRY,
    REPROJECT,
    REPROJECT_V2,
    BandMeta,
    RasterMeta,
    ReprojectParams,
    applicable,
)
from earthx.processing.operators import reproject as reproject_module
from earthx.processing.recipe import recipe_from_data
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import resolved
from tests.earthx.processing.test_reproject_tolerance import Measured, row
from tests.earthx.processing.testops import OPERATORS

WIDTH, HEIGHT = 1300, 1100

METHODS = ("nearest", "bilinear", "cubic", "cubicspline", "lanczos", "average", "mode")
OLD_METHODS = ("nearest", "bilinear", "cubic")


def _params(**overrides) -> ReprojectParams:
    data = {"crs": "EPSG:3035", "resolution": 10.0, "resampling": "nearest", **overrides}
    return ReprojectParams.model_validate_json(json.dumps(data), strict=True)


def _step(**overrides) -> dict:
    params = {"crs": "EPSG:3035", "resolution": 10.0, "resampling": "nearest", **overrides}
    return {"op": "reproject", "op_version": 3, "params": params}


class TestParameters:
    def test_a_valid_order(self) -> None:
        params = _params(resampling="bilinear", align=True)
        assert (params.crs, params.resolution, params.resampling, params.align) == ("EPSG:3035", 10.0, "bilinear", True)

    def test_there_is_no_default_resampling(self) -> None:
        with pytest.raises(ValidationError, match="resampling"):
            ReprojectParams.model_validate_json('{"crs": "EPSG:3035", "resolution": 10}', strict=True)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"crs": "3035"},
            {"crs": "epsg:3035"},
            {"crs": "EPSG:3035; DROP"},
            {"crs": "EPSG:99999"},
            {"crs": "+proj=utm +zone=32"},
            {"resolution": 0},
            {"resolution": -10},
            {"resolution": "10"},
            {"resampling": "magic"},
            {"resampling": "near"},
            {"resampling": "cubic_spline"},
            {"resampling": "gauss"},
            {"resampling": "sum"},
            {"resampling": "Mode"},
            {"align": "yes"},
            {"tolerance": 0},
            {"warp_mem_limit": 1},
            {"block_size": 512},
        ],
        ids=str,
    )
    def test_a_misuse_is_refused(self, overrides: dict) -> None:
        with pytest.raises(ValidationError):
            _params(**overrides)

    @pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
    def test_a_resolution_that_is_not_a_number_is_refused(self, value: str) -> None:
        with pytest.raises(ValidationError):
            ReprojectParams.model_validate_json(
                f'{{"crs": "EPSG:3035", "resolution": {value}, "resampling": "nearest"}}', strict=True
            )

    def test_the_parameters_are_a_json_schema(self) -> None:
        schema = REGISTRY.params_schema("reproject", 3)
        assert schema["required"] == ["crs", "resolution", "resampling"]
        assert schema["additionalProperties"] is False

    def test_each_method_is_described_in_one_sentence_and_none_is_the_default(self) -> None:
        resampling = REGISTRY.params_schema("reproject", 3)["properties"]["resampling"]
        assert "default" not in resampling and "enum" not in resampling
        assert [choice["const"] for choice in resampling["oneOf"]] == list(METHODS)
        for choice in resampling["oneOf"]:
            assert choice["title"] == choice["const"]
            assert choice["description"].endswith(".") and choice["description"].count(". ") == 0

    @pytest.mark.parametrize("method", METHODS)
    def test_every_method_is_accepted(self, method: str) -> None:
        assert _params(resampling=method).resampling == method


class TestWhereItApplies:
    @pytest.mark.parametrize("config", list(DATASETS), ids=lambda config: config.dataset_id)
    def test_every_registry_entry_allows_it(self, config) -> None:
        for resampling in METHODS:
            assert applicable(REPROJECT, config, _params(resampling=resampling)) == []

    def test_without_the_reprojection_flag(self) -> None:
        config = next(iter(DATASETS))
        config = replace(config, capabilities=replace(config.capabilities, reprojection=False))
        for resampling in ("nearest", "bilinear"):
            assert f"{config.dataset_id} does not allow reprojection" in applicable(
                REPROJECT, config, _params(resampling=resampling)
            )

    @pytest.mark.parametrize("resampling", ["nearest", "mode"])
    def test_a_method_that_picks_a_source_value_does_not_need_interpolation(self, resampling: str) -> None:
        config = next(iter(DATASETS))
        config = replace(config, capabilities=replace(config.capabilities, interpolation=False))
        assert applicable(REPROJECT, config, _params(resampling=resampling)) == []

    @pytest.mark.parametrize("resampling", ["bilinear", "cubic", "cubicspline", "lanczos", "average"])
    def test_every_other_method_needs_interpolation(self, resampling: str) -> None:
        config = next(iter(DATASETS))
        config = replace(config, capabilities=replace(config.capabilities, interpolation=False))
        assert applicable(REPROJECT, config, _params(resampling=resampling)) == [
            f"{config.dataset_id} does not allow interpolation"
        ]

    def test_it_runs_in_t2_only(self) -> None:
        assert (REPROJECT.kind, {tier.value for tier in REPROJECT.tiers}) == ("grid", {"T2"})


def _meta(**overrides) -> RasterMeta:
    base = {
        "crs": sources.CRS,
        "transform": from_origin(sources.ORIGIN_X, sources.ORIGIN_Y, 10.0, 10.0),
        "width": WIDTH,
        "height": HEIGHT,
        "bands": (BandMeta("red", "float32", float("nan"), None, 1.0, 0.0),),
    }
    return RasterMeta(**{**base, **overrides})


class TestTheTargetGrid:
    def test_the_grid_covers_the_source_and_is_marked_resampled(self) -> None:
        source = _meta()
        target = REPROJECT.transform(source, _params())
        assert target.crs == "EPSG:3035" and target.resampled is True
        assert target.resolution == (10.0, 10.0)
        assert target.bands == source.bands
        left, bottom, right, top = target.bounds
        assert right - left >= WIDTH * 10 * 0.99 and top - bottom >= HEIGHT * 10 * 0.99

    def test_align_snaps_the_edges_to_multiples_of_the_resolution(self) -> None:
        target = REPROJECT.transform(_meta(), _params(resolution=100.0, align=True))
        assert all(value % 100.0 == 0 for value in target.bounds)

    def test_without_align_the_grid_starts_at_the_data(self) -> None:
        target = REPROJECT.transform(_meta(), _params(resolution=100.0))
        assert any(value % 100.0 != 0 for value in target.bounds)

    def test_a_resolution_that_makes_the_grid_absurd_is_refused(self) -> None:
        with pytest.raises(UnsupportedRecipe, match="longest side"):
            REPROJECT.transform(_meta(), _params(resolution=0.01))

    def test_the_cost_depends_on_the_method(self) -> None:
        costs = {name: REPROJECT.cost_factor(_params(resampling=name)) for name in METHODS}
        assert costs == {  # adr/0014 §5.5 and §15j (plan M4-24 §7.4)
            "nearest": 0.4,
            "bilinear": 1.0,
            "cubic": 1.1,
            "cubicspline": 1.7,
            "lanczos": 2.2,
            "average": 1.2,
            "mode": 1.1,
        }

    def test_the_lineage_says_what_happened(self) -> None:
        assert REPROJECT.lineage(_params(resampling="cubic")) == "reprojected to EPSG:3035 at 10 (cubic)"

    def test_the_block_plan_is_part_of_the_version_not_of_the_order(self) -> None:
        assert (reproject_module.TOLERANCE, reproject_module.WARP_MEM_LIMIT_MB) == (0.125, 64.0)
        assert (REPROJECT.op_version, REPROJECT_V2.op_version) == (3, 2)

    def test_a_recipe_of_version_1_is_refused(self) -> None:
        with pytest.raises(UnknownOperator):
            recipe_from_data(_recipe({**_step(), "op_version": 1}), REGISTRY)

    @pytest.mark.parametrize("method", ["cubicspline", "lanczos", "average", "mode"])
    def test_version_2_does_not_know_the_methods_of_version_3(self, method: str) -> None:
        with pytest.raises(RecipeInvalid, match="resampling"):
            recipe_from_data(_recipe({**_step(resampling=method), "op_version": 2}), REGISTRY)

    def test_version_2_is_the_same_operator_with_the_old_methods(self) -> None:
        for method in OLD_METHODS:
            params = REPROJECT_V2.params.model_validate_json(
                json.dumps(_step(resampling=method)["params"]), strict=True
            )
            assert REPROJECT_V2.cost_factor(params) == REPROJECT.cost_factor(_params(resampling=method))
            assert REPROJECT_V2.extra_requirements(params) == REPROJECT.extra_requirements(_params(resampling=method))


def _work_file(path: Path, size: int) -> Path:
    """A float64 pass file as the core writes it: two noisy bands, NaN where masked, a NaN strip."""
    generator = numpy.random.default_rng(seed=20261007)
    rows, cols = numpy.arange(size)[:, None], numpy.arange(size)[None, :]
    red = 0.12 + 0.04 * numpy.sin(rows / 90) + 0.03 * numpy.cos(cols / 70) + generator.normal(0, 0.006, (size, size))
    data = numpy.stack([red, 2 * red])
    data[:, :, size // 2 : size // 2 + 40] = numpy.nan
    profile = {
        "driver": "GTiff",
        "dtype": "float64",
        "count": 2,
        "width": size,
        "height": size,
        "crs": sources.CRS,
        "transform": from_origin(sources.ORIGIN_X, sources.ORIGIN_Y, sources.RESOLUTION, sources.RESOLUTION),
        "nodata": float("nan"),
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(path, "w", **profile) as destination:
        destination.write(data)
    return path


@pytest.mark.parametrize("resampling", METHODS)
def test_a_block_is_masked_exactly_where_the_warp_left_no_value(tmp_path: Path, resampling: str) -> None:
    """Version 1 took the mask from a second warp and masked values the first one had (M4-10b)."""
    params = _params(resampling=resampling)
    with rasterio.open(_work_file(tmp_path / "pass-0.tif", 1024)) as source:
        bands = tuple(BandMeta(name, "float64", float("nan")) for name in ("red", "nir"))
        target = REPROJECT.transform(_meta(width=1024, height=1024, bands=bands), params)
        block = REPROJECT.run(source, target, Window(0, 0, 1024, 1024), params)
    assert block.dtype == numpy.float64
    assert 0 < block.mask.sum() < block.size
    assert numpy.array_equal(block.mask, numpy.isnan(block.data))


@pytest.fixture(scope="module")
def band(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("reproject")
    return sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200))


@pytest.fixture
def served(band: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return sources.serve({sources.url("red"): band}, monkeypatch)


def _recipe(*steps: dict) -> dict:
    entry = resolved("ITEM_A", "red", href=sources.url("red"))
    return {
        "recipe_version": 1,
        "inputs": [
            {"name": "s2", "dataset": "synthetic", "groups": [["ITEM_A"]], "assets": ["red"], "resolved": [entry]}
        ],
        "aoi": sources.whole(WIDTH, HEIGHT),
        "steps": list(steps),
        "output": {"kind": "raster", "format": "cog", "dtype": "float32"},
    }


def _run(tmp_path: Path, *steps: dict):
    return run(recipe_from_data(_recipe(*steps), REGISTRY), workdir=tmp_path, progress=lambda done, total: None)


def _read(path: Path) -> numpy.ma.MaskedArray:
    with rasterio.open(path) as dataset:
        return dataset.read(1, masked=True)


def _reference(band: Path, result, resampling: Resampling) -> numpy.ndarray:
    """The whole raster in one ``reproject`` call onto the grid the operator chose (§6.3 row 4)."""
    with Reader(str(band)) as reader:  # the tile path's unscale, as the core's first pass
        physical = reader.read(unscale=True).array[0].astype("float64").filled(numpy.nan)
    with rasterio.open(band) as dataset:
        out = numpy.full((result.meta.height, result.meta.width), numpy.nan)
        warp_reproject(
            physical,
            out,
            src_transform=dataset.transform,
            src_crs=dataset.crs,
            src_nodata=numpy.nan,
            dst_transform=result.meta.transform,
            dst_crs=result.meta.crs,
            dst_nodata=numpy.nan,
            resampling=resampling,
        )
    return out.astype("float32").astype("float64")  # the result is stored as float32


def _compare(result, reference: numpy.ndarray) -> tuple[float, float, float]:
    """``(share of identical valid pixels, p99, max)`` of the difference where both are valid."""
    data = _read(result.path)
    both = ~numpy.ma.getmaskarray(data) & ~numpy.isnan(reference)
    difference = numpy.abs(data.filled(numpy.nan).astype("float64") - reference)[both]
    assert both.sum() > 0.9 * numpy.isfinite(reference).sum()
    return float((difference == 0).mean()), float(numpy.percentile(difference, 99)), float(difference.max())


@pytest.mark.usefixtures("served")
class TestAWholeRun:
    @pytest.mark.parametrize("method", METHODS)
    def test_a_whole_run_stays_inside_the_row_of_its_method(self, tmp_path: Path, band: Path, method: str) -> None:
        """The whole core, unscaling included, on a ramp of reflectance: unit-less like NDVI (§6.3, §15j)."""
        result = _run(tmp_path, _step(resampling=method, resolution=15.0))
        identical, p99, worst = _compare(result, _reference(band, result, reproject_module._METHODS[method][0]))
        row(method, "ndvi", "same").check(Measured(identical, p99, worst))

    def test_v2_and_v3_give_the_same_bytes_for_the_methods_of_version_2(self, tmp_path: Path) -> None:
        for method in OLD_METHODS:
            (tmp_path / f"{method}-2").mkdir()
            (tmp_path / f"{method}-3").mkdir()
            two = _run(tmp_path / f"{method}-2", {**_step(resampling=method), "op_version": 2})
            three = _run(tmp_path / f"{method}-3", _step(resampling=method))
            assert _read(two.path).tobytes() == _read(three.path).tobytes()
            assert numpy.array_equal(_read(two.path).mask, _read(three.path).mask)

    def test_the_result_is_in_the_new_grid_and_says_so(self, tmp_path: Path) -> None:
        result = _run(tmp_path, _step(resampling="bilinear"))
        with rasterio.open(result.path) as data:
            assert data.crs.to_epsg() == 3035
            assert (data.width, data.height) == (result.meta.width, result.meta.height)
            assert data.dtypes == ("float32",)
        assert result.properties["proj:code"] == "EPSG:3035"
        assert result.properties["earthx:resampled"] is True
        assert result.properties["processing:lineage"] == "reprojected to EPSG:3035 at 10 (bilinear)"

    def test_the_corner_without_data_stays_without_data(self, tmp_path: Path) -> None:
        result = _run(tmp_path, _step(resampling="nearest", resolution=10.0))
        data = _read(result.path)
        assert data.mask.any() and not data.mask.all()

    @pytest.mark.parametrize("resampling", METHODS)
    def test_two_runs_are_bit_identical(self, tmp_path: Path, resampling: str) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        first = _run(tmp_path / "a", _step(resampling=resampling))
        second = _run(tmp_path / "b", _step(resampling=resampling))
        one, two = _read(first.path), _read(second.path)
        assert one.tobytes() == two.tobytes()
        assert numpy.array_equal(one.mask, two.mask)

    def test_a_step_behind_a_pixel_step(self, tmp_path: Path) -> None:
        scale = {"op": "scale", "op_version": 1, "params": {"factor": 2.0}}
        recipe = recipe_from_data(_recipe(scale, _step(resampling="nearest")), OPERATORS)
        result = run(recipe, workdir=tmp_path, progress=lambda done, total: None, operators=OPERATORS)
        assert result.properties["processing:lineage"].startswith("scaled by 2.0; reprojected to EPSG:3035")
