"""Item search and access resolution for Earth Search v1 (adr/0005).

The source holds the items; we hold the collection. This module is the translation
between the two: it builds the upstream request, reads the upstream answer, and hands
back STAC items plus a page marker of our own. Everything it sends goes through
``gateway`` (KLAERUNGEN B8) — there is no HTTP client here and no ``pystac_client``
(adr/0005 rule IV).

What is specific to Earth Search lives here; what is not is
``earthx.adapters.federated_search`` (split out for M2-09b's second source, plan
§4.2), starting with the shape of our own page marker (rule III) and the input
checks of ``SearchParams`` (rule V). What stays here:

* **Rule I** — ``resolve_dataset`` looks the collection up in our own catalogue
  *first*. Earth Search answers an unknown collection with ``200`` and an empty
  result (§3.5), which would turn "there is no such dataset" into "there is
  nothing in it".
* **Rule III, continued** — reading the ``next`` link out of Earth Search's own
  answer shape (``_next_marker``) and building the search body it expects
  (``_search_body``) — both source-specific, per M1-07 (docs/plans/
  m1-07-stac-api.md §7).

Input checks that are not source-specific (bbox, limit, the time window) already
ran inside ``SearchParams.__post_init__`` before anything reaches this module. A
bbox outside ±90 is *silently accepted* upstream (§3.5), which is the worst of the
three possible answers — checking it ourselves is why ``SearchParams`` exists at all.
"""

from __future__ import annotations

import logging
from typing import Any

from earthx.adapters.cache import CacheValue, SearchCache
from earthx.adapters.federated_search import (
    ITEM_ID,
    SORTBY,
    TTL_ITEM_S,
    InvalidQuery,
    ItemPage,
    SearchParams,
    UnknownCollection,
    UnsupportedSource,
    UpstreamShapeError,
    cache_get,
    cache_set,
    decode_page_token,
    endpoint_of,
    item_cache_key,
    matched_count,
    page_from_stored,
    require_feature_list,
    search_cache_key,
    search_fingerprint,
    stac_interval,
    ttl_for_window,
)
from earthx.catalog.datasets import REGISTRY
from earthx.catalog.registry import AdapterKind, DatasetConfig, DatasetRegistry, UnknownDatasetError
from earthx.gateway import Gateway

LOGGER = logging.getLogger("earthx.adapters.earth_search")

# M3-08 F4a: what this source can filter by, measured against the live API in the
# plan step (M3-08 plan §2.1) — `adapters._check_capabilities` reads these before a
# search reaches this module, so an unsupported filter is refused by name instead
# of reaching here and being silently dropped from the request body.
SUPPORTS_INTERSECTS = True
SUPPORTS_IDS = True


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
    config = resolve_dataset(dataset_id, registry)
    fingerprint = search_fingerprint(dataset_id, params)
    marker = None if params.page_token is None else decode_page_token(params.page_token, dataset_id, fingerprint)

    key = search_cache_key(fingerprint, marker)
    cached = await cache_get(cache, key)
    if cached is not None and isinstance(cached.get("features"), list):
        return page_from_stored(dataset_id, fingerprint, cached, from_cache=True)

    response = await gateway.post_json(
        f"{endpoint_of(config)}/search",
        json=_search_body(config, params, marker),
        # A search is a read; repeating it after a 503 is safe. The gateway leaves that
        # judgement to the caller, because only the caller knows what the POST means.
        retry=True,
    )
    stored = _storable(response.json())
    await cache_set(cache, key, stored, ttl_s=ttl_for_window(params.end), dataset_id=dataset_id)
    return page_from_stored(dataset_id, fingerprint, stored, from_cache=False)


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
    config = resolve_dataset(dataset_id, registry)
    if not ITEM_ID.match(item_id):
        raise InvalidQuery("item id contains characters we do not put into a URL path")

    key = item_cache_key(dataset_id, item_id)
    cached = await cache_get(cache, key)
    if isinstance(cached, dict) and isinstance(cached.get("item"), dict):
        return cached["item"]

    url = f"{endpoint_of(config)}/collections/{config.source.source_collection_id}/items/{item_id}"
    item = (await gateway.get(url)).json()
    if not isinstance(item, dict):
        # Same reason as for a search answer: what is not an item must not become one
        # by being passed on, and must not be cached as one either.
        raise UpstreamShapeError("item answer is not a JSON object")
    await cache_set(cache, key, {"item": item}, ttl_s=TTL_ITEM_S, dataset_id=dataset_id)
    return item


def resolve_dataset(dataset_id: str, registry: DatasetRegistry) -> DatasetConfig:
    """Our own catalogue decides whether a collection exists (adr/0005 rule I)."""
    try:
        config = registry.get(dataset_id)
    except UnknownDatasetError:
        raise UnknownCollection(dataset_id) from None
    if config.source.adapter is not AdapterKind.EARTH_SEARCH_V1:
        raise UnsupportedSource(f"{dataset_id} is served by {config.source.adapter}, not Earth Search v1")
    return config


def _search_body(config: DatasetConfig, params: SearchParams, marker: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "collections": [config.source.source_collection_id],
        "limit": params.limit,
        "sortby": list(SORTBY),
    }
    if params.bbox is not None:
        body["bbox"] = [float(value) for value in params.bbox]
    if params.intersects is not None:
        body["intersects"] = params.intersects
    if params.ids is not None:
        # Measured (M3-08 plan §2.1): `ids` is AND-combined with a spatial or time
        # filter by this source, not a shortcut around them — a caller who narrows
        # both gets the intersection, not just the ids.
        body["ids"] = list(params.ids)
    window = stac_interval(params.start, params.end)
    if window is not None:
        body["datetime"] = window
    if marker is not None:
        # Keyset paging: the marker is the sort key of the last item of the page
        # before, so the same search body plus this field is the next page (§3.3).
        body["next"] = marker
    return body


def _storable(payload: Any) -> CacheValue:
    """What we keep of an upstream answer: the items, the count, the marker.

    Reduced here rather than at the cache, so that a cache hit and a live answer go
    through exactly the same translation afterwards.
    """
    features = require_feature_list(payload)
    return {"features": features, "matched": matched_count(payload), "marker": _next_marker(payload)}


def _next_marker(payload: dict[str, Any]) -> str | None:
    """The upstream page marker out of the ``next`` link, which is a POST link."""
    for link in payload.get("links") or []:
        if not isinstance(link, dict) or link.get("rel") != "next":
            continue
        body = link.get("body")
        if isinstance(body, dict) and isinstance(body.get("next"), str):
            return body["next"]
        # There are more items and we cannot reach them. Returning None here would
        # hand the caller a page that looks like the last one — the same silent
        # truncation adr/0005 rule I refuses for an unknown collection.
        raise UpstreamShapeError("the next link carries no marker we can follow")
    return None
