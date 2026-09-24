"""What the tools refuse before anything goes out, and how they read what they accept."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from earthx.chatbot import validation
from earthx.chatbot.validation import InvalidArgument


@pytest.mark.parametrize(
    "value",
    [
        [1, 2, 3],
        [1, 2, 3, 4, 5],
        "8,47,9,48",
        [8, 47, "9", 48],
        [8, 47, True, 48],
        [8, 47, math.nan, 48],
        [8, 47, math.inf, 48],
        [-181, 47, 9, 48],
        [8, 47, 181, 48],
        [8, -91, 9, 48],
        [8, 47, 9, 91],
        [9, 47, 8, 48],
        [8, 48, 9, 47],
    ],
)
def test_a_malformed_bbox_is_refused(value: object) -> None:
    with pytest.raises(InvalidArgument):
        validation.bbox(value)


def test_a_bbox_comes_back_as_four_floats() -> None:
    assert validation.bbox([8, 47, 9.5, 48]) == (8.0, 47.0, 9.5, 48.0)
    assert validation.bbox(None) is None


@pytest.mark.parametrize(
    "value",
    ["", "   ", 20240601, "yesterday", "2024-06-30/2024-06-01", "../..", "/", "2024-01-01/2024-02-01/2024-03-01"],
)
def test_a_malformed_datetime_is_refused(value: object) -> None:
    with pytest.raises(InvalidArgument):
        validation.interval(value)


def test_a_date_only_end_covers_the_whole_day() -> None:
    start, end = validation.interval("2024-06-01/2024-06-30")
    assert start == datetime(2024, 6, 1, tzinfo=timezone.utc)
    assert end == datetime(2024, 6, 30, 23, 59, 59, 999999, tzinfo=timezone.utc)


def test_an_open_end_stays_open_in_the_stac_spelling() -> None:
    bounds = validation.interval("2024-06-01T00:00:00Z/..")
    assert bounds == (datetime(2024, 6, 1, tzinfo=timezone.utc), None)
    assert validation.stac_datetime(bounds) == "2024-06-01T00:00:00Z/.."


def test_one_instant_is_written_as_one_instant() -> None:
    bounds = validation.interval("2024-06-01T10:00:00+02:00")
    assert validation.stac_datetime(bounds) == "2024-06-01T08:00:00Z"


@pytest.mark.parametrize("value", [None, "", "a/b", "../etc", "x" * 200, "col lection", 42, "-leading-dash"])
def test_a_collection_id_that_could_change_the_path_is_refused(value: object) -> None:
    with pytest.raises(InvalidArgument):
        validation.collection_id(value)


@pytest.mark.parametrize("value", [0, 51, -1, 2.5, "10", True])
def test_a_limit_outside_the_range_is_refused(value: object) -> None:
    with pytest.raises(InvalidArgument):
        validation.limit(value, 10)


def test_a_query_is_normalized_and_bounded() -> None:
    assert validation.query("  sentinel \n 2 ") == "sentinel 2"
    assert validation.query(None) == ""
    with pytest.raises(InvalidArgument):
        validation.query("x" * 201)
    with pytest.raises(InvalidArgument):
        validation.query(["sentinel"])
