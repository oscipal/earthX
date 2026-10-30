"""What guards a job without a cap on its bands: the estimate of its memory, time and units (NM4-43c PR 2, adr/0020 §7)."""

from __future__ import annotations

import pytest

from earthx.processing.errors import JobTooLarge, UnsupportedRecipe
from earthx.processing.operators import REGISTRY
from earthx.processing.plan import (
    MAX_JOB_MEMORY_BYTES,
    SECONDS_PER_OUTPUT_BAND_MPIXEL,
    disk_needed,
    estimate,
    memory_needed,
)
from earthx.processing.recipe import Recipe
from tests.earthx.processing.recipes import SQUARE, recipe_data, recipe_of_data, resolved

#: About 25 km square at 10 m: many blocks, so that the number of bands is the only thing that changes.
BIG = {"type": "Polygon", "coordinates": [[[9.0, 47.0], [9.3, 47.0], [9.3, 47.3], [9.0, 47.3], [9.0, 47.0]]]}

#: A square near the cap on the size of the output for 17 bands: about 70 million pixels at 10 m.
NEAR_THE_CAP = {"type": "Polygon", "coordinates": [[[9.0, 47.0], [9.95, 47.0], [9.95, 47.75], [9.0, 47.75], [9.0, 47.0]]]}


def _names(count: int) -> list[str]:
    return [f"b{index:02d}" for index in range(count)]


def _math(index: int, name: str, first: str = "b00", second: str = "b01") -> dict:
    return {
        "op": "band_math",
        "op_version": 2,
        "params": {"expression": f"({first} - {second}) / ({first} + {second}) + {index}", "name": name},
    }


def wide_job(
    bands: int = 17,
    *,
    steps: int = 0,
    keep: str = "all",
    aoi: dict = SQUARE,
    scenes: int = 1,
    asset_bands: int = 1,
) -> Recipe:
    """``bands`` single-band assets (or ``bands // asset_bands`` assets of ``asset_bands`` bands), ``steps`` results."""
    names = _names(bands)
    items = [f"ITEM_{index}" for index in range(scenes)]
    results = [f"R{index:02d}" for index in range(steps)]
    data = recipe_data(
        aoi=aoi, steps=[_math(index, name) for index, name in enumerate(results)]
    )
    data["inputs"][0].update(
        groups=[items],
        assets=names,
        resolved=[resolved(item, name) for item in items for name in names],
    )
    data["output"]["bands"] = results if keep == "results" else [*names, *results]
    return recipe_of_data(data, REGISTRY)


#: ``(bands in the widest pass, scenes, peak MB)`` measured with ``scripts/nm4-43-bands/memory.py`` on synthetic scenes of
#: 17 bands at most, 1024² to 5632², real ``band_math`` steps (the Nachtrag NM4-43c PR 2 of adr/0014). The peak does not
#: follow the area, so the largest of the areas stands for each.
MEASURED = [
    (2, 1, 289), (4, 1, 345), (8, 1, 482), (17, 1, 727), (18, 1, 615), (24, 1, 859), (33, 1, 1149),
    (17, 2, 656), (17, 3, 785), (17, 5, 816), (17, 8, 862), (17, 12, 924), (17, 25, 1371),
    (2, 5, 269), (2, 25, 393), (6, 5, 456), (6, 25, 586), (33, 25, 1625),
]  # fmt: skip


class TestTheFormulaLiesAboveWhatWasMeasured:
    @pytest.mark.parametrize(("bands", "scenes", "peak_mb"), MEASURED)
    def test_the_estimate_is_not_below_the_peak(self, bands: int, scenes: int, peak_mb: int) -> None:
        assert memory_needed(bands, scenes) >= peak_mb * 1_000_000

    def test_a_mosaic_of_25_scenes_of_17_bands_passes_the_cap_it_was_measured_under(self) -> None:
        assert 1_371_000_000 <= estimate(wide_job(17, scenes=25), REGISTRY).memory_bytes <= MAX_JOB_MEMORY_BYTES

    def test_the_same_mosaic_with_16_results_kept_is_refused(self) -> None:
        with pytest.raises(JobTooLarge, match="of memory"):
            estimate(wide_job(17, steps=16, scenes=25), REGISTRY)


class TestMoreThanSixteenBands:
    def test_seventeen_bands_without_a_step_are_estimated(self) -> None:
        cost = estimate(wide_job(17), REGISTRY)
        assert cost.output_bytes == cost.output_pixels * 17 * 4
        assert 0 < cost.memory_bytes < MAX_JOB_MEMORY_BYTES

    def test_the_memory_grows_with_the_bands_the_pass_holds(self) -> None:
        two, seventeen = (estimate(wide_job(count), REGISTRY).memory_bytes for count in (2, 17))
        assert seventeen > two

    def test_a_result_band_is_held_while_it_is_kept(self) -> None:
        plain = estimate(wide_job(3), REGISTRY).memory_bytes
        assert estimate(wide_job(3, steps=4), REGISTRY).memory_bytes > plain

    def test_a_result_nobody_keeps_is_not_computed_and_costs_nothing(self) -> None:
        lone = recipe_data(steps=[_math(0, "R00")])
        lone["output"]["bands"] = ["red", "nir"]
        recipe = recipe_of_data(lone, REGISTRY)
        assert estimate(recipe, REGISTRY).memory_bytes == estimate(
            recipe_of_data(recipe_data(steps=[]), REGISTRY), REGISTRY
        ).memory_bytes

    def test_the_order_of_the_assets_changes_no_number(self) -> None:
        names = _names(17)
        reversed_job = wide_job(17)
        data = reversed_job.model_dump(mode="json")
        data["inputs"][0]["assets"] = names[::-1]
        data["inputs"][0]["resolved"] = data["inputs"][0]["resolved"][::-1]
        assert estimate(recipe_of_data(data, REGISTRY), REGISTRY) == estimate(wide_job(17), REGISTRY)

    def test_the_memory_does_not_follow_the_area(self) -> None:
        """Measured: 17 bands peak at 727 MB at 2048² and at 4096² (adr/0020 §7, the Nachtrag of adr/0014)."""
        assert estimate(wide_job(17, aoi=SQUARE), REGISTRY).memory_bytes == estimate(wide_job(17, aoi=BIG), REGISTRY).memory_bytes


