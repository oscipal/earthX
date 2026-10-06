"""Tiers, passes, output window and cost estimate (adr/0014 §5.5, §6.1; plan M4-07a §3.3)."""

from __future__ import annotations

import pytest
from rasterio.transform import Affine, from_origin
from rasterio.warp import transform_geom

from earthx.processing.errors import AoiOutsideInputs, UnknownOperator, UnsupportedRecipe
from earthx.processing.plan import (
    EXPORT_FACTOR,
    SECONDS_PER_ASSET,
    crop_window,
    estimate,
    plan_steps,
    segments,
    split_tiers,
)
from earthx.processing.recipe import Step, recipe_from_data
from tests.earthx.processing.recipes import recipe_data
from tests.earthx.processing.testops import OPERATORS

SCALE = Step(op="scale", op_version=1, params={"factor": 2.0})
COARSEN = Step(op="coarsen", op_version=1, params={"factor": 2})


class TestSplitTiers:
    @pytest.mark.parametrize(
        ("steps", "tile", "job"),
        [
            ([], 0, 0),
            ([SCALE], 1, 0),
            ([SCALE, SCALE], 2, 0),
            ([SCALE, COARSEN], 1, 1),
            ([COARSEN, SCALE], 0, 2),
            ([SCALE, COARSEN, SCALE], 1, 2),
        ],
    )
    def test_the_longest_leading_t1_pixel_run_goes_to_the_tile(self, steps: list, tile: int, job: int) -> None:
        tile_steps, job_steps = split_tiers(steps, OPERATORS)
        assert (len(tile_steps), len(job_steps)) == (tile, job)
        assert tile_steps + job_steps == steps

    def test_an_unknown_step_is_named(self) -> None:
        with pytest.raises(UnknownOperator):
            split_tiers([Step(op="nope", op_version=1, params={})], OPERATORS)


class TestSegments:
    @pytest.mark.parametrize(
        ("steps", "shape"),
        [
            ([], [("pixel", 0)]),
            ([SCALE, SCALE], [("pixel", 2)]),
            ([COARSEN], [("pixel", 0), ("grid", 1)]),
            ([SCALE, COARSEN], [("pixel", 1), ("grid", 1)]),
            ([COARSEN, COARSEN, SCALE], [("pixel", 0), ("grid", 1), ("grid", 1), ("pixel", 1)]),
            ([SCALE, COARSEN, SCALE, SCALE], [("pixel", 1), ("grid", 1), ("pixel", 2)]),
        ],
    )
    def test_passes_in_order_and_the_first_one_reads(self, steps: list, shape: list) -> None:
        passes = segments(plan_steps(steps, OPERATORS))
        assert [(segment.kind, len(segment.steps)) for segment in passes] == shape

    def test_parameters_are_validated_by_the_operator(self) -> None:
        with pytest.raises(ValueError):
            plan_steps([Step(op="coarsen", op_version=1, params={"factor": 1})], OPERATORS)


GRID = from_origin(500000.0, 5210000.0, 10.0, 10.0)
UTM = "EPSG:32632"


def _aoi(left: float, bottom: float, right: float, top: float) -> dict:
    ring = [[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]
    return transform_geom(UTM, "EPSG:4326", {"type": "Polygon", "coordinates": [ring]})


class TestCropWindow:
    def test_an_aoi_inside_is_snapped_outward_to_whole_pixels(self) -> None:
        window, transform = crop_window(_aoi(500105.0, 5209005.0, 500395.0, 5209895.0), UTM, GRID, 100, 100)
        assert (window.col_off, window.row_off) == (10, 10)
        assert (window.width, window.height) == (30, 90)
        assert transform == GRID @ Affine.translation(10, 10)

    def test_an_aoi_over_the_edge_is_clipped_to_the_raster(self) -> None:
        window, _ = crop_window(_aoi(499000.0, 5209505.0, 500195.0, 5211000.0), UTM, GRID, 100, 100)
        assert (window.col_off, window.row_off, window.width, window.height) == (0, 0, 20, 50)

    def test_an_aoi_outside_is_named(self) -> None:
        with pytest.raises(AoiOutsideInputs):
            crop_window(_aoi(600000.0, 5000000.0, 600100.0, 5000100.0), UTM, GRID, 100, 100)

    def test_a_rotated_grid_is_not_processed(self) -> None:
        with pytest.raises(UnsupportedRecipe):
            crop_window(_aoi(500105.0, 5209005.0, 500395.0, 5209895.0), UTM, GRID @ Affine.rotation(5), 100, 100)


class TestEstimate:
    def test_a_band_math_like_run(self) -> None:
        cost = estimate(recipe_from_data(recipe_data(), OPERATORS), OPERATORS)
        assert cost.assets == 2
        assert cost.input_bytes == cost.input_pixels * 2  # uint16
        assert cost.output_pixels == cost.input_pixels // 2  # one asset's grid
        assert cost.output_bytes == cost.output_pixels * 4  # one float32 band
        assert cost.seconds >= 2 * SECONDS_PER_ASSET
        assert cost.units == pytest.approx(cost.output_pixels / 1e6 * 1.0)

    def test_a_grid_step_changes_the_output_size_and_its_factor_counts(self) -> None:
        steps = [
            {"op": "scale", "op_version": 1, "params": {"factor": 2.0}},
            {"op": "coarsen", "op_version": 1, "params": {"factor": 2}},
        ]
        plain = estimate(recipe_from_data(recipe_data(), OPERATORS), OPERATORS)
        coarse = estimate(recipe_from_data(recipe_data(steps=steps), OPERATORS), OPERATORS)
        assert coarse.output_pixels < plain.output_pixels / 3
        assert coarse.units == pytest.approx(coarse.output_pixels / 1e6 * 1.4)

    def test_no_step_is_an_export(self) -> None:
        cost = estimate(recipe_from_data(recipe_data(steps=[]), OPERATORS), OPERATORS)
        assert cost.units == pytest.approx(cost.output_pixels / 1e6 * EXPORT_FACTOR)

    def test_without_gsd_the_estimate_is_the_conservative_bound(self) -> None:
        data = recipe_data()
        known = estimate(recipe_from_data(data, OPERATORS), OPERATORS)
        for entry in data["inputs"][0]["resolved"]:
            entry["gsd"] = None
        unknown = estimate(recipe_from_data(data, OPERATORS), OPERATORS)
        assert unknown.input_pixels > known.input_pixels
