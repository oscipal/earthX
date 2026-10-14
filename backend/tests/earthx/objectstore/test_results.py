"""Upload, signed download, delete and the lifecycle check against `moto` (adr/0015 §12 point 5)."""

from __future__ import annotations

import os
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from earthx.objectstore import results
from earthx.objectstore.errors import ResultExpiring, ResultNotFound, StoreUnavailable
from earthx.objectstore.results import (
    Store,
    delete_result,
    lifecycle_ok,
    new_result_id,
    signed_download,
    upload_result,
)

from .conftest import ACCESS_KEY, BUCKET, RESULTS_RULE, SECRET_KEY, put_rules

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _file(tmp_path: Path, size: int) -> Path:
    path = tmp_path / f"payload-{size}"
    path.write_bytes(os.urandom(size))
    return path


def _keys(store: Store, prefix: str = "") -> set[str]:
    return set(store.s3.list_keys(prefix))


def _open_uploads(store: Store) -> list:
    return store.s3.list_multipart_uploads("")


def _head(store: Store, key: str) -> dict:
    return store.s3._internal.head_object(Bucket=BUCKET, Key=key)


# --- identifiers -----------------------------------------------------------------


def test_a_new_result_id_is_random_and_well_formed() -> None:
    ids = {new_result_id() for _ in range(100)}
    assert len(ids) == 100
    for result_id in ids:
        assert results._check_result_id(result_id) == result_id


@pytest.mark.parametrize(
    "result_id",
    ["", "short", "../../../../etc/passwd0", "a" * 21, "a" * 23, "aaaaaaaaaaaaaaaaaaaa/a", "aaaaaaaaaaaaaaaaaaaa.a"],
)
def test_a_result_id_of_another_shape_is_refused(store: Store, tmp_path: Path, result_id: str) -> None:
    with pytest.raises(ValueError, match="result_id"):
        upload_result(store, result_id, "result.tif", _file(tmp_path, 10))
    with pytest.raises(ValueError, match="result_id"):
        delete_result(store, result_id)
    assert _keys(store) == set()


@pytest.mark.parametrize("name", ["result.TIF", "other.tif", "../result.tif", "", "results/result.tif"])
def test_a_name_outside_the_fixed_set_is_refused(store: Store, tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="file name"):
        upload_result(store, new_result_id(), name, _file(tmp_path, 10))
    assert _keys(store) == set()


# --- upload ----------------------------------------------------------------------


def test_a_small_file_is_put_under_the_result_prefix(store: Store, tmp_path: Path) -> None:
    result_id = new_result_id()
    path = _file(tmp_path, 1024)
    upload_result(store, result_id, "recipe.json", path)
    key = f"results/{result_id}/recipe.json"
    assert _keys(store) == {key}
    head = _head(store, key)
    assert head["ContentLength"] == 1024
    assert head["ContentType"] == "application/json"


def test_the_mask_of_a_result_lies_next_to_it_as_a_geotiff(store: Store, tmp_path: Path) -> None:
    """M4-08a F4: a job leaves `result.tif` and `mask.tif`, and nothing else, under its prefix."""
    result_id = new_result_id()
    for name in ("result.tif", "mask.tif"):
        upload_result(store, result_id, name, _file(tmp_path, 64))
    assert _keys(store) == {f"results/{result_id}/result.tif", f"results/{result_id}/mask.tif"}
    assert _head(store, f"results/{result_id}/mask.tif")["ContentType"] == "image/tiff; application=geotiff"


def test_a_large_file_goes_up_in_parts(store: Store, tmp_path: Path) -> None:
    result_id = new_result_id()
    size = 2 * results.PART_SIZE + 1234
    path = _file(tmp_path, size)
    upload_result(store, result_id, "result.tif", path)
    key = f"results/{result_id}/result.tif"
    head = _head(store, key)
    assert head["ContentLength"] == size
    assert head["ETag"].strip('"').endswith("-3")
    body = store.s3._internal.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    assert body == path.read_bytes()
    assert _open_uploads(store) == []


