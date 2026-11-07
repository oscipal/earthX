"""Item search and item fetch for STAC APIs, one dialect per source (adr/0005, adr/0011 F6 and §8.2, M5-08).

The source holds the items; we hold the collection. This module is the translation
between the two: it builds the upstream request, reads the upstream answer, and hands
back STAC items plus a page marker of our own. Everything it sends goes through
``gateway`` (KLAERUNGEN B8) — there is no HTTP client here and no ``pystac_client``
(adr/0005 rule IV).

What every source with a search API shares is ``earthx.adapters.federated_search``:
our own page marker (rule III), the input checks of ``SearchParams`` (rule V), the
cache. What every *STAC* API shares is here: the search body, the item path, the
reading of an item collection. What differs from one STAC API to the next is a
:class:`StacDialect` — measured per source, like ``FilterSupport`` (adr/0011 F1), and
therefore code, not registry data. adr/0011 §3.2 B2 found three such places:

* **the page marker** — the field of the ``next`` link's body that carries it
  (``next`` at Earth Search, ``cursor`` at the FSDI of swisstopo, M5-08 plan §2);
* **the conditions** of a dataset's search filters — how they go on the wire, if the
  source takes them at all (Earth Search: the STAC query extension, DS-02);
* **the normalisation** an item needs before it looks like ours.

Rule I stays in front of all of it: the caller hands in our own registry entry, looked
up *first* by ``adapters.dataset_config``. A STAC API answers an unknown collection
with ``200`` and an empty result (adr/0005 §3.5, measured at the FSDI too), which would
turn "there is no such dataset" into "there is nothing in it".

Input checks that are not source-specific (bbox, limit, the time window) already
ran inside ``SearchParams.__post_init__`` before anything reaches this module. A
bbox outside ±90 is *silently accepted* by Earth Search (§3.5), which is the worst of
the three possible answers — checking it ourselves is why ``SearchParams`` exists at all.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from earthx.adapters.cache import CacheValue, SearchCache
from earthx.adapters.errors import InvalidQuery, UnsupportedFilter, UnsupportedSource, UpstreamShapeError
from earthx.adapters.federated_search import (
    ITEM_ID,
    SORTBY,
    TTL_ITEM_S,
    FilterSupport,
    ItemPage,
    SearchParams,
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
    with_core_bands,
)
from earthx.catalog.registry import AdapterKind, DatasetConfig
from earthx.catalog.search_filters import FilterConditions, RangeCondition
from earthx.gateway import Gateway

Item = dict[str, Any]

# The fields our own search body may carry; a dialect's marker or conditions must not take one of them over.
BODY_FIELDS = frozenset({"collections", "limit", "sortby", "bbox", "intersects", "ids", "datetime"})


@dataclass(frozen=True, slots=True)
class StacDialect:
    """What one STAC API does its own way (adr/0011 §8.2). No field has a default (B10).

    ``write_conditions`` turns the conditions of a dataset's search filters into the
    fields of the search body that carry them, or is ``None`` where the source applies
    none; ``filters.query`` says the same for the dispatch, which refuses such a search
    before it reaches this module.
    """

    kind: AdapterKind
    marker_field: str
    filters: FilterSupport
    write_conditions: Callable[[FilterConditions], dict[str, Any]] | None
    normalize_item: Callable[[Item], Item]

    def __post_init__(self) -> None:
        if (self.write_conditions is None) == self.filters.query:
            raise ValueError(f"{self.kind}: conditions are written exactly when the source applies a query")
        if self.marker_field in BODY_FIELDS:
            raise ValueError(f"{self.kind}: the page marker cannot take over the body field {self.marker_field!r}")


def query_extension(conditions: FilterConditions) -> dict[str, dict[str, Any]]:
    """The conditions in the STAC query extension (DS-02 plan §6.5).

    Only ``gte``, ``lte`` and ``in``: measured to narrow at Earth Search on 28.10.2026, where an operator the
    source does not know is passed over without a word (plan §6.2).
    """
    query: dict[str, dict[str, Any]] = {}
    for name, condition in conditions.items():
        if isinstance(condition, RangeCondition):
            bounds = {"gte": condition.minimum, "lte": condition.maximum}
            query[name] = {operator: bound for operator, bound in bounds.items() if bound is not None}
        else:
            query[name] = {"in": list(condition.values)}
    return query


def with_core_bands_on_assets(item: Item) -> Item:
    """The item with the core field ``bands`` mirrored from ``eo:bands`` on every asset (M4-23).

    Earth Search speaks STAC 1.0 already, so this is the only change: ``eo:bands``
    stays, ``stac_version`` stays, nothing is asked of the source.
    """
    assets = item.get("assets")
    if not isinstance(assets, dict):
        return item
    return {**item, "assets": {key: with_core_bands(asset) for key, asset in assets.items()}}


EARTH_SEARCH = StacDialect(
    kind=AdapterKind.EARTH_SEARCH_V1,
    # The `next` link is a POST link whose body carries the keyset marker as `next` (adr/0005 §3.3).
    marker_field="next",
    # CQL2 is not answered by this source (measured, M3-13 plan §2.3); `query` is (DS-02 plan §6.2).
    filters=FilterSupport(intersects=True, ids=True, cql2=False, query=True),
    write_conditions=lambda conditions: {"query": query_extension(conditions)},
    normalize_item=with_core_bands_on_assets,
)


def dialect_table(*dialects: StacDialect) -> Mapping[AdapterKind, StacDialect]:
    """A read-only table keyed by each dialect's own ``kind``; a kind twice is an error."""
    table = {dialect.kind: dialect for dialect in dialects}
    if len(table) != len(dialects):
        raise ValueError("an adapter kind has two dialects")
    return MappingProxyType(table)


