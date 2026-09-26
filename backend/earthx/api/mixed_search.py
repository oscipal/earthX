"""The pure pieces of the mixed search (M3-13): shares, fingerprint, page token.

Split out of ``federating_client.py`` (which already carries the per-collection
dispatch and the network/database orchestration) so this half — arithmetic and
encoding, no ``Request``, no ``gateway``, no pgstac — is directly unit-testable.

A **mixed search** is one that spans more than one *source*: a federated
collection, or a group of this platform's own collections that share whether a
``datetime`` filter applies to them (``earthx:capabilities.time_range`` — a
materialized dataset without a time axis, such as the DEM, never shares a group
with one that has one, `plans/m3-13-gemischte-suche.md` §4.2). Fan-out (Option 1
of that plan's §3): every open source is asked in parallel, each for a *share* of
the page's ``limit``; the shares are recomputed every page, so a source that
still has more once another runs out gets the rest of the room rather than a
shrinking page (the fixed-share alternative, Option 2, was not chosen).

The page token this module mints is a second, distinct shape from the adapter's
own (``adapters.federated_search.encode_page_token``) — never confused with it
(the ``"k": "mixed"`` marker; see that module's own rejection of a mixed token
handed to a single-collection search, and :func:`decode_mixed_token` below's
rejection of an adapter token handed to a mixed one).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Collection, Mapping, Sequence
from typing import Any, TypedDict

from earthx.adapters.federated_search import InvalidQuery

# adr/0005 rule V's read timeout is 15 s (gateway.Policy); a mixed page's own budget
# per source sits under that with room to spare, well above the slowest single
# federated answer measured so far (EOPF, up to 3.8 s with a 20,000-point polygon,
# `plans/m3-08-intersects-ids.md` §2.1) — a native (pgstac) source carries no budget
# at all: a failure there is a failure of our own database, not a partial result
# (`plans/m3-13-gemischte-suche.md` §4.4, "Ein Fehler der eigenen Datenbank...").
SOURCE_TIMEOUT_S = 10.0

MIXED_TOKEN_VERSION = 1

# Why a source failed, named in `IncompleteSource.reason` and repeated on every
# following page of the same search (plan §4.4) — never the source's own error
# text (adr/0005 rule III applies here too).
REASON_TIMEOUT = "timeout"
REASON_UNREACHABLE = "unreachable"
REASON_UPSTREAM_ERROR = "upstream_error"
REASON_UNRECOGNISED_ANSWER = "unrecognised_answer"


class IncompleteSource(TypedDict):
    """One entry of a mixed answer's ``incomplete_collections`` (plan §4.4)."""

    collection: str
    reason: str


def compute_shares(limit: int, n_sources: int) -> list[int]:
    """``limit`` split into ``n_sources`` shares, in the fixed source order.

    ``limit // n_sources`` each, the remainder given one each to the first
    sources (plan §4.2 step 3) — so with ``limit=100`` over three sources the
    shares are ``[34, 33, 33]``, and with ``limit`` below ``n_sources`` the
    later sources get ``0`` and stay open rather than being asked for nothing.
    """
    if n_sources <= 0:
        return []
    base, remainder = divmod(limit, n_sources)
    return [base + 1 if index < remainder else base for index in range(n_sources)]


