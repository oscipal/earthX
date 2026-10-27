"""The assets that are no band of a dataset (NM4-07)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A
from earthx.catalog.registry import ConfigError


class TestTheEntries:
    def test_the_pictures_of_sentinel_2_are_auxiliary_and_the_bands_are_not(self) -> None:
        assert set(SENTINEL_2_L2A.auxiliary_assets) == {"visual", "preview"}
        assert not {"red", "nir", "aot", "scl"} & set(SENTINEL_2_L2A.auxiliary_assets)

    def test_the_dem_has_none(self) -> None:
        assert COP_DEM_GLO_30.auxiliary_assets == ()

    def test_the_collection_publishes_them(self) -> None:
        assert to_stac_collection(SENTINEL_2_L2A)["earthx:auxiliary_assets"] == ["visual", "preview"]
        assert to_stac_collection(COP_DEM_GLO_30)["earthx:auxiliary_assets"] == []


class TestTheCheck:
    @pytest.mark.parametrize(
        "keys",
        [("visual", "visual"), ("",), (" visual",), ("visual ",), "visual", (None,), (3,)],
    )
    def test_unusable_keys_are_refused(self, valid_config, keys) -> None:
        with pytest.raises(ConfigError, match="auxiliary_assets"):
            replace(valid_config, auxiliary_assets=keys)

    def test_the_mask_layer_is_not_auxiliary(self) -> None:
        with pytest.raises(ConfigError, match="mask"):
            replace(SENTINEL_2_L2A, auxiliary_assets=("visual", "scl"))
