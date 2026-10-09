"""T-A: the pure pieces of the federating client, no Postgres and no network.

Everything that needs a running app (dispatch, conformance, error mapping through a
real request) is in ``tests/integration/test_api_federating.py`` instead — this file
is only for the helpers that do not need either.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from earthx.api.federating_client import (
    _datetime_bounds,
    _dump_intersects,
    _parse_intersects_param,
    _reject_disallowed_keys,
    _reject_items_endpoint_keys,
    _strip_forward_token,
)


class TestRejectDisallowedKeys:
    def test_a_plain_search_passes(self) -> None:
        _reject_disallowed_keys({"collections", "limit", "bbox"})

    @pytest.mark.parametrize("key", ["filter", "filter-lang", "filter_lang", "sortby"])
    def test_each_disallowed_key_is_refused(self, key: str) -> None:
        with pytest.raises(HTTPException) as excinfo:
            _reject_disallowed_keys({"collections", key})
        assert excinfo.value.status_code == 400
        assert key in excinfo.value.detail

    def test_names_every_offending_key_at_once(self) -> None:
        with pytest.raises(HTTPException) as excinfo:
            _reject_disallowed_keys({"filter", "sortby"})
        assert "filter" in excinfo.value.detail
        assert "sortby" in excinfo.value.detail

    @pytest.mark.parametrize("key", ["ids", "intersects"])
    def test_ids_and_intersects_now_pass_here(self, key: str) -> None:
        """M3-08: `/search` forwards both now; only `item_collection` still says no
        (`TestRejectItemsEndpointKeys` below) — M2-17's blanket rejection of either
        parameter on every federated route is gone."""
        _reject_disallowed_keys({"collections", key})


class TestRejectItemsEndpointKeys:
    """M3-08: `GET /collections/{id}/items` never had `ids`/`intersects` — unlike
    `/search`, which forwards both from M3-08 on."""

    def test_a_plain_items_request_passes(self) -> None:
        _reject_items_endpoint_keys({"bbox", "limit", "token"})

    @pytest.mark.parametrize("key", ["ids", "intersects"])
    def test_each_key_is_refused(self, key: str) -> None:
        with pytest.raises(HTTPException) as excinfo:
            _reject_items_endpoint_keys({key})
        assert excinfo.value.status_code == 400
        assert key in excinfo.value.detail
        assert "M3-08" in excinfo.value.detail


class TestParseIntersectsParam:
    def test_none_is_none(self) -> None:
        assert _parse_intersects_param(None) is None

    def test_valid_json_becomes_a_dict(self) -> None:
        assert _parse_intersects_param('{"type": "Point", "coordinates": [10.0, 49.0]}') == {
            "type": "Point",
            "coordinates": [10.0, 49.0],
        }

    def test_broken_json_is_refused(self) -> None:
        with pytest.raises(HTTPException) as excinfo:
            _parse_intersects_param("{not json")
        assert excinfo.value.status_code == 400

    def test_a_json_array_is_refused_as_not_an_object(self) -> None:
        with pytest.raises(HTTPException) as excinfo:
            _parse_intersects_param("[1, 2]")
        assert excinfo.value.status_code == 400


class TestDumpIntersects:
    def test_none_is_none(self) -> None:
        assert _dump_intersects(None) is None

    def test_a_plain_mapping_passes_through(self) -> None:
        geometry = {"type": "Point", "coordinates": [10.0, 49.0]}
        assert _dump_intersects(geometry) == geometry

    def test_a_geojson_pydantic_model_is_dumped_to_a_plain_mapping(self) -> None:
        from geojson_pydantic.geometries import Point

        model = Point(type="Point", coordinates=(10.0, 49.0))
        dumped = _dump_intersects(model)
        assert dumped == {"type": "Point", "coordinates": [10.0, 49.0]}
        assert isinstance(dumped, dict)


class TestStripForwardToken:
    def test_no_token_is_no_token(self) -> None:
        assert _strip_forward_token(None) is None

    def test_the_next_prefix_from_paginglinks_comes_off(self) -> None:
        assert _strip_forward_token("next:abc123") == "abc123"

    def test_a_bare_token_passes_through(self) -> None:
        """Not every caller goes through PagingLinks' link (a hand-built request, a
        replayed one) — the adapter's own decoder is what actually validates it."""
        assert _strip_forward_token("abc123") == "abc123"

    def test_backward_paging_is_refused_not_answered_with_page_one(self) -> None:
        with pytest.raises(HTTPException) as excinfo:
            _strip_forward_token("prev:abc123")
        assert excinfo.value.status_code == 400


class TestDatetimeBounds:
    def test_no_datetime_is_an_open_window(self) -> None:
        assert _datetime_bounds(None) == (None, None)

    def test_an_interval_becomes_start_and_end(self) -> None:
        start, end = _datetime_bounds("2024-06-01T00:00:00Z/2024-06-30T00:00:00Z")
        assert start == datetime(2024, 6, 1, tzinfo=timezone.utc)
        assert end == datetime(2024, 6, 30, tzinfo=timezone.utc)

    def test_a_single_instant_is_both_start_and_end(self) -> None:
        """SearchParams has no notion of an instant search — start == end says
        the same thing without adding a third shape to what it accepts."""
        start, end = _datetime_bounds("2024-06-01T00:00:00Z")
        assert start == end == datetime(2024, 6, 1, tzinfo=timezone.utc)

    def test_an_open_start_stays_open(self) -> None:
        start, end = _datetime_bounds("../2024-06-30T00:00:00Z")
        assert start is None
        assert end == datetime(2024, 6, 30, tzinfo=timezone.utc)
