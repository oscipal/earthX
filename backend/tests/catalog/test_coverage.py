"""The coverage seam: rule V, the two level caps, the grid arithmetic, and the query.

Nothing here touches a network or a database. That is the point of putting these
decisions in ``catalog``: the rules of adr/0004 §5 that hold for *every* source are
plain functions, so they are checked rather than trusted — and the trap of §3.3, where
the source reports ``overflow: 0`` while a third of the scenes are missing, cannot slip
through unnoticed.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from earthx.catalog.coverage import (
    FOOTPRINT_THRESHOLD,
    HISTOGRAM_INTERVAL,
    MAX_GEOTILE_LEVEL,
    WORLD_LEVEL_CAP,
    Completeness,
    CoverageCell,
    CoverageQuery,
    CoverageResult,
    InvalidCoverageQuery,
    UpstreamCoverageShapeError,
    cell_bbox,
    check_completeness,
    extent_result,
    level_for_viewport,
    parse_cell_key,
)
from earthx.catalog.datasets import SENTINEL_2_L2A

UTC = timezone.utc


def result(cells: tuple[CoverageCell, ...] = (), total: int | None = 0, **kwargs) -> CoverageResult:
    return CoverageResult(
        dataset_id="d",
        level=6,
        cells=cells,
        total_count=total,
        completeness=check_completeness(sum(cell.count for cell in cells), total),
        histogram=(),
        from_cache=False,
        **kwargs,
    )


class TestRuleV:
    """adr/0004 §5: the completeness is checked, not claimed."""

    def test_equal_sums_are_complete(self) -> None:
        assert check_completeness(3848, 3848) is Completeness.COMPLETE

    def test_the_truncation_trap_of_3_3_is_caught(self) -> None:
        """The measured z8 case: ten thousand cells, a third of the scenes missing.

        The source reports ``overflow: 0`` for exactly this answer. Nothing in this
        function looks at that field, which is the whole reason it exists.
        """
        assert check_completeness(21_091_846, 30_375_556) is Completeness.TRUNCATED

    def test_a_missing_total_cannot_prove_completeness(self) -> None:
        """Note of 20.09.2026: no total, no proof — so truncated, never complete."""
        assert check_completeness(4711, None) is Completeness.TRUNCATED

    def test_a_simplified_aoi_is_truncated_even_when_the_sums_agree(self) -> None:
        """A boxed or thinned AOI answers a different question (adr/0004 §3.4)."""
        assert check_completeness(3848, 3848, simplified_aoi=True) is Completeness.TRUNCATED

    def test_a_declared_sample_stays_a_sample(self) -> None:
        """Whatever the numbers say — the way in decides this one (option 6)."""
        assert check_completeness(100, 100, sampled=True) is Completeness.SAMPLE

    def test_more_cells_than_total_is_not_complete_either(self) -> None:
        """Not a case anyone expects, which is why it must not read as complete."""
        assert check_completeness(50, 40) is Completeness.TRUNCATED


class TestSwitchPoint:
    """adr/0004 §5, Otto's answer 3: footprints below 500 hits, density above."""

    def test_just_below_the_threshold_advises_footprints(self) -> None:
        assert result(total=FOOTPRINT_THRESHOLD - 1).footprints_advised is True

    def test_at_the_threshold_the_density_stays(self) -> None:
        assert result(total=FOOTPRINT_THRESHOLD).footprints_advised is False

    def test_a_sample_keeps_the_density(self) -> None:
        """The replacement rule for M2-07c: without a checked total, no automatic switch."""
        assert result(total=None).footprints_advised is False


class TestLevelCaps:
    """adr/0004 §5 and its note of 20.09.2026 — and both caps clamp, never refuse."""

    @staticmethod
    def config_with(cap: int, valid_config):
        return replace(valid_config, coverage=replace(valid_config.coverage, max_geotile_level=cap))

    def test_a_zoom_below_both_caps_is_taken_as_it_is(self, valid_config) -> None:
        config = self.config_with(8, valid_config)
        assert level_for_viewport(5, config, has_spatial_filter=True) == 5

    def test_the_dataset_cap_clamps_rather_than_refuses(self, valid_config) -> None:
        """Below the cap a cell gets smaller than a footprint and the map turns to dots."""
        config = self.config_with(8, valid_config)
        assert level_for_viewport(14, config, has_spatial_filter=True) == 8

    def test_without_a_spatial_filter_the_world_cap_applies(self, valid_config) -> None:
        """From z7 on the source truncates world-wide (note of 20.09.2026)."""
        config = self.config_with(8, valid_config)
        assert level_for_viewport(8, config, has_spatial_filter=False) == WORLD_LEVEL_CAP

    def test_the_tighter_of_the_two_caps_wins(self, valid_config) -> None:
        config = self.config_with(4, valid_config)
        assert level_for_viewport(9, config, has_spatial_filter=False) == 4

    def test_a_negative_zoom_becomes_the_whole_world(self, valid_config) -> None:
        config = self.config_with(8, valid_config)
        assert level_for_viewport(-3, config, has_spatial_filter=True) == 0

    def test_sentinel_2_is_capped_at_z8(self) -> None:
        """The value Otto set on 19.09.2026, read off the real registry entry."""
        assert level_for_viewport(12, SENTINEL_2_L2A, has_spatial_filter=True) == 8


