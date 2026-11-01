"""The target grid of ``reproject`` is worked out once per question, not once per place that asks (backlog 63).

Finding the grid projects the outline of the raster. The planner asked for the raster behind a ``reproject`` step in
several places of one order (the judgement of the whole stock, the plan, the estimate, the passes of the run), and each
place worked the grid out again. The step now carries the grid the planner worked out (`PlannedStep.place`). What
these tests hold fixed is that nothing else moves: the recipe and its hash, the raster described behind every step, and
the bytes of the result.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import replace
from pathlib import Path

import pytest
from rasterio.transform import from_origin

from earthx.processing import plan, run
from earthx.processing.errors import UnsupportedRecipe
from earthx.processing.operators import REGISTRY, REPROJECT, BandMeta, RasterMeta, ReprojectParams
from earthx.processing.operators import reproject as reproject_module
from earthx.processing.plan import PlannedStep, plan_steps
from earthx.processing.recipe import recipe_hash
from tests.earthx.processing import sources
from tests.earthx.processing.recipes import recipe_of_data
from tests.earthx.processing.test_reproject import HEIGHT, WIDTH, _recipe, _step
from tests.earthx.processing.testops import OPERATORS

#: The hash of the recipe below, taken on the code before the change: the planner reads a recipe and never writes it.
RECIPE_HASH = "c1:47e07b403c27e7ea694f4655c0e1d7cae81ec838ec2062db0c453269faa28fe8"


@pytest.fixture(scope="module")
def band(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("grid-once")
    return sources.build_band_cog(root / "red.tif", sources.ramp(WIDTH, HEIGHT, 1200))


@pytest.fixture
def served(band: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    return sources.serve({sources.url("red"): band}, monkeypatch)


@pytest.fixture
def grids(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[float, float, float, float]]]:
    """The grids worked out, as (CRS, bounds) of the raster each was worked out for."""
    worked: list[tuple[str, tuple[float, float, float, float]]] = []
    real = reproject_module._target_grid

    def counting(meta: RasterMeta, params: ReprojectParams):
        worked.append((meta.crs, meta.bounds))
        return real(meta, params)

    monkeypatch.setattr(reproject_module, "_target_grid", counting)
    return worked


def _order(*steps: dict):
    return recipe_of_data(_recipe(*steps), REGISTRY)


def _meta(**overrides) -> RasterMeta:
    base = {
        "crs": sources.CRS,
        "transform": from_origin(sources.ORIGIN_X, sources.ORIGIN_Y, 10.0, 10.0),
        "width": WIDTH,
        "height": HEIGHT,
        "bands": (BandMeta("red", "float32", float("nan"), None, 1.0, 0.0),),
    }
    return RasterMeta(**{**base, **overrides})


def same(one: RasterMeta, other: RasterMeta) -> bool:
    """Equal as described; compared as text because a band without a value (NaN) is not equal to itself."""
    return repr(one) == repr(other)


def _params(**overrides) -> ReprojectParams:
    return ReprojectParams.model_validate({"crs": "EPSG:3035", "resolution": 10.0, "resampling": "nearest", **overrides})


class TestOnceForEveryQuestion:
    def test_judging_the_bands_works_the_grid_out_once(self, grids: list) -> None:
        plan.check_bands(_order(_step(resampling="bilinear")), REGISTRY)
        assert len(grids) == 1

    def test_the_estimate_works_the_grid_out_once(self, grids: list) -> None:
        plan.estimate(_order(_step(resampling="bilinear")), REGISTRY)
        assert len(grids) == 1

    def test_the_disk_need_works_it_out_once_for_the_estimate_and_once_for_the_stock(self, grids: list) -> None:
        plan.disk_needed(_order(_step(resampling="bilinear")), REGISTRY)
        assert len(grids) == 2

    def test_a_run_works_the_grid_out_once(self, tmp_path: Path, served: list[str], grids: list) -> None:
        run(_order(_step(resampling="bilinear")), workdir=tmp_path, progress=lambda done, total: None)
        assert len(grids) == 1

    def test_each_step_of_a_chain_has_its_own_grid_and_gets_it_once(self, grids: list) -> None:
        second = _step(resampling="nearest", crs="EPSG:32633", resolution=20.0)
        plan.check_bands(_order(_step(resampling="bilinear"), second), REGISTRY)
        assert len(grids) == 2
        assert grids[0] != grids[1], "the second step is asked about the raster the first one leaves"


class TestNothingElseMoves:
    def test_the_recipe_and_its_hash_are_the_same_before_and_after_planning_and_running(
        self, tmp_path: Path, served: list[str]
    ) -> None:
        recipe = _order(_step(resampling="bilinear"))
        before = (recipe.model_dump(mode="json"), recipe_hash(recipe))
        plan.check_bands(recipe, REGISTRY)
        plan.estimate(recipe, REGISTRY)
        run(recipe, workdir=tmp_path, progress=lambda done, total: None)
        assert (recipe.model_dump(mode="json"), recipe_hash(recipe)) == before
        assert before[1] == RECIPE_HASH

    @pytest.mark.parametrize("resampling", ["nearest", "bilinear", "lanczos"])
    def test_the_bytes_of_the_result_are_those_of_a_run_that_works_the_grid_out_again_each_time(
        self, tmp_path: Path, served: list[str], monkeypatch: pytest.MonkeyPatch, resampling: str
    ) -> None:
        (tmp_path / "shared").mkdir()
        (tmp_path / "again").mkdir()
        recipe = _order(_step(resampling=resampling, resolution=15.0))
        shared = run(recipe, workdir=tmp_path / "shared", progress=lambda done, total: None)
        with monkeypatch.context() as patch:
            patch.setattr(PlannedStep, "place", lambda self, meta: self)  # the way it was: no grid carried
            again = run(recipe, workdir=tmp_path / "again", progress=lambda done, total: None)
        assert hashlib.sha256(shared.path.read_bytes()).digest() == hashlib.sha256(again.path.read_bytes()).digest()
        assert shared.properties == again.properties

    @pytest.mark.parametrize("align", [False, True])
    @pytest.mark.parametrize("crs", ["EPSG:3035", "EPSG:4326", "EPSG:32633"])
    def test_the_raster_behind_a_step_is_the_one_transform_gives(self, crs: str, align: bool) -> None:
        params = _params(crs=crs, resolution=0.001 if crs == "EPSG:4326" else 25.0, align=align)
        planned = PlannedStep(None, REPROJECT, params)  # type: ignore[arg-type]
        meta = _meta()
        assert same(planned.place(meta).advance(meta), REPROJECT.transform(meta, params))


class TestOnlyForTheRasterItWasWorkedOutFor:
    def test_placing_twice_keeps_the_first_grid(self, grids: list) -> None:
        planned = PlannedStep(None, REPROJECT, _params()).place(_meta())  # type: ignore[arg-type]
        assert planned.place(_meta()) is planned
        assert len(grids) == 1

    def test_another_raster_gets_its_own_grid(self, grids: list) -> None:
        planned = PlannedStep(None, REPROJECT, _params()).place(_meta())  # type: ignore[arg-type]
        other = _meta(transform=from_origin(sources.ORIGIN_X + 50_000, sources.ORIGIN_Y, 10.0, 10.0))
        advanced = planned.advance(other)
        assert len(grids) == 2, "once to place it, once more for the raster it was not worked out for"
        assert same(advanced, REPROJECT.transform(other, _params()))
        assert not same(advanced, REPROJECT.transform(_meta(), _params()))

    def test_other_parameters_get_their_own_grid(self) -> None:
        planned = PlannedStep(None, REPROJECT, _params()).place(_meta())  # type: ignore[arg-type]
        changed = replace(planned, params=_params(resolution=30.0))
        assert same(changed.advance(_meta()), REPROJECT.transform(_meta(), _params(resolution=30.0)))

    def test_a_step_with_no_grid_to_lay_is_not_touched(self) -> None:
        scale = {"op": "scale", "op_version": 1, "params": {"factor": 2.0}}
        planned = plan_steps(recipe_of_data(_recipe(scale), OPERATORS).steps, OPERATORS)[0]
        assert planned.place(_meta()) is planned
        assert same(planned.advance(_meta()), planned.operator.transform(_meta(), planned.params))  # type: ignore[arg-type]


class TestRefusalsAreThoseOfBefore:
    def test_a_grid_over_the_side_the_core_allows_is_refused_once_with_its_words(self, grids: list) -> None:
        recipe = _order(_step(resampling="nearest", resolution=0.01))
        with pytest.raises(UnsupportedRecipe, match="the target grid would be .* px; the longest side is"):
            plan.estimate(recipe, REGISTRY)
        assert len(grids) == 1

    def test_a_raster_with_no_finite_extent_is_refused_and_nothing_is_kept(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(reproject_module, "transform_bounds", lambda *args, **kwargs: (math.inf, 0.0, 1.0, 1.0))
        planned = PlannedStep(None, REPROJECT, _params())  # type: ignore[arg-type]
        with pytest.raises(UnsupportedRecipe, match="no finite extent"):
            planned.place(_meta())
        assert planned.placed is None
