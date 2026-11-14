"""Overview pyramids in the object store: where they live and how long (M5-30b part 8b, adr/0032 §5.2, §5.3, §8.4).

Objects live at ``overviews/{dataset_id}/{version}/{z}/{x}/{y}.tif``. ``version`` is the name of a source version
(`earthx_overview_version` in the database); a new version is a new path and the old one is never read again.

**How long.** Every object carries ``checked-at``, the time its content was last confirmed at the source, and goes
30 days after it (:data:`OVERVIEW_TTL`); a confirmed version is extended, an unconfirmed one runs out. The bucket rule is
the net under that and has 31 days (:data:`OVERVIEW_RULE_DAYS`): an extension rewrites the object, so the rule counts
from the extension (:func:`extend_version`). A dataset whose id starts with ``proto-`` (adr/0024) lives 7 days and is
never extended (:data:`PROTOTYPE_TTL`).
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from earthx.objectstore.errors import ResultNotFound
from earthx.objectstore.results import Store, is_expiry_rule

__all__ = [
    "CHECKED_AT",
    "NO_STORE",
    "OVERVIEW_PREFIX",
    "OVERVIEW_RULE_DAYS",
    "OVERVIEW_TTL",
    "PROTOTYPE_PREFIX",
    "PROTOTYPE_TTL",
    "StoredTile",
    "delete_keys",
    "delete_version",
    "extend_version",
    "overview_key",
    "overview_keys",
    "overviews_lifecycle_ok",
    "read_tile",
    "term_of",
    "upload_tile",
]

OVERVIEW_PREFIX = "overviews/"
#: From the last confirmation of a version at the source (adr/0032 §5.2, F3).
OVERVIEW_TTL = timedelta(days=30)
#: The bucket rule, one day over the term so that it only catches what the cleanup did not.
OVERVIEW_RULE_DAYS = 31
#: A prototype source (adr/0024): 7 days like a result, and no extension (adr/0032 §8.4).
PROTOTYPE_PREFIX = "proto-"
PROTOTYPE_TTL = timedelta(days=7)


def term_of(dataset_id: str) -> timedelta:
    """How long a pyramid of this dataset lives from its ``checked-at``."""
    return PROTOTYPE_TTL if dataset_id.startswith(PROTOTYPE_PREFIX) else OVERVIEW_TTL


def overviews_lifecycle_ok(store: Store) -> bool:
    """Whether the bucket carries the rule for ``overviews/``, read only; recognised by content like the one for results."""
    return any(
        is_expiry_rule(rule, prefix=OVERVIEW_PREFIX, days=OVERVIEW_RULE_DAYS) for rule in store.s3.lifecycle_rules()
    )


#: The metadatum that carries the time a tile was last confirmed at the source (adr/0032 §5.2).
CHECKED_AT = "checked-at"
#: What a prototype source's objects are served with (adr/0024 R7).
NO_STORE = "no-store"
_CONTENT_TYPE = "image/tiff; application=geotiff"
_DATASET = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_VERSION = re.compile(r"^[0-9a-f]{16}$")


def _version_prefix(dataset_id: str, version: str) -> str:
    if not _DATASET.match(dataset_id):
        raise ValueError("a dataset id is lowercase letters, digits and hyphens")
    if not _VERSION.match(version):
        raise ValueError("a version is 16 hex digits (earthx_overview_version)")
    return f"{OVERVIEW_PREFIX}{dataset_id}/{version}/"


def overview_key(dataset_id: str, version: str, z: int, x: int, y: int) -> str:
    """``overviews/{dataset_id}/{version}/{z}/{x}/{y}.tif``; a part that is not of its shape is a ``ValueError``."""
    prefix = _version_prefix(dataset_id, version)
    if any(isinstance(n, bool) or not isinstance(n, int) for n in (z, x, y)) or not (
        0 <= z <= 30 and 0 <= x < 2**z and 0 <= y < 2**z
    ):
        raise ValueError("a tile is z, x, y of the WebMercatorQuad grid")
    return f"{prefix}{z}/{x}/{y}.tif"


def upload_tile(
    store: Store, dataset_id: str, version: str, z: int, x: int, y: int, path: Path, *, checked_at: datetime
) -> None:
    """Upload one stored tile with ``checked-at``; a prototype source's tile is also ``Cache-Control: no-store`` (adr/0024 R7)."""
    if checked_at.tzinfo is None:
        raise ValueError("checked_at must be timezone-aware")
    key = overview_key(dataset_id, version, z, x, y)
    with path.open("rb") as body:
        store.s3.put_object(
            key,
            body,
            _CONTENT_TYPE,
            cache_control=NO_STORE if dataset_id.startswith(PROTOTYPE_PREFIX) else None,
            metadata={CHECKED_AT: checked_at.isoformat()},
        )