class TestGridArithmetic:
    """Geotile is the XYZ scheme of the map itself (adr/0004 §3.7)."""

    def test_level_zero_is_the_whole_world(self) -> None:
        west, south, east, north = cell_bbox("0/0/0")
        assert (west, east) == (-180.0, 180.0)
        assert south == pytest.approx(-85.051129, abs=1e-5)
        assert north == pytest.approx(85.051129, abs=1e-5)

    def test_a_measured_cell_lands_where_it_was_measured(self) -> None:
        """``8/133/84`` came back for a bbox over central Europe on 20.09.2026."""
        west, south, east, north = cell_bbox("8/133/84")
        assert 5.0 <= west < east <= 15.0
        assert 45.0 <= south < north <= 55.0

    def test_cells_of_one_level_tile_without_a_gap(self) -> None:
        assert cell_bbox("4/7/5")[2] == pytest.approx(cell_bbox("4/8/5")[0])
        assert cell_bbox("4/7/5")[1] == pytest.approx(cell_bbox("4/7/6")[3])

    @pytest.mark.parametrize(
        "key",
        [
            "8/133",  # too few parts
            "8/133/84/2",  # too many
            "8/x/84",  # not a number
            "3/8/0",  # column outside 2**3
            "3/0/8",  # row outside 2**3
            f"{MAX_GEOTILE_LEVEL + 1}/0/0",  # a level the source would refuse
            "-1/0/0",
            "",
        ],
    )
    def test_a_key_that_is_not_a_cell_is_refused(self, key: str) -> None:
        """These arrive from outside and end up in a map layer, so none may pass."""
        with pytest.raises(UpstreamCoverageShapeError):
            parse_cell_key(key)


class TestQueryChecks:
    """Purpose-defeating input, refused before anything is sent upstream."""

    def test_the_plain_query_is_accepted(self) -> None:
        assert CoverageQuery(dataset_id="d", level=6).level == 6

    def test_bbox_and_intersects_together_are_two_questions(self) -> None:
        with pytest.raises(InvalidCoverageQuery, match="send one"):
            CoverageQuery(
                dataset_id="d",
                level=6,
                bbox=(5.0, 45.0, 15.0, 55.0),
                intersects={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            )

    @pytest.mark.parametrize(
        "bbox",
        [
            (5.0, 45.0, 15.0),  # three values
            (5.0, -95.0, 15.0, 55.0),  # latitude outside ±90
            (-200.0, 45.0, 15.0, 55.0),  # longitude outside ±180
            (5.0, 55.0, 15.0, 45.0),  # upside down
        ],
    )
    def test_a_broken_bbox_is_refused(self, bbox) -> None:
        with pytest.raises(InvalidCoverageQuery):
            CoverageQuery(dataset_id="d", level=6, bbox=bbox)

    @pytest.mark.parametrize(
        "geometry",
        [
            {"type": "Point", "coordinates": [1, 2]},
            {"type": "Polygon"},
            {"type": "Polygon", "coordinates": []},
            {"type": "Polygon", "coordinates": [[]]},  # a ring with nothing in it
            {"type": "Polygon", "coordinates": ["abc"]},  # a "ring" that is a string
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 0]]]},  # three positions
            {"type": "Polygon", "coordinates": [[["a", "b"], [1, 0], [1, 1], ["a", "b"]]]},
            {"type": "MultiPolygon", "coordinates": [[[]]]},
            "not a geometry at all",
        ],
    )
    def test_something_that_is_not_an_area_never_reaches_a_query_string(self, geometry) -> None:
        with pytest.raises(InvalidCoverageQuery):
            CoverageQuery(dataset_id="d", level=6, intersects=geometry)

    @pytest.mark.parametrize(
        "coordinates",
        [
            [[[0.0, 0.0], [999.0, 0.0], [999.0, 1.0], [0.0, 0.0]]],  # longitude outside ±180
            [[[0.0, 0.0], [1.0, 888.0], [1.0, 1.0], [0.0, 0.0]]],  # latitude outside ±90
        ],
    )
    def test_a_ring_outside_the_globe_is_refused(self, coordinates) -> None:
        """The bbox lesson of adr/0005 §3.5, applied to intersects (M2-05b scope).

        Unchecked, the source answers such a polygon with a plausible-looking ``200``
        instead of refusing it — the same silent acceptance measured for a bbox.
        """
        with pytest.raises(InvalidCoverageQuery, match="±"):
            CoverageQuery(
                dataset_id="d", level=6, intersects={"type": "Polygon", "coordinates": coordinates}
            )

    def test_a_ring_inside_the_globe_is_accepted(self) -> None:
        area = {"type": "Polygon", "coordinates": [[[5.0, 45.0], [6.0, 45.0], [6.0, 46.0], [5.0, 45.0]]]}
        assert CoverageQuery(dataset_id="d", level=6, intersects=area).intersects == area

    def test_no_out_of_bounds_message_names_the_coordinate(self) -> None:
        """projektplan.md 7, point 6: an exception text becomes a log line."""
        with pytest.raises(InvalidCoverageQuery) as raised:
            CoverageQuery(
                dataset_id="d",
                level=6,
                intersects={"type": "Polygon", "coordinates": [[[0.0, 0.0], [999.0, 0.0], [999.0, 1.0], [0.0, 0.0]]]},
            )
        assert "999" not in str(raised.value)

    def test_a_naive_instant_is_refused(self) -> None:
        with pytest.raises(InvalidCoverageQuery, match="timezone"):
            CoverageQuery(dataset_id="d", level=6, start=datetime(2024, 1, 1))

    def test_a_window_that_ends_before_it_starts_is_refused(self) -> None:
        with pytest.raises(InvalidCoverageQuery, match="ends before"):
            CoverageQuery(
                dataset_id="d",
                level=6,
                start=datetime(2024, 6, 1, tzinfo=UTC),
                end=datetime(2024, 1, 1, tzinfo=UTC),
            )

    @pytest.mark.parametrize("value", [-1.0, 100.1])
    def test_a_cloud_cover_outside_the_percentage_range_is_refused(self, value: float) -> None:
        with pytest.raises(InvalidCoverageQuery, match="percentage"):
            CoverageQuery(dataset_id="d", level=6, max_cloud_cover=value)

    @pytest.mark.parametrize("level", [-1, MAX_GEOTILE_LEVEL + 1])
    def test_a_level_outside_the_grid_is_refused(self, level: int) -> None:
        with pytest.raises(InvalidCoverageQuery, match="grid level"):
            CoverageQuery(dataset_id="d", level=level)

    def test_no_check_message_ever_names_a_coordinate(self) -> None:
        """projektplan.md 7, point 6: an exception text becomes a log line."""
        with pytest.raises(InvalidCoverageQuery) as raised:
            CoverageQuery(dataset_id="d", level=6, bbox=(5.5, -95.25, 15.5, 55.5))
        for coordinate in ("5.5", "95.25", "15.5", "55.5"):
            assert coordinate not in str(raised.value)


