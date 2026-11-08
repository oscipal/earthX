"""M5-08 plan §4.3, §4.4: fixed asset keys and states per tile, the start checks of the registry."""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.registry import (
    AssetKeyRule,
    ConfigError,
    CoverageProvider,
    ItemHolding,
    ItemStateRule,
    ItemStates,
    SourceInfo,
)
from tests.catalog.entries import REGISTRY

COG = "image/tiff; application=geotiff; profile=cloud-optimized"
RULES = (AssetKeyRule("red", COG, 10.0), AssetKeyRule("green", COG, 20.0), AssetKeyRule("blue", COG, 60.0))
STATES = ItemStates(rule=ItemStateRule.LATEST, tile_pattern=r"tiles_\d{4}_(?P<tile>\d{4}-\d{4})")


def _with_keys(vary, valid_config, rules, **changes):
    return vary(source=replace(valid_config.source, asset_keys=rules), **changes)


def _materialized(vary, valid_config, states):
    source = replace(valid_config.source, item_holding=ItemHolding.MATERIALIZED, item_states=states)
    coverage = replace(valid_config.coverage, provider=CoverageProvider.LOCAL_SQL)
    return vary(source=source, coverage=coverage)


@pytest.mark.parametrize("field", ["asset_keys", "item_states"])
def test_neither_field_has_a_default(valid_config, field) -> None:
    """KLAERUNGEN B10, like every other field of the source."""
    fields = {name: getattr(valid_config.source, name) for name in SourceInfo.__dataclass_fields__ if name != field}
    with pytest.raises(TypeError):
        SourceInfo(**fields)


class TestAssetKeys:
    def test_every_entry_of_the_registry_keeps_the_source_keys(self) -> None:
        """No entry before swissALTI3D renames an asset (M5-08 plan §4.3)."""
        assert all(entry.source.asset_keys == () for entry in REGISTRY)

    def test_rules_for_every_key_the_entry_names_are_accepted(self, vary, valid_config) -> None:
        assert _with_keys(vary, valid_config, RULES).source.asset_keys == RULES

    @pytest.mark.parametrize("key", ["", "2m", "dtm-2m", "dtm:2m", "a" * 33, "dtm 2m", None])
    def test_a_key_that_is_no_band_name_is_refused(self, vary, valid_config, key) -> None:
        with pytest.raises(ConfigError, match="not a fixed asset key"):
            _with_keys(vary, valid_config, (*RULES, AssetKeyRule(key, COG, 2.0)))

    @pytest.mark.parametrize("media_type", ["", " ", f" {COG}", None])
    def test_a_rule_needs_a_media_type(self, vary, valid_config, media_type) -> None:
        with pytest.raises(ConfigError, match="needs a media type"):
            _with_keys(vary, valid_config, (*RULES, AssetKeyRule("extra", media_type, 2.0)))

    @pytest.mark.parametrize("gsd", [0.0, -1.0, float("nan"), float("inf"), True, "2"])
    def test_a_rule_needs_a_positive_gsd(self, vary, valid_config, gsd) -> None:
        with pytest.raises(ConfigError, match="positive number"):
            _with_keys(vary, valid_config, (*RULES, AssetKeyRule("extra", COG, gsd)))

    def test_a_key_twice_is_refused(self, vary, valid_config) -> None:
        with pytest.raises(ConfigError, match="names a key twice"):
            _with_keys(vary, valid_config, (*RULES, AssetKeyRule("red", COG, 2.0)))

    def test_two_rules_on_one_type_and_gsd_are_refused(self, vary, valid_config) -> None:
        with pytest.raises(ConfigError, match="claim the same media type and gsd"):
            _with_keys(vary, valid_config, (*RULES, AssetKeyRule("extra", COG, 10.0)))

    def test_one_rule_is_no_tuple(self, vary, valid_config) -> None:
        with pytest.raises(ConfigError, match="tuple of AssetKeyRule"):
            _with_keys(vary, valid_config, RULES[0])

    def test_the_default_render_names_only_fixed_keys(self, vary, valid_config) -> None:
        with pytest.raises(ConfigError, match="'blue' is no key"):
            _with_keys(vary, valid_config, (*RULES[:2], AssetKeyRule("nir", COG, 60.0)))

    def test_an_auxiliary_asset_is_a_fixed_key_too(self, vary, valid_config) -> None:
        with pytest.raises(ConfigError, match="'visual' is no key"):
            _with_keys(vary, valid_config, RULES, auxiliary_assets=("visual",))

    def test_band_units_name_only_fixed_keys(self, vary, valid_config) -> None:
        units = {**valid_config.band_units, "nir": "1"}
        with pytest.raises(ConfigError, match="band_units names 'nir'"):
            _with_keys(vary, valid_config, RULES, band_units=units)

    def test_a_pattern_of_band_units_has_to_match_a_fixed_key(self, vary, valid_config) -> None:
        assert _with_keys(vary, valid_config, RULES, band_units={"red": "1", "gr*": "1", "blue": "1"})
        with pytest.raises(ConfigError, match="band_units names 'nir\\*'"):
            _with_keys(vary, valid_config, RULES, band_units={**valid_config.band_units, "nir*": "1"})

    def test_the_collection_publishes_the_rules(self, vary, valid_config) -> None:
        source = to_stac_collection(_with_keys(vary, valid_config, RULES))["earthx:source"]
        assert source["asset_keys"][0] == {"key": "red", "media_type": COG, "gsd": 10.0}
        assert source["item_states"] is None


