"""T2 ↔ T2L: the same recipe through the child of `jobs` and through the runner (adr/0016 F7, adr/0014 §6.4, §15c).

Both run as fresh ``spawn`` processes on this machine, in the same test, behind the same
seams (``targets.py``). They are compared with each other, never with a stored hash
(adr/0016 §3.3): pixels, mask and file bytes, and what each says about the result. The
counter-test changes the recipe on the runner's side and expects the comparison to fail.
"""

from __future__ import annotations

import hashlib
import json
import math
import multiprocessing
from pathlib import Path
from typing import Any

import numpy
import pytest
import rasterio

from tests.earthx.processing import sources
from tests.earthx.readers import mini_zarr_cf
from tests.earthx.runner import support, targets

TIMEOUT = 120


@pytest.fixture(scope="module")
def cogs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    root = tmp_path_factory.mktemp("bands")
    return {
        sources.url("red"): str(
            sources.build_band_cog(root / "red.tif", sources.ramp(support.WIDTH, support.HEIGHT, 1200))
        ),
        sources.url("nir"): str(
            sources.build_band_cog(root / "nir.tif", sources.ramp(support.WIDTH, support.HEIGHT, 3400))
        ),
    }


@pytest.fixture(scope="module")
def cf_store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return mini_zarr_cf.build_mini_zarr_cf(tmp_path_factory.mktemp("cf") / "mini.zarr")


@pytest.fixture(autouse=True)
def served(cogs: dict[str, str], cf_store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNNER_COGS", json.dumps(cogs))
    monkeypatch.setenv("RUNNER_ZARR", str(cf_store))


def _both(tmp_path: Path, job_recipe: dict[str, Any], runner_recipe: dict[str, Any]) -> tuple[dict, Path]:
    """Start the job's child and the runner side by side; the job's report and the runner's folder."""
    context = multiprocessing.get_context("spawn")
    workdir = tmp_path / "job"
    workdir.mkdir()
    (workdir / "recipe.json").write_text(json.dumps(job_recipe), encoding="utf-8")
    recipe_file = tmp_path / "recipe.json"
    recipe_file.write_bytes(support.recipe_file(runner_recipe))
    out = tmp_path / "out"
    out.mkdir()

    job_end, job_child = context.Pipe()
    runner_end, runner_child = context.Pipe()
    job = context.Process(target=targets.job, args=(str(workdir), job_child))
    runner = context.Process(target=targets.runner, args=(str(recipe_file), str(out), runner_child))
    job.start()
    runner.start()
    job_child.close()
    runner_child.close()
    try:
        report = _last(job_end)
        assert runner_end.poll(TIMEOUT), "the runner did not finish"
        code = runner_end.recv()
    finally:
        for process in (job, runner):
            process.join(TIMEOUT)
            process.kill()
    assert report[0] == "done", report
    assert code == 0
    (folder,) = out.iterdir()
    return {**report[1], "workdir": workdir}, folder


def _last(conn: Any) -> tuple:
    while True:
        assert conn.poll(TIMEOUT), "the job's child did not finish"
        message = conn.recv()
        if message[0] != "progress":
            return message


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raster(path: Path) -> tuple[numpy.ndarray, dict[str, Any], list[dict[str, str]], list[int]]:
    """Pixels, profile, the tags of the dataset and of each band (the statistics, M4-32), overviews."""
    with rasterio.open(path) as dataset:
        profile = dict(dataset.profile)
        if isinstance(profile.get("nodata"), float) and math.isnan(profile["nodata"]):
            profile["nodata"] = "nan"  # NaN is unequal to itself, and the comparison is of the profile
        tags = [dataset.tags(), *(dataset.tags(index) for index in dataset.indexes)]
        return dataset.read(), profile, tags, dataset.overviews(1)


def _assert_same(job: dict, folder: Path) -> None:
    provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
    for name in ("result.tif", "mask.tif"):
        job_pixels, job_profile, job_tags, job_overviews = _raster(job["workdir"] / name)
        local_pixels, local_profile, local_tags, local_overviews = _raster(folder / name)
        assert numpy.array_equal(job_pixels, local_pixels, equal_nan=True), name
        assert (job_profile, job_tags, job_overviews) == (local_profile, local_tags, local_overviews), name
        assert _sha256(job["workdir"] / name) == _sha256(folder / name), name
    assert provenance["properties"] == job["properties"]
    assert all(band["statistics"]["count"] > 0 for band in job["properties"]["bands"])
    assert provenance["scaling"] == job["scaling"]
    assert provenance["engine"] == job["engine"]


class TestTheJobAndTheRunnerComputeTheSameBits:
    def test_band_math_on_scaled_cogs(self, tmp_path: Path) -> None:
        recipe = support.band_math_recipe()
        job, folder = _both(tmp_path, recipe, recipe)
        assert job["valid_pixels"] > 0
        _assert_same(job, folder)

    @pytest.mark.parametrize("method", list(support.NORMALIZE_METHODS))
    def test_each_method_of_normalize_with_the_numbers_of_the_recipe(self, tmp_path: Path, method: str) -> None:
        """The runner measures nothing: the numbers in the recipe give the child's bytes (NM4-11)."""
        recipe = support.normalize_recipe(method)
        job, folder = _both(tmp_path, recipe, recipe)
        assert job["valid_pixels"] > 0
        _assert_same(job, folder)

    def test_reprojection_bilinear_on_a_cf_zarr(self, tmp_path: Path) -> None:
        recipe = support.reproject_recipe("bilinear")
        job, folder = _both(tmp_path, recipe, recipe)
        assert job["properties"]["proj:code"] == "EPSG:3035" and job["valid_pixels"] > 0
        _assert_same(job, folder)

    def test_the_runner_marks_its_result_as_its_own(self, tmp_path: Path) -> None:
        recipe = support.band_math_recipe()
        _, folder = _both(tmp_path, recipe, recipe)
        provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
        assert (provenance["execution"], provenance["self_attested"]) == ("local", True)
        assert provenance["attribution"] == support.ATTRIBUTION
        assert (folder / "recipe.json").read_bytes() == support.recipe_file(recipe)


class TestTheCounterTest:
    """A comparison that cannot fail proves nothing: a changed recipe must break it."""

    def test_another_constant_in_the_expression(self, tmp_path: Path) -> None:
        job, folder = _both(tmp_path, support.band_math_recipe(), support.band_math_recipe(support.EXPRESSION + " + 1"))
        with pytest.raises(AssertionError):
            _assert_same(job, folder)

    @pytest.mark.parametrize("method", ["percentile", "zscore"])
    def test_another_number_in_the_measured_values(self, tmp_path: Path, method: str) -> None:
        other = json.loads(json.dumps(support.NORMALIZE_METHODS[method]))
        entry = other["measured"]["bands"]["red"]
        key = "p_high" if method == "percentile" else "mean"
        entry[key] = entry[key] + 0.01
        job, folder = _both(tmp_path, support.normalize_recipe(method), support.normalize_recipe(params=other))
        with pytest.raises(AssertionError):
            _assert_same(job, folder)

    def test_another_resampling(self, tmp_path: Path) -> None:
        job, folder = _both(tmp_path, support.reproject_recipe("bilinear"), support.reproject_recipe("nearest"))
        with pytest.raises(AssertionError):
            _assert_same(job, folder)
