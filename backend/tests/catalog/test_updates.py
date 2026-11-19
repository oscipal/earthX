"""The registry field ``updates`` (M5-58, adr/0038 §3.1): cadence, states and how a change is seen."""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.catalog.datasets import registry
from earthx.catalog.registry import (
    AdapterKind,
    ChangeDetection,
    ConfigError,
    CoverageInfo,
    CoverageProvider,
    DatasetConfig,
    ItemHolding,
    ItemState,
    OverviewMode,
    OverviewResampling,
    TemporalExtent,
    UpdateCadence,
    UpdatesInfo,
)

RUNNING = UpdatesInfo(UpdateCadence.DAILY, (ItemState.PROVISIONAL, ItemState.FINAL), ChangeDetection.UNITS)


def materialized(config: DatasetConfig, **changes: object) -> DatasetConfig:
    """``config`` as a materialized series over a fixed grid, the shape of the MeteoSwiss entries."""
    source = replace(config.source, adapter=AdapterKind.METEOSWISS_GRID, item_holding=ItemHolding.MATERIALIZED)
    coverage = CoverageInfo(provider=CoverageProvider.FIXED_GRID, typical_footprint_km=300.0, max_geotile_level=6)
    fields: dict[str, object] = {
        "source": source,
        "coverage": coverage,
        "updates": RUNNING,
        "limitations": ("Values of the last weeks are provisional.",),
    }
    fields.update(changes)
    return replace(config, **fields)


class TestTheField:
    def test_every_entry_of_the_registry_says_it(self) -> None:
        for config in registry():
            assert isinstance(config.updates, UpdatesInfo), config.dataset_id

    def test_the_entries_of_today_behave_as_before(self) -> None:
        """Plan A2: nothing changes until a task gives an entry its own values; M5-58 PR 2 gave them to MeteoSwiss."""
        running = {"meteoswiss-daily-1km", "meteoswiss-daily-precip-1km"}
        for config in registry():
            if config.dataset_id in running:
                assert config.updates == UpdatesInfo(
                    UpdateCadence.DAILY, (ItemState.PROVISIONAL, ItemState.FINAL), ChangeDetection.UNITS
                )
                assert config.temporal_extent.end is None
            else:
                assert config.updates == UpdatesInfo(UpdateCadence.NONE, (ItemState.FINAL,), ChangeDetection.WHOLE)

    def test_the_rank_is_the_order_of_the_states(self) -> None:
        assert ItemState.PROVISIONAL.rank < ItemState.FINAL.rank

    @pytest.mark.parametrize(
        ("states", "message"),
        [
            ((), "at least one state"),
            ((ItemState.FINAL, ItemState.FINAL), "twice"),
            ((ItemState.FINAL, ItemState.PROVISIONAL), "ascending rank"),
            ((ItemState.PROVISIONAL,), "end with final"),
            (["final"], "at least one state"),
        ],
    )
    def test_states_are_ascending_and_end_with_final(self, states: object, message: str) -> None:
        with pytest.raises(ConfigError, match=message):
            UpdatesInfo(UpdateCadence.DAILY, states, ChangeDetection.UNITS)  # type: ignore[arg-type]

    def test_a_source_that_never_changes_has_nothing_provisional(self) -> None:
        with pytest.raises(ConfigError, match="nothing provisional"):
            UpdatesInfo(UpdateCadence.NONE, (ItemState.PROVISIONAL, ItemState.FINAL), ChangeDetection.WHOLE)

    def test_running(self) -> None:
        assert RUNNING.running
        assert not UpdatesInfo(UpdateCadence.NONE, (ItemState.FINAL,), ChangeDetection.WHOLE).running


class TestTheEntry:
    def test_a_running_materialized_series(self, valid_config: DatasetConfig) -> None:
        config = materialized(valid_config)
        assert config.updates.detect is ChangeDetection.UNITS

    def test_units_need_materialized_items(self, valid_config: DatasetConfig) -> None:
        with pytest.raises(ConfigError, match="needs materialized items"):
            replace(valid_config, updates=RUNNING, limitations=("Values of the last weeks are provisional.",))

    def test_units_cannot_keep_a_pyramid(self, valid_config: DatasetConfig) -> None:
        assert valid_config.viewer is not None
        viewer = replace(valid_config.viewer, overview=OverviewMode.PYRAMID, overview_resampling=OverviewResampling.NEAREST, min_zoom=7)
        with pytest.raises(ConfigError, match="pyramid"):
            materialized(valid_config, viewer=viewer)

    def test_provisional_values_are_said_in_the_limitations(self, valid_config: DatasetConfig) -> None:
        with pytest.raises(ConfigError, match="limitations"):
            materialized(valid_config, limitations=())

    def test_updates_must_be_the_dataclass(self, valid_config: DatasetConfig) -> None:
        with pytest.raises(ConfigError, match="UpdatesInfo"):
            materialized(valid_config, updates={"cadence": "daily"})


class TestAnOpenEnd:
    """adr/0038 §3.6: a running source may leave the end of its time extent open; a static one may not."""

    def open_end(self, config: DatasetConfig) -> TemporalExtent:
        return TemporalExtent(start=config.temporal_extent.start, end=None)

    def test_a_running_fixed_grid_may_stay_open(self, valid_config: DatasetConfig) -> None:
        config = materialized(valid_config, temporal_extent=self.open_end(valid_config))
        assert config.temporal_extent.end is None

    def test_a_static_fixed_grid_closes_its_period(self, valid_config: DatasetConfig) -> None:
        static = UpdatesInfo(UpdateCadence.NONE, (ItemState.FINAL,), ChangeDetection.WHOLE)
        with pytest.raises(ConfigError, match="closed temporal_extent or a running source"):
            materialized(valid_config, temporal_extent=self.open_end(valid_config), updates=static, limitations=())

    def test_a_fixed_grid_always_has_a_start(self, valid_config: DatasetConfig) -> None:
        with pytest.raises(ConfigError, match="from the start"):
            materialized(valid_config, temporal_extent=TemporalExtent(start=None, end=None))
