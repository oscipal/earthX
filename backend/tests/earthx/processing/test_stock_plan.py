"""The stock of named bands: what the planner drops, keeps and orders (adr/0020 §4, NM4-43c)."""

from __future__ import annotations

import pytest
from rasterio.transform import from_origin

from earthx.processing.errors import RecipeInvalid
from earthx.processing.operators import REGISTRY, BandMeta, RasterMeta
from earthx.processing.plan import needed_source_bands, plan_steps, stock_steps
from earthx.processing.recipe import Step

NAMES = ("red", "nir", "green", "swir", "scl")


def _meta(names: tuple[str, ...] = NAMES) -> RasterMeta:
    bands = tuple(BandMeta(name, "float32", float("nan"), resampled=name in ("swir", "scl")) for name in names)
    return RasterMeta("EPSG:32632", from_origin(0, 100, 10, 10), 10, 10, bands)


def _step(op: str, version: int, **params) -> Step:
    return Step(op=op, op_version=version, params=params)


def _math(expression: str, name: str) -> Step:
    return _step("band_math", 2, expression=expression, name=name)


MASK = _step("mask", 2, source="scl", classes=[3, 8])
NORMALIZE = {"in_min": 0.0, "in_max": 1.0, "out_min": 0.0, "out_max": 255.0, "clip": True}
NDVI = _math("(nir - red) / (nir + red)", "NDVI")
NDWI = _math("(green - nir) / (green + nir)", "NDWI")
REPROJECT = _step("reproject", 4, crs="EPSG:3035", resolution=20.0, resampling="nearest", align=False)


def _plan(steps: list[Step], output: list[str], names: tuple[str, ...] = NAMES):
    """The names every step of the executable chain sees, and what it leaves (the planner's own selections named)."""
    chain = stock_steps(_meta(names), plan_steps(steps, REGISTRY), output)
    meta, trace = _meta(names), []
    for step in chain:
        before = [band.name for band in meta.bands]
        meta = step.operator.transform(meta, step.params)
        trace.append((step.step.op, before, [band.name for band in meta.bands]))
    return chain, trace, meta


def _ops(chain) -> list[str]:
    return [step.step.op for step in chain]


class TestWhatTheOutputNeeds:
    def test_a_chain_without_steps_needs_the_bands_of_the_output(self) -> None:
        assert needed_source_bands(plan_steps([], REGISTRY), ["nir", "red"]) == {"nir", "red"}

    def test_an_expression_needs_the_bands_it_names_and_not_its_own_result(self) -> None:
        planned = plan_steps([NDVI], REGISTRY)
        assert needed_source_bands(planned, ["NDVI"]) == {"nir", "red"}

    def test_a_later_step_may_use_the_result_of_an_earlier_one(self) -> None:
        planned = plan_steps([NDVI, _math("NDVI * 2 + green", "Twice")], REGISTRY)
        assert needed_source_bands(planned, ["Twice"]) == {"nir", "red", "green"}

    def test_the_layer_of_a_mask_is_needed_but_only_for_what_the_output_keeps(self) -> None:
        planned = plan_steps([MASK, NDVI], REGISTRY)
        assert needed_source_bands(planned, ["NDVI"]) == {"nir", "red", "scl"}

    def test_a_result_nobody_asks_for_needs_nothing(self) -> None:
        planned = plan_steps([NDVI, NDWI], REGISTRY)
        assert needed_source_bands(planned, ["NDWI"]) == {"green", "nir"}

    def test_a_step_of_recipe_version_1_is_refused_with_its_place(self) -> None:
        planned = plan_steps([_step("band_math", 1, expression="red + nir")], REGISTRY)
        with pytest.raises(RecipeInvalid, match=r"step 0: band_math version 1 replaces or removes bands"):
            needed_source_bands(planned, ["band_math"])


