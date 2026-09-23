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
from earthx.catalog.registry import MissingProperty, ViewerInfo, group_key


def viewer(*, group_by: tuple[str, ...]) -> ViewerInfo:
    """A ``ViewerInfo`` that varies only in its grouping key.

    The zoom levels are mandatory on the entry (M2-10, KLAERUNGEN B10) but say
    nothing about grouping, so they are filled in once here rather than repeated
    in every case below, where they would only be noise.
    """
    return ViewerInfo(group_by=group_by, min_zoom=0, max_zoom=19)


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