class TestTheMemoryCap:
    def test_a_job_over_the_cap_is_refused_with_the_number_and_what_to_do(self) -> None:
        # One asset of 224 bands, the shape of a hyperspectral product: the bands are read together.
        data = recipe_data(steps=[])
        data["inputs"][0].update(assets=["cube"], resolved=[resolved("ITEM_A", "cube")])
        data["inputs"][0]["resolved"][0]["bands"] *= 224
        data["output"]["bands"] = [f"cube_{index + 1}" for index in range(224)]
        with pytest.raises(JobTooLarge, match=r"would need about [0-9.]+ GB of memory, more than the 1\.5 GB a job may use"):
            estimate(recipe_of_data(data, REGISTRY), REGISTRY)

    def test_the_refusal_names_what_to_change(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("earthx.processing.plan.MAX_JOB_MEMORY_BYTES", 1)
        with pytest.raises(JobTooLarge, match="Put fewer bands in the output"):
            estimate(wide_job(17, steps=16), REGISTRY)

    def test_the_cap_holds_to_the_byte(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recipe = wide_job(17, steps=4)
        needed = estimate(recipe, REGISTRY).memory_bytes
        monkeypatch.setattr("earthx.processing.plan.MAX_JOB_MEMORY_BYTES", needed)
        estimate(recipe, REGISTRY)
        monkeypatch.setattr("earthx.processing.plan.MAX_JOB_MEMORY_BYTES", needed - 1)
        with pytest.raises(JobTooLarge):
            estimate(recipe, REGISTRY)

    def test_sentinel_2_at_its_widest_passes(self) -> None:
        """17 data assets and 16 steps, every band kept: 33 bands (adr/0020 §7.2 names this job as the one that fits)."""
        assert estimate(wide_job(17, steps=16, aoi=BIG), REGISTRY).memory_bytes <= MAX_JOB_MEMORY_BYTES

    def test_a_missing_pixel_size_is_still_refused_as_before(self) -> None:
        data = wide_job(3).model_dump(mode="json")
        data["inputs"][0]["resolved"][0]["gsd"] = None
        with pytest.raises(UnsupportedRecipe, match="no gsd"):
            estimate(recipe_of_data(data, REGISTRY), REGISTRY)

    def test_the_formula_rises_with_every_input(self) -> None:
        assert memory_needed(bands=2, scenes=1) < memory_needed(bands=3, scenes=1) < memory_needed(bands=3, scenes=2)


class TestTheDiskFollowsTheStock:
    def test_the_float64_file_of_a_pass_holds_the_results_the_steps_add(self) -> None:
        plain, grown = (disk_needed(wide_job(17, steps=steps, aoi=BIG), REGISTRY) for steps in (0, 16))
        assert grown > plain
        # The pass file is 33 bands against 17 and, twice over, is most of what the run needs.
        assert grown > 1.7 * plain

    def test_an_output_of_one_band_needs_less_than_one_of_all(self) -> None:
        one = disk_needed(wide_job(17, steps=1, keep="results", aoi=BIG), REGISTRY)
        assert one < disk_needed(wide_job(17, aoi=BIG), REGISTRY)


class TestTheTimeAndTheUnitsCountTheBands:
    def test_the_seconds_grow_with_the_bands_of_the_output(self) -> None:
        two, seventeen = (estimate(wide_job(count), REGISTRY) for count in (2, 17))
        assert seventeen.seconds - two.seconds >= SECONDS_PER_OUTPUT_BAND_MPIXEL * 15 * two.output_pixels / 1e6

    def test_the_seconds_do_not_count_a_band_the_output_does_not_keep(self) -> None:
        many = estimate(wide_job(17, keep="results", steps=1), REGISTRY)
        assert many.output_bytes == many.output_pixels * 4  # one band is written
        assert many.seconds < estimate(wide_job(17), REGISTRY).seconds

    def test_the_units_grow_with_the_bands(self) -> None:
        one, seventeen = (estimate(wide_job(count), REGISTRY) for count in (1, 17))
        assert seventeen.units == pytest.approx(17 * one.units)

    def test_one_result_band_costs_what_it_did(self) -> None:
        cost = estimate(wide_job(2, steps=1, keep="results"), REGISTRY)
        assert cost.units == pytest.approx(cost.output_pixels / 1e6 * 1.2)  # one band, band math's factor

    def test_a_job_at_the_size_cap_gets_a_time_that_covers_it(self) -> None:
        """adr/0020 §3.2 Befund 9: 17 bands at 30 km took 115 s where 21 s were estimated; the limit is twice the estimate."""
        thirty_km = {"type": "Polygon", "coordinates": [[[9.0, 47.0], [9.4, 47.0], [9.4, 47.27], [9.0, 47.27], [9.0, 47.0]]]}
        cost = estimate(wide_job(17, aoi=thirty_km), REGISTRY)
        assert 9e6 < cost.output_pixels < 10e6
        assert cost.seconds >= 115
