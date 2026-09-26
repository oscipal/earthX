"""earthx's outward STAC API: collections from pgstac, items federated (adr/0005).

``FederatingCoreCrudClient`` overrides only the four public search/item methods of
``CoreCrudClient`` (rule I, option 2 of adr/0005 §4) — never ``_search_base``, pgstac's
own SQL path, which stays untouched for a collection it actually holds items for. Per
collection, ``earthx:source`` — read off the very document pgstac itself just returned,
so an unknown collection is still pgstac's own 404 (rule I) — decides whether a call
goes to ``super()`` or to ``earthx.adapters``.

The gateway and the search-cache pool are not constructor arguments: ``instantiate_api``
builds this client itself (``client(pgstac_search_model=...)``), so there is nowhere to
hand them in at construction time. They live on ``request.app.state`` instead, set once
by the process lifespan in ``earthx.api.main`` — the same place pgstac's own connection
pool already lives (``request.app.state.get_connection``).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import HTTPException, Request
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
from earthx.adapters import get_item as adapter_get_item
from earthx.adapters import search_items as adapter_search_items
from earthx.catalog.registry import ItemHolding
from earthx.catalog.search_cache import PostgresSearchCache
from earthx.gateway import UpstreamError, UpstreamTimeout, UpstreamUnreachable

LOGGER = logging.getLogger("earthx.api.federating_client")

# adr/0005 rule VI treats `filter`/CQL2 this way; the plan (docs/plans/
# m1-07-stac-api.md §6, F2) extends the same reasoning to `sort`: the federated path
# cannot yet honour a client-chosen field, so neither extension is enabled
# (earthx/api/main.py). This is the other half of "not silently dropped": the request
# models simply do not declare these fields when the extension is off, so without this
# check pydantic's `extra="ignore"` (or FastAPI ignoring an undeclared query parameter)
# would swallow them rather than reject them.
_DISALLOWED_QUERY_KEYS = frozenset({"filter", "filter-lang", "filter_lang", "sortby"})

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

    A search naming one collection with a time axis and one without is not
    decided yet (M3-13) and does not reach this function today: the caller only
    gathers ``time_ranges`` for the collections a single answer will actually
    come from — one federated collection alone, or every native/materialized
    one together — and ``_dispatch_search``'s own mixed-source rejection covers
    every other combination before this runs.
    """
    if datetime_value is None:
        return None, ()
    _datetime_bounds(datetime_value)
    if time_ranges and not any(time_ranges):
        return None, ("datetime",)
    return datetime_value, ()


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
        try:
            async with _cache_for(request) as cache:
                item = await adapter_get_item(
                    collection_id, item_id, gateway=_gateway_of(request), cache=cache
                )
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
        result, effective_datetime, ignored_filters = await self._dispatch_search(
            request,
            collections=collections,
            bbox=bbox,
            intersects=_dump_intersects(search_request.intersects),
            ids=tuple(search_request.ids) if search_request.ids else None,
            datetime_value=search_request.datetime,
            limit=search_request.limit,
            token=search_request.token,
        )
        if result is None:
            if effective_datetime != search_request.datetime:
                search_request = search_request.model_copy(update={"datetime": effective_datetime})
            result = await super().post_search(search_request, request, **kwargs)
            if ignored_filters:
                result["ignored_filters"] = list(ignored_filters)
            return result
        if ignored_filters:
            result["ignored_filters"] = list(ignored_filters)
        result["links"] = await SearchLinks(request=request).get_links(extra_links=result["links"])
        return result

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
        result, effective_datetime, ignored_filters = await self._dispatch_search(
            request,
            collections=collections,
            bbox=bbox,
            intersects=_parse_intersects_param(intersects),
            ids=tuple(ids) if ids else None,
            datetime_value=datetime,
            limit=limit,
            token=token,
        )
        if result is None:
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
                datetime=effective_datetime,
                limit=limit,
                token=token,
                **kwargs,
            )
            if ignored_filters:
                result["ignored_filters"] = list(ignored_filters)
            return result
        if ignored_filters:
            result["ignored_filters"] = list(ignored_filters)
        result["links"] = await SearchLinks(request=request).get_links(extra_links=result["links"])
        return result

    # -- dispatch -----------------------------------------------------------------

    async def _source_info_of(self, collection_id: str, request: Request) -> tuple[ItemHolding, bool]:
        """``earthx:source.item_holding`` and ``earthx:capabilities.time_range`` of
        a collection pgstac already knows about, off the one document both live on.

        Reuses ``super().get_collection`` on purpose: an unknown collection raises
        pgstac's own ``NotFoundError`` here exactly as it would for ``GET
        /collections/{id}`` (adr/0005 rule I) — there is no second lookup to keep
        in sync with it.

        M3-11a (K-05): every collection in pgstac was written by ``catalog.load``
        from a registry entry, so ``item_holding`` is always present and one of the
        two values — never optional the way it is on a collection this platform did
        not write itself. A collection where it is missing or unrecognised is
        therefore a data problem (a stale document from before this field existed,
        or a collection nobody loaded through the registry), not a signal to guess:
        this raises rather than falling back to treating it as either kind, so a
        broken collection fails loudly instead of silently answering pgstac's own
        near-empty result for it (adr/0005 rule I).

        ``time_range`` (M3-12) is read the same way but fails safe rather than
        loudly when it is missing or not a plain bool: unlike ``item_holding``,
        nothing about *routing* depends on it, only whether a `datetime` filter is
        honoured — treating an unreadable value as "has a time axis" keeps a
        search filtered exactly as it always was, rather than turning a stale or
        foreign document into a new class of `500`.
        """
        collection = await self.get_collection(collection_id, request=request)
        source = collection.get("earthx:source")
        raw_holding = source.get("item_holding") if isinstance(source, dict) else None
        try:
            holding = ItemHolding(raw_holding)
        except ValueError:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"collection {collection_id!r} carries no valid earthx:source.item_holding "
                    "(not loaded from the registry? run `python -m earthx.catalog.load`)"
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
    ) -> tuple[ItemCollection | None, str | None, tuple[str, ...]]:
        """A federated page, or ``(None, effective_datetime, ignored_filters)``
        meaning: nothing here is federated, let ``super()`` answer as usual — with
        ``effective_datetime`` in place of the raw value (M3-12) and
        ``ignored_filters`` merged into whatever it returns.

        ``native_ids`` now also holds every *materialized* collection (M3-11a) —
        pgstac answers those exactly as it always answered a collection with no
        ``earthx:source`` at all, so the mixed-source rejection below covers a
        federated-plus-materialized search the same way it already covered
        federated-plus-federated.
        """
        target_ids = collections or await self._all_collection_ids(request)
        infos = {cid: await self._source_info_of(cid, request) for cid in target_ids}
        federated_ids = [cid for cid in target_ids if infos[cid][0] is ItemHolding.FEDERATED]
        native_ids = [cid for cid in target_ids if cid not in federated_ids]

        if not federated_ids:
            effective_datetime, ignored_filters = _apply_time_axis(
                datetime_value, [time_range for _, time_range in infos.values()]
            )
            return None, effective_datetime, ignored_filters

        if len(federated_ids) == 1 and not native_ids:
            effective_datetime, ignored_filters = _apply_time_axis(datetime_value, [infos[federated_ids[0]][1]])
            page = await self._federated_page(
                federated_ids[0],
                request,
                bbox=bbox,
                intersects=intersects,
                ids=ids,
                datetime_value=effective_datetime,
                limit=limit,
                token=token,
            )
            return page, effective_datetime, ignored_filters

        # More than one source active at once (several federated collections, or a
        # mix of federated and native): rejected rather than merged. A merge across
        # heterogeneous sources needs a real second dataset to build and test
        # against — with M2-09b's second federated dataset this branch is reachable
        # by *any* search that does not name a collection, not only the deliberate
        # multi-collection case M2's own tests still cover. A best-effort
        # concatenation nobody could verify stayed correct would only look tested.
        # Otto, before merge (docs/ENTSCHEIDUNGSLOG.md); M2-09b plan §10 F3 kept the
        # rejection and only sharpened the message below. Left unvalidated on
        # purpose (M3-12): a malformed `datetime` on a search this route rejects
        # anyway still gets *a* 400, just this one rather than a datetime-format one.
        LOGGER.warning("rejected a search spanning more than one source at once: %s", target_ids)
        raise HTTPException(
            status_code=400,
            detail=(
                "a search spanning more than one source is not supported yet; "
                f"name exactly one collection ({', '.join(sorted(federated_ids))})"
            ),
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
        start, end = _datetime_bounds(datetime_value)
        try:
            # M3-08 finding: `SearchParams(...)` used to be built *outside* this
            # try block, so its own `InvalidQuery` (bbox/time checks, now also
            # intersects/ids) never reached `_adapter_error_to_http` and propagated
            # as an unhandled `500` instead of the `400` it was always meant to be
            # — unnoticed because no integration test had exercised that path
            # through the real app before this task added one for `intersects`.
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
                page = await adapter_search_items(
                    collection_id, params, gateway=_gateway_of(request), cache=cache
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
