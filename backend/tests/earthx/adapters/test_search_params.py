"""T-A: what we refuse before anything leaves the house.

adr/0005 §3.5 measured what Earth Search does with bad input: a bbox outside ±90 is
**accepted without a word**, an upside-down one is a 400 with the source's wording.
Neither is a good answer for our callers, so both are decided here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from earthx.adapters import DEFAULT_LIMIT, MAX_LIMIT, InvalidQuery, SearchParams

JUNE = datetime(2024, 6, 1, tzinfo=timezone.utc)


class TestLimit:
    def test_the_default_page_is_ten(self) -> None:
        """adr/0005 rule V, Otto's answer F3."""
        assert SearchParams().limit == DEFAULT_LIMIT == 10

    def test_a_hundred_is_still_allowed(self) -> None:
        assert SearchParams(limit=MAX_LIMIT).limit == 100

    @pytest.mark.parametrize("limit", [101, 1000, 10000])
    def test_more_than_a_hundred_is_refused(self, limit: int) -> None:
        """Upstream caps nothing: limit=10000 was answered in full (adr/0005 §3.2)."""
        with pytest.raises(InvalidQuery, match="outside 1..100"):
            SearchParams(limit=limit)

    @pytest.mark.parametrize("limit", [0, -1])
    def test_an_empty_page_is_refused(self, limit: int) -> None:
        with pytest.raises(InvalidQuery, match="outside 1..100"):
            SearchParams(limit=limit)


class TestBbox:
    def test_a_plain_bbox_passes(self) -> None:
        assert SearchParams(bbox=(8.0, 47.0, 12.0, 51.0)).bbox == (8.0, 47.0, 12.0, 51.0)

    @pytest.mark.parametrize("bbox", [(8.0, -91.0, 12.0, 51.0), (8.0, 47.0, 12.0, 91.0)])
    def test_latitudes_outside_ninety_are_refused(self, bbox: tuple[float, ...]) -> None:
        """The case upstream swallows silently (adr/0005 §3.5, row five)."""
        with pytest.raises(InvalidQuery, match="±90"):
            SearchParams(bbox=bbox)  # type: ignore[arg-type]

    def test_longitudes_outside_one_eighty_are_refused(self) -> None:
        with pytest.raises(InvalidQuery, match="±180"):
            SearchParams(bbox=(-181.0, 47.0, 12.0, 51.0))

    def test_an_upside_down_bbox_is_refused_here_not_upstream(self) -> None:
        with pytest.raises(InvalidQuery, match="upside down"):
            SearchParams(bbox=(8.0, 51.0, 12.0, 47.0))

    def test_a_bbox_of_zero_height_is_refused(self) -> None:
        """Upstream says "SW latitude must be less than NE latitude", so must we."""
        with pytest.raises(InvalidQuery, match="upside down"):
            SearchParams(bbox=(8.0, 47.0, 12.0, 47.0))

    def test_a_bbox_across_the_antimeridian_is_allowed(self) -> None:
        """west > east is how GeoJSON writes that box — it is not an inverted one."""
        assert SearchParams(bbox=(170.0, -10.0, -170.0, 10.0)).bbox[0] == 170.0

    def test_a_bbox_that_is_not_four_values_is_refused(self) -> None:
        with pytest.raises(InvalidQuery, match="four values"):
            SearchParams(bbox=(8.0, 47.0, 12.0))  # type: ignore[arg-type]


class TestTimeWindow:
    def test_an_open_window_is_allowed(self) -> None:
        assert SearchParams(start=JUNE, end=None).end is None

    def test_a_window_that_ends_before_it_starts_is_refused(self) -> None:
        with pytest.raises(InvalidQuery, match="ends before it starts"):
            SearchParams(start=JUNE, end=JUNE - timedelta(days=1))

    @pytest.mark.parametrize("field", ["start", "end"])
    def test_an_instant_without_a_timezone_is_refused(self, field: str) -> None:
        """A naive instant would silently mean something else in every other timezone."""
        with pytest.raises(InvalidQuery, match="no timezone"):
            SearchParams(**{field: datetime(2024, 6, 1)})
