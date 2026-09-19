"""Item search and access resolution for Earth Search v1 (adr/0005).

The source holds the items; we hold the collection. This module is the translation
between the two: it builds the upstream request, reads the upstream answer, and hands
back STAC items plus a page marker of our own. Everything it sends goes through
``gateway`` (KLAERUNGEN B8) — there is no HTTP client here and no ``pystac_client``
(adr/0005 rule IV).

Four rules of adr/0005 are implemented here, and they are the reason this module
exists rather than a few lines inside the API route:

* **Rule I** — the collection is looked up in our own catalogue *first*. Earth Search
  answers an unknown collection with ``200`` and an empty result (§3.5), which would
  turn "there is no such dataset" into "there is nothing in it".
* **Rule II** — two cache lifetimes, decided by whether the time window still touches
  the moving edge of the archive.
* **Rule III** — the page marker we hand out is our own. The upstream marker (and the
  Elasticsearch error text that comes with a broken one) never leaves this module.
* **Rule V** — ``limit`` is capped here, because upstream does not cap it at all
  (§3.2): a single request could otherwise pull hundreds of megabytes.

Input checks are ours too, not the source's: a bbox outside ±90 is *silently accepted*
upstream (§3.5), which is the worst of the three possible answers.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from earthx.adapters.cache import CacheValue, SearchCache
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import AdapterKind, DatasetConfig, DatasetRegistry, UnknownDatasetError
from earthx.gateway import Gateway

LOGGER = logging.getLogger("earthx.adapters.earth_search")

# adr/0005 rule V, Otto's answer F3: a page holds at most 100 items, ten by default.
DEFAULT_LIMIT = 10
MAX_LIMIT = 100

# adr/0005 rule II with Otto's precision from F1: a time window counts as closed only
# once its end is more than seven days back, because scenes are still delivered late
# into the days right behind the edge.
CLOSED_WINDOW = timedelta(days=7)
TTL_CLOSED_S = 24 * 60 * 60
TTL_OPEN_EDGE_S = 5 * 60
TTL_ITEM_S = 24 * 60 * 60

# The shape of our own page marker. It is versioned so a marker minted by an older
# release is refused rather than misread.
TOKEN_VERSION = 1

# An item id goes into a URL path. Rather than escaping it — `urllib` is off limits
# outside `gateway`, and escaping hides odd input instead of naming it — the ids we
# accept are restricted to what a STAC id normally is. That rules out `../` along
# with everything else that would leave the path segment.
_ITEM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")


class InvalidQuery(ValueError):
    """The request breaks one of our own rules, before anything is sent upstream."""


class UnknownCollection(LookupError):
    """No such collection in our catalogue (adr/0005 rule I) — the caller's 404."""


class UnsupportedSource(LookupError):
    """The collection exists, but another adapter serves it. A dispatch mistake."""


class UpstreamShapeError(RuntimeError):
    """The source answered something that is not a STAC item collection."""


@dataclass(frozen=True, slots=True)
class SearchParams:
    """One page of a search, as the platform accepts it.

    Checks run in ``__post_init__`` so that no caller can hold a set of parameters
    that was never checked — the acceptance cases of M1-06 are all right here.
    """

    bbox: tuple[float, float, float, float] | None = None
    start: datetime | None = None
    end: datetime | None = None
    limit: int = DEFAULT_LIMIT
    page_token: str | None = None

    def __post_init__(self) -> None:
        self._check_limit()
        self._check_bbox()
        self._check_time()

    def _check_limit(self) -> None:
        if self.limit < 1 or self.limit > MAX_LIMIT:
            raise InvalidQuery(
                f"limit {self.limit} is outside 1..{MAX_LIMIT} (adr/0005 rule V — upstream does not cap it)"
            )

    def _check_bbox(self) -> None:
        if self.bbox is None:
            return
        if len(self.bbox) != 4:
            raise InvalidQuery("bbox needs four values: west, south, east, north")
        west, south, east, north = self.bbox
        if not all(-90.0 <= value <= 90.0 for value in (south, north)):
            # Upstream takes this without a word (adr/0005 §3.5), which is why we do not.
            raise InvalidQuery(f"bbox latitudes are outside ±90: {south}, {north}")
        if not all(-180.0 <= value <= 180.0 for value in (west, east)):
            raise InvalidQuery(f"bbox longitudes are outside ±180: {west}, {east}")
        if south >= north:
            raise InvalidQuery(f"bbox is upside down: south {south} is not below north {north}")
        # west > east is deliberately allowed: that is how GeoJSON and STAC write a box
        # that crosses the antimeridian, and Earth Search reads it that way too. Only
        # the latitudes have an order that can be wrong.

    def _check_time(self) -> None:
        for name, value in (("start", self.start), ("end", self.end)):
            if value is not None and value.tzinfo is None:
                raise InvalidQuery(f"{name} has no timezone; STAC instants carry one")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise InvalidQuery("time window ends before it starts")