class TestDroppingWhatNobodyNeeds:
    def test_bands_that_no_step_and_not_the_output_need_are_dropped_before_the_first_step(self) -> None:
        chain, trace, _ = _plan([NDVI], ["NDVI"])
        assert trace[0] == ("select_bands", list(NAMES), ["red", "nir"])
        assert _ops(chain) == ["select_bands", "band_math", "select_bands"]

    def test_the_sources_of_a_result_leave_the_stock_after_their_last_use(self) -> None:
        _, trace, meta = _plan([NDVI, NDWI], ["NDVI", "NDWI"])
        seen_by_ndwi = [names for op, names, _ in trace if op == "band_math"][1]
        assert sorted(seen_by_ndwi) == ["NDVI", "green", "nir"]  # red was only for NDVI, swir and scl for nobody
        assert [band.name for band in meta.bands] == ["NDVI", "NDWI"]

    def test_a_band_of_the_data_in_the_output_stays_and_a_result_comes_after_it_if_the_output_says_so(self) -> None:
        _, _, meta = _plan([NDVI], ["red", "NDVI"])
        assert [band.name for band in meta.bands] == ["red", "NDVI"]

    def test_the_bands_of_the_result_are_in_the_order_of_the_output(self) -> None:
        _, _, meta = _plan([NDVI, NDWI], ["NDWI", "swir", "NDVI"])
        assert [band.name for band in meta.bands] == ["NDWI", "swir", "NDVI"]

    def test_a_result_nobody_asks_for_is_not_computed(self) -> None:
        chain, _, meta = _plan([NDVI, NDWI], ["NDVI"])
        assert [step.step.params.get("name") for step in chain if step.step.op == "band_math"] == ["NDVI"]
        assert [band.name for band in meta.bands] == ["NDVI"]

    def test_normalize_of_a_band_nobody_asks_for_is_not_run(self) -> None:
        normalize = _step("normalize", 2, bands=["green"], **NORMALIZE)
        chain, _, _ = _plan([normalize], ["red"])
        assert "normalize" not in _ops(chain)

    def test_normalize_of_a_band_in_the_output_is_run_and_leaves_the_others_alone(self) -> None:
        normalize = _step("normalize", 2, bands=["red"], **NORMALIZE)
        chain, _, meta = _plan([normalize], ["red", "nir"])
        assert "normalize" in _ops(chain)
        assert [(band.name, band.data_type) for band in meta.bands] == [("red", "float32"), ("nir", "float32")]

    def test_the_layer_of_a_mask_is_dropped_after_the_mask_unless_the_output_names_it(self) -> None:
        _, _, meta = _plan([MASK], ["red", "nir"])
        assert [band.name for band in meta.bands] == ["red", "nir"]
        _, trace, meta = _plan([MASK], ["red", "scl"])
        assert [band.name for band in meta.bands] == ["red", "scl"]
        assert next(names for op, names, _ in trace if op == "mask") == ["red", "scl"]

    def test_nothing_is_selected_where_the_stock_is_already_what_is_needed(self) -> None:
        chain, _, _ = _plan([NDVI], ["NDVI"], names=("red", "nir"))
        assert _ops(chain) == ["band_math", "select_bands"]
        chain, _, _ = _plan([], ["red", "nir"], names=("red", "nir"))
        assert chain == []


class TestAGridStep:
    def test_reproject_warps_only_the_bands_the_output_keeps_and_needs_no_pass_to_sort_them(self) -> None:
        chain, trace, meta = _plan([REPROJECT], ["nir", "red"])
        assert _ops(chain) == ["select_bands", "reproject"]
        assert trace[0][2] == ["nir", "red"] and trace[1][1] == ["nir", "red"]
        assert meta.resampled and all(band.resampled for band in meta.bands)

    def test_a_result_computed_before_reproject_is_warped_alone(self) -> None:
        chain, trace, _ = _plan([NDVI, REPROJECT], ["NDVI"])
        assert _ops(chain) == ["select_bands", "band_math", "select_bands", "reproject"]
        assert trace[-1][1] == ["NDVI"]

    def test_a_result_after_reproject_is_computed_on_the_warped_bands(self) -> None:
        chain, trace, _ = _plan([REPROJECT, NDVI], ["NDVI"])
        assert _ops(chain)[:2] == ["select_bands", "reproject"]
        assert trace[1][1] == ["red", "nir"]


class TestRefusals:
    def test_an_output_band_that_the_stock_does_not_hold_is_named(self) -> None:
        with pytest.raises(RecipeInvalid, match="output.bands names unknown band.*: NDWI;"):
            _plan([NDVI], ["NDVI", "NDWI"])

    def test_an_output_band_that_only_a_later_step_adds_is_unknown_to_the_chain_before_it(self) -> None:
        with pytest.raises(RecipeInvalid, match="unknown band"):
            _plan([_math("NDWI + red", "Out"), NDWI], ["Out"])

    def test_a_step_that_nobody_needs_is_not_judged_its_bands_are_not_read(self) -> None:
        chain, _, meta = _plan([NDVI, _math("blue + red", "Unused")], ["NDVI"])
        assert [band.name for band in meta.bands] == ["NDVI"] and "Unused" not in str(chain)

    def test_a_wrong_name_in_a_step_that_is_run_is_refused_with_its_place(self) -> None:
        with pytest.raises(RecipeInvalid, match=r"step 1: expression names unknown band\(s\): blue"):
            _plan([NDVI, _math("blue + red", "Used")], ["NDVI", "Used"])

    def test_a_result_named_like_a_band_of_the_stock_in_any_case_is_refused(self) -> None:
        with pytest.raises(RecipeInvalid, match="RED is used twice"):
            _plan([_math("nir + red", "RED")], ["RED"])
        with pytest.raises(RecipeInvalid, match="ndvi is used twice"):
            _plan([NDVI, _math("nir + red", "ndvi")], ["NDVI", "ndvi"])

    def test_a_step_of_recipe_version_1_is_refused(self) -> None:
        with pytest.raises(RecipeInvalid, match="replaces or removes bands"):
            _plan([_step("mask", 1, source="scl", classes=[3])], ["red"])

    def test_the_selection_is_not_an_operator_a_recipe_can_name(self) -> None:
        assert ("select_bands", 1) not in REGISTRY
