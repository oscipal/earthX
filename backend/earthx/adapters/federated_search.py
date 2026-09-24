"""What every federated source shares: input checks, our own page marker, caching.

Split out of ``earth_search.py`` for M2-09b's second adapter (plan §4.2): the four
rules of adr/0005 that motivate this split apply to *any* source with a search API,
not only Earth Search, and re-deriving them per adapter would let the two drift
apart at exactly the place adr/0005 rule III cares about — the shape of our own
page marker.

What lives here, and why it does not vary by source:

* **Rule I** groundwork — :class:`UnknownCollection` and :class:`UnsupportedSource`
  are the vocabulary every adapter's ``resolve_dataset`` raises; the lookup itself
  stays with the adapter, because it is the one place that knows its own
  :class:`~earthx.catalog.registry.AdapterKind`.
* **Rule III** — the page marker we hand out is ours, one shape (:data:`TOKEN_VERSION`)
  regardless of which source it points into. Splitting the token format per source
  would mean a client's marker only works against the source it was minted for,
  which is not how a page token is supposed to behave.
* **Rule V** — :data:`DEFAULT_LIMIT`/:data:`MAX_LIMIT` are a platform limit, not a
  source one; :class:`SearchParams` enforces it before any adapter is asked.

What does **not** live here, because it genuinely differs per source (plan §4.2):
building the search request body, reading the upstream ``next``/``token`` link, and
any normalisation a source's answer needs before it looks like ours. Those stay in
each adapter's own ``search_items``/``get_item``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from shapely.errors import ShapelyError
from shapely.geometry import shape as shapely_shape

from earthx.adapters.cache import CacheValue, SearchCache
from earthx.catalog.registry import DatasetConfig

LOGGER = logging.getLogger("earthx.adapters.federated_search")

# adr/0005 rule V, Otto's answer F3 (M1-06): a page holds at most 100 items, ten by
# default. A platform limit, so every adapter enforces the same one.
DEFAULT_LIMIT = 10
MAX_LIMIT = 100

# adr/0005 rule II with Otto's precision from F1 (M1-06): a time window counts as
# closed only once its end is more than seven days back, because scenes are still
# delivered late into the days right behind the edge. M2-09b carries the same two
# lifetimes over to the second source (ENTSCHEIDUNGSLOG 2026-09-20, adr/0004 §5) —
# nothing measured for EOPF suggests a different edge.
CLOSED_WINDOW = timedelta(days=7)
TTL_CLOSED_S = 24 * 60 * 60
TTL_OPEN_EDGE_S = 5 * 60
TTL_ITEM_S = 24 * 60 * 60

# The shape of our own page marker. Versioned so a marker minted by an older release,
# or by a version that changed SORTBY, is refused rather than misread — one counter
# for every adapter, because the marker's shape does not depend on which source it
# was minted against.
TOKEN_VERSION = 1

# M1-06 sent no ``sortby`` and rode on Earth Search's undocumented default order
# (adr/0005 §8 point 5); M1-07 fixed one instead (docs/plans/m1-07-stac-api.md §7).
# ``datetime`` alone is not a unique key — tiles of one swath can share it — so
# ``id`` breaks the tie. Measured to work identically against the EOPF STAC API in
# the M2-09b plan step (plan §3): same field names, same accepted shape. This is a
# constant, not a caller choice (the STAC API's ``sort`` extension stays off,
# docs/plans/m1-07-stac-api.md §6), so it is not part of the search fingerprint.
# Changing it later would silently reinterpret a page marker minted under the old
# order — bump ``TOKEN_VERSION`` alongside any change here.
SORTBY: tuple[dict[str, str], ...] = (
    {"field": "properties.datetime", "direction": "desc"},
    {"field": "id", "direction": "asc"},
)

# An item id goes into a URL path. Rather than escaping it — `urllib` is off limits
# outside `gateway`, and escaping hides odd input instead of naming it — the ids we
# accept are restricted to what a STAC id normally is. That rules out `../` along
# with everything else that would leave the path segment.
# ``\Z``, not ``$``: ``$`` also matches in front of a trailing newline, so "id\n"
# would pass and then appear both in a URL path and as a second cache key.
ITEM_ID = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,254}\Z")

# M3-08 F1a: neither source caps the vertex count of `intersects` (measured up to
# 20 000 points / 454 kB going through both without a word, plan §2.1). Above this,
# a caller is rejected and falls back to the bounding box on its own side (F2a) —
# reducing it for them here would make a STAC answer look complete when it is not
# (the same "silently something else" adr/0004 §3.4's simplification avoids by
# flagging `truncated`, which a plain item search answer has no field for).
MAX_INTERSECTS_POINTS = 1000

# M3-08 F3a: equal to MAX_LIMIT, so every requested id fits on a single page and a
# caller never has to wonder which of more ids than that got dropped.
MAX_IDS = MAX_LIMIT

# A closed ring needs at least this many positions (three distinct corners plus the
# repeated first/last one) to be an outline at all.
MIN_RING_POINTS = 4

_GEOMETRY_TYPES = frozenset(
    {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "GeometryCollection"}
)
_POLYGONAL_TYPES = frozenset({"Polygon", "MultiPolygon"})


class InvalidQuery(ValueError):
    """The request breaks one of our own rules, before anything is sent upstream."""


class UnknownCollection(LookupError):
    """No such collection in our catalogue (adr/0005 rule I) — the caller's 404."""


