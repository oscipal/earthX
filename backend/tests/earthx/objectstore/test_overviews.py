"""The terms and the bucket rule of the overview pyramids (M5-30b part 8b, adr/0032 §5.2, §5.3, §8.4)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from earthx.objectstore.overviews import (
    OVERVIEW_PREFIX,
    OVERVIEW_RULE_DAYS,
    OVERVIEW_TTL,
    PROTOTYPE_TTL,
    overviews_lifecycle_ok,
    term_of,
)
from earthx.objectstore.results import RESULT_TTL, Store, lifecycle_ok

from .conftest import OVERVIEWS_RULE, RESULTS_RULE, put_rules


def test_the_terms_are_those_of_the_adr() -> None:
    assert OVERVIEW_PREFIX == "overviews/"
    assert OVERVIEW_TTL == timedelta(days=30)
    assert OVERVIEW_RULE_DAYS == 31, "one day over the term: the rule is the net under the clean-up"
    assert PROTOTYPE_TTL == RESULT_TTL == timedelta(days=7)


@pytest.mark.parametrize(
    ("dataset_id", "term"),
    [
        ("cop-dem-glo-30", OVERVIEW_TTL),
        ("esa-worldcover-2021", OVERVIEW_TTL),
        ("proto-anything", PROTOTYPE_TTL),
        ("my-proto-x", OVERVIEW_TTL),
        ("PROTO-x", OVERVIEW_TTL),
    ],
)
def test_only_the_prefix_makes_a_dataset_a_prototype(dataset_id: str, term: timedelta) -> None:
    assert term_of(dataset_id) == term


def test_no_rule_is_not_ok(store: Store) -> None:
    assert overviews_lifecycle_ok(store) is False


def test_the_rule_for_overviews_is_ok_and_does_not_make_the_one_for_results_ok(store: Store) -> None:
    put_rules(store, [OVERVIEWS_RULE])
    assert overviews_lifecycle_ok(store) is True
    assert lifecycle_ok(store) is False


def test_the_rule_for_results_does_not_make_the_one_for_overviews_ok(store: Store) -> None:
    put_rules(store, [RESULTS_RULE])
    assert overviews_lifecycle_ok(store) is False
    assert lifecycle_ok(store) is True


def test_both_rules_side_by_side_are_ok_and_recognised_by_content(store: Store) -> None:
    put_rules(store, [{**OVERVIEWS_RULE, "ID": "anything"}, RESULTS_RULE])
    assert overviews_lifecycle_ok(store) is True
    assert lifecycle_ok(store) is True


@pytest.mark.parametrize(
    "change",
    [
        {"Status": "Disabled"},
        {"Filter": {"Prefix": "overview/"}},
        {"Filter": {"Prefix": ""}},
        {"Filter": {"And": {"Prefix": "overviews/", "ObjectSizeGreaterThan": 10}}},
        {"Expiration": {"Days": 30}},
        {"Expiration": {"Days": 32}},
        {"AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 2}},
    ],
    ids=["disabled", "other-prefix", "whole-bucket", "narrowed", "30-days", "32-days", "abort-2-days"],
)
def test_a_rule_that_differs_in_content_is_not_ok(store: Store, change: dict) -> None:
    put_rules(store, [{**OVERVIEWS_RULE, **change}])
    assert overviews_lifecycle_ok(store) is False