def mixed_fingerprint(
    collection_ids: Sequence[str],
    bbox: Sequence[float] | None,
    intersects: Mapping[str, Any] | None,
    ids: Sequence[str] | None,
    datetime_value: str | None,
) -> str:
    """A hash of the *whole* mixed search — the raw request, before any per-source
    splitting or per-source datetime dropping (`_apply_time_axis` in
    ``federating_client.py``). ``limit`` plays no part, for the same reason it plays
    none in the adapter's own fingerprint: a mixed search continued at a different
    page size is still the same search (plan §4.3).
    """
    payload: dict[str, Any] = {
        "collections": sorted(collection_ids),
        "bbox": None if bbox is None else [float(value) for value in bbox],
        "datetime": datetime_value,
    }
    if intersects is not None:
        payload["intersects"] = json.dumps(intersects, separators=(",", ":"), sort_keys=True)
    if ids is not None:
        payload["ids"] = sorted(set(ids))
    return hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def is_mixed_token(token: str) -> bool:
    """Whether ``token`` (already stripped of any ``next:``/``prev:`` prefix) is
    shaped like one of this module's own mixed-search tokens.

    Used only so a search that is single-source *this time* can refuse a mixed
    token from an earlier page of the same paging sequence before handing it
    to pgstac unchanged — the single-collection path never decodes a token of
    its own at all (it is pgstac's native marker, opaque to us), so nothing
    else would catch this. A token that fails to parse at all is simply not a
    mixed one, exactly as ``decode_mixed_token`` finds out the hard way.
    """
    padded = token + "=" * (-len(token) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, binascii.Error):
        return False
    return isinstance(payload, dict) and payload.get("k") == "mixed"


def encode_mixed_token(
    fingerprint: str, source_markers: Mapping[str, str | None], failed: Mapping[str, str]
) -> str:
    """The page marker for a mixed search: which sources are still open (and at
    which of their own inner markers), and which have already failed for good
    (plan §4.3). ``source_markers`` may hold ``None`` for a source that has not
    been asked yet (its share was ``0`` on every page so far, plan §4.2 step 3) —
    still open, just without a marker of its own to continue from.
    """
    payload = {
        "v": MIXED_TOKEN_VERSION,
        "k": "mixed",
        "h": fingerprint,
        "s": dict(source_markers),
        "f": dict(failed),
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(encoded.encode("utf-8")).decode("ascii").rstrip("=")


def decode_mixed_token(
    token: str,
    fingerprint: str,
    known_source_keys: Collection[str],
    known_collection_ids: Collection[str],
) -> tuple[dict[str, str | None], dict[str, str]]:
    """Read back a marker this module minted — ``(source_markers, failed)`` — or
    refuse it in our own words (adr/0005 rule III, same posture as
    ``adapters.federated_search.decode_page_token``).
    """
    padded = token + "=" * (-len(token) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, binascii.Error) as error:
        raise InvalidQuery("page token is not readable") from error
    if not isinstance(payload, dict) or payload.get("k") != "mixed":
        # Covers both a foreign shape and a single-collection adapter token
        # (`{"v", "d", "h", "m"}`, no `"k"`) handed to a mixed search.
        raise InvalidQuery("page token is not a mixed-search token")
    if payload.get("v") != MIXED_TOKEN_VERSION:
        raise InvalidQuery("page token has a shape this version does not read")
    if payload.get("h") != fingerprint:
        raise InvalidQuery("page token belongs to a different search")
    source_markers = payload.get("s")
    failed = payload.get("f")
    if not isinstance(source_markers, dict) or not isinstance(failed, dict):
        raise InvalidQuery("page token carries no source map")
    if not all(isinstance(key, str) and (value is None or isinstance(value, str)) for key, value in source_markers.items()):
        raise InvalidQuery("page token source map is malformed")
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in failed.items()):
        raise InvalidQuery("page token failure map is malformed")
    if not source_markers and not failed:
        raise InvalidQuery("page token carries no source to continue")
    unknown_sources = set(source_markers) - set(known_source_keys)
    if unknown_sources:
        raise InvalidQuery("page token names a source that does not belong to this search")
    unknown_collections = set(failed) - set(known_collection_ids)
    if unknown_collections:
        raise InvalidQuery("page token names a collection that does not belong to this search")
    return source_markers, failed


__all__ = [
    "MIXED_TOKEN_VERSION",
    "REASON_TIMEOUT",
    "REASON_UNRECOGNISED_ANSWER",
    "REASON_UNREACHABLE",
    "REASON_UPSTREAM_ERROR",
    "SOURCE_TIMEOUT_S",
    "IncompleteSource",
    "compute_shares",
    "decode_mixed_token",
    "encode_mixed_token",
    "is_mixed_token",
    "mixed_fingerprint",
]
