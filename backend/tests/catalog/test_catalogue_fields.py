"""Group, providers and resolution of a dataset for the Data catalogue (UI-05 plan §5, F1 and F2)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.datasets import (
    COP_DEM_GLO_30,
    ESA_WORLDCOVER_2020,
    ESA_WORLDCOVER_2021,
    REGISTRY,
    SENTINEL_2_L2A,
)
from earthx.catalog.registry import ConfigError, DatasetCategory, DatasetConfig, Provider, ProviderRole


class TestTheEntries:
    @pytest.mark.parametrize("entry", list(REGISTRY), ids=lambda entry: entry.dataset_id)
    def test_every_entry_sets_all_three(self, entry: DatasetConfig) -> None:
        assert isinstance(entry.category, DatasetCategory)
        assert entry.providers
        assert entry.gsd

    def test_the_groups_of_the_entries(self) -> None:
        assert SENTINEL_2_L2A.category is DatasetCategory.OPTICAL
        assert COP_DEM_GLO_30.category is DatasetCategory.ELEVATION
        assert ESA_WORLDCOVER_2020.category is DatasetCategory.LAND_COVER
        assert ESA_WORLDCOVER_2021.category is DatasetCategory.LAND_COVER

    def test_the_resolutions_of_the_entries(self) -> None:
        assert SENTINEL_2_L2A.gsd == (10.0, 20.0, 60.0)
        assert COP_DEM_GLO_30.gsd == (30.0,)
        assert ESA_WORLDCOVER_2020.gsd == ESA_WORLDCOVER_2021.gsd == (10.0,)

    @pytest.mark.parametrize("entry", list(REGISTRY), ids=lambda entry: entry.dataset_id)
    def test_every_entry_names_a_producer(self, entry: DatasetConfig) -> None:
        assert any(ProviderRole.PRODUCER in provider.roles for provider in entry.providers)


class TestTheCollection:
    def test_publishes_the_group(self) -> None:
        assert to_stac_collection(COP_DEM_GLO_30)["earthx:category"] == "elevation"

    def test_publishes_the_resolution_as_stac_summaries(self) -> None:
        assert to_stac_collection(SENTINEL_2_L2A)["summaries"] == {"gsd": [10.0, 20.0, 60.0]}

    def test_publishes_the_providers_as_stac_does(self) -> None:
        providers = to_stac_collection(ESA_WORLDCOVER_2021)["providers"]
        assert providers[0] == {
            "name": "ESA",
            "roles": ["licensor", "producer", "host"],
            "url": "https://esa-worldcover.org",
        }

    def test_a_provider_without_a_link_has_no_url_key(self) -> None:
        aws = [p for p in to_stac_collection(SENTINEL_2_L2A)["providers"] if p["name"] == "AWS"]
        assert aws == [{"name": "AWS", "roles": ["host"]}]

    def test_a_change_to_the_published_lists_does_not_reach_the_entry(self) -> None:
        collection = to_stac_collection(SENTINEL_2_L2A)
        collection["summaries"]["gsd"].append(1.0)
        collection["providers"][0]["roles"].append("host")
        assert to_stac_collection(SENTINEL_2_L2A)["summaries"] == {"gsd": [10.0, 20.0, 60.0]}
        assert to_stac_collection(SENTINEL_2_L2A)["providers"][0]["roles"] == ["producer"]


class TestTheCategoryCheck:
    @pytest.mark.parametrize("category", ["optical", None, 1])
    def test_anything_but_a_category_is_refused(self, valid_config, category) -> None:
        with pytest.raises(ConfigError, match="category"):
            replace(valid_config, category=category)

    def test_has_no_default(self, valid_config) -> None:
        fields = {name: getattr(valid_config, name) for name in DatasetConfig.__dataclass_fields__}
        del fields["category"]
        with pytest.raises(TypeError, match="category"):
            DatasetConfig(**fields)


class TestTheProvidersCheck:
    def test_none_is_refused(self, valid_config) -> None:
        with pytest.raises(ConfigError, match="providers names no provider"):
            replace(valid_config, providers=())

    def test_a_list_is_refused(self, valid_config) -> None:
        with pytest.raises(ConfigError, match="providers"):
            replace(valid_config, providers=list(valid_config.providers))

    def test_a_plain_mapping_is_refused(self, valid_config) -> None:
        with pytest.raises(ConfigError, match="every provider"):
            replace(valid_config, providers=({"name": "ESA", "roles": ["producer"]},))

    @pytest.mark.parametrize("name", ["", "  ", None])
    def test_a_provider_needs_a_name(self, name) -> None:
        with pytest.raises(ConfigError, match="needs a name"):
            Provider(name, (ProviderRole.PRODUCER,), None)

    def test_a_provider_needs_a_role(self) -> None:
        with pytest.raises(ConfigError, match="names no role"):
            Provider("ESA", (), None)

    @pytest.mark.parametrize("role", ["producer", "owner", None])
    def test_an_unknown_role_is_refused(self, role) -> None:
        with pytest.raises(ConfigError, match="every role"):
            Provider("ESA", (role,), None)

    def test_a_role_twice_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="twice"):
            Provider("ESA", (ProviderRole.HOST, ProviderRole.HOST), None)

    @pytest.mark.parametrize(
        "url", ["http://example.org", "javascript:alert(1)", "//example.org", "", "example.org"]
    )
    def test_a_link_that_is_not_https_is_refused(self, url) -> None:
        with pytest.raises(ConfigError, match="not https"):
            Provider("ESA", (ProviderRole.PRODUCER,), url)


class TestTheGsdCheck:
    def test_none_is_refused(self, valid_config) -> None:
        with pytest.raises(ConfigError, match="gsd names no resolution"):
            replace(valid_config, gsd=())

    def test_a_single_number_is_refused(self, valid_config) -> None:
        with pytest.raises(ConfigError, match="gsd"):
            replace(valid_config, gsd=10.0)

    @pytest.mark.parametrize(
        "gsd", [(0.0,), (-10.0,), (float("nan"),), (float("inf"),), (True,), ("10",), (None,)]
    )
    def test_anything_but_metres_above_zero_is_refused(self, valid_config, gsd) -> None:
        with pytest.raises(ConfigError, match="greater than zero"):
            replace(valid_config, gsd=gsd)

    @pytest.mark.parametrize("gsd", [(20.0, 10.0), (10.0, 10.0)])
    def test_out_of_order_or_twice_is_refused(self, valid_config, gsd) -> None:
        with pytest.raises(ConfigError, match="ascending"):
            replace(valid_config, gsd=gsd)
