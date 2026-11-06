"""``normalize`` version 4 at the door of the job: what an order may carry and what it is refused for (NM4-71).

Version 4 has no numbers of its own to give: an order that brings some, names a field of another method or a method that
does not exist is a `422` before anything is fetched. Synthetic and offline, on the items and helpers of
``test_intake``.
"""

from __future__ import annotations

from typing import Any

import pytest

from earthx.processing.recipe import recipe_hash
from tests.earthx.api.test_intake import S2, Source, accept, refused
from tests.earthx.api.test_intake_stock import _item, _order

pytestmark = pytest.mark.anyio

REPROJECT = {
    "op": "reproject",
    "op_version": 4,
    "params": {"crs": "EPSG:3035", "resolution": 20.0, "resampling": "nearest"},
}
STRETCH = {"low": 2, "high": 98, "out_min": 0.0, "out_max": 1.0, "clip": True}


def normalize(method: str, bands: list[str], **more: Any) -> dict[str, Any]:
    return {"op": "normalize", "op_version": 4, "params": {"method": method, "bands": bands, **more}}


class TestWhatIsAccepted:
    @pytest.mark.parametrize("method", ["zscore", "robust", "percentile"])
    async def test_each_method_without_numbers(self, method: str) -> None:
        step = normalize(method, ["red"], **(STRETCH if method == "percentile" else {}))
        accepted = await accept(_order([step], ["red"]), Source((S2, _item())))
        (kept,) = accepted.recipe.steps
        assert (kept.op, kept.op_version) == ("normalize", 4) and "measured" not in kept.params

    async def test_the_hash_of_the_recipe_does_not_depend_on_what_the_run_will_measure(self) -> None:
        step = normalize("zscore", ["red"])
        first = await accept(_order([step], ["red"]), Source((S2, _item())))
        second = await accept(_order([step], ["red"]), Source((S2, _item())))
        assert recipe_hash(first.recipe) == recipe_hash(second.recipe)

    async def test_a_step_that_measures_may_stand_before_or_after_a_grid_step(self) -> None:
        await accept(_order([normalize("zscore", ["red"]), REPROJECT], ["red"]), Source((S2, _item())))
        linear = normalize("linear", ["red"], in_min=0.0, in_max=0.5, out_min=0.0, out_max=1.0, clip=True)
        await accept(_order([linear, REPROJECT], ["red"]), Source((S2, _item())))
        await accept(_order([REPROJECT, normalize("robust", ["red"])], ["red"]), Source((S2, _item())))


class TestWhatIsRefusedBeforeAnythingIsFetched:
    @pytest.mark.parametrize(
        ("step", "words"),
        [
            (
                normalize("zscore", ["red"], measured={"factor": 1, "bands": {"red": {"mean": 0.1, "stddev": 0.2}}}),
                "measured: extra_forbidden",
            ),
            (
                normalize(
                    "percentile",
                    ["red"],
                    **STRETCH,
                    measured={"factor": 1, "bands": {"red": {"p_low": 0.1, "p_high": 0.9}}},
                ),
                "measured: extra_forbidden",
            ),
            (normalize("median", ["red"]), "method: literal_error"),
            (normalize("zscore", ["red"], clip=True), "value_error"),
            (normalize("zscore", ["red"], low=2), "value_error"),
            (
                normalize("percentile", ["red"], low=3, high=98, out_min=0.0, out_max=1.0, clip=True),
                "low: literal_error",
            ),
            (normalize("robust", ["red", "RED"]), "bands: value_error"),
            (normalize("robust", []), "bands: too_short"),
        ],
        ids=[
            "measured on zscore",
            "measured on percentile",
            "unknown method",
            "clip on zscore",
            "low on zscore",
            "a low that is no choice",
            "a band twice",
            "no band",
        ],
    )
    async def test_parameters_that_do_not_fit(self, step: dict[str, Any], words: str) -> None:
        source = Source((S2, _item()))
        error = await refused(_order([step], ["red"]), source)
        assert (error.status_code, error.stage) == (422, "order") and source.calls == []
        assert "invalid parameters of step 0 (normalize)" in error.detail and words in error.detail

    async def test_a_band_the_chain_does_not_have_is_named(self) -> None:
        error = await refused(_order([normalize("zscore", ["red", "swir9"])], ["red"]), Source((S2, _item())))
        assert (error.status_code, error.stage) == (422, "applicable") and "swir9" in error.detail