def test_a_failed_part_aborts_the_upload_and_keeps_the_error(
    store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    real_upload_part = type(store.s3).upload_part

    def failing_upload_part(self, key, upload_id, number, body):  # noqa: ANN001, ANN202
        calls.append(number)
        if number == 2:
            raise StoreUnavailable("object store UploadPart failed (InternalError, HTTP 500)")
        return real_upload_part(self, key, upload_id, number, body)

    monkeypatch.setattr(type(store.s3), "upload_part", failing_upload_part)
    with pytest.raises(StoreUnavailable, match="UploadPart"):
        upload_result(store, new_result_id(), "result.tif", _file(tmp_path, 2 * results.PART_SIZE + 1))
    assert calls == [1, 2]
    assert _open_uploads(store) == []
    assert _keys(store) == set()


def test_a_failing_abort_does_not_hide_the_original_error(
    store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object) -> None:
        raise StoreUnavailable("first")

    def fail_abort(*args: object) -> None:
        raise StoreUnavailable("abort")

    monkeypatch.setattr(type(store.s3), "upload_part", fail)
    monkeypatch.setattr(type(store.s3), "abort_multipart_upload", fail_abort)
    with pytest.raises(StoreUnavailable, match="first"):
        upload_result(store, new_result_id(), "result.tif", _file(tmp_path, results.MULTIPART_THRESHOLD + 1))


# --- signed download -------------------------------------------------------------


def test_a_signed_url_points_at_the_public_endpoint_with_the_file_name(store: Store) -> None:
    result_id = new_result_id()
    url = signed_download(
        store, result_id, "result.tif", not_after=NOW + timedelta(days=7), filename="s2-ndvi-2026-10-06.tif", now=NOW
    )
    assert url.startswith(f"http://localhost:3900/{BUCKET}/results/{result_id}/result.tif?")
    assert "objectstore" not in url
    assert "X-Amz-Expires=900&" in url
    assert "response-content-disposition=attachment%3B%20filename%3D%22s2-ndvi-2026-10-06.tif%22" in url
    assert SECRET_KEY not in url


def test_a_signed_url_never_outlives_the_result(store: Store) -> None:
    url = signed_download(
        store, new_result_id(), "result.tif", not_after=NOW + timedelta(seconds=120), filename="r.tif", now=NOW
    )
    assert "X-Amz-Expires=120&" in url


@pytest.mark.parametrize("left", [timedelta(seconds=59), timedelta(0), timedelta(days=-1)])
def test_no_signed_url_with_less_than_a_minute_left(store: Store, left: timedelta) -> None:
    with pytest.raises(ResultExpiring):
        signed_download(store, new_result_id(), "result.tif", not_after=NOW + left, filename="r.tif", now=NOW)


def test_a_naive_expiry_is_refused(store: Store) -> None:
    with pytest.raises(ValueError, match="timezone"):
        signed_download(store, new_result_id(), "result.tif", not_after=datetime(2026, 10, 13), filename="r.tif")


@pytest.mark.parametrize(
    "filename", ["", ".hidden", 'a"b.tif', "a/b.tif", "a b.tif", "a;b.tif", "x" * 129, "ä.tif", "a\r\nb.tif"]
)
def test_a_file_name_that_could_break_the_header_is_refused(store: Store, filename: str) -> None:
    with pytest.raises(ValueError, match="filename"):
        signed_download(
            store, new_result_id(), "result.tif", not_after=NOW + timedelta(days=1), filename=filename, now=NOW
        )


# --- delete ----------------------------------------------------------------------


def test_delete_removes_the_result_and_its_open_uploads_only(store: Store, tmp_path: Path) -> None:
    gone, kept = new_result_id(), new_result_id()
    for name in ("result.tif", "recipe.json", "citation.bib"):
        upload_result(store, gone, name, _file(tmp_path, 10))
    upload_result(store, kept, "result.tif", _file(tmp_path, 10))
    store.s3.create_multipart_upload(f"results/{gone}/result.tif", "image/tiff")
    store.s3.create_multipart_upload(f"results/{kept}/result.tif", "image/tiff")

    delete_result(store, gone)

    assert _keys(store) == {f"results/{kept}/result.tif"}
    assert [key for key, _ in _open_uploads(store)] == [f"results/{kept}/result.tif"]


def test_deleting_a_result_that_is_not_there_is_quiet(store: Store) -> None:
    delete_result(store, new_result_id())


# --- lifecycle -------------------------------------------------------------------


def test_no_lifecycle_configuration_is_not_ok(store: Store) -> None:
    assert lifecycle_ok(store) is False


def test_the_results_rule_is_ok(store: Store) -> None:
    put_rules(store, [RESULTS_RULE])
    assert lifecycle_ok(store) is True


def test_the_rule_is_recognised_by_content_not_by_id(store: Store) -> None:
    """Plan M4-06, F4: production sets its own IDs; other rules do not matter."""
    other = {"ID": "keep-tmp", "Status": "Enabled", "Filter": {"Prefix": "tmp/"}, "Expiration": {"Days": 1}}
    put_rules(store, [other, {**RESULTS_RULE, "ID": "anything"}])
    assert lifecycle_ok(store) is True


@pytest.mark.parametrize(
    "change",
    [
        {"Status": "Disabled"},
        {"Filter": {"Prefix": "result/"}},
        {"Filter": {"Prefix": ""}},
        {"Filter": {"And": {"Prefix": "results/", "ObjectSizeGreaterThan": 10}}},
        {"Expiration": {"Days": 6}},
        {"Expiration": {"Days": 8}},
        {"AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 2}},
    ],
    ids=["disabled", "other-prefix", "whole-bucket", "narrowed", "6-days", "8-days", "abort-2-days"],
)
def test_a_rule_that_differs_in_content_is_not_ok(store: Store, change: dict) -> None:
    put_rules(store, [{**RESULTS_RULE, **change}])
    assert lifecycle_ok(store) is False


def test_a_rule_without_the_multipart_abort_is_not_ok(store: Store) -> None:
    rule = {key: value for key, value in RESULTS_RULE.items() if key != "AbortIncompleteMultipartUpload"}
    put_rules(store, [rule])
    assert lifecycle_ok(store) is False


@pytest.mark.parametrize(
    ("rule", "ok"),
    [
        ({**RESULTS_RULE}, True),
        ({k: v for k, v in RESULTS_RULE.items() if k != "Filter"} | {"Prefix": "results/"}, True),
        ({k: v for k, v in RESULTS_RULE.items() if k != "Filter"}, False),
        ({**RESULTS_RULE, "Expiration": {"Date": "2026-10-13T00:00:00Z"}}, False),
    ],
    ids=["filter", "legacy-prefix", "no-prefix", "date-not-days"],
)
def test_the_rule_shapes_garage_and_aws_return(rule: dict, ok: bool) -> None:
    assert results._is_results_rule(rule) is ok


def test_nothing_in_the_store_names_the_access_key_outside_signed_urls(store: Store) -> None:
    assert ACCESS_KEY not in repr(store)


# --- size and CRC of a file; size and byte range of an object (M4-11b-1) ----------


def _stored(store: Store, tmp_path: Path, size: int, name: str = "result.tif") -> tuple[str, bytes]:
    result_id = new_result_id()
    path = _file(tmp_path, size)
    upload_result(store, result_id, name, path)
    return result_id, path.read_bytes()


@pytest.mark.parametrize("size", [0, 1, 1024, results._CRC_BLOCK, results._CRC_BLOCK + 7, 3 * results._CRC_BLOCK + 11])
def test_file_facts_are_the_size_and_crc_of_the_bytes(tmp_path: Path, size: int) -> None:
    path = _file(tmp_path, size)
    assert results.file_facts(path) == {"bytes": size, "crc32": zlib.crc32(path.read_bytes())}


def test_file_facts_of_a_missing_file_raise_instead_of_describing_nothing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        results.file_facts(tmp_path / "gone.tif")


def test_the_facts_of_an_uploaded_file_are_those_of_the_object_in_the_store(store: Store, tmp_path: Path) -> None:
    result_id, content = _stored(store, tmp_path, 2 * results.PART_SIZE + 99)
    body = store.s3._internal.get_object(Bucket=BUCKET, Key=f"results/{result_id}/result.tif")["Body"].read()
    assert body == content
    assert results.file_facts(tmp_path / f"payload-{len(content)}")["crc32"] == zlib.crc32(body)
    assert results.result_size(store, result_id, "result.tif") == len(content)


def test_the_size_of_a_missing_result_is_not_found_and_names_nothing(store: Store) -> None:
    result_id = new_result_id()
    with pytest.raises(ResultNotFound) as caught:
        results.result_size(store, result_id, "mask.tif")
    assert result_id not in str(caught.value) and "mask.tif" not in str(caught.value)


@pytest.mark.parametrize(
    ("start", "end"), [(0, 0), (0, 99), (5, 5), (100, 2999), (2999, 2999), (0, 2999), (1500, 2999)]
)
def test_a_byte_range_is_read_in_pieces(store: Store, tmp_path: Path, start: int, end: int) -> None:
    result_id, content = _stored(store, tmp_path, 3000)
    stream = results.open_result_range(store, result_id, "result.tif", start, end)
    try:
        pieces = []
        while piece := stream.read(700):
            pieces.append(piece)
    finally:
        stream.close()
    assert b"".join(pieces) == content[start : end + 1]
    assert all(len(piece) <= 700 for piece in pieces)


def test_the_end_of_a_range_beyond_the_object_is_cut_at_its_end(store: Store, tmp_path: Path) -> None:
    result_id, content = _stored(store, tmp_path, 1000)
    stream = results.open_result_range(store, result_id, "result.tif", 900, 5000)
    try:
        assert stream.read(10_000) == content[900:]
    finally:
        stream.close()


def test_a_range_that_starts_beyond_the_object_is_an_error_without_key_or_endpoint(
    store: Store, tmp_path: Path
) -> None:
    result_id, _ = _stored(store, tmp_path, 1000)
    with pytest.raises(StoreUnavailable) as caught:
        results.open_result_range(store, result_id, "result.tif", 1000, 2000)
    for secret in (result_id, "objectstore", ACCESS_KEY, SECRET_KEY):
        assert secret not in str(caught.value)


@pytest.mark.parametrize(("start", "end"), [(-1, 5), (5, 4), (-5, -1)])
def test_a_range_of_the_wrong_shape_is_refused_before_a_request(store: Store, start: int, end: int) -> None:
    with pytest.raises(ValueError, match="start and end"):
        results.open_result_range(store, new_result_id(), "result.tif", start, end)


def test_a_range_of_a_missing_object_is_not_found(store: Store) -> None:
    with pytest.raises(ResultNotFound):
        results.open_result_range(store, new_result_id(), "mask.tif", 0, 10)


def test_a_range_of_a_name_outside_the_fixed_set_is_refused(store: Store) -> None:
    with pytest.raises(ValueError, match="file name"):
        results.open_result_range(store, new_result_id(), "other.tif", 0, 10)
    with pytest.raises(ValueError, match="file name"):
        results.result_size(store, new_result_id(), "other.tif")


def test_a_read_that_fails_on_the_wire_is_translated_without_its_text() -> None:
    from botocore.exceptions import ReadTimeoutError

    from earthx.objectstore.client import ObjectRange

    class Broken:
        def read(self, size: int) -> bytes:
            raise ReadTimeoutError(endpoint_url="http://objectstore:3900/earthx/results/x")

        def close(self) -> None:
            pass

    with pytest.raises(StoreUnavailable) as caught:
        ObjectRange(Broken()).read(10)
    assert "objectstore" not in str(caught.value) and "ReadTimeoutError" in str(caught.value)