@dataclass(frozen=True, slots=True)
class StoredTile:
    """The bytes of a stored tile and the ``checked-at`` it carries (``None`` if the metadatum is missing or unreadable)."""

    data: bytes
    checked_at: datetime | None


def read_tile(store: Store, dataset_id: str, version: str, z: int, x: int, y: int) -> StoredTile | None:
    """One stored tile with its ``checked-at``, or ``None`` if there is none.

    A build that reuses a tile of an older version uploads these bytes itself, with this time: it never asks that version
    again, which may have expired by the time the build ends.
    """
    try:
        data, metadata = store.s3.get_bytes_and_metadata(overview_key(dataset_id, version, z, x, y))
    except ResultNotFound:
        return None
    try:
        checked_at = datetime.fromisoformat(metadata[CHECKED_AT])
    except (KeyError, ValueError):
        return StoredTile(data, None)
    return StoredTile(data, checked_at if checked_at.tzinfo is not None else None)


def extend_version(store: Store, dataset_id: str, version: str, checked_at: datetime) -> int:
    """Give every object of a version a new ``checked-at`` by copying it onto itself; the number of objects rewritten.

    The content is not read or sent again; the bucket rule counts from the new write (adr/0032 §5.3). Only after the
    source confirmed the version (the caller's condition), and never for a prototype source (adr/0032 §8.4: a
    ``ValueError``). A version with no object returns 0; an object that vanishes meanwhile raises
    :class:`~earthx.objectstore.errors.ResultNotFound`.
    """
    if checked_at.tzinfo is None:
        raise ValueError("checked_at must be timezone-aware")
    if dataset_id.startswith(PROTOTYPE_PREFIX):
        raise ValueError("a prototype source's pyramid is never extended")
    count = 0
    for key in store.s3.list_keys(_version_prefix(dataset_id, version)):
        store.s3.rewrite_object(
            key, content_type=_CONTENT_TYPE, cache_control=None, metadata={CHECKED_AT: checked_at.isoformat()}
        )
        count += 1
    return count


def overview_keys(store: Store) -> Iterator[str]:
    """Every key under ``overviews/``."""
    return store.s3.list_keys(OVERVIEW_PREFIX)


def delete_keys(store: Store, keys: Iterable[str]) -> int:
    """Delete these keys, which must all lie under ``overviews/``, in batches of 1000; the number deleted."""
    count, batch = 0, []
    for key in keys:
        if not key.startswith(OVERVIEW_PREFIX):
            raise ValueError("only keys under overviews/ are deleted here")
        batch.append(key)
        if len(batch) == 1000:
            store.s3.delete_objects(batch)
            count, batch = count + len(batch), []
    if batch:
        store.s3.delete_objects(batch)
        count += len(batch)
    return count


def delete_version(store: Store, dataset_id: str, version: str) -> None:
    """Delete every object of one version and abort its open uploads."""
    prefix = _version_prefix(dataset_id, version)
    batch: list[str] = []
    for key in store.s3.list_keys(prefix):
        batch.append(key)
        if len(batch) == 1000:
            store.s3.delete_objects(batch)
            batch = []
    if batch:
        store.s3.delete_objects(batch)
    for key, upload_id in store.s3.list_multipart_uploads(prefix):
        with contextlib.suppress(ResultNotFound):
            store.s3.abort_multipart_upload(key, upload_id)
