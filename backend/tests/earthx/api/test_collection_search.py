"""Reading a Collection Search request without a database (M5-22 plan §3.7, A5; adr/0026 §4.4, F6)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import TypeAdapter
from stac_pydantic.api.search import Intersection

from earthx.api.collection_search import MAX_PAGE, MAX_TEXT_PAGE, read_query


def _read(**given):
    return read_query(
        **{"q": None, "bbox": None, "intersects": None, "datetime": None, "limit": None, "offset": None, **given}
    )


@pytest.mark.parametrize(("limit", "expected"), [(None, MAX_TEXT_PAGE), (5, 5), (MAX_TEXT_PAGE + 1, MAX_TEXT_PAGE)])
def test_a_text_search_pages_by_twenty_at_most(limit, expected):
    assert _read(q="elevation", limit=limit).limit == expected


@pytest.mark.parametrize(("limit", "expected"), [(None, MAX_PAGE), (50, 50), (MAX_PAGE + 1, MAX_PAGE)])
def test_without_text_a_page_holds_every_match_unless_limited(limit, expected):
    assert _read(bbox="7,46,8,47", limit=limit).limit == expected


@pytest.mark.parametrize("text", ["", "  \t"])
def test_only_spaces_is_no_text(text):
    assert _read(q=text).text is None


def test_a_box_with_heights_is_read_flat():
    assert _read(bbox=[7, 46, 0, 8, 47, 4000]).area == _read(bbox=[7, 46, 8, 47]).area


def test_a_box_across_the_antimeridian_is_two_boxes():
    area = _read(bbox="170,-20,-170,-10").area
    assert area["type"] == "MultiPolygon"
    assert [ring[0][0][0] for ring in area["coordinates"]] == [170, -180]


@pytest.mark.parametrize("nested", [False, True])
def test_a_position_inside_a_geometry_collection_is_checked(nested):
    outside = {"type": "Point", "coordinates": [7, 95]}
    if nested:
        outside = {"type": "GeometryCollection", "geometries": [outside]}
    geometry = {"type": "GeometryCollection", "geometries": [{"type": "Point", "coordinates": [7, 46]}, outside]}
    with pytest.raises(HTTPException) as refused:
        _read(intersects=TypeAdapter(Intersection).validate_python(geometry))
    assert refused.value.status_code == 400 and "95" not in refused.value.detail


def test_an_error_names_no_coordinate():
    with pytest.raises(HTTPException) as refused:
        _read(bbox="7.123457,95,8,96")
    assert "7.123457" not in refused.value.detail