class TestUnfilteredFlag:
    """What counts as the world overview, which is the one answer kept for a day."""

    def test_nothing_set_is_the_world_overview(self) -> None:
        assert CoverageQuery(dataset_id="d", level=3).is_unfiltered is True

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"bbox": (5.0, 45.0, 15.0, 55.0)},
            {"start": datetime(2024, 1, 1, tzinfo=UTC)},
            {"end": datetime(2024, 1, 1, tzinfo=UTC)},
            {"max_cloud_cover": 20.0},
        ],
    )
    def test_any_filter_at_all_takes_it_out_of_the_world_overview(self, kwargs) -> None:
        assert CoverageQuery(dataset_id="d", level=3, **kwargs).is_unfiltered is False


def test_the_histogram_interval_is_fixed_because_the_source_ignores_it() -> None:
    """Measured 20.09.2026: ``datetime_frequency_interval`` changes nothing upstream.

    Day, month, year and a nonsense value all return the same monthly buckets, so no
    caller is offered a choice that would not be kept — there is no such parameter.
    """
    assert HISTOGRAM_INTERVAL == "month"
    assert not hasattr(CoverageQuery(dataset_id="d", level=6), "interval")


def test_counted_is_the_cells_own_sum_and_cannot_be_set() -> None:
    """Rule V compares against this number, so it may not come from anywhere else."""
    cells = (CoverageCell("6/1/1", 3), CoverageCell("6/1/2", 4))
    assert result(cells, total=7).counted == 7
    with pytest.raises(TypeError):
        CoverageResult(
            dataset_id="d",
            level=6,
            cells=cells,
            total_count=7,
            completeness=Completeness.COMPLETE,
            histogram=(),
            from_cache=False,
            counted=99,
        )


def test_max_count_anchors_the_log_scale() -> None:
    cells = (CoverageCell("6/1/1", 3), CoverageCell("6/1/2", 399), CoverageCell("6/2/1", 12))
    assert result(cells, total=414).max_count == 399


def test_max_count_of_an_empty_answer_is_zero() -> None:
    """An empty window is a legitimate answer, and a log scale still needs an anchor."""
    assert result((), total=0).max_count == 0


class TestExtentResult:
    """adr/0004 §5, "Einmal-Produkte": extent instead of density."""

    def test_the_extent_is_carried_through(self) -> None:
        bbox = (5.0, 45.0, 15.0, 55.0)
        answer = extent_result("one-off", bbox)
        assert answer.extent == bbox
        assert answer.completeness is Completeness.COMPLETE

    def test_there_is_nothing_to_count(self) -> None:
        answer = extent_result("one-off", (5.0, 45.0, 15.0, 55.0))
        assert answer.cells == ()
        assert answer.counted == 0
        assert answer.histogram == ()
        assert answer.total_count is None

    def test_a_regular_result_carries_no_extent(self) -> None:
        assert result().extent is None