# Looked up by the entry's own adapter kind rather than bound into the spec table: the functions keep the
# signatures of `SearchItems` and `FetchItem`, and `spec.check_adapter_specs` refuses a spec that serves a kind
# with these functions but has no dialect here (M5-08 plan §11).
DIALECTS: Mapping[AdapterKind, StacDialect] = dialect_table(EARTH_SEARCH)


def dialect_of(config: DatasetConfig) -> StacDialect:
    """The dialect of the source serving ``config``, or :class:`UnsupportedSource` for one that is no STAC API.

    The dispatch never hands over such an entry (``adapters.spec``); this guards a direct call, which would
    otherwise ask a source about a collection it does not hold.
    """
    dialect = DIALECTS.get(config.source.adapter)
    if dialect is None:
        raise UnsupportedSource(f"{config.dataset_id} is served by {config.source.adapter}, which is no STAC API")
    return dialect


async def search_items(
    config: DatasetConfig,
    params: SearchParams | None = None,
    *,
    gateway: Gateway,
    cache: SearchCache | None = None,
) -> ItemPage:
    """Search items of one federated collection.

    ``cache=None`` is a valid call: without a cache this is slower, never wrong (E5).
    """
    params = params or SearchParams()
    dialect = dialect_of(config)
    if params.conditions is not None and dialect.write_conditions is None:
        # Refused before the cache is read, like the dispatch does (`adapters._check_filters`).
        raise UnsupportedFilter(f"{config.dataset_id} does not support search filters")
    dataset_id = config.dataset_id
    fingerprint = search_fingerprint(dataset_id, params)
    marker = None if params.page_token is None else decode_page_token(params.page_token, dataset_id, fingerprint)

    key = search_cache_key(fingerprint, marker, params.limit)
    cached = await cache_get(cache, key)
    if cached is not None and isinstance(cached.get("features"), list):
        return page_from_stored(dataset_id, fingerprint, cached, from_cache=True)

    response = await gateway.post_json(
        f"{endpoint_of(config)}/search",
        json=_search_body(dialect, config, params, marker),
        # A search is a read; repeating it after a 503 is safe. The gateway leaves that
        # judgement to the caller, because only the caller knows what the POST means.
        retry=True,
    )
    stored = _storable(dialect, response.json())
    await cache_set(cache, key, stored, ttl_s=ttl_for_window(params.end), dataset_id=dataset_id)
    return page_from_stored(dataset_id, fingerprint, stored, from_cache=False)


async def get_item(
    config: DatasetConfig,
    item_id: str,
    *,
    gateway: Gateway,
    cache: SearchCache | None = None,
) -> Item:
    """One item by id, without a search in front of it (adr/0001 Z1).

    A missing item stays the source's ``404``: the gateway carries the status code
    through unchanged, which is exactly what ``pystac_client`` would have lost.
    """
    dialect = dialect_of(config)
    dataset_id = config.dataset_id
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
    item = dialect.normalize_item(item)
    await cache_set(cache, key, {"item": item}, ttl_s=TTL_ITEM_S, dataset_id=dataset_id)
    return item


def _search_body(
    dialect: StacDialect, config: DatasetConfig, params: SearchParams, marker: str | None
) -> dict[str, Any]:
    """Our own search body, the same for every dialect but the conditions and the marker's field.

    A source may refuse any field it does not know (the FSDI answers ``400``, M5-08 plan §2), so nothing goes
    in that the caller did not ask for.
    """
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
        # filter by Earth Search, not a shortcut around them — a caller who narrows
        # both gets the intersection, not just the ids.
        body["ids"] = list(params.ids)
    window = stac_interval(params.start, params.end)
    if window is not None:
        body["datetime"] = window
    if params.conditions is not None and dialect.write_conditions is not None:
        written = dialect.write_conditions(params.conditions)
        if not written.keys().isdisjoint(body.keys() | BODY_FIELDS | {dialect.marker_field}):
            raise ValueError(f"{dialect.kind}: the conditions would take over a field of the search body")
        body.update(written)
    if marker is not None:
        # Keyset paging: the marker is what the source handed out for the page after
        # this one, so the same search body plus this field is the next page (§3.3).
        # Our body is complete either way, whether the source's own link says to merge
        # its body into the last request (`merge: true`) or to send it alone.
        body[dialect.marker_field] = marker
    return body


def _storable(dialect: StacDialect, payload: Any) -> CacheValue:
    """What we keep of an upstream answer: the items, the count, the marker.

    Reduced here rather than at the cache, so that a cache hit and a live answer go
    through exactly the same translation afterwards.
    """
    features = [
        dialect.normalize_item(feature) if isinstance(feature, dict) else feature
        for feature in require_feature_list(payload)
    ]
    return {"features": features, "matched": matched_count(payload), "marker": _next_marker(dialect, payload)}


def _next_marker(dialect: StacDialect, payload: dict[str, Any]) -> str | None:
    """The upstream page marker out of the ``next`` link, which is a POST link with a body."""
    for link in payload.get("links") or []:
        if not isinstance(link, dict) or link.get("rel") != "next":
            continue
        body = link.get("body")
        if isinstance(body, dict) and isinstance(body.get(dialect.marker_field), str):
            return body[dialect.marker_field]
        # There are more items and we cannot reach them. Returning None here would
        # hand the caller a page that looks like the last one — the same silent
        # truncation adr/0005 rule I refuses for an unknown collection.
        raise UpstreamShapeError("the next link carries no marker we can follow")
    return None