@dataclass(frozen=True, slots=True)
class ItemPage:
    """One page of items, the same shape whether it came from the source or the cache."""

    items: tuple[dict[str, Any], ...]
    matched: int | None
    next_page_token: str | None
    from_cache: bool


async def search_items(
    dataset_id: str,
    params: SearchParams | None = None,
    *,
    gateway: Gateway,
    registry: DatasetRegistry = REGISTRY,
    cache: SearchCache | None = None,
) -> ItemPage:
    """Search items of one federated collection.

    ``cache=None`` is a valid call: without a cache this is slower, never wrong (E5).
    """
    params = params or SearchParams()
    config = _resolve(dataset_id, registry)
    fingerprint = _search_fingerprint(dataset_id, params)
    marker = None if params.page_token is None else _decode_page_token(params.page_token, dataset_id, fingerprint)

    key = _search_cache_key(fingerprint, params.page_token)
    cached = await _cache_get(cache, key)
    if cached is not None:
        return _page(dataset_id, fingerprint, cached, from_cache=True)

    response = await gateway.post_json(
        f"{_endpoint(config)}/search",
        json=_search_body(config, params, marker),
        # A search is a read; repeating it after a 503 is safe. The gateway leaves that
        # judgement to the caller, because only the caller knows what the POST means.
        retry=True,
    )
    stored = _storable(response.json())
    await _cache_set(cache, key, stored, ttl_s=_search_ttl(params), dataset_id=dataset_id)
    return _page(dataset_id, fingerprint, stored, from_cache=False)


async def get_item(
    dataset_id: str,
    item_id: str,
    *,
    gateway: Gateway,
    registry: DatasetRegistry = REGISTRY,
    cache: SearchCache | None = None,
) -> dict[str, Any]:
    """One item by id, without a search in front of it (adr/0001 Z1).

    A missing item stays the source's ``404``: the gateway carries the status code
    through unchanged, which is exactly what ``pystac_client`` would have lost.
    """
    config = _resolve(dataset_id, registry)
    if not _ITEM_ID.match(item_id):
        raise InvalidQuery("item id contains characters we do not put into a URL path")

    key = _item_cache_key(dataset_id, item_id)
    cached = await _cache_get(cache, key)
    if cached is not None:
        return cached["item"]

    url = f"{_endpoint(config)}/collections/{config.source.source_collection_id}/items/{item_id}"
    item = (await gateway.get(url)).json()
    await _cache_set(cache, key, {"item": item}, ttl_s=TTL_ITEM_S, dataset_id=dataset_id)
    return item


def _resolve(dataset_id: str, registry: DatasetRegistry) -> DatasetConfig:
    """Our own catalogue decides whether a collection exists (adr/0005 rule I)."""
    try:
        config = registry.get(dataset_id)
    except UnknownDatasetError:
        raise UnknownCollection(dataset_id) from None
    if config.source.adapter is not AdapterKind.EARTH_SEARCH_V1:
        raise UnsupportedSource(f"{dataset_id} is served by {config.source.adapter}, not Earth Search v1")
    return config


def _endpoint(config: DatasetConfig) -> str:
    return config.source.endpoint.rstrip("/")


