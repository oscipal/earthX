"""The one rule that comes with ``earthx:viewer.group_by``, as a test.

``ViewerInfo`` says it in a sentence: *a property that holds a STAC instant enters
the key as its UTC date*. The sentence is what M2-07a implements in the frontend,
so it has to be checked here rather than believed — a rule nobody tests is a rule
two sides read differently.

The items are written out in place: they are three properties each, and a fixture
would hide the very values these tests are about.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from earthx.catalog.datasets import SENTINEL_2_L2A
from earthx.catalog.registry import BrowseMode, MissingProperty, ViewerInfo, group_key


def viewer(*, group_by: tuple[str, ...]) -> ViewerInfo:
    """A ``ViewerInfo`` that varies only in its grouping key.

    The zoom levels and the M3-12 browse/grouping fields are mandatory on the
    entry (M2-10, KLAERUNGEN B10) but say nothing about ``group_key``, so they
    are filled in once here rather than repeated in every case below, where
    they would only be noise.
    """
    return ViewerInfo(
        group_by=group_by,
        min_zoom=0,
        max_zoom=19,
        browse=BrowseMode.FULL_RESOLUTION,
        quicklook_nodata_max=None,
        results_group_by=group_by,
    )


SENTINEL_2 = viewer(group_by=("datetime", "grid:code"))


def item(**properties: object) -> dict[str, object]:
    return {"id": "an-item", "properties": properties}


class TestAnInstantBecomesItsUtcDate:
    def test_the_time_of_day_drops_out_of_the_key(self) -> None:
        """A time line groups an acquisition day, not a second (Inventar F5)."""
        assert group_key(item(datetime="2026-07-24T10:38:17.453000Z"), viewer(group_by=("datetime",))) == (
            "2026-07-24",
        )

    def test_two_scenes_of_the_same_day_land_in_one_group(self) -> None:
        morning = item(datetime="2026-07-24T10:38:17Z", **{"grid:code": "MGRS-32TMS"})
        evening = item(datetime="2026-07-24T22:01:03Z", **{"grid:code": "MGRS-32TMS"})
        assert group_key(morning, SENTINEL_2) == group_key(evening, SENTINEL_2)

    def test_the_date_is_the_one_in_utc_not_the_local_one(self) -> None:
        """The same moment in two offsets is one group; otherwise a scene would move
        between steps depending on how the source happened to write its instant."""
        utc = item(datetime="2026-07-24T23:30:00Z", **{"grid:code": "MGRS-32TMS"})
        local = item(datetime="2026-07-25T01:30:00+02:00", **{"grid:code": "MGRS-32TMS"})
        assert group_key(utc, SENTINEL_2) == group_key(local, SENTINEL_2) == ("2026-07-24", "MGRS-32TMS")

    def test_a_second_across_midnight_is_another_day(self) -> None:
        """The rule has an edge, and the edge is where UTC midnight is."""
        before = item(datetime="2026-07-24T23:59:59Z")
        after = item(datetime="2026-07-25T00:00:00Z")
        key = viewer(group_by=("datetime",))
        assert group_key(before, key) == ("2026-07-24",)
        assert group_key(after, key) == ("2026-07-25",)

    def test_an_instant_that_is_already_a_datetime_is_read_the_same_way(self) -> None:
        """Whoever hands in a parsed item must not get a different key than the raw one."""
        parsed = item(datetime=datetime(2026, 7, 24, 23, 30, tzinfo=timezone.utc))
        assert group_key(parsed, viewer(group_by=("datetime",))) == ("2026-07-24",)


class TestEverythingElseIsItsOwnText:
    def test_a_grid_code_is_carried_over_unchanged(self) -> None:
        key = group_key(item(**{"grid:code": "MGRS-32TMS"}), viewer(group_by=("grid:code",)))
        assert key == ("MGRS-32TMS",)

    def test_a_bare_date_stays_the_date_it_is(self) -> None:
        assert group_key(item(acquired="2026-07-24"), viewer(group_by=("acquired",))) == ("2026-07-24",)

    def test_a_number_becomes_its_text_rather_than_a_type_error(self) -> None:
        assert group_key(item(orbit=137), viewer(group_by=("orbit",))) == ("137",)

    def test_the_parts_keep_the_order_the_registry_names(self) -> None:
        """The key is read by people too, and a key that reorders itself is unreadable."""
        scene = item(datetime="2026-07-24T10:00:00Z", **{"grid:code": "MGRS-32TMS"})
        assert group_key(scene, SENTINEL_2) == ("2026-07-24", "MGRS-32TMS")
        assert group_key(scene, viewer(group_by=("grid:code", "datetime"))) == (
            "MGRS-32TMS",
            "2026-07-24",
        )


class TestAMissingPropertyIsAnError:
    """A key that quietly loses a part merges two groups that do not belong together."""

    def test_a_property_the_item_does_not_carry(self) -> None:
        with pytest.raises(MissingProperty, match="grid:code"):
            group_key(item(datetime="2026-07-24T10:00:00Z"), SENTINEL_2)

    def test_an_item_without_properties_at_all(self) -> None:
        with pytest.raises(MissingProperty):
            group_key({"id": "an-item"}, SENTINEL_2)


def test_the_key_of_the_registered_dataset_is_the_acquisition_day_per_tile() -> None:
    """The entry and the rule together, so neither can change alone unnoticed."""
    viewer = SENTINEL_2_L2A.viewer
    assert viewer is not None
    scene = item(datetime="2026-07-24T10:38:17.453000Z", **{"grid:code": "MGRS-32TMS"})
    assert group_key(scene, viewer) == ("2026-07-24", "MGRS-32TMS")


class TestTheOverpassKey:
    """``fields`` names the other key of the registry: the overpass a mosaic job covers (M4-12)."""

    def test_the_named_fields_replace_group_by(self) -> None:
        both = ViewerInfo(
            group_by=("datetime", "grid:code"),
            min_zoom=0,
            max_zoom=19,
            browse=BrowseMode.FULL_RESOLUTION,
            quicklook_nodata_max=None,
            results_group_by=("datetime", "s2:datatake_id"),
        )
        scene = item(datetime="2026-07-24T10:38:17Z", **{"grid:code": "MGRS-32TMS", "s2:datatake_id": "GS2B_1"})
        assert group_key(scene, both) == ("2026-07-24", "MGRS-32TMS")
        assert group_key(scene, both, both.results_group_by) == ("2026-07-24", "GS2B_1")

    def test_two_tiles_of_one_overpass_share_the_key_and_the_next_day_does_not(self) -> None:
        keys = [
            group_key(item(datetime=day, **{"s2:datatake_id": take}), viewer(group_by=("datetime", "s2:datatake_id")))
            for day, take in (
                ("2026-07-24T10:38:17Z", "GS2B_1"),
                ("2026-07-24T10:38:19Z", "GS2B_1"),
                ("2026-07-25T10:38:17Z", "GS2B_1"),
            )
        ]
        assert keys[0] == keys[1] != keys[2]

    def test_a_missing_overpass_property_is_an_error_too(self) -> None:
        with pytest.raises(MissingProperty, match="s2:datatake_id"):
            group_key(item(datetime="2026-07-24T10:00:00Z"), SENTINEL_2, ("datetime", "s2:datatake_id"))


class TestTheDayOfAcquisition:
    """Otto, 14.10.2026: the day in a download's name is the day of the overpass, where the dataset has one."""

    S2 = ViewerInfo(
        group_by=("datetime", "grid:code"),
        min_zoom=0,
        max_zoom=19,
        browse=BrowseMode.FULL_RESOLUTION,
        quicklook_nodata_max=None,
        results_group_by=("datetime", "datatake"),
    )
    PERIOD = ViewerInfo(
        group_by=("start_datetime",),
        min_zoom=0,
        max_zoom=19,
        browse=BrowseMode.FULL_RESOLUTION,
        quicklook_nodata_max=None,
        results_group_by=("start_datetime",),
    )

    def test_the_instant_of_the_key_is_the_utc_day_not_the_day_of_the_offset(self) -> None:
        from datetime import date

        from earthx.catalog.registry import acquisition_day

        late = item(datetime="2025-07-05T23:30:00-05:00", datatake="G1")
        assert acquisition_day(late, self.S2) == date(2025, 7, 6)
        assert acquisition_day(item(datetime="2025-07-05T10:20:30.123Z", datatake="G1"), self.S2) == date(2025, 7, 5)

    def test_an_item_that_lacks_another_part_of_the_key_still_has_its_day(self) -> None:
        from datetime import date

        from earthx.catalog.registry import acquisition_day

        assert acquisition_day(item(datetime="2025-07-05T10:20:30Z"), self.S2) == date(2025, 7, 5)

    def test_the_part_may_stand_anywhere_in_the_key(self) -> None:
        from datetime import date

        from earthx.catalog.registry import acquisition_day

        key = viewer(group_by=("platform", "datetime"))
        assert acquisition_day(item(platform="a", datetime="2025-07-05T10:00:00Z"), key) == date(2025, 7, 5)

    def test_a_dataset_whose_key_is_a_period_has_no_day(self) -> None:
        from earthx.catalog.registry import acquisition_day

        dem = item(start_datetime="2010-12-01T00:00:00Z", datetime="2021-04-22T00:00:00Z")
        assert acquisition_day(dem, self.PERIOD) is None, "the instant of the item is not in the key: the key rules"

    @pytest.mark.parametrize(
        "properties",
        [{"datatake": "G1"}, {"datetime": None, "datatake": "G1"}, {"datetime": "not a time", "datatake": "G1"}, {}],
    )
    def test_an_item_without_an_instant_has_no_day_and_is_not_refused(self, properties: dict[str, object]) -> None:
        from earthx.catalog.registry import acquisition_day

        assert acquisition_day(item(**properties), self.S2) is None

    def test_an_item_without_properties_has_no_day(self) -> None:
        from earthx.catalog.registry import acquisition_day

        assert acquisition_day({"id": "x"}, self.S2) is None

    def test_the_registry_has_a_day_for_the_two_sentinel_datasets_and_none_for_the_dem(self) -> None:
        from earthx.catalog.datasets import COP_DEM_GLO_30, SENTINEL_2_L2A_ZARR3

        assert ACQ in SENTINEL_2_L2A.viewer.results_group_by  # type: ignore[union-attr]
        assert ACQ in SENTINEL_2_L2A_ZARR3.viewer.results_group_by  # type: ignore[union-attr]
        assert ACQ not in COP_DEM_GLO_30.viewer.results_group_by  # type: ignore[union-attr]


ACQ = "datetime"
