"""Item search, access resolution and STAC normalisation for the EOPF Sentinel Zarr
Samples Service (adr/0007 §6 point 4, §12.11 point 11; M2-09b plan §4.2).

The second adapter for adr/0005's rules, over a different source. What is specific
to it lives here; what is not is ``earthx.adapters.federated_search`` — the page
marker, ``SearchParams``, the caching, all of it identical to Earth Search's, since
adr/0005 rule III does not vary by source. Three things genuinely differ, measured
in adr/0007 §12 and rechecked in the M2-09b plan step (plan §3):

* **The search body's page marker field is ``token``, not ``next``** (measured:
  Earth Search's ``next`` link carries ``body.next``, this source's carries
  ``body.token`` — the field name, not the mechanism).
* **The answer carries no ``numberMatched`` at all**, ever — this dataset's
  coverage is a declared sample (adr/0007 §12.11 point 13, M2-09b-3), not a
  consequence of anything this module does; ``matched_count`` from
  ``federated_search`` already returns ``None`` for that shape without help.
* **Every item needs normalising before it looks like ours**: the source speaks
  STAC 1.1, our own API speaks 1.0 (``earthx.catalog.collection.STAC_VERSION``).
  :func:`normalize_item` does exactly the fields adr/0007 §6 point 4 named, and
  nothing else — what is not mapped stays as it stands rather than being dropped
  or guessed at.

Everything this module sends goes through ``gateway`` (KLAERUNGEN B8) — there is no
HTTP client here.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
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

LOGGER = logging.getLogger("earthx.adapters.eopf_stac")


async def search_items(
    dataset_id: str,
    params: SearchParams | None = None,
    *,
    gateway: Gateway,
    registry: DatasetRegistry = REGISTRY,
    cache: SearchCache | None = None,
) -> ItemPage:
    """Search items of one federated collection. ``cache=None`` is a valid call (E5)."""
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
        # A search is a read; repeating it after a 503 is safe, same as Earth Search.
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
    """One item by id, without a search in front of it (adr/0001 Z1), normalised
    to STAC 1.0 before it is cached or returned."""
    config = resolve_dataset(dataset_id, registry)
    if not ITEM_ID.match(item_id):
        raise InvalidQuery("item id contains characters we do not put into a URL path")

    key = item_cache_key(dataset_id, item_id)
    cached = await cache_get(cache, key)
    if isinstance(cached, dict) and isinstance(cached.get("item"), dict):
        return cached["item"]

    url = f"{endpoint_of(config)}/collections/{config.source.source_collection_id}/items/{item_id}"
    payload = (await gateway.get(url)).json()
    if not isinstance(payload, dict):
        raise UpstreamShapeError("item answer is not a JSON object")
    item = normalize_item(payload)
    await cache_set(cache, key, {"item": item}, ttl_s=TTL_ITEM_S, dataset_id=dataset_id)
    return item


def resolve_dataset(dataset_id: str, registry: DatasetRegistry) -> DatasetConfig:
    """Our own catalogue decides whether a collection exists (adr/0005 rule I)."""
    try:
        config = registry.get(dataset_id)
    except UnknownDatasetError:
        raise UnknownCollection(dataset_id) from None
    if config.source.adapter is not AdapterKind.EOPF_STAC_V1:
        raise UnsupportedSource(f"{dataset_id} is served by {config.source.adapter}, not the EOPF STAC API")
    return config


def _search_body(config: DatasetConfig, params: SearchParams, marker: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "collections": [config.source.source_collection_id],
        "limit": params.limit,
        "sortby": list(SORTBY),
    }
    if params.bbox is not None:
        body["bbox"] = [float(value) for value in params.bbox]
    window = stac_interval(params.start, params.end)
    if window is not None:
        body["datetime"] = window
    if marker is not None:
        # Keyset paging, same mechanism as Earth Search (adr/0007 §12, plan §3.1) —
        # only the field name differs: this source's next link carries `token`,
        # not `next`, measured in the M2-09b plan step.
        body["token"] = marker
    return body


def _storable(payload: Any) -> CacheValue:
    """What we keep of an upstream answer: the items (normalised), the count, the
    marker. Reduced here rather than at the cache, so a cache hit and a live answer
    go through exactly the same translation afterwards."""
    features = require_feature_list(payload)
    normalized = [normalize_item(feature) for feature in features]
    return {"features": normalized, "matched": matched_count(payload), "marker": _next_marker(payload)}


def _next_marker(payload: dict[str, Any]) -> str | None:
    """The upstream page marker out of the ``next`` link — this source's own answer
    shape carries it under ``body.token``, not ``body.next`` (adr/0007 §12, measured
    in the M2-09b plan step, plan §3.1)."""
    for link in payload.get("links") or []:
        if not isinstance(link, dict) or link.get("rel") != "next":
            continue
        body = link.get("body")
        if isinstance(body, dict) and isinstance(body.get("token"), str):
            return body["token"]
        # There are more items and we cannot reach them. Returning None here would
        # hand the caller a page that looks like the last one — the same silent
        # truncation adr/0005 rule I refuses for an unknown collection.
        raise UpstreamShapeError("the next link carries no marker we can follow")
    return None


# -- STAC 1.1 -> 1.0 normalisation (adr/0007 §6 point 4, §12.11 point 11) -----------
#
# Our own API declares stac_version 1.0.0 (earthx.catalog.collection.STAC_VERSION);
# this source's items carry 1.1. Only the fields the two versions spell differently
# are touched below — everything else, including the `zarr` extension (which has no
# 1.0 counterpart at all), passes through unchanged rather than being dropped.

_EXTENSION_1_1_TO_1_0 = {
    "https://stac-extensions.github.io/eo/v2.0.0/schema.json": "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
    "https://stac-extensions.github.io/projection/v2.0.0/schema.json": (
        "https://stac-extensions.github.io/projection/v1.1.0/schema.json"
    ),
    "https://stac-extensions.github.io/raster/v2.0.0/schema.json": (
        "https://stac-extensions.github.io/raster/v1.1.0/schema.json"
    ),
}

_EO_BAND_PREFIX = "eo:"
_EPSG_PREFIX = "EPSG:"
# UTM zones only (adr/0007 §3.4, §6 point 4): the one broken combination measured in
# the wild is a UTM `proj:code` paired with a `proj:bbox` in degrees. This is a
# plausibility check, not a reprojection — a mismatch under any other CRS is not
# caught here and is left to whoever reads `proj:bbox` next.
_UTM_PREFIXES = ("EPSG:326", "EPSG:327")
_DEGREE_LIKE_MAGNITUDE = 1000.0


def normalize_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """The item as our STAC 1.0 API would have emitted it, had it harvested this
    source instead of reading it live."""
    normalized = dict(item)
    normalized["stac_version"] = "1.0.0"
    normalized["stac_extensions"] = [
        _EXTENSION_1_1_TO_1_0.get(extension, extension) for extension in item.get("stac_extensions") or []
    ]
    properties = item.get("properties")
    if isinstance(properties, Mapping):
        normalized["properties"] = _normalize_properties(properties)
    assets = item.get("assets")
    if isinstance(assets, Mapping):
        normalized["assets"] = {key: _normalize_asset(asset) for key, asset in assets.items()}
    return normalized


def _normalize_properties(properties: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(properties)
    code = normalized.get("proj:code")
    bbox = normalized.get("proj:bbox")
    if isinstance(bbox, Sequence) and not isinstance(bbox, (str, bytes)) and not _proj_bbox_matches_crs(bbox, code):
        del normalized["proj:bbox"]
    if isinstance(code, str) and code.startswith(_EPSG_PREFIX):
        suffix = code[len(_EPSG_PREFIX) :]
        if suffix.isdigit():
            del normalized["proj:code"]
            normalized["proj:epsg"] = int(suffix)
        # A code with the EPSG: prefix but a non-numeric suffix is not something our
        # 1.0 field could carry either — left as `proj:code`, not guessed at.
    return normalized


def _proj_bbox_matches_crs(bbox: Sequence[Any], code: Any) -> bool:
    if not isinstance(code, str) or not code.startswith(_UTM_PREFIXES):
        return True
    if len(bbox) != 4:
        return False
    try:
        values = [float(value) for value in bbox]
    except (TypeError, ValueError):
        return False
    return not all(abs(value) <= _DEGREE_LIKE_MAGNITUDE for value in values)


def _normalize_asset(asset: Any) -> Any:
    if not isinstance(asset, Mapping):
        return asset
    normalized = dict(asset)
    bands = normalized.pop("bands", None)
    if isinstance(bands, list):
        normalized["eo:bands"] = [_normalize_band(band) for band in bands]
    raster_band: dict[str, Any] = {}
    for source_key, target_key in (
        ("nodata", "nodata"),
        ("data_type", "data_type"),
        ("raster:spatial_resolution", "spatial_resolution"),
    ):
        if source_key in normalized:
            raster_band[target_key] = normalized.pop(source_key)
    if raster_band:
        normalized["raster:bands"] = [raster_band]
    return normalized


def _normalize_band(band: Any) -> Any:
    if not isinstance(band, Mapping):
        return band
    return {
        (key[len(_EO_BAND_PREFIX) :] if key.startswith(_EO_BAND_PREFIX) else key): value
        for key, value in band.items()
    }
