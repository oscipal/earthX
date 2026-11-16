"""How the band a step makes is drawn is registry data of the operator (M5-10, Otto, 16.11.2026), told to the panel in the description."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from rio_tiler.colormap import cmap

from earthx.api.processing_docs import order_schema
from earthx.processing.operators import REGISTRY
from earthx.processing.operators.base import Look, Looks


def _step(product: str) -> SimpleNamespace:
    return SimpleNamespace(product=product)


class TestTerrainLooks:
    def test_slope_is_green_where_flat_and_red_where_steep_on_the_usual_scale(self) -> None:
        look = REGISTRY[("terrain", 1)].looks.of(_step("slope"))  # type: ignore[union-attr]
        assert look == Look(colormap="rdylgn_r", scale="measured")

    def test_hillshade_is_light_where_lit_from_the_minimum_to_the_maximum(self) -> None:
        look = REGISTRY[("terrain", 1)].looks.of(_step("hillshade"))  # type: ignore[union-attr]
        assert look == Look(colormap="greys_r", scale="percentiles", low=0, high=100)

    def test_aspect_is_a_cycle_of_colours_over_a_fixed_circle(self) -> None:
        look = REGISTRY[("terrain", 1)].looks.of(_step("aspect"))  # type: ignore[union-attr]
        assert look == Look(colormap="hsv", scale="fixed", low=0, high=360)

    def test_an_unknown_product_has_no_look(self) -> None:
        assert REGISTRY[("terrain", 1)].looks.of(_step("curvature")) is None  # type: ignore[union-attr]


def test_every_colormap_of_a_look_is_one_the_tiler_has() -> None:
    known = set(cmap.list())
    for operator in REGISTRY.values():
        if operator.looks is not None:
            for value, look in operator.looks.by_value.items():
                assert look.colormap in known, f"{operator.op} {value}: the tiler knows no colormap {look.colormap!r}"


class TestTheDescription:
    def test_terrain_says_its_looks_by_product(self) -> None:
        said = order_schema(REGISTRY)["$defs"]["step_terrain_v1"]["x-earthx-looks"]
        assert said == {
            "param": "product",
            "by": {
                "aspect": {"colormap": "hsv", "scale": "fixed", "low": 0, "high": 360},
                "hillshade": {"colormap": "greys_r", "scale": "percentiles", "low": 0, "high": 100},
                "slope": {"colormap": "rdylgn_r", "scale": "measured"},
            },
        }

    def test_a_step_without_looks_says_none(self) -> None:
        definitions = order_schema(REGISTRY)["$defs"]
        for operator in REGISTRY.values():
            definition = definitions.get(f"step_{operator.op}_v{operator.op_version}")
            if definition is not None and operator.looks is None:
                assert "x-earthx-looks" not in definition


class TestALookIsChecked:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"colormap": ""},
            {"colormap": "viridis", "scale": "fixed"},
            {"colormap": "viridis", "scale": "fixed", "low": 5, "high": 5},
            {"colormap": "viridis", "scale": "fixed", "low": 9, "high": 1},
            {"colormap": "viridis", "scale": "measured", "low": 0, "high": 1},
            {"colormap": "viridis", "scale": "percentiles", "low": -1, "high": 100},
            {"colormap": "viridis", "scale": "percentiles", "low": 0, "high": 101},
        ],
    )
    def test_refuses_what_cannot_be_drawn(self, kwargs: dict) -> None:
        with pytest.raises(ValueError):
            Look(**kwargs)

    def test_looks_of_a_missing_parameter_value_is_none(self) -> None:
        looks = Looks(param="product", by_value={"a": Look(colormap="viridis")})
        assert looks.of(SimpleNamespace(product="b")) is None
