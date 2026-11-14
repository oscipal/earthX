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
    StoredTile,
    delete_keys,
    delete_version,
    extend_version,
    overview_key,
    overview_keys,
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
        assert read_tile(store, "cop-dem-glo-30", VERSION, 3, 4, 2) == StoredTile(tile_file.read_bytes(), WHEN)

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


class TestReadDelete:
    def test_a_read_gives_the_bytes_and_the_time_the_object_carries(self, store: Store, tile_file: Path) -> None:
        upload_tile(store, "dem", VERSION, 5, 1, 1, tile_file, checked_at=WHEN)
        assert read_tile(store, "dem", VERSION, 5, 1, 1) == StoredTile(tile_file.read_bytes(), WHEN)

    @pytest.mark.parametrize("metadata", [{}, {CHECKED_AT: "yesterday"}, {CHECKED_AT: "2026-11-14T12:00:00"}])
    def test_a_time_that_is_missing_or_unreadable_or_naive_reads_as_none(
        self, store: Store, tile_file: Path, metadata: dict
    ) -> None:
        key = f"overviews/dem/{VERSION}/5/1/1.tif"
        store.s3._internal.put_object(Bucket=BUCKET, Key=key, Body=tile_file.read_bytes(), Metadata=metadata)
        assert read_tile(store, "dem", VERSION, 5, 1, 1) == StoredTile(tile_file.read_bytes(), None)

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


class TestExtend:
    LATER = datetime(2026, 12, 1, 8, 30, tzinfo=UTC)

    def test_every_object_of_the_version_gets_the_new_time_and_keeps_its_bytes_and_type(
        self, store: Store, tile_file: Path
    ) -> None:
        for z, x, y in ((1, 0, 0), (1, 1, 1), (2, 3, 3)):
            upload_tile(store, "dem", VERSION, z, x, y, tile_file, checked_at=WHEN)
        upload_tile(store, "dem", OTHER, 1, 0, 0, tile_file, checked_at=WHEN)
        before = _head(store, f"overviews/dem/{VERSION}/1/0/0.tif")["LastModified"]

        assert extend_version(store, "dem", VERSION, self.LATER) == 3

        for z, x, y in ((1, 0, 0), (1, 1, 1), (2, 3, 3)):
            head = _head(store, f"overviews/dem/{VERSION}/{z}/{x}/{y}.tif")
            assert head["Metadata"] == {CHECKED_AT: self.LATER.isoformat()}
            assert head["ContentType"] == "image/tiff; application=geotiff"
            assert "CacheControl" not in head
            assert read_tile(store, "dem", VERSION, z, x, y) == tile_file.read_bytes()
        assert _head(store, f"overviews/dem/{VERSION}/1/0/0.tif")["LastModified"] >= before, "the bucket rule counts from now"
        assert _head(store, f"overviews/dem/{OTHER}/1/0/0.tif")["Metadata"] == {CHECKED_AT: WHEN.isoformat()}

    def test_a_version_without_objects_extends_nothing(self, store: Store) -> None:
        assert extend_version(store, "dem", VERSION, self.LATER) == 0

    def test_a_prototype_source_is_never_extended(self, store: Store, tile_file: Path) -> None:
        upload_tile(store, "proto-dem", VERSION, 0, 0, 0, tile_file, checked_at=WHEN)
        with pytest.raises(ValueError, match="prototype"):
            extend_version(store, "proto-dem", VERSION, self.LATER)
        assert _head(store, f"overviews/proto-dem/{VERSION}/0/0/0.tif")["Metadata"] == {CHECKED_AT: WHEN.isoformat()}

    def test_a_naive_time_is_refused_and_nothing_is_rewritten(self, store: Store, tile_file: Path) -> None:
        upload_tile(store, "dem", VERSION, 0, 0, 0, tile_file, checked_at=WHEN)
        with pytest.raises(ValueError, match="timezone"):
            extend_version(store, "dem", VERSION, datetime(2026, 12, 1))
        assert _head(store, f"overviews/dem/{VERSION}/0/0/0.tif")["Metadata"] == {CHECKED_AT: WHEN.isoformat()}

    def test_an_object_that_vanishes_meanwhile_is_not_found(
        self, store: Store, tile_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The listing names a key the copy then does not find: the rule of the bucket was faster."""
        upload_tile(store, "dem", VERSION, 0, 0, 0, tile_file, checked_at=WHEN)
        listing = store.s3.list_keys

        def listed_then_gone(prefix: str):
            keys = list(listing(prefix))
            store.s3._internal.delete_object(Bucket=BUCKET, Key=keys[0])
            return iter(keys)

        object.__setattr__(store.s3, "list_keys", listed_then_gone)
        with pytest.raises(ResultNotFound):
            extend_version(store, "dem", VERSION, self.LATER)


class TestKeysAndDeleteKeys:
    def test_only_keys_under_overviews_are_listed(self, store: Store, tile_file: Path) -> None:
        upload_tile(store, "dem", VERSION, 0, 0, 0, tile_file, checked_at=WHEN)
        store.s3.put_object("results/x/result.tif", tile_file.open("rb"), "image/tiff")
        assert list(overview_keys(store)) == [f"overviews/dem/{VERSION}/0/0/0.tif"]

    def test_keys_outside_the_prefix_are_refused_before_anything_is_deleted(self, store: Store, tile_file: Path) -> None:
        upload_tile(store, "dem", VERSION, 0, 0, 0, tile_file, checked_at=WHEN)
        store.s3.put_object("results/x/result.tif", tile_file.open("rb"), "image/tiff")
        with pytest.raises(ValueError, match="overviews/"):
            delete_keys(store, [f"overviews/dem/{VERSION}/0/0/0.tif", "results/x/result.tif"])
        assert list(store.s3.list_keys("results/")) == ["results/x/result.tif"]

    def test_more_than_a_batch_is_deleted_in_batches(self, store: Store, tile_file: Path) -> None:
        keys = [f"overviews/dem/{VERSION}/9/{n}/0.tif" for n in range(1005)]
        for key in keys:
            store.s3.put_object(key, tile_file.open("rb"), "image/tiff")
        assert delete_keys(store, iter(keys)) == 1005
        assert list(overview_keys(store)) == []

    def test_nothing_to_delete_is_zero(self, store: Store) -> None:
        assert delete_keys(store, []) == 0
