"""The true-colour bands of a registry entry (NM4-64)."""

from __future__ import annotations

import dataclasses
from dataclasses import replace

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A
from earthx.catalog.registry import ConfigError, DatasetConfig


def _with(true_color: object) -> DatasetConfig:
    return replace(SENTINEL_2_L2A, true_color=true_color)


class TestTheEntries:
    def test_sentinel_2_names_red_green_blue_in_this_order(self) -> None:
        assert SENTINEL_2_L2A.true_color == ("red", "green", "blue")

    def test_the_dem_has_none(self) -> None:
        assert COP_DEM_GLO_30.true_color == ()

    def test_the_field_has_no_default(self) -> None:
        field = next(f for f in dataclasses.fields(DatasetConfig) if f.name == "true_color")
        assert field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING


class TestTheCollection:
    def test_it_publishes_the_names_in_order(self) -> None:
        assert to_stac_collection(SENTINEL_2_L2A)["earthx:true_color"] == ["red", "green", "blue"]

    def test_the_dem_publishes_an_empty_list(self) -> None:
        assert to_stac_collection(COP_DEM_GLO_30)["earthx:true_color"] == []


class TestTheCheck:
    def test_the_entry_as_it_stands_passes(self) -> None:
        assert _with(("red", "green", "blue")) == SENTINEL_2_L2A

    def test_the_bands_may_come_in_another_order(self) -> None:
        assert _with(("blue", "green", "red")).true_color == ("blue", "green", "red")

    def test_none_is_allowed_where_the_data_has_no_such_picture(self) -> None:
        assert _with(()).true_color == ()

    @pytest.mark.parametrize("names", ["red", ["red", "green", "blue"], None, {"red", "green", "blue"}])
    def test_anything_but_a_tuple_is_refused(self, names: object) -> None:
        with pytest.raises(ConfigError, match="true_color is a tuple"):
            _with(names)

    @pytest.mark.parametrize(
        "names", [("red",), ("red", "green"), ("red", "green", "blue", "nir"), ("red", "green", 3), ("red", None, "blue")]
    )
    def test_other_than_three_names_is_refused(self, names: object) -> None:
        with pytest.raises(ConfigError, match="red, green and blue, three bands"):
            _with(names)

    @pytest.mark.parametrize("names", [("red", "red", "blue"), ("red", "green", "red")])
    def test_a_band_twice_is_refused(self, names: tuple[str, ...]) -> None:
        with pytest.raises(ConfigError, match="three different bands"):
            _with(names)

    @pytest.mark.parametrize("name", ["rojo", "RED", "visual", "preview", "scl", "SR_10m:b04"])
    def test_a_name_that_is_no_band_of_the_data_is_refused(self, name: str) -> None:
        """An unknown name, a picture made from the bands (``visual``) and the mask layer (``scl``) are no bands."""
        with pytest.raises(ConfigError, match=f"{name!r}, which is no band of the data"):
            _with(("red", "green", name))

    def test_the_message_names_the_dataset(self) -> None:
        with pytest.raises(ConfigError, match=SENTINEL_2_L2A.dataset_id):
            _with(("red", "green", "rojo"))
