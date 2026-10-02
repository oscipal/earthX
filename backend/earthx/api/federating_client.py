"""earthx's outward STAC API: collections from pgstac, items federated (adr/0005).

``FederatingCoreCrudClient`` overrides only the four public search/item methods of
``CoreCrudClient`` (rule I, option 2 of adr/0005 §4) — never ``_search_base``, pgstac's
own SQL path, which stays untouched for a collection it actually holds items for. Per
collection, ``earthx:source`` — read off the very document pgstac itself just returned,
so an unknown collection is still pgstac's own 404 (rule I) — decides whether a call
goes to ``super()`` or to ``earthx.adapters``.

**Mixed search (M3-13).** A search naming more than one *source* — a federated
collection, or a group of this platform's own collections that share whether a
``datetime`` filter applies to them — used to be rejected with a ``400``
(``_dispatch_search``'s old third branch). It now fans out: every open source is
asked in parallel, each for its own share of ``limit``, recomputed on every page
(``_mixed_page``, ``earthx.api.mixed_search``); a source that fails or times out
turns into an ``incomplete_collections`` entry rather than failing the whole
answer, except a failure of this platform's *own* database (a native source),
which still fails the request outright — there is no partial result for that,
same as before this task. ``_native_group_page`` still only ever reaches
``super().post_search`` (rule I), never ``_search_base`` directly.

The gateway and the search-cache pool are not constructor arguments: ``instantiate_api``
builds this client itself (``client(pgstac_search_model=...)``), so there is nowhere to
hand them in at construction time. They live on ``request.app.state`` instead, set once
by the process lifespan in ``earthx.api.main`` — the same place pgstac's own connection
pool already lives (``request.app.state.get_connection``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast

from fastapi import HTTPException, Request
from pydantic import ValidationError
from stac_fastapi.pgstac.core import CoreCrudClient
from stac_fastapi.pgstac.models.links import ItemCollectionLinks, ItemLinks, PagingLinks, SearchLinks
from stac_fastapi.types.rfc3339 import str_to_interval
from stac_fastapi.types.stac import Item, ItemCollection

from earthx.adapters import (
    InvalidQuery,
    ItemPage,
    SearchCache,
    SearchParams,
    UnknownCollection,
    UnsupportedFilter,
    UpstreamShapeError,
)
from earthx.adapters import search_items as adapter_search_items
from earthx.api import mixed_search
from earthx.api.item_source import build_item_source, item_holding_of
from earthx.api.mixed_search import (
    REASON_TIMEOUT,
    REASON_UNREACHABLE,
    REASON_UNRECOGNISED_ANSWER,
    REASON_UPSTREAM_ERROR,
    IncompleteSource,
    compute_shares,
    decode_mixed_token,
    encode_mixed_token,
    is_mixed_token,
    mixed_fingerprint,
)
from earthx.catalog.registry import DatasetRegistry, ItemHolding
from earthx.catalog.search_cache import PostgresSearchCache
from earthx.gateway import UpstreamError, UpstreamTimeout, UpstreamUnreachable

LOGGER = logging.getLogger("earthx.api.federating_client")

# adr/0005 rule VI treats `filter`/CQL2 this way; the plan (docs/plans/
# m1-07-stac-api.md §6, F2) extends the same reasoning to `sort`: the federated path
# cannot yet honour a client-chosen field, so neither extension is enabled
# (earthx/api/main.py). M3-13 F5 adds `query`/`fields`: measured against the real API
# (plan §2.2), both are silently dropped on a federated collection today (`#query`/
# `#fields` are advertised on the landing page, K8, but the federated path never
# builds them into the upstream request) — the fix is the same one already applied to
# `filter`/`sort`: turn the extension off and refuse the parameter by name instead of
# letting it look honoured. This is the other half of "not silently dropped": the
# request models simply do not declare these fields when the extension is off, so
# without this check pydantic's `extra="ignore"` (or FastAPI ignoring an undeclared
# query parameter) would swallow them rather than reject them.
_DISALLOWED_QUERY_KEYS = frozenset({"filter", "filter-lang", "filter_lang", "sortby", "query", "fields"})

# M3-08: `/search` forwards `ids`/`intersects` to a federated source now (§4 of the
# M3-08 plan), but OGC API Features' items endpoint (`GET /collections/{id}/items`)
# never had either parameter — it is not `item-search`, and nothing here builds a
# request body for it these two could go into. Kept as its own set (distinct from
# M2-17's now-obsolete blanket rejection) so `item_collection` still says no, with
# its own reason, while `/search` says yes.
_ITEMS_ENDPOINT_DISALLOWED_KEYS = frozenset({"ids", "intersects"})


def _reject_keys(keys: object, disallowed: frozenset[str], reason: str) -> None:
    found = sorted(disallowed.intersection(keys))
    if found:
        raise HTTPException(status_code=400, detail=f"{', '.join(found)} {reason}")


def _reject_disallowed_keys(keys: object) -> None:
    _reject_keys(
        frozenset(keys),
        _DISALLOWED_QUERY_KEYS,
        "is not available in M1 (adr/0005 rule VI; docs/plans/m1-07-stac-api.md §6)",
    )


def _reject_items_endpoint_keys(keys: object) -> None:
    _reject_keys(
        frozenset(keys),
        _ITEMS_ENDPOINT_DISALLOWED_KEYS,
        "is not a parameter of this endpoint; search at GET/POST /stac/search instead (M3-08)",
    )


async def _reject_disallowed_body(request: Request) -> None:
    if request.method != "POST":
        return
    body = await request.json()
    if isinstance(body, dict):
        _reject_disallowed_keys(body.keys())


def _dump_intersects(geometry: Any) -> dict[str, Any] | None:
    """A POST body's ``intersects`` as a plain GeoJSON mapping.

    ``search_request.intersects`` is already a parsed ``geojson_pydantic`` geometry
    model (stac-pydantic's ``Intersection`` type), not a dict — ``model_dump`` turns
    it back into the same shape ``SearchParams`` and the GET path both expect.
    """
    if geometry is None:
        return None
    if isinstance(geometry, Mapping):
        return dict(geometry)
    return geometry.model_dump(mode="json", exclude_none=True)


def _parse_intersects_param(value: str | None) -> dict[str, Any] | None:
    """A GET ``intersects`` query parameter — raw JSON text, same convention as the
    coverage route (``api/coverage_route.py::_parse_intersects``)."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="intersects is not valid JSON") from None
    if not isinstance(parsed, Mapping):
        raise HTTPException(status_code=400, detail="intersects is not a GeoJSON object")
    return dict(parsed)


def _strip_forward_token(token: str | None) -> str | None:
    """Undo the ``next:``/``prev:`` prefix ``PagingLinks`` puts on our own marker.

    Only forward paging exists here, same as the adapter it calls (M1-06 never built
    ``prev`` either) — a ``token=prev:...`` sent at a federated collection is refused
    rather than silently answered with the first page again.
    """
    if token is None:
        return None
    if token.startswith("next:"):
        return token[len("next:") :]
    if token.startswith("prev:"):
        raise HTTPException(status_code=400, detail="backward paging is not offered for a federated collection")
    return token


def _datetime_bounds(value: str | None) -> tuple[Any, Any]:
    parsed = str_to_interval(value)
    if parsed is None:
        return None, None
    if isinstance(parsed, tuple):
        return parsed
    return parsed, parsed


def _apply_time_axis(datetime_value: str | None, time_ranges: list[bool]) -> tuple[str | None, tuple[str, ...]]:
    """Whether/how ``datetime`` applies, given whether each target collection has
    a time axis at all (M3-12, Otto 26.09.2026, M3-11b F11 Nachtrag).

    A dataset with ``capabilities.time_range=False`` (the DEM) answers a search
    the same for any chosen window — never filtered, not even the frontend's own
    ±90-day fallback (``dateFallback.ts``). Dropped only when *every* named
    collection lacks a time axis; named in the answer's ``ignored_filters``, the
    same field the coverage route already uses for the identical rule
    (``api/coverage_route.py``).

    Validated once here, before anything is dropped: a malformed value is a
    ``400`` (``str_to_interval`` raises its own ``HTTPException`` inside
    ``_datetime_bounds``) whether or not the dataset has a time axis.

    M3-13: a search naming one collection with a time axis and one without is
    handled by never mixing them into the same call in the first place —
    ``_partition_sources`` groups this platform's own collections by their
    ``time_range`` before this runs, and a federated collection is always its
    own source. Every call this function gets is therefore already for *one*
    source, which is why ``time_ranges`` — despite the plural name kept for the
    "every named collection" wording above — is always a list of one identical
    value in practice (several ids sharing one group's ``time_range``, or one
    federated collection's own).
    """
    if datetime_value is None:
        return None, ()
    _datetime_bounds(datetime_value)
    if time_ranges and not any(time_ranges):
        return None, ("datetime",)
    return datetime_value, ()


@dataclass(frozen=True, slots=True)
class _NativeGroup:
    """One or more of this platform's own collections, sharing whether a
    ``datetime`` filter applies to them — answered by pgstac in a single call
    (M3-13 §4.2). ``key`` addresses it inside a mixed page token; it never
    collides with a federated source's key (a bare collection id), because it
    always carries the ``native:`` prefix.
    """

    ids: tuple[str, ...]
    effective_datetime: str | None
    dropped_datetime: bool

    @property
    def key(self) -> str:
        return "native:" + ",".join(self.ids)


@dataclass(frozen=True, slots=True)
class _FederatedSource:
    """One federated collection — always its own source (M3-13 §4.2)."""

    collection_id: str
    effective_datetime: str | None
    dropped_datetime: bool

    @property
    def key(self) -> str:
        return self.collection_id


_Source = _NativeGroup | _FederatedSource


def _partition_sources(
    target_ids: list[str], infos: Mapping[str, tuple[ItemHolding, bool]], datetime_value: str | None
) -> list[_Source]:
    """The distinct *sources* a search over ``target_ids`` reaches (M3-13 §4.2):
    this platform's own collections, split into at most two groups by whether
    ``datetime`` applies to them, followed by every federated collection in a
    fixed order (native groups first, then federated by id) — pgstac-first
    because a query with fewer, larger sources this platform controls is
    cheaper to try than one that reaches out.

    ``time_ranges``/``effective_datetime`` are resolved once here, per source —
    not once for the whole search — because that is the only way a search
    naming a collection with a time axis and one without honours ``datetime``
    for the one and drops it for the other (M3-12, Otto's Nachtrag) rather than
    doing one or the other for both, which was the state before this task.
    """
    federated_ids = sorted(cid for cid in target_ids if infos[cid][0] is ItemHolding.FEDERATED)
    native_ids = [cid for cid in target_ids if cid not in federated_ids]
    sources: list[_Source] = []
    for time_range in (True, False):
        group_ids = tuple(sorted(cid for cid in native_ids if infos[cid][1] is time_range))
        if not group_ids:
            continue
        effective, ignored = _apply_time_axis(datetime_value, [time_range])
        sources.append(_NativeGroup(ids=group_ids, effective_datetime=effective, dropped_datetime=bool(ignored)))
    for collection_id in federated_ids:
        effective, ignored = _apply_time_axis(datetime_value, [infos[collection_id][1]])
        sources.append(
            _FederatedSource(collection_id=collection_id, effective_datetime=effective, dropped_datetime=bool(ignored))
        )
    return sources


def _ignored_filters_of(sources: list[_Source]) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """The flat ``ignored_filters`` (unchanged shape, for a simple client) and the
    new per-collection breakdown (Otto, M3-13 F4: "weil der Viewer mit
    Mehrfachauswahl je Datensatz einen Hinweis zeigen soll") — computed together
    because both read off the same per-source ``dropped_datetime``.
    """
    by_collection: dict[str, tuple[str, ...]] = {}
    any_dropped = False
    for source in sources:
        if not source.dropped_datetime:
            continue
        any_dropped = True
        ids = source.ids if isinstance(source, _NativeGroup) else (source.collection_id,)
        for collection_id in ids:
            by_collection[collection_id] = ("datetime",)
    return (("datetime",) if any_dropped else ()), by_collection


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    """What ``_dispatch_search`` decided, for ``post_search``/``get_search`` to act
    on. ``result is None`` means: nothing here needs anything but pgstac's own
    ``super()`` call, with ``effective_datetime`` in place of the raw value.
    """

    result: ItemCollection | None
    effective_datetime: str | None
    ignored_filters: tuple[str, ...]
    ignored_by_collection: Mapping[str, tuple[str, ...]]
    incomplete: tuple[IncompleteSource, ...] = ()
    # `open_collections` (Otto, 30.09.2026, M3-10b): a mixed page names them
    # itself; a single-source answer (`None` here) has them all open exactly
    # while it links a next page — `searched` are that source's collections.
    open_collections: tuple[str, ...] | None = None
    searched: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _MixedResult:
    """What one page of ``_mixed_page`` produced: the merged answer, and every
    source it could not reach this time (plan §4.4)."""

    page: ItemCollection
    incomplete: tuple[IncompleteSource, ...]
    open_collections: tuple[str, ...]


def _collections_of(source: _Source) -> tuple[str, ...]:
    return source.ids if isinstance(source, _NativeGroup) else (source.collection_id,)


def _open_collections_of(result: dict[str, Any], outcome: DispatchOutcome) -> tuple[str, ...]:
    if outcome.open_collections is not None:
        return outcome.open_collections
    has_next = any(link.get("rel") == "next" for link in result.get("links") or [])
    return outcome.searched if has_next else ()


def _apply_outcome_extras(result: dict[str, Any], outcome: DispatchOutcome) -> None:
    # Which collections' source still has pages (Otto, 30.09.2026, M3-10b): the
    # viewer's ±90-day fallback waits for a dataset whose source may still bring
    # scenes of the date range. Collections sharing a source are open together.
    # The page token itself stays opaque (adr/0005 rule III).
    result["open_collections"] = list(_open_collections_of(result, outcome))
    if outcome.ignored_filters:
        result["ignored_filters"] = list(outcome.ignored_filters)
    if outcome.ignored_by_collection:
        result["ignored_filters_by_collection"] = {
            collection_id: list(values) for collection_id, values in outcome.ignored_by_collection.items()
        }
    if outcome.incomplete:
        result["incomplete_collections"] = [dict(entry) for entry in outcome.incomplete]


def _unquote_percent(value: str) -> str:
    """A minimal ``%XX``/``+`` decoder for one query-string value.

    ``earthx.api`` may not import ``urllib`` (the import-linter's
    ``http-only-in-gateway`` contract, M1-02) — this is the one value a mixed
    search's own paging ever needs out of a URL (the ``token`` parameter of a
    pgstac-built ``GET``-style "next" link, ``PagingLinks.link_next``), decoded
    by hand instead of pulling in the module that contract keeps out of every
    module but ``gateway``. Percent-triples are collected as raw bytes before
    decoding, so a multi-byte UTF-8 sequence split across them still reads back
    correctly — not that a page marker (a collection id and an item id) is ever
    anything but ASCII in practice.
    """
    value = value.replace("+", " ")
    raw = bytearray()
    index, length = 0, len(value)
    while index < length:
        char = value[index]
        if char == "%" and index + 2 < length:
            try:
                raw.append(int(value[index + 1 : index + 3], 16))
                index += 3
                continue
            except ValueError:
                pass
        raw.extend(char.encode("utf-8"))
        index += 1
    return raw.decode("utf-8", errors="replace")


def _href_query_param(href: str, name: str) -> str | None:
    query = href.split("?", 1)[1] if "?" in href else ""
    for pair in query.split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        if _unquote_percent(key) == name:
            return _unquote_percent(value)
    return None


def _extract_next_marker(links: list[dict[str, Any]] | None) -> str | None:
    """The raw pgstac marker of a "next" link, whichever shape it was built in.

    A native group's own sub-search always goes through ``super().post_search``
    (M3-13's ``_native_group_page``), but the *inbound* request that triggered a
    mixed search may have been a ``GET`` — and ``PagingLinks.link_next`` shapes
    the link after ``request.method``, not after how this module happened to
    call pgstac. Reading either shape here means the caller need not know which
    one it got: the marker in a ``POST``-shaped link's ``body["token"]``, or the
    ``token`` query parameter of a ``GET``-shaped link's ``href`` — both carry
    the same ``next:<marker>`` text, ``next:`` stripped here exactly as
    ``_strip_forward_token`` already does for an inbound one.
    """
    for link in links or []:
        if not isinstance(link, dict) or link.get("rel") != "next":
            continue
        body = link.get("body")
        token = body.get("token") if isinstance(body, dict) else None
        if not isinstance(token, str):
            href = link.get("href")
            token = _href_query_param(href, "token") if isinstance(href, str) else None
        if isinstance(token, str):
            return token[len("next:") :] if token.startswith("next:") else token
    return None


def _adapter_error_to_http(error: Exception) -> HTTPException:
    """Our own upstream errors, in the shape a STAC client already expects.

    Never re-raises the source's own error text (adr/0005 rule III) — only its
    status, which ``gateway.UpstreamError`` already carries unchanged (M1-03).
    """
    if isinstance(error, InvalidQuery):
        return HTTPException(status_code=400, detail=str(error))
    if isinstance(error, UnsupportedFilter):
        return HTTPException(status_code=400, detail=str(error))
    if isinstance(error, UnknownCollection):
        return HTTPException(status_code=404, detail=f"Collection {error} does not exist.")
    if isinstance(error, UpstreamError):
        return HTTPException(status_code=error.status_code, detail="the source answered with an error")
    if isinstance(error, UpstreamTimeout):
        return HTTPException(status_code=504, detail="the source did not answer in time")
    if isinstance(error, UpstreamUnreachable):
        return HTTPException(status_code=502, detail="the source could not be reached")
    if isinstance(error, UpstreamShapeError):
        return HTTPException(status_code=502, detail="the source answered something we do not recognise")
    raise error


@asynccontextmanager
async def _cache_for(request: Request):
    """A ``SearchCache`` for the one call, or ``None`` if the pool is not wired up.

    ``cache=None`` reaching the adapter is a valid call (E5) — this process simply
    runs slower, never wrong, the same guarantee M1-06 already tested.
    """
    pool = getattr(request.app.state, "earthx_cache_pool", None)
    if pool is None:
        yield None
        return
    async with pool.connection() as conn:
        yield cast(SearchCache, PostgresSearchCache(conn))


def _registry_of(request: Request) -> DatasetRegistry:
    registry = getattr(request.app.state, "earthx_registry", None)
    if registry is None:
        raise RuntimeError("earthx.api.main did not set request.app.state.earthx_registry")
    return registry


def _gateway_of(request: Request):
    gateway = getattr(request.app.state, "earthx_gateway", None)
    if gateway is None:
        raise RuntimeError("earthx.api.main did not set request.app.state.earthx_gateway")
    return gateway


class FederatingCoreCrudClient(CoreCrudClient):
    """Branches per collection on ``earthx:source`` instead of on the route."""

    async def item_collection(
        self,
        collection_id: str,
        request: Request,
        bbox: tuple[float, ...] | None = None,
        datetime: str | None = None,
        limit: int | None = None,
        token: str | None = None,
        **kwargs: Any,
    ) -> ItemCollection:
        # Not `kwargs.keys()`: a disabled extension's field is absent from the parsed
        # request model entirely, so it never reaches here as a keyword argument at
        # all — the same gap `post_search`/`get_search` close by looking at the raw
        # request instead of the already-filtered method arguments. Checked before
        # the holding lookup below, and so for a materialized collection too (M3-11a):
        # before M3-11a this branch was unreachable for anything but a federated
        # collection, because every collection in pgstac had a known adapter.
        _reject_disallowed_keys(request.query_params.keys())
        _reject_items_endpoint_keys(request.query_params.keys())
        holding, time_range = await self._source_info_of(collection_id, request)
        effective_datetime, ignored_filters = _apply_time_axis(datetime, [time_range])
        if holding is not ItemHolding.FEDERATED:
            result = await super().item_collection(
                collection_id,
                request,
                bbox=bbox,
                datetime=effective_datetime,
                limit=limit,
                token=token,
                **kwargs,
            )
            if ignored_filters:
                result["ignored_filters"] = list(ignored_filters)
            return result
        result = await self._federated_page(
            collection_id, request, bbox=bbox, datetime_value=effective_datetime, limit=limit, token=token
        )
        if ignored_filters:
            result["ignored_filters"] = list(ignored_filters)
        result["links"] = await ItemCollectionLinks(collection_id=collection_id, request=request).get_links(
            extra_links=result["links"]
        )
        return result

    async def get_item(self, item_id: str, collection_id: str, request: Request, **kwargs: Any) -> Item:
        holding = await self._holding_of(collection_id, request)
        if holding is not ItemHolding.FEDERATED:
            return await super().get_item(item_id, collection_id, request, **kwargs)
        # The same item source as the tiler's tiles and download (adr/0011 §7 D2),
        # built per call around this process's gateway and pool.
        item_source = build_item_source(
            _registry_of(request), _gateway_of(request), getattr(request.app.state, "earthx_cache_pool", None)
        )
        try:
            item = await item_source(collection_id, item_id)
        except (
            InvalidQuery,
            UnknownCollection,
            UpstreamError,
            UpstreamTimeout,
            UpstreamUnreachable,
            UpstreamShapeError,
        ) as error:
            # M2-17 finding: this was missing `UpstreamShapeError`, so a source that
            # answers something that is not an item turned into our own `500`
            # instead of the `502` `_adapter_error_to_http` already knows for it.
            raise _adapter_error_to_http(error) from error
        item = dict(item)
        item["links"] = await ItemLinks(collection_id=collection_id, item_id=item_id, request=request).get_links(
            extra_links=item.get("links")
        )
        return cast(Item, item)

    async def post_search(self, search_request: Any, request: Request, **kwargs: Any) -> ItemCollection:
        await _reject_disallowed_body(request)
        collections = list(search_request.collections) if search_request.collections else None
        bbox = search_request.bbox
        outcome = await self._dispatch_search(
            request,
            collections=collections,
            bbox=bbox,
            intersects=_dump_intersects(search_request.intersects),
            ids=tuple(search_request.ids) if search_request.ids else None,
            datetime_value=search_request.datetime,
            limit=search_request.limit,
            token=search_request.token,
        )
        if outcome.result is None:
            if outcome.effective_datetime != search_request.datetime:
                search_request = search_request.model_copy(update={"datetime": outcome.effective_datetime})
            result = await super().post_search(search_request, request, **kwargs)
            _apply_outcome_extras(result, outcome)
            return result
        _apply_outcome_extras(outcome.result, outcome)
        outcome.result["links"] = await SearchLinks(request=request).get_links(extra_links=outcome.result["links"])
        return outcome.result

    async def get_search(
        self,
        request: Request,
        collections: list[str] | None = None,
        bbox: tuple[float, ...] | None = None,
        intersects: str | None = None,
        ids: list[str] | None = None,
        datetime: str | None = None,
        limit: int | None = None,
        token: str | None = None,
        **kwargs: Any,
    ) -> ItemCollection:
        _reject_disallowed_keys(request.query_params.keys())
        outcome = await self._dispatch_search(
            request,
            collections=collections,
            bbox=bbox,
            intersects=_parse_intersects_param(intersects),
            ids=tuple(ids) if ids else None,
            datetime_value=datetime,
            limit=limit,
            token=token,
        )
        if outcome.result is None:
            # `ids`/`intersects` forwarded raw (as pgstac's own `get_search` — a
            # native, non-federated collection — declares them itself): dropping
            # them here would silently re-introduce the M2-17 bug for whichever
            # collection this platform holds items for first.
            result = await super().get_search(
                request,
                collections=collections,
                bbox=bbox,
                intersects=intersects,
                ids=ids,
                datetime=outcome.effective_datetime,
                limit=limit,
                token=token,
                **kwargs,
            )
            _apply_outcome_extras(result, outcome)
            return result
        _apply_outcome_extras(outcome.result, outcome)
        outcome.result["links"] = await SearchLinks(request=request).get_links(extra_links=outcome.result["links"])
        return outcome.result

    # -- dispatch -----------------------------------------------------------------

    async def _source_info_of(self, collection_id: str, request: Request) -> tuple[ItemHolding, bool]:
        """How the items of a collection pgstac knows are held, and whether it has
        a time axis.

        Reuses ``super().get_collection`` on purpose: an unknown collection raises
        pgstac's own ``NotFoundError`` here exactly as it would for ``GET
        /collections/{id}`` (adr/0005 rule I) — there is no second lookup to keep
        in sync with it.

        **The holding comes from the registry**, not from the document
        (adr/0011 §7 D2, M4-01a): the tiler and the download route by the registry
        too, and the start of this process has already refused a pgstac that
        disagrees (``api.item_source.check_item_holdings``). A collection pgstac
        knows and the registry does not — a left-over, or one written outside
        ``catalog.load`` — cannot be routed, and is refused loudly rather than
        answered as pgstac's own near-empty result for it (Otto, M4-01a F2).

        ``time_range`` (M3-12) still comes from the document, and fails safe rather
        than loudly when it is missing or not a plain bool: unlike ``item_holding``,
        nothing about *routing* depends on it, only whether a `datetime` filter is
        honoured — treating an unreadable value as "has a time axis" keeps a
        search filtered exactly as it always was, rather than turning a stale or
        foreign document into a new class of `500`.
        """
        collection = await self.get_collection(collection_id, request=request)
        try:
            holding = item_holding_of(_registry_of(request), collection_id)
        except UnknownCollection:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"collection {collection_id!r} is not in the registry, so it has no "
                    "earthx:source.item_holding to route by (run `python -m earthx.catalog.load`)"
                ),
            ) from None
        capabilities = collection.get("earthx:capabilities")
        raw_time_range = capabilities.get("time_range") if isinstance(capabilities, dict) else None
        time_range = raw_time_range if isinstance(raw_time_range, bool) else True
        return holding, time_range

    async def _holding_of(self, collection_id: str, request: Request) -> ItemHolding:
        holding, _ = await self._source_info_of(collection_id, request)
        return holding

    async def _all_collection_ids(self, request: Request) -> list[str]:
        collections = await self.all_collections(request=request)
        return [c["id"] for c in collections.get("collections", [])]

    async def _dispatch_search(
        self,
        request: Request,
        *,
        collections: list[str] | None,
        bbox: tuple[float, ...] | None,
        intersects: Mapping[str, Any] | None = None,
        ids: tuple[str, ...] | None = None,
        datetime_value: str | None,
        limit: int | None,
        token: str | None,
    ) -> DispatchOutcome:
        """A federated page, a mixed page, or an outcome with ``result=None`` meaning:
        nothing here is federated, let ``super()`` answer as usual — with
        ``effective_datetime`` in place of the raw value (M3-12).

        ``_partition_sources`` treats every *materialized* collection (M3-11a) as
        one of this platform's own — pgstac answers those exactly as it always
        answered a collection with no ``earthx:source`` at all. M3-13 replaces the
        old three-way split (all native / one federated alone / reject) with a
        general one: ``_partition_sources`` names every distinct *source* the
        search reaches, and a search touching more than one goes through
        ``_mixed_page`` — the two narrower branches below are exactly the
        ``len(sources) <= 1`` case of that same partition, kept as their own
        branches because they need neither a page token of their own nor a
        fan-out.
        """
        target_ids = collections or await self._all_collection_ids(request)
        infos = {cid: await self._source_info_of(cid, request) for cid in target_ids}
        sources = _partition_sources(target_ids, infos, datetime_value)
        ignored_filters, ignored_by_collection = _ignored_filters_of(sources)

        if len(sources) <= 1:
            if not sources:
                return DispatchOutcome(None, datetime_value, ignored_filters, ignored_by_collection)
            source = sources[0]
            searched = _collections_of(source)
            if isinstance(source, _NativeGroup):
                # A mixed token from an earlier page of the same paging sequence
                # (a source dropped out and the search is single-source again):
                # the native path below hands `token` straight to pgstac, which
                # would otherwise try to read our own base64 blob as its keyset
                # marker and answer with its own confusing internals rather than
                # our own `400` (adr/0005 rule III).
                bare = token[len("next:") :] if token is not None and token.startswith("next:") else token
                if bare is not None and is_mixed_token(bare):
                    raise _adapter_error_to_http(
                        InvalidQuery("page token is a mixed-search token, not valid for a single collection")
                    )
                return DispatchOutcome(
                    None, source.effective_datetime, ignored_filters, ignored_by_collection, searched=searched
                )
            page = await self._federated_page(
                source.collection_id,
                request,
                bbox=bbox,
                intersects=intersects,
                ids=ids,
                datetime_value=source.effective_datetime,
                limit=limit,
                token=token,
            )
            return DispatchOutcome(
                page, source.effective_datetime, ignored_filters, ignored_by_collection, searched=searched
            )

        try:
            # A broken page token (`decode_mixed_token`) or a malformed group query
            # (`_native_group_page`) is a client mistake, the same as it already was
            # for a single-collection search — not caught inside `_mixed_page` itself
            # because it happens before, or outside, any one source's own fan-out call.
            mixed = await self._mixed_page(
                sources, request, bbox=bbox, intersects=intersects, ids=ids, datetime_value=datetime_value,
                limit=limit, token=token,
            )
        except InvalidQuery as error:
            raise _adapter_error_to_http(error) from error
        return DispatchOutcome(
            mixed.page,
            datetime_value,
            ignored_filters,
            ignored_by_collection,
            mixed.incomplete,
            open_collections=mixed.open_collections,
        )

    async def _federated_page(
        self,
        collection_id: str,
        request: Request,
        *,
        bbox: tuple[float, ...] | None,
        intersects: Mapping[str, Any] | None = None,
        ids: tuple[str, ...] | None = None,
        datetime_value: str | None,
        limit: int | None,
        token: str | None,
    ) -> ItemCollection:
        try:
            page = await self._federated_search_raw(
                collection_id, request, bbox=bbox, intersects=intersects, ids=ids,
                datetime_value=datetime_value, limit=limit, token=token,
            )
        except (
            InvalidQuery,
            UnsupportedFilter,
            UnknownCollection,
            UpstreamError,
            UpstreamTimeout,
            UpstreamUnreachable,
        ) as error:
            raise _adapter_error_to_http(error) from error
        return await self._to_item_collection(page, request, collection_id=collection_id)

    async def _federated_search_raw(
        self,
        collection_id: str,
        request: Request,
        *,
        bbox: tuple[float, ...] | None,
        intersects: Mapping[str, Any] | None,
        ids: tuple[str, ...] | None,
        datetime_value: str | None,
        limit: int | None,
        token: str | None,
    ) -> ItemPage:
        """The adapter's own answer, with none of its exceptions caught.

        Split out of ``_federated_page`` (M3-13) so a mixed search's fan-out can
        tell a client mistake (``InvalidQuery``/``UnsupportedFilter`` — the whole
        request is wrong, not just this source) from a source that is merely
        unavailable right now (``UpstreamError`` and friends — this one source
        becomes an ``incomplete_collections`` entry, the rest still answer);
        ``_federated_page`` above turns every one of them into the single
        request's own ``HTTPException``, the shape a lone federated search
        already had before this task.
        """
        # M3-08 finding: `SearchParams(...)` used to be built *outside* the caller's
        # try block, so its own `InvalidQuery` (bbox/time checks, now also
        # intersects/ids) never reached `_adapter_error_to_http` and propagated as
        # an unhandled `500` instead of the `400` it was always meant to be.
        start, end = _datetime_bounds(datetime_value)
        params = SearchParams(
            bbox=tuple(bbox) if bbox else None,
            intersects=intersects,
            ids=ids,
            start=start,
            end=end,
            limit=limit or SearchParams().limit,
            page_token=_strip_forward_token(token),
        )
        async with _cache_for(request) as cache:
            return await adapter_search_items(collection_id, params, gateway=_gateway_of(request), cache=cache)

    async def _native_group_page(
        self,
        group: _NativeGroup,
        request: Request,
        *,
        bbox: tuple[float, ...] | None,
        intersects: Mapping[str, Any] | None,
        ids: tuple[str, ...] | None,
        limit: int,
        marker: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """One page of this platform's own items, for one group of collections
        (M3-13). Reaches pgstac only through ``super().post_search`` (rule I) —
        never ``_search_base`` directly — the same public entry point a lone
        native search already went through before this task; the group's
        ``collections``/``limit``/``token`` are simply this call's own, not the
        whole request's. A malformed group query (should not happen: every
        input already passed ``SearchParams``' own checks for the search as a
        whole) is a client mistake here too, so it becomes ``InvalidQuery``
        rather than an unhandled ``500`` — a genuine failure of *our own*
        database, by contrast, is left to propagate and fail the whole request
        (plan §4.4: no partial result for that).
        """
        try:
            model = self.pgstac_search_model(
                collections=list(group.ids),
                bbox=bbox,
                intersects=intersects,
                ids=list(ids) if ids else None,
                datetime=group.effective_datetime,
                limit=limit,
                token=None if marker is None else f"next:{marker}",
            )
        except (ValidationError, ValueError) as error:
            raise InvalidQuery(str(error)) from error
        result = await super().post_search(model, request)
        features = result.get("features") or []
        return list(features), _extract_next_marker(result.get("links"))

    async def _mixed_page(
        self,
        sources: list[_Source],
        request: Request,
        *,
        bbox: tuple[float, ...] | None,
        intersects: Mapping[str, Any] | None,
        ids: tuple[str, ...] | None,
        datetime_value: str | None,
        limit: int | None,
        token: str | None,
    ) -> _MixedResult:
        """One page of a search spanning more than one source (M3-13 §3, Option 1):
        every still-open source is asked in parallel, each for its own share of
        ``limit`` — recomputed every page, so a source that still has more once
        another runs out gets the room the finished one no longer needs, instead
        of a page that only ever shrinks (the fixed-share alternative).
        """
        collection_ids = tuple(cid for source in sources for cid in _collections_of(source))
        fingerprint = mixed_fingerprint(collection_ids, bbox, intersects, ids, datetime_value)
        known_source_keys = {source.key for source in sources}
        by_key = {source.key: source for source in sources}

        stripped_token = _strip_forward_token(token)
        if stripped_token is None:
            pending: dict[str, str | None] = {source.key: None for source in sources}
            failed: dict[str, str] = {}
        else:
            pending, failed = decode_mixed_token(stripped_token, fingerprint, known_source_keys, set(collection_ids))

        to_query = [by_key[key] for key in pending]
        page_limit = limit if limit is not None else SearchParams().limit
        shares = dict(zip((source.key for source in to_query), compute_shares(page_limit, len(to_query)), strict=True))

        async def run(source: _Source) -> tuple[list[dict[str, Any]], str | None, str | None]:
            """``(features, next inner marker, failure reason)``."""
            share = shares[source.key]
            marker = pending[source.key]
            if share <= 0:
                # Plan §4.2 step 3: no share this page, no call — carried forward
                # unchanged by the caller below.
                return [], marker, None
            if isinstance(source, _NativeGroup):
                features, next_marker = await self._native_group_page(
                    source, request, bbox=bbox, intersects=intersects, ids=ids, limit=share, marker=marker
                )
                return features, next_marker, None
            try:
                page = await asyncio.wait_for(
                    self._federated_search_raw(
                        source.collection_id, request, bbox=bbox, intersects=intersects, ids=ids,
                        datetime_value=source.effective_datetime, limit=share, token=marker,
                    ),
                    # Read off the module, not a name imported at load time
                    # (`from ... import SOURCE_TIMEOUT_S`): a test's monkeypatch of
                    # `mixed_search.SOURCE_TIMEOUT_S` would otherwise never reach a
                    # constant this module already bound its own copy of.
                    timeout=mixed_search.SOURCE_TIMEOUT_S,
                )
            except (InvalidQuery, UnsupportedFilter, UnknownCollection) as error:
                # A client mistake, not a source outage — fails the whole request,
                # the same as a lone federated search would (`_federated_page`).
                raise _adapter_error_to_http(error) from error
            except TimeoutError:
                return [], None, REASON_TIMEOUT
            except UpstreamTimeout:
                return [], None, REASON_TIMEOUT
            except UpstreamUnreachable:
                return [], None, REASON_UNREACHABLE
            except UpstreamError:
                return [], None, REASON_UPSTREAM_ERROR
            except UpstreamShapeError:
                return [], None, REASON_UNRECOGNISED_ANSWER
            item_collection = await self._to_item_collection(page, request, collection_id=source.collection_id)
            return item_collection["features"], page.next_page_token, None

        tasks = [asyncio.ensure_future(run(source)) for source in to_query]
        try:
            outcomes = await asyncio.gather(*tasks)
        except BaseException:
            # A client-mistake `HTTPException` from one source must not leave the
            # others running past the response that already failed the request.
            for task in tasks:
                task.cancel()
            raise

        combined_features: list[dict[str, Any]] = []
        next_pending: dict[str, str | None] = {}
        newly_failed: dict[str, str] = {}
        for source, (features, next_marker, reason) in zip(to_query, outcomes, strict=True):
            combined_features.extend(features)
            if reason is not None:
                newly_failed[source.key] = reason
            elif next_marker is not None:
                next_pending[source.key] = next_marker
            elif shares[source.key] <= 0:
                next_pending[source.key] = pending[source.key]
            # else: queried, no error, no further marker — this source is done.

        failed_total = {**failed, **newly_failed}
        links: list[dict[str, Any]] = []
        if next_pending:
            next_token = encode_mixed_token(fingerprint, next_pending, failed_total)
            links = await PagingLinks(request=request, next=next_token, prev=None).get_links()
        page: ItemCollection = cast(
            ItemCollection,
            {
                "type": "FeatureCollection",
                "features": combined_features,
                "links": links,
                "numberReturned": len(combined_features),
            },
        )
        incomplete = tuple(
            IncompleteSource(collection=collection_id, reason=reason)
            for collection_id, reason in sorted(failed_total.items())
        )
        open_collections = tuple(cid for source in sources if source.key in next_pending for cid in _collections_of(source))
        return _MixedResult(page=page, incomplete=incomplete, open_collections=open_collections)

    async def _to_item_collection(
        self, page: ItemPage, request: Request, *, collection_id: str
    ) -> ItemCollection:
        links = await PagingLinks(request=request, next=page.next_page_token, prev=None).get_links()
        features = []
        for raw_item in page.items:
            item = dict(raw_item)
            # The same rewrite `get_item` does for a single item: our own self/
            # parent/root/collection links replace whatever the source's own item
            # carried (`ItemLinks.get_links` drops INFERRED_LINK_RELS from
            # `extra_links`) — without this, a search or item_collection answer
            # leaks the source's own address in every feature (M2-09b, Otto's
            # local check against the real EOPF source; the same gap exists for
            # Earth Search, whose synthetic search fixtures happened not to carry
            # per-item links and so never showed it).
            item["links"] = await ItemLinks(
                collection_id=collection_id, item_id=item["id"], request=request
            ).get_links(extra_links=item.get("links"))
            features.append(item)
        result: ItemCollection = cast(
            ItemCollection,
            {
                "type": "FeatureCollection",
                "features": features,
                "links": links,
                "numberReturned": len(page.items),
            },
        )
        if page.matched is not None:
            # Left out entirely rather than guessed at from the page size: a source
            # without a checked total (adr/0007 §12.6) must not look like one that
            # answered "10 of 10" (`numberMatched` is NotRequired on this type).
            result["numberMatched"] = page.matched
        return result
