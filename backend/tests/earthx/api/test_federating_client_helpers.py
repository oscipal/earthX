"""T-A: the pure pieces of the federating client, no Postgres and no network.

Everything that needs a running app (dispatch, conformance, error mapping through a
real request) is in ``tests/integration/test_api_federating.py`` instead — this file
is only for the helpers that do not need either.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from earthx.api.federating_client import _datetime_bounds, _reject_disallowed_keys, _strip_forward_token


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
