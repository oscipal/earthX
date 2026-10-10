"""Results in the object store: upload, signed download, delete, lifecycle check.

The public functions take a :class:`Store` and identifiers — a `result_id`
and a `name` from a fixed set — and never an endpoint, host, bucket or URL
(adr/0015 §4.1, Auflage F2). A `Store` comes into being only through
:meth:`Store.from_environ`, so the only way to the client is the process
environment.

Objects live at `results/{result_id}/{name}`; `result_id` is random and is
never the job ID, the recipe hash or anything derived from an AOI (§8.1, F10).
"""

from __future__ import annotations

import contextlib
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from earthx.objectstore.client import S3, build_clients
from earthx.objectstore.config import StoreConfig
from earthx.objectstore.errors import ObjectStoreError, ResultExpiring

RESULT_PREFIX = "results/"
# Q10: results live 7 days. The bucket rule (adr/0015 §7.3) carries the same
# value, and `lifecycle_ok` checks that it does.
RESULT_TTL = timedelta(days=7)
# Leftovers of an aborted multipart upload go after one day (§7.3).
MULTIPART_ABORT_DAYS = 1
# F5: a signed URL lives 15 minutes, never past the result's expiry, and none is
# handed out with less than 60 seconds left (§6.2).
SIGNED_URL_TTL = timedelta(minutes=15)
MIN_REMAINING = timedelta(seconds=60)
# Plan M4-06 F6: s3transfer's own defaults (`manager.py`, 8 MiB each). S3 wants
# parts of at least 5 MiB except the last and at most 10 000 of them.
MULTIPART_THRESHOLD = 8 * 1024 * 1024
PART_SIZE = 8 * 1024 * 1024

# What a job writes next to its result (adr/0015 §8.1, adr/0014 §10); an export
# writes `export.zip` alone (M4-11a). Grows with M4-12 when a job writes further files.
RESULT_NAMES: Mapping[str, str] = {
    "result.tif": "image/tiff; application=geotiff; profile=cloud-optimized",
    "mask.tif": "image/tiff; application=geotiff",
    "recipe.json": "application/json",
    "citation.bib": "application/x-bibtex",
    "attribution.txt": "text/plain; charset=utf-8",
    "export.zip": "application/zip",
}

# The shape of `secrets.token_urlsafe(16)`: 128 bits, 22 characters.
_RESULT_ID_LENGTH = 22
_RESULT_ID_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
_FILENAME_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
_FILENAME_MAX = 128


@dataclass(frozen=True)
class Store:
    """The configured store and its clients. Built once per process, at start."""

    config: StoreConfig
    s3: S3

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> Store:
        config = StoreConfig.from_environ(environ)
        return cls(config, build_clients(config))


def new_result_id() -> str:
    return secrets.token_urlsafe(16)


def upload_result(store: Store, result_id: str, name: str, path: Path) -> None:
    """Upload one file; multipart above the threshold, aborted again on any error."""
    key = _key(result_id, name)
    content_type = RESULT_NAMES[name]
    with path.open("rb") as body:
        if path.stat().st_size <= MULTIPART_THRESHOLD:
            store.s3.put_object(key, body, content_type)
            return
        upload_id = store.s3.create_multipart_upload(key, content_type)
        try:
            etags = []
            while chunk := body.read(PART_SIZE):
                etags.append(store.s3.upload_part(key, upload_id, len(etags) + 1, chunk))
            store.s3.complete_multipart_upload(key, upload_id, etags)
        except BaseException:
            # The original error is the one worth raising; the bucket rule cleans
            # up the parts if this abort fails too (§7.3).
            with contextlib.suppress(ObjectStoreError):
                store.s3.abort_multipart_upload(key, upload_id)
            raise


def signed_download(
    store: Store,
    result_id: str,
    name: str,
    *,
    not_after: datetime,
    filename: str,
    now: datetime | None = None,
) -> str:
    """A GET URL for the browser, signed for the public endpoint.

    Valid for 15 minutes or until `not_after`, whichever comes first; with less
    than 60 seconds left it raises :class:`ResultExpiring` instead (M4-08b turns
    that into `410`). `filename` becomes the download's file name; it is built
    from dataset, operator and date, never from an AOI or a hash (§6.5).
    """
    key = _key(result_id, name)
    if not_after.tzinfo is None:
        raise ValueError("not_after must be timezone-aware")
    _check_filename(filename)
    remaining = not_after - (now or datetime.now(UTC))
    if remaining < MIN_REMAINING:
        raise ResultExpiring("the result expires in less than 60 seconds")
    expires_in = int(min(SIGNED_URL_TTL, remaining).total_seconds())
    return store.s3.presign_get(key, expires_in, f'attachment; filename="{filename}"')


def delete_result(store: Store, result_id: str) -> None:
    """Delete every object under the result's prefix and abort its open uploads."""
    prefix = f"{RESULT_PREFIX}{_check_result_id(result_id)}/"
    batch: list[str] = []
    for key in store.s3.list_keys(prefix):
        batch.append(key)
        if len(batch) == 1000:
            store.s3.delete_objects(batch)
            batch = []
    if batch:
        store.s3.delete_objects(batch)
    for key, upload_id in store.s3.list_multipart_uploads(prefix):
        store.s3.abort_multipart_upload(key, upload_id)


def lifecycle_ok(store: Store) -> bool:
    """Whether the bucket carries the rule of adr/0015 §7.3, read only.

    Recognised by its content, not its ID (plan M4-06, F4): enabled, prefix
    `results/`, expiry after 7 days, open multipart uploads aborted after 1 day.
    Other rules on the bucket do not matter.
    """
    return any(_is_results_rule(rule) for rule in store.s3.lifecycle_rules())


def _is_results_rule(rule: Mapping[str, Any]) -> bool:
    filter_ = rule.get("Filter")
    # The legacy form puts the prefix at the top level; a filter with `And`
    # narrows it further (size), which would leave objects behind.
    prefix = filter_.get("Prefix") if isinstance(filter_, Mapping) else rule.get("Prefix")
    if isinstance(filter_, Mapping) and set(filter_) - {"Prefix"}:
        return False
    expiration = rule.get("Expiration") or {}
    abort = rule.get("AbortIncompleteMultipartUpload") or {}
    return (
        rule.get("Status") == "Enabled"
        and prefix == RESULT_PREFIX
        and expiration.get("Days") == RESULT_TTL.days
        and abort.get("DaysAfterInitiation") == MULTIPART_ABORT_DAYS
    )


def _key(result_id: str, name: str) -> str:
    if name not in RESULT_NAMES:
        raise ValueError(f"unknown result file name; expected one of {', '.join(sorted(RESULT_NAMES))}")
    return f"{RESULT_PREFIX}{_check_result_id(result_id)}/{name}"


def _check_result_id(result_id: str) -> str:
    if len(result_id) != _RESULT_ID_LENGTH or not set(result_id) <= _RESULT_ID_CHARS:
        raise ValueError("result_id must have the form of secrets.token_urlsafe(16)")
    return result_id


def _check_filename(filename: str) -> None:
    if not 0 < len(filename) <= _FILENAME_MAX or not set(filename) <= _FILENAME_CHARS or filename[0] == ".":
        raise ValueError("filename must be 1-128 letters, digits, '.', '_' or '-', not starting with '.'")