class UnsupportedSource(LookupError):
    """The collection exists, but another adapter serves it. A dispatch mistake."""


class UnsupportedFilter(LookupError):
    """The collection's own source cannot honour `intersects` or `ids` (M3-08 F4a).

    A dispatch fact, not a caller mistake — the parameter itself is valid, this
    particular source just cannot filter by it (yet). Kept apart from
    :class:`InvalidQuery` so the two map to different, honest `400` texts.
    """


class UpstreamShapeError(RuntimeError):
    """The source answered something that is not a STAC item collection."""


@dataclass(frozen=True, slots=True)
class SearchParams:
    """One page of a search, as the platform accepts it — the same shape for every
    federated source (adr/0005 rule V and the bbox/time checks of M1-06).

    Checks run in ``__post_init__`` so that no caller can hold a set of parameters
    that was never checked.
    """

    bbox: tuple[float, float, float, float] | None = None
    intersects: Mapping[str, Any] | None = None
    ids: tuple[str, ...] | None = None
    start: datetime | None = None
    end: datetime | None = None
    limit: int = DEFAULT_LIMIT
    page_token: str | None = None

    def __post_init__(self) -> None:
        self._check_limit()
        self._check_bbox()
        self._check_intersects()
        self._check_ids()
        self._check_time()

    def _check_limit(self) -> None:
        if self.limit < 1 or self.limit > MAX_LIMIT:
            raise InvalidQuery(
                f"limit {self.limit} is outside 1..{MAX_LIMIT} (adr/0005 rule V — upstream does not cap it)"
            )

    def _check_bbox(self) -> None:
        if self.bbox is None:
            return
        if self.intersects is not None:
            raise InvalidQuery("bbox and intersects ask two different questions; send one")
        if len(self.bbox) != 4:
            raise InvalidQuery("bbox needs four values: west, south, east, north")
        west, south, east, north = self.bbox
        # None of these messages names a coordinate: an exception text becomes a log
        # line and an error body, and the AOI belongs in neither (projektplan.md 7,
        # point 6). They name the rule that was broken, which is what a caller needs.
        if not all(-90.0 <= value <= 90.0 for value in (south, north)):
            # Upstream takes this without a word (adr/0005 §3.5), which is why we do not.
            raise InvalidQuery("bbox latitudes are outside ±90")
        if not all(-180.0 <= value <= 180.0 for value in (west, east)):
            raise InvalidQuery("bbox longitudes are outside ±180")
        if south >= north:
            raise InvalidQuery("bbox is upside down: south is not below north")
        # west > east is deliberately allowed: that is how GeoJSON and STAC write a box
        # that crosses the antimeridian, and both sources read it that way too. Only
        # the latitudes have an order that can be wrong.

    def _check_intersects(self) -> None:
        """M3-08 F6a: every GeoJSON geometry type `item-search`'s own conformance
        class promises (K8), checked on our side rather than left to the source —
        both sources take a latitude of 999 or a self-intersecting ring without a
        word, or otherwise answer with their own internals in the error text
        (adr/0005 rule III; M3-08 plan §2.2)."""
        if self.intersects is None:
            return
        points = _check_geometry(self.intersects)
        if points > MAX_INTERSECTS_POINTS:
            raise InvalidQuery(
                f"intersects has more than {MAX_INTERSECTS_POINTS} positions "
                "(M3-08 F1a — search its bounding box instead)"
            )

    def _check_ids(self) -> None:
        if self.ids is None:
            return
        if not self.ids:
            raise InvalidQuery("ids is empty; omit it instead of asking for nothing")
        if len(self.ids) > MAX_IDS:
            raise InvalidQuery(f"ids has more than {MAX_IDS} entries (M3-08 F3a)")
        if not all(ITEM_ID.match(item_id) for item_id in self.ids):
            raise InvalidQuery("ids contains a value that is not a scene id we would put into a URL path")

    def _check_time(self) -> None:
        for name, value in (("start", self.start), ("end", self.end)):
            if value is not None and value.tzinfo is None:
                raise InvalidQuery(f"{name} has no timezone; STAC instants carry one")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise InvalidQuery("time window ends before it starts")


