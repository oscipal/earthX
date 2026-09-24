"""T-A: what we refuse before anything leaves the house.

adr/0005 §3.5 measured what Earth Search does with bad input: a bbox outside ±90 is
**accepted without a word**, an upside-down one is a 400 with the source's wording.
Neither is a good answer for our callers, so both are decided here.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from earthx.adapters import DEFAULT_LIMIT, MAX_IDS, MAX_INTERSECTS_POINTS, MAX_LIMIT, InvalidQuery, SearchParams
from earthx.adapters.federated_search import search_fingerprint

JUNE = datetime(2024, 6, 1, tzinfo=timezone.utc)

_TRIANGLE = {"type": "Polygon", "coordinates": [[[8.0, 47.0], [12.0, 47.0], [8.0, 51.0], [8.0, 47.0]]]}
_POINT = {"type": "Point", "coordinates": [10.0, 49.0]}


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


def _convex_ring(n: int, *, cx: float = 10.0, cy: float = 49.0, r: float = 1.0) -> list[list[float]]:
    """A closed, non-self-intersecting ring of ``n`` positions plus the closing one."""
    points = [[cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)] for i in range(n)]
    return [*points, points[0]]


class TestIntersects:
    """M3-08: measured against Earth Search and the EOPF STAC API in the plan step
    (M3-08 plan §2.1, §2.2) — what both sources take without a word (a latitude of
    999, a self-intersecting ring) is refused here instead."""

    def test_a_point_passes(self) -> None:
        assert SearchParams(intersects=_POINT).intersects == _POINT

    def test_a_polygon_passes(self) -> None:
        assert SearchParams(intersects=_TRIANGLE).intersects == _TRIANGLE

    def test_a_multipolygon_passes(self) -> None:
        multi = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[8.0, 47.0], [9.0, 47.0], [9.0, 48.0], [8.0, 48.0], [8.0, 47.0]]],
                [[[11.0, 50.0], [12.0, 50.0], [12.0, 51.0], [11.0, 51.0], [11.0, 50.0]]],
            ],
        }
        assert SearchParams(intersects=multi).intersects == multi

    def test_a_geometry_collection_of_valid_members_passes(self) -> None:
        collection = {"type": "GeometryCollection", "geometries": [_POINT]}
        assert SearchParams(intersects=collection).intersects == collection

    def test_bbox_and_intersects_together_are_refused(self) -> None:
        with pytest.raises(InvalidQuery, match="two different questions"):
            SearchParams(bbox=(8.0, 47.0, 12.0, 51.0), intersects=_TRIANGLE)

    def test_a_longitude_outside_one_eighty_is_refused(self) -> None:
        """Earth Search took this without a word and returned matches (M3-08 plan §2.2)."""
        bad = {"type": "Polygon", "coordinates": [[[999.0, 47.0], [1000.0, 47.0], [1000.0, 48.0], [999.0, 47.0]]]}
        with pytest.raises(InvalidQuery, match="±180"):
            SearchParams(intersects=bad)

    def test_a_latitude_outside_ninety_is_refused(self) -> None:
        bad = {"type": "Polygon", "coordinates": [[[8.0, 888.0], [9.0, 888.0], [9.0, 889.0], [8.0, 888.0]]]}
        with pytest.raises(InvalidQuery, match="±90"):
            SearchParams(intersects=bad)

    def test_a_point_outside_the_globe_is_refused(self) -> None:
        with pytest.raises(InvalidQuery, match="±90"):
            SearchParams(intersects={"type": "Point", "coordinates": [10.0, 95.0]})

    def test_an_unclosed_ring_is_refused(self) -> None:
        bad = {"type": "Polygon", "coordinates": [[[8.0, 47.0], [12.0, 47.0], [8.0, 51.0], [9.0, 50.0]]]}
        with pytest.raises(InvalidQuery, match="not closed"):
            SearchParams(intersects=bad)

    def test_a_ring_with_two_points_is_refused(self) -> None:
        bad = {"type": "Polygon", "coordinates": [[[8.0, 47.0], [12.0, 47.0]]]}
        with pytest.raises(InvalidQuery, match="not closed"):
            SearchParams(intersects=bad)

    def test_empty_coordinates_are_refused(self) -> None:
        with pytest.raises(InvalidQuery, match="no coordinates"):
            SearchParams(intersects={"type": "Polygon", "coordinates": []})

    def test_a_self_intersecting_polygon_is_refused(self) -> None:
        """M3-08 plan §2.2: Earth Search answered this "bowtie" with 229 matches,
        none of them checked against the shape actually asked for."""
        bowtie = {
            "type": "Polygon",
            "coordinates": [[[8.0, 47.0], [12.0, 51.0], [12.0, 47.0], [8.0, 51.0], [8.0, 47.0]]],
        }
        with pytest.raises(InvalidQuery, match="self-intersect"):
            SearchParams(intersects=bowtie)

    def test_an_unrecognised_geometry_type_is_refused(self) -> None:
        with pytest.raises(InvalidQuery, match="geometry type"):
            SearchParams(intersects={"type": "Circle", "coordinates": [10.0, 49.0]})

    def test_a_nested_geometry_collection_is_refused(self) -> None:
        nested = {"type": "GeometryCollection", "geometries": [{"type": "GeometryCollection", "geometries": [_POINT]}]}
        with pytest.raises(InvalidQuery, match="nest"):
            SearchParams(intersects=nested)

    def test_a_nan_coordinate_is_refused(self) -> None:
        with pytest.raises(InvalidQuery):
            SearchParams(intersects={"type": "Point", "coordinates": [float("nan"), 49.0]})

    def test_exactly_the_point_budget_passes(self) -> None:
        ring = _convex_ring(MAX_INTERSECTS_POINTS - 1)  # +1 closing point == the cap
        SearchParams(intersects={"type": "Polygon", "coordinates": [ring]})

    def test_one_point_over_the_budget_is_refused(self) -> None:
        ring = _convex_ring(MAX_INTERSECTS_POINTS)  # +1 closing point == cap + 1
        with pytest.raises(InvalidQuery, match=f"more than {MAX_INTERSECTS_POINTS}"):
            SearchParams(intersects={"type": "Polygon", "coordinates": [ring]})


class TestIds:
    """M3-08: measured that both sources AND-combine `ids` with any other filter
    rather than treat it as a shortcut around them (plan §2.1)."""

    def test_a_single_id_passes(self) -> None:
        assert SearchParams(ids=("S2A_T32UMA_20240630T103658_L2A",)).ids == ("S2A_T32UMA_20240630T103658_L2A",)

    def test_the_maximum_number_of_ids_passes(self) -> None:
        ids = tuple(f"id-{i}" for i in range(MAX_IDS))
        assert len(SearchParams(ids=ids).ids) == MAX_IDS

    def test_one_id_over_the_maximum_is_refused(self) -> None:
        ids = tuple(f"id-{i}" for i in range(MAX_IDS + 1))
        with pytest.raises(InvalidQuery, match=f"more than {MAX_IDS}"):
            SearchParams(ids=ids)

    def test_an_empty_list_is_refused_rather_than_meaning_no_filter(self) -> None:
        with pytest.raises(InvalidQuery, match="empty"):
            SearchParams(ids=())

    @pytest.mark.parametrize("bad_id", ["../etc/passwd", "id\n", "", "a" * 256])
    def test_an_id_that_is_not_a_url_path_segment_is_refused(self, bad_id: str) -> None:
        with pytest.raises(InvalidQuery, match="not a scene id"):
            SearchParams(ids=(bad_id,))


class TestSearchFingerprint:
    """M3-08: `intersects`/`ids` join the fingerprint only when set, so a page token
    or search-cache row minted before M3-08 still reads back (M3-08 plan §4.1)."""

    def test_a_search_using_neither_hashes_exactly_as_before(self) -> None:
        """Reimplements the pre-M3-08 payload independently of `search_fingerprint`
        itself: a search without `intersects`/`ids` must still hash to what the
        four-field payload (`dataset`/`bbox`/`datetime`/`limit`) always produced, or
        every page token and search-cache row minted before M3-08 stops matching."""
        import hashlib
        import json

        params = SearchParams(bbox=(8.0, 47.0, 12.0, 51.0), start=JUNE, limit=10)
        pre_m3_08_payload = json.dumps(
            {
                "dataset": "sentinel-2-c1-l2a",
                "bbox": [8.0, 47.0, 12.0, 51.0],
                "datetime": "2024-06-01T00:00:00Z/..",
                "limit": 10,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        expected = hashlib.sha256(pre_m3_08_payload.encode("utf-8")).hexdigest()
        assert search_fingerprint("sentinel-2-c1-l2a", params) == expected

    def test_intersects_changes_the_fingerprint(self) -> None:
        plain = search_fingerprint("ds", SearchParams())
        with_area = search_fingerprint("ds", SearchParams(intersects=_TRIANGLE))
        assert plain != with_area

    def test_ids_changes_the_fingerprint(self) -> None:
        plain = search_fingerprint("ds", SearchParams())
        with_ids = search_fingerprint("ds", SearchParams(ids=("a",)))
        assert plain != with_ids

    def test_ids_order_and_duplicates_do_not_change_the_fingerprint(self) -> None:
        a = search_fingerprint("ds", SearchParams(ids=("a", "b")))
        b = search_fingerprint("ds", SearchParams(ids=("b", "a", "a")))
        assert a == b

    def test_intersects_and_bbox_are_different_searches_even_over_the_same_area(self) -> None:
        as_bbox = search_fingerprint("ds", SearchParams(bbox=(8.0, 47.0, 12.0, 51.0)))
        as_polygon = search_fingerprint(
            "ds",
            SearchParams(intersects={"type": "Polygon", "coordinates": [[[8.0, 47.0], [12.0, 47.0], [12.0, 51.0], [8.0, 51.0], [8.0, 47.0]]]}),
        )
        assert as_bbox != as_polygon