class TestItemStates:
    def test_every_entry_of_the_registry_loads_every_item(self) -> None:
        assert all(entry.source.item_states is None for entry in REGISTRY)

    def test_a_materialized_entry_may_choose_a_state_per_tile(self, vary, valid_config) -> None:
        assert _materialized(vary, valid_config, STATES).source.item_states == STATES

    def test_a_federated_entry_may_not(self, vary, valid_config) -> None:
        with pytest.raises(ConfigError, match="needs materialized items"):
            vary(source=replace(valid_config.source, item_states=STATES))

    @pytest.mark.parametrize("pattern", ["(", "[a-", None, 3])
    def test_a_pattern_that_does_not_compile_is_refused(self, pattern) -> None:
        with pytest.raises(ConfigError, match="no regular expression"):
            ItemStates(rule=ItemStateRule.LATEST, tile_pattern=pattern)

    @pytest.mark.parametrize(
        "pattern", [r"tiles_\d{4}_(\d+)", r"tiles_(?P<year>\d{4})_(?P<tile>\d+)", r"(?P<kachel>\d+)", r"tiles_.*"]
    )
    def test_the_pattern_has_exactly_one_named_group_tile(self, pattern) -> None:
        with pytest.raises(ConfigError, match="exactly one named group"):
            ItemStates(rule=ItemStateRule.LATEST, tile_pattern=pattern)

    def test_an_unnamed_group_beside_it_is_fine(self) -> None:
        states = ItemStates(rule=ItemStateRule.LATEST, tile_pattern=r"tiles_(\d{4})_(?P<tile>\d+)")
        assert states.tile_of("tiles_2019_12") == "12"

    def test_a_rule_that_is_no_rule_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="item_states.rule"):
            ItemStates(rule="latest", tile_pattern=STATES.tile_pattern)

    @pytest.mark.parametrize(
        ("item_id", "tile"),
        [
            ("tiles_2019_2600-1200", "2600-1200"),
            ("tiles_2019_2600-1200x", None),
            ("xtiles_2019_2600-1200", None),
            ("tiles_19_2600-1200", None),
            ("tiles_2019_2600-1200\n", None),
        ],
    )
    def test_the_whole_id_has_to_match(self, item_id, tile) -> None:
        assert STATES.tile_of(item_id) == tile

    def test_the_collection_publishes_the_rule(self, vary, valid_config) -> None:
        source = to_stac_collection(_materialized(vary, valid_config, STATES))["earthx:source"]
        assert source["item_states"] == {"rule": "latest", "tile_pattern": STATES.tile_pattern}