def _check_geometry(geometry: Any, *, _nested: bool = False) -> int:
    """Enough of a GeoJSON check that nothing shapeless, out of bounds, or invalid
    reaches a source — returns the number of positions found, so the caller can
    enforce the point budget (F1a) without a second walk.

    Not a full GeoJSON validator, same posture as `catalog.coverage`'s own check for
    the coverage AOI: this refuses what would otherwise be serialised into a request
    body without anyone having looked at it. No message here names a coordinate
    (projektplan.md 7, point 6).
    """
    if not isinstance(geometry, Mapping):
        raise InvalidQuery("intersects is not a GeoJSON object")
    kind = geometry.get("type")
    if kind == "GeometryCollection":
        if _nested:
            raise InvalidQuery("intersects must not nest a GeometryCollection inside another")
        members = geometry.get("geometries")
        if not isinstance(members, list) or not members:
            raise InvalidQuery("intersects carries no geometries")
        return sum(_check_geometry(member, _nested=True) for member in members)
    if kind not in _GEOMETRY_TYPES:
        raise InvalidQuery("intersects is not a GeoJSON geometry type we recognise")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise InvalidQuery("intersects carries no coordinates")
    if kind in _POLYGONAL_TYPES:
        for ring in _rings_of(kind, coordinates):
            if len(ring) < MIN_RING_POINTS or ring[0] != ring[-1]:
                raise InvalidQuery("intersects has a ring that is not closed or has too few positions")
    points = _check_positions(coordinates)
    if kind in _POLYGONAL_TYPES:
        # Cheapest check first: a polygon far over the point budget is rejected
        # before shapely is asked to validate it, not after.
        if points > MAX_INTERSECTS_POINTS:
            raise InvalidQuery(
                f"intersects has more than {MAX_INTERSECTS_POINTS} positions "
                "(M3-08 F1a — search its bounding box instead)"
            )
        _check_polygon_validity(geometry)
    return points


def _rings_of(kind: str, coordinates: list[Any]) -> list[list[Any]]:
    if kind == "Polygon":
        return [ring for ring in coordinates if isinstance(ring, list)]
    return [ring for polygon in coordinates if isinstance(polygon, list) for ring in polygon if isinstance(ring, list)]


def _check_positions(coordinates: Any) -> int:
    """Walks a (possibly nested) coordinates array; returns the number of positions.

    A position is the first list this recursion meets whose own entries are numbers
    rather than further lists — that works for every GeoJSON geometry type, since
    they differ only in how many list layers wrap the positions.
    """
    if isinstance(coordinates, list) and coordinates and all(_is_number(value) for value in coordinates):
        if len(coordinates) < 2:
            raise InvalidQuery("intersects has a position with fewer than two numbers")
        longitude, latitude = coordinates[0], coordinates[1]
        if not -180.0 <= float(longitude) <= 180.0:
            raise InvalidQuery("intersects longitude is outside ±180")
        if not -90.0 <= float(latitude) <= 90.0:
            raise InvalidQuery("intersects latitude is outside ±90")
        return 1
    if not isinstance(coordinates, list) or not coordinates:
        raise InvalidQuery("intersects carries no coordinates")
    return sum(_check_positions(item) for item in coordinates)


