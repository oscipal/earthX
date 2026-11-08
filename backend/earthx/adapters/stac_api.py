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

from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any

from earthx.adapters.cache import CacheValue, SearchCache
from earthx.adapters.cop_dem_bucket import MAX_NOT_LOADABLE_FRACTION, MaterializeOutcome
from earthx.adapters.errors import (
    InvalidQuery,
    NotMaterialized,
    UnsupportedFilter,
    UnsupportedSource,
    UpstreamShapeError,
)
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
from earthx.catalog.registry import AdapterKind, AssetKeyRule, DatasetConfig, ItemHolding, ItemStates
from earthx.catalog.search_filters import FilterConditions, RangeCondition
from earthx.gateway import Gateway, host_of

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


def as_given(item: Item) -> Item:
    """The item unchanged: a source whose items need no translation of their own."""
    return item


FSDI = StacDialect(
    kind=AdapterKind.FSDI_STAC_V1,
    # The `next` link is a POST link with `merge: true` whose body carries only `cursor` (M5-08 plan §2).
    marker_field="cursor",
    # `ids` and `intersects` narrow; CQL2 and every `query` on an item property answer 400 (measured, M5-08 plan §2).
    filters=FilterSupport(intersects=True, ids=True, cql2=False, query=False),
    write_conditions=None,
    normalize_item=as_given,
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
DIALECTS: Mapping[AdapterKind, StacDialect] = dialect_table(EARTH_SEARCH, FSDI)


def dialect_of(config: DatasetConfig) -> StacDialect:
    """The dialect of the source serving ``config``, or :class:`UnsupportedSource` for one that is no STAC API.

    The dispatch never hands over such an entry (``adapters.spec``); this guards a direct call, which would
    otherwise ask a source about a collection it does not hold.
    """
    dialect = DIALECTS.get(config.source.adapter)
    if dialect is None:
        raise UnsupportedSource(f"{config.dataset_id} is served by {config.source.adapter}, which is no STAC API")
    return dialect


def with_fixed_asset_keys(item: Item, rules: tuple[AssetKeyRule, ...]) -> Item:
    """The item with every asset under the key of the one rule its media type and gsd fit (M5-08 plan §4.3).

    No rules: the item unchanged, keys as the source gives them. Otherwise an asset that fits no rule, two assets on
    one rule or a rule no asset fits is :class:`UpstreamShapeError`: an asset never stays under the source's own key,
    where nothing the entry names would find it. The message names no key of the source, which is a file name.
    """
    if not rules:
        return item
    assets = item.get("assets")
    if not isinstance(assets, dict):
        raise UpstreamShapeError("item carries no assets to key")
    keyed: dict[str, Any] = {}
    for asset in assets.values():
        rule = next((rule for rule in rules if isinstance(asset, dict) and _fits(asset, rule)), None)
        if rule is None:
            raise UpstreamShapeError("an asset of the item fits no rule of source.asset_keys")
        if rule.key in keyed:
            raise UpstreamShapeError(f"two assets of the item fit the asset key {rule.key}")
        keyed[rule.key] = asset
    missing = [rule.key for rule in rules if rule.key not in keyed]
    if missing:
        raise UpstreamShapeError(f"the item has no asset for {', '.join(missing)}")
    return {**item, "assets": {rule.key: keyed[rule.key] for rule in rules}}


def _fits(asset: dict[str, Any], rule: AssetKeyRule) -> bool:
    gsd = asset.get("gsd")
    return asset.get("type") == rule.media_type and not isinstance(gsd, bool) and gsd == rule.gsd


def normalize_for(dialect: StacDialect, config: DatasetConfig, item: Item) -> Item:
    """An item of the source as ours: the dialect's translation first, then what the entry fixes (M5-08 plan §4.1)."""
    return with_fixed_asset_keys(dialect.normalize_item(item), config.source.asset_keys)


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
    stored = _storable(dialect, config, response.json())
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
    item = normalize_for(dialect, config, item)
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


def _storable(dialect: StacDialect, config: DatasetConfig, payload: Any) -> CacheValue:
    """What we keep of an upstream answer: the items, the count, the marker.

    Reduced here rather than at the cache, so that a cache hit and a live answer go
    through exactly the same translation afterwards.
    """
    features = [
        normalize_for(dialect, config, feature) if isinstance(feature, dict) else feature
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


# One page of a materialization: the FSDI's own maximum (`limit` 101 answers 100 items, M5-08 plan §2).
MATERIALIZE_PAGE_LIMIT = 100
# By id alone: no time window and no area, so every item of the collection comes, each once (M5-08 plan §4.2).
MATERIALIZE_SORTBY: tuple[dict[str, str], ...] = ({"field": "id", "direction": "asc"},)
# What a materialized item of an entry with states per tile carries besides the source's properties (M5-08 plan §4.4).
TILE_PROPERTY = "earthx:tile"
STATE_PROPERTY = "earthx:state"
# The source version of a run is the collection's ETag and its `updated` (M5-08 plan §7 R1).
_VERSION_UPDATED = ";updated="


@dataclass(slots=True)
class _Tile:
    """The states of one tile read so far: every ``datetime``, and the items of the youngest."""

    instants: list[datetime] = field(default_factory=list)
    latest: list[Item] = field(default_factory=list)

    def add(self, instant: datetime, item: Item) -> None:
        if not self.instants or instant > max(self.instants):
            self.latest = [item]
        elif instant == max(self.instants):
            self.latest.append(item)
        self.instants.append(instant)


async def materialize_items(
    config: DatasetConfig,
    *,
    gateway: Gateway,
    known_version: str | None,
) -> MaterializeOutcome:
    """Every item of the collection, read page by page and checked against the entry, or "unchanged" (M5-08 §4.2).

    The collection is asked first, with ``If-None-Match``; ``304`` or the same ETag and ``updated`` as last time is
    "unchanged" without a search. Otherwise ``POST /search`` over the whole collection, sorted by id, to the last page.
    An item the entry cannot take (collection, geometry, ``datetime``, an asset off ``asset_hosts``, the asset keys,
    an id without a tile) counts as ``unknown``; above 1 % of what was read the run aborts without an item. Where the
    entry names ``item_states``, one state per tile is loaded and the others count as ``withheld``. ``in_bucket`` is
    ``listed`` and ``missing`` is 0: the source lists nothing apart from its items. No asset is opened.
    """
    if config.source.item_holding is not ItemHolding.MATERIALIZED:
        raise NotMaterialized(
            f"{config.dataset_id} is not materialized; adapters.materialize_items does not build its items"
        )
    dialect = dialect_of(config)
    known_etag = None if known_version is None else known_version.partition(_VERSION_UPDATED)[0]
    url = f"{endpoint_of(config)}/collections/{config.source.source_collection_id}"
    response = await gateway.get(url, headers={"if-none-match": known_etag} if known_etag else None)
    if response.status_code == 304:
        return _unchanged(known_version or "")
    version = _collection_version(config, response.headers.get("etag", ""), response.json())
    if version == known_version:
        return _unchanged(version)

    states = config.source.item_states
    tiles: dict[str, _Tile] = {}
    items: list[Item] = []
    seen: set[str] = set()
    listed = unknown = 0
    async for feature in _every_item(dialect, config, gateway):
        listed += 1
        item_id = feature.get("id") if isinstance(feature, dict) else None
        if isinstance(item_id, str):
            if item_id in seen:
                raise UpstreamShapeError("the source returned an item twice; its paging cannot be trusted")
            seen.add(item_id)
        try:
            item, instant, tile = _checked_item(dialect, config, feature)
        except UpstreamShapeError:
            unknown += 1
            continue
        if states is None or tile is None:
            items.append(item)
        else:
            tiles.setdefault(tile, _Tile()).add(instant, _with_state(item, tile, states))

    withheld = 0
    for tile_states in tiles.values():
        twice = {instant for instant in tile_states.instants if tile_states.instants.count(instant) > 1}
        # Which of two states with the same `datetime` is the younger one cannot be told: neither is loaded.
        tied = sum(1 for instant in tile_states.instants if instant in twice)
        unknown += tied
        loaded = tile_states.latest if len(tile_states.latest) == 1 else []
        items.extend(loaded)
        withheld += len(tile_states.instants) - tied - len(loaded)

    if not listed:
        raise UpstreamShapeError(f"the source lists no item of {config.source.source_collection_id}")
    if unknown / listed > MAX_NOT_LOADABLE_FRACTION:
        raise UpstreamShapeError(
            f"{unknown} of {listed} items do not fit the registry entry — over the 1% abort threshold (M5-08 plan §4.2)"
        )
    return MaterializeOutcome(
        status="loaded",
        source_version=version,
        listed=listed,
        in_bucket=listed,
        missing=0,
        withheld=withheld,
        unknown=unknown,
        items=tuple(items),
    )


def _unchanged(version: str) -> MaterializeOutcome:
    return MaterializeOutcome(
        status="unchanged", source_version=version, listed=0, in_bucket=0, missing=0, withheld=0, unknown=0, items=()
    )


def _collection_version(config: DatasetConfig, etag: str, collection: Any) -> str:
    """ETag and ``updated`` of the collection; without either a later run could not compare (M5-08 plan §7 R1)."""
    if not etag:
        raise UpstreamShapeError("the collection answered without an ETag; a later run could not compare")
    if not isinstance(collection, dict) or collection.get("id") != config.source.source_collection_id:
        raise UpstreamShapeError("the collection answer is not the collection the entry names")
    updated = collection.get("updated")
    if not isinstance(updated, str) or not updated:
        raise UpstreamShapeError("the collection carries no updated; a later run could not compare")
    return f"{etag}{_VERSION_UPDATED}{updated}"


async def _every_item(dialect: StacDialect, config: DatasetConfig, gateway: Gateway) -> AsyncIterator[Any]:
    """The features of every page of a search over the whole collection, page after page."""
    body: dict[str, Any] = {
        "collections": [config.source.source_collection_id],
        "limit": MATERIALIZE_PAGE_LIMIT,
        "sortby": list(MATERIALIZE_SORTBY),
    }
    markers: set[str] = set()
    while True:
        payload = (await gateway.post_json(f"{endpoint_of(config)}/search", json=body, retry=True)).json()
        for feature in require_feature_list(payload):
            yield feature
        marker = _next_marker(dialect, payload)
        if marker is None:
            return
        if marker in markers:
            # The same page again would be read forever.
            raise UpstreamShapeError("the source handed out the same page marker twice")
        markers.add(marker)
        body = {**body, dialect.marker_field: marker}


def _checked_item(dialect: StacDialect, config: DatasetConfig, feature: Any) -> tuple[Item, datetime, str | None]:
    """Our item for one feature of the source, its ``datetime`` and its tile (``None`` without ``item_states``), or
    :class:`UpstreamShapeError`.

    The item names our collection and carries no links of the source; pgstac and ``api`` give it links of our own.
    """
    if not isinstance(feature, dict):
        raise UpstreamShapeError("a feature is not a JSON object")
    item_id = feature.get("id")
    if not isinstance(item_id, str) or not ITEM_ID.match(item_id):
        raise UpstreamShapeError("an item has no id we can keep")
    if feature.get("collection") != config.source.source_collection_id:
        raise UpstreamShapeError("an item names another collection")
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) or not isinstance(geometry.get("type"), str) or "coordinates" not in geometry:
        raise UpstreamShapeError("an item has no geometry")
    properties = feature.get("properties")
    instant = _instant(properties.get("datetime") if isinstance(properties, dict) else None)
    item = normalize_for(dialect, config, feature)
    for asset in item.get("assets", {}).values():
        if not _on_asset_host(asset, config.source.asset_hosts):
            raise UpstreamShapeError("an asset of an item lies off the entry's asset hosts")
    states = config.source.item_states
    tile = None if states is None else states.tile_of(item_id)
    if states is not None and tile is None:
        raise UpstreamShapeError("an item id names no tile of item_states.tile_pattern")
    return {**item, "collection": config.dataset_id, "links": []}, instant, tile


def _instant(value: Any) -> datetime:
    if not isinstance(value, str):
        raise UpstreamShapeError("an item has no datetime")
    try:
        instant = datetime.fromisoformat(value)
    except ValueError:
        raise UpstreamShapeError("the datetime of an item is no instant") from None
    if instant.tzinfo is None:
        raise UpstreamShapeError("the datetime of an item has no offset")
    return instant


def _on_asset_host(asset: Any, hosts: tuple[str, ...]) -> bool:
    href = asset.get("href") if isinstance(asset, dict) else None
    if not isinstance(href, str) or not href.startswith("https://"):
        return False
    try:
        return host_of(href) in hosts
    except ValueError:
        return False


def _with_state(item: Item, tile: str, states: ItemStates) -> Item:
    """``earthx:tile`` for the tile, ``earthx:state`` for the rule: one value for all, so one mosaic (A3)."""
    return {**item, "properties": {**item["properties"], TILE_PROPERTY: tile, STATE_PROPERTY: states.rule.value}}
