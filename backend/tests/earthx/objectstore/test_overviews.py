"""The terms and the bucket rule of the overview pyramids (M5-30b part 8b, adr/0032 §5.2, §5.3, §8.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from earthx.objectstore.errors import ObjectStoreError, ResultNotFound
from earthx.objectstore.overviews import (
    CHECKED_AT,
    NO_STORE,
    OVERVIEW_PREFIX,
    OVERVIEW_RULE_DAYS,
    OVERVIEW_TTL,
    PROTOTYPE_TTL,
    copy_tile,
    delete_version,
    overview_key,
    overviews_lifecycle_ok,
    read_tile,
    term_of,
    upload_tile,
)
from earthx.objectstore.results import RESULT_TTL, Store, lifecycle_ok

from .conftest import BUCKET, OVERVIEWS_RULE, RESULTS_RULE, put_rules


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


# --- tiles in the store


@pytest.fixture
def tile_file(tmp_path: Path) -> Path:
    path = tmp_path / "tile.tif"
    path.write_bytes(b"II*\x00 tile bytes")
    return path


def _head(store: Store, key: str) -> dict:
    return store.s3._internal.head_object(Bucket=BUCKET, Key=key)


VERSION = "0123456789abcdef"
OTHER = "fedcba9876543210"
WHEN = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


class TestKeys:
    def test_the_key_is_prefix_dataset_version_and_tile(self) -> None:
        assert overview_key("cop-dem-glo-30", VERSION, 6, 33, 22) == f"overviews/cop-dem-glo-30/{VERSION}/6/33/22.tif"

    @pytest.mark.parametrize(
        ("dataset_id", "version", "tile"),
        [
            ("../results", VERSION, (0, 0, 0)),
            ("a/b", VERSION, (0, 0, 0)),
            ("", VERSION, (0, 0, 0)),
            ("Dem", VERSION, (0, 0, 0)),
            ("dem", "abc", (0, 0, 0)),
            ("dem", VERSION.upper(), (0, 0, 0)),
            ("dem", "../../../x", (0, 0, 0)),
            ("dem", VERSION, (-1, 0, 0)),
            ("dem", VERSION, (2, 4, 0)),
            ("dem", VERSION, (2, 0, 4)),
            ("dem", VERSION, (31, 0, 0)),
            ("dem", VERSION, (True, 0, 0)),
        ],
    )
    def test_a_part_that_is_not_of_its_shape_makes_no_key(self, dataset_id: str, version: str, tile: tuple) -> None:
        with pytest.raises(ValueError):
            overview_key(dataset_id, version, *tile)


class TestUpload:
    def test_a_tile_carries_checked_at_and_is_a_geotiff(self, store: Store, tile_file: Path) -> None:
        upload_tile(store, "cop-dem-glo-30", VERSION, 3, 4, 2, tile_file, checked_at=WHEN)
        head = _head(store, f"overviews/cop-dem-glo-30/{VERSION}/3/4/2.tif")
        assert head["Metadata"] == {CHECKED_AT: WHEN.isoformat()}
        assert head["ContentType"] == "image/tiff; application=geotiff"
        assert "CacheControl" not in head
        assert read_tile(store, "cop-dem-glo-30", VERSION, 3, 4, 2) == tile_file.read_bytes()

    def test_a_prototype_source_is_served_with_no_store(self, store: Store, tile_file: Path) -> None:
        upload_tile(store, "proto-anything", VERSION, 0, 0, 0, tile_file, checked_at=WHEN)
        assert _head(store, f"overviews/proto-anything/{VERSION}/0/0/0.tif")["CacheControl"] == NO_STORE

    def test_a_naive_time_is_refused_and_nothing_is_written(self, store: Store, tile_file: Path) -> None:
        with pytest.raises(ValueError, match="timezone"):
            upload_tile(store, "dem", VERSION, 0, 0, 0, tile_file, checked_at=datetime(2026, 11, 14))
        assert list(store.s3.list_keys("overviews/")) == []

    def test_a_missing_file_is_an_oserror_and_nothing_is_written(self, store: Store, tmp_path: Path) -> None:
        with pytest.raises(OSError):
            upload_tile(store, "dem", VERSION, 0, 0, 0, tmp_path / "gone.tif", checked_at=WHEN)
        assert list(store.s3.list_keys("overviews/")) == []

    def test_a_store_that_fails_raises_the_error_of_the_store(self, store: Store, tile_file: Path) -> None:
        store.s3._internal.delete_bucket(Bucket=BUCKET)
        with pytest.raises(ObjectStoreError) as caught:
            upload_tile(store, "dem", VERSION, 0, 0, 0, tile_file, checked_at=WHEN)
        assert "PutObject" in str(caught.value) and "dem" not in str(caught.value)


class TestCopyReadDelete:
    def test_a_copy_has_the_bytes_and_the_checked_at_of_its_source(self, store: Store, tile_file: Path) -> None:
        upload_tile(store, "dem", VERSION, 5, 1, 1, tile_file, checked_at=WHEN)
        copy_tile(store, "dem", VERSION, OTHER, 5, 1, 1)
        copied = _head(store, f"overviews/dem/{OTHER}/5/1/1.tif")
        assert copied["Metadata"] == {CHECKED_AT: WHEN.isoformat()}
        assert read_tile(store, "dem", OTHER, 5, 1, 1) == tile_file.read_bytes()

    def test_a_copy_of_a_tile_that_is_not_there_is_an_error_and_writes_nothing(self, store: Store) -> None:
        with pytest.raises(ResultNotFound):
            copy_tile(store, "dem", VERSION, OTHER, 5, 1, 1)
        assert list(store.s3.list_keys("overviews/")) == []

    def test_a_tile_that_is_not_there_reads_as_none(self, store: Store) -> None:
        assert read_tile(store, "dem", VERSION, 1, 0, 0) is None

    def test_deleting_a_version_leaves_the_others_and_other_datasets(self, store: Store, tile_file: Path) -> None:
        for dataset_id, version in (("dem", VERSION), ("dem", OTHER), ("land", VERSION)):
            upload_tile(store, dataset_id, version, 1, 0, 0, tile_file, checked_at=WHEN)
            upload_tile(store, dataset_id, version, 1, 1, 1, tile_file, checked_at=WHEN)
        delete_version(store, "dem", VERSION)
        assert sorted(store.s3.list_keys("overviews/")) == sorted(
            f"overviews/{d}/{v}/1/{n}/{n}.tif" for d, v in (("dem", OTHER), ("land", VERSION)) for n in (0, 1)
        )

    def test_deleting_a_version_with_nothing_in_it_is_fine(self, store: Store) -> None:
        delete_version(store, "dem", VERSION)

    def test_deleting_does_not_reach_results(self, store: Store, tile_file: Path) -> None:
        store.s3.put_object("results/abc/result.tif", tile_file.open("rb"), "image/tiff")
        delete_version(store, "dem", VERSION)
        assert list(store.s3.list_keys("results/")) == ["results/abc/result.tif"]