def _is_number(value: Any) -> bool:
    """A coordinate, and not a bool — ``True`` is an ``int`` and would pass otherwise,
    and not NaN/±inf, which JSON cannot spell but a caller inside this process can
    still hand us as a Python float."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _check_polygon_validity(geometry: Mapping[str, Any]) -> None:
    """Refuses a polygon whose rings self-intersect or otherwise fail the OGC
    simple-feature rules — both sources take one without complaint and answer a
    plausible-looking, silently wrong result (M3-08 plan §2.2: a self-intersecting
    "bowtie" polygon against Earth Search returned 229 matches, none of them
    checked against the shape actually asked for)."""
    try:
        shape = shapely_shape(geometry)
    except (ShapelyError, ValueError, TypeError, KeyError, AttributeError):
        raise InvalidQuery("intersects is not a usable GeoJSON geometry") from None
    if not shape.is_valid:
        raise InvalidQuery("intersects is not a valid polygon (rings must not self-intersect)")


@dataclass(frozen=True, slots=True)
class ItemPage:
    """One page of items, the same shape whether it came from the source or the cache,
    and whichever adapter answered it."""

    items: tuple[dict[str, Any], ...]
    matched: int | None
    next_page_token: str | None
    from_cache: bool


def _stac_instant(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def stac_interval(start: datetime | None, end: datetime | None) -> str | None:
    """The time window as STAC writes it, with ``..`` for an open end.

    Takes the two instants rather than a ``SearchParams``, because the coverage
    aggregation of M2-05 asks the same question of a query object of its own
    (``earthx/adapters/earth_search_coverage.py``).
    """
    if start is None and end is None:
        return None
    low = ".." if start is None else _stac_instant(start)
    high = ".." if end is None else _stac_instant(end)
    return f"{low}/{high}"


def search_fingerprint(dataset_id: str, params: SearchParams) -> str:
    """A hash of the search itself — without the page marker, which points into it.

    Numbers go in as floats and instants as their UTC text, so that ``47`` and ``47.0``,
    or the same moment written in two offsets, are one search and not two.

    ``intersects``/``ids`` are added to the payload only when set (M3-08): a search
    that uses neither hashes exactly as it did before this field existed, so every
    page token and search-cache row minted before M3-08 still reads back correctly.
    """
    payload: dict[str, Any] = {
        "dataset": dataset_id,
        "bbox": None if params.bbox is None else [float(value) for value in params.bbox],
        "datetime": stac_interval(params.start, params.end),
        "limit": params.limit,
    }
    if params.intersects is not None:
        # Serialised to its own normalised JSON text first (sorted keys, no
        # whitespace) rather than embedded as a nested object: two geometries that
        # differ only in key order or float spelling become one fingerprint.
        payload["intersects"] = json.dumps(params.intersects, separators=(",", ":"), sort_keys=True)
    if params.ids is not None:
        # Sorted and de-duplicated: the same set of ids asked for in a different
        # order, or with a repeated id, is one search.
        payload["ids"] = sorted(set(params.ids))
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def search_cache_key(fingerprint: str, marker: str | None) -> str:
    """The search plus the page it is on.

    Keyed on the decoded marker rather than on the token text: the same page, asked
    for with a token that lost or regained its base64 padding, is one entry.
    """
    return hashlib.sha256(f"search:{fingerprint}:{marker or ''}".encode()).hexdigest()


def item_cache_key(dataset_id: str, item_id: str) -> str:
    return hashlib.sha256(f"item:{dataset_id}:{item_id}".encode()).hexdigest()


def ttl_for_window(end: datetime | None, now: datetime | None = None) -> float:
    """adr/0005 rule II: only a window whose end is well behind us has stopped moving."""
    now = now or datetime.now(timezone.utc)
    if end is None:
        return TTL_OPEN_EDGE_S
    return TTL_CLOSED_S if end < now - CLOSED_WINDOW else TTL_OPEN_EDGE_S


def encode_page_token(dataset_id: str, fingerprint: str, marker: str) -> str:
    payload = json.dumps(
        {"v": TOKEN_VERSION, "d": dataset_id, "h": fingerprint, "m": marker},
        separators=(",", ":"),
        sort_keys=True,
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_page_token(token: str, dataset_id: str, fingerprint: str) -> str:
    """Read back a marker we minted, or refuse it in our own words.

    Refusing in our own words is the point of rule III: a broken upstream marker
    would otherwise be answered with the source's own internals in the error text,
    and that must not become our error text.
    """
    padded = token + "=" * (-len(token) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, binascii.Error) as error:
        raise InvalidQuery("page token is not readable") from error
    if not isinstance(payload, dict) or payload.get("v") != TOKEN_VERSION:
        raise InvalidQuery("page token has a shape this version does not read")
    if payload.get("d") != dataset_id or payload.get("h") != fingerprint:
        raise InvalidQuery("page token belongs to a different search")
    marker = payload.get("m")
    if not isinstance(marker, str):
        raise InvalidQuery("page token carries no marker")
    return marker


def require_feature_list(payload: Any) -> list[Any]:
    """The ``features`` array of a search answer, or the reason it is not one.

    Shared because the shape check is identical for every source; reading the next
    link is not (it names a different field per source), so it stays with the
    adapter that calls this.
    """
    if not isinstance(payload, dict):
        raise UpstreamShapeError("search answer is not a JSON object")
    features = payload.get("features")
    if not isinstance(features, list):
        raise UpstreamShapeError("search answer carries no feature list")
    return features


def matched_count(payload: dict[str, Any]) -> int | None:
    """``numberMatched`` (OGC) or ``context.matched`` (the older STAC extension).

    ``None`` either where neither is present (both sources) or where the value is
    not an int — the caller decides what an absent count means, this only reads it.
    """
    value = payload.get("numberMatched")
    if value is None:
        context = payload.get("context")
        value = context.get("matched") if isinstance(context, dict) else None
    return value if isinstance(value, int) else None


def endpoint_of(config: DatasetConfig) -> str:
    """A dataset's endpoint, without a trailing slash to build a URL on. Identical
    for every source, so it lives here rather than once per adapter."""
    return config.source.endpoint.rstrip("/")


def page_from_stored(dataset_id: str, fingerprint: str, stored: CacheValue, *, from_cache: bool) -> ItemPage:
    """An :class:`ItemPage` from what an adapter decided to keep of an answer.

    ``stored`` already carries the adapter's own reading of the next marker under
    ``"marker"`` — this only turns that into our own page token, the same way for
    every source.
    """
    marker = stored.get("marker")
    return ItemPage(
        items=tuple(stored["features"]),
        matched=stored.get("matched"),
        next_page_token=None if marker is None else encode_page_token(dataset_id, fingerprint, marker),
        from_cache=from_cache,
    )


async def cache_get(cache: SearchCache | None, key: str) -> CacheValue | None:
    """A cached value, or None. Callers check its shape: a row written by an older
    release, or damaged, counts as a miss rather than as an answer (E5)."""
    if cache is None:
        return None
    try:
        return await cache.get(key)
    except Exception:
        # E5 and adr/0001 §9.3: a cache that fails makes the platform slower, never
        # wrong. Broad on purpose — whatever the store does, the answer is fetched.
        LOGGER.warning("search cache unreadable, asking the source instead", exc_info=True)
        return None


async def cache_set(
    cache: SearchCache | None, key: str, value: CacheValue, *, ttl_s: float, dataset_id: str
) -> None:
    if cache is None:
        return
    try:
        await cache.set(key, value, ttl_s=ttl_s, dataset_id=dataset_id)
    except Exception:
        # Same rule as reading, and it matters more here: the answer is already in
        # hand, so failing now would throw away a good response over bookkeeping.
        LOGGER.warning("search cache not writable, answer is not stored", exc_info=True)