def _stac_instant(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _datetime_query(params: SearchParams) -> str | None:
    """The time window as STAC writes it, with ``..`` for an open end."""
    if params.start is None and params.end is None:
        return None
    start = ".." if params.start is None else _stac_instant(params.start)
    end = ".." if params.end is None else _stac_instant(params.end)
    return f"{start}/{end}"


def _search_fingerprint(dataset_id: str, params: SearchParams) -> str:
    """A hash of the search itself — without the page marker, which points into it.

    Numbers go in as floats and instants as their UTC text, so that ``47`` and ``47.0``,
    or the same moment written in two offsets, are one search and not two.
    """
    payload = json.dumps(
        {
            "dataset": dataset_id,
            "bbox": None if params.bbox is None else [float(value) for value in params.bbox],
            "datetime": _datetime_query(params),
            "limit": params.limit,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _search_cache_key(fingerprint: str, page_token: str | None) -> str:
    return hashlib.sha256(f"search:{fingerprint}:{page_token or ''}".encode()).hexdigest()


def _item_cache_key(dataset_id: str, item_id: str) -> str:
    return hashlib.sha256(f"item:{dataset_id}:{item_id}".encode()).hexdigest()


def _search_ttl(params: SearchParams, now: datetime | None = None) -> float:
    """adr/0005 rule II: only a window whose end is well behind us has stopped moving."""
    now = now or datetime.now(timezone.utc)
    if params.end is None:
        return TTL_OPEN_EDGE_S
    return TTL_CLOSED_S if params.end < now - CLOSED_WINDOW else TTL_OPEN_EDGE_S


def _search_body(config: DatasetConfig, params: SearchParams, marker: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "collections": [config.source.source_collection_id],
        "limit": params.limit,
    }
    if params.bbox is not None:
        body["bbox"] = [float(value) for value in params.bbox]
    window = _datetime_query(params)
    if window is not None:
        body["datetime"] = window
    if marker is not None:
        # Keyset paging: the marker is the sort key of the last item of the page
        # before, so the same search body plus this field is the next page (§3.3).
        body["next"] = marker
    return body


def _encode_page_token(dataset_id: str, fingerprint: str, marker: str) -> str:
    payload = json.dumps(
        {"v": TOKEN_VERSION, "d": dataset_id, "h": fingerprint, "m": marker},
        separators=(",", ":"),
        sort_keys=True,
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_page_token(token: str, dataset_id: str, fingerprint: str) -> str:
    """Read back a marker we minted, or refuse it in our own words.

    Refusing in our own words is the point of rule III: a broken upstream marker is
    answered with an Elasticsearch internals message (§3.3), and that must not become
    our error text.
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


def _storable(payload: Any) -> CacheValue:
    """What we keep of an upstream answer: the items, the count, the marker.

    Reduced here rather than at the cache, so that a cache hit and a live answer go
    through exactly the same translation afterwards.
    """
    if not isinstance(payload, dict):
        raise UpstreamShapeError("search answer is not a JSON object")
    features = payload.get("features")
    if not isinstance(features, list):
        raise UpstreamShapeError("search answer carries no feature list")
    return {"features": features, "matched": _matched(payload), "marker": _next_marker(payload)}


def _matched(payload: dict[str, Any]) -> int | None:
    """``numberMatched`` (OGC) or ``context.matched`` (the older STAC extension)."""
    value = payload.get("numberMatched")
    if value is None:
        context = payload.get("context")
        value = context.get("matched") if isinstance(context, dict) else None
    return value if isinstance(value, int) else None


def _next_marker(payload: dict[str, Any]) -> str | None:
    """The upstream page marker out of the ``next`` link, which is a POST link."""
    for link in payload.get("links") or []:
        if not isinstance(link, dict) or link.get("rel") != "next":
            continue
        body = link.get("body")
        if isinstance(body, dict) and isinstance(body.get("next"), str):
            return body["next"]
        LOGGER.warning("upstream next link carries no marker we can follow; paging stops here")
    return None


def _page(dataset_id: str, fingerprint: str, stored: CacheValue, *, from_cache: bool) -> ItemPage:
    marker = stored.get("marker")
    return ItemPage(
        items=tuple(stored["features"]),
        matched=stored.get("matched"),
        next_page_token=None if marker is None else _encode_page_token(dataset_id, fingerprint, marker),
        from_cache=from_cache,
    )


async def _cache_get(cache: SearchCache | None, key: str) -> CacheValue | None:
    if cache is None:
        return None
    try:
        return await cache.get(key)
    except Exception:
        # E5 and adr/0001 §9.3: a cache that fails makes the platform slower, never
        # wrong. Broad on purpose — whatever the store does, the answer is fetched.
        LOGGER.warning("search cache unreadable, asking the source instead", exc_info=True)
        return None


async def _cache_set(
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
