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

import logging
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
    UpstreamShapeError,
)
from earthx.adapters import get_item as adapter_get_item
from earthx.adapters import search_items as adapter_search_items
from earthx.catalog.registry import AdapterKind
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


def _reject_disallowed_keys(keys: object) -> None:
    found = sorted(_DISALLOWED_QUERY_KEYS.intersection(keys))
    if found:
        raise HTTPException(
            status_code=400,
            detail=f"{', '.join(found)} is not available in M1 (adr/0005 rule VI; docs/plans/m1-07-stac-api.md §6)",
        )


async def _reject_disallowed_body(request: Request) -> None:
    if request.method != "POST":
        return
    body = await request.json()
    if isinstance(body, dict):
        _reject_disallowed_keys(body.keys())


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


def _adapter_error_to_http(error: Exception) -> HTTPException:
    """Our own upstream errors, in the shape a STAC client already expects.

    Never re-raises the source's own error text (adr/0005 rule III) — only its
    status, which ``gateway.UpstreamError`` already carries unchanged (M1-03).
    """
    if isinstance(error, InvalidQuery):
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
        adapter = await self._adapter_of(collection_id, request)
        if adapter is None:
            return await super().item_collection(
                collection_id, request, bbox=bbox, datetime=datetime, limit=limit, token=token, **kwargs
            )
        # Not `kwargs.keys()`: a disabled extension's field is absent from the parsed
        # request model entirely, so it never reaches here as a keyword argument at
        # all — the same gap `post_search`/`get_search` close by looking at the raw
        # request instead of the already-filtered method arguments.
        _reject_disallowed_keys(request.query_params.keys())
        result = await self._federated_page(
            collection_id, request, bbox=bbox, datetime_value=datetime, limit=limit, token=token
        )
        result["links"] = await ItemCollectionLinks(collection_id=collection_id, request=request).get_links(
            extra_links=result["links"]
        )
        return result

    async def get_item(self, item_id: str, collection_id: str, request: Request, **kwargs: Any) -> Item:
        adapter = await self._adapter_of(collection_id, request)
        if adapter is None:
            return await super().get_item(item_id, collection_id, request, **kwargs)
        try:
            async with _cache_for(request) as cache:
                item = await adapter_get_item(
                    collection_id, item_id, gateway=_gateway_of(request), cache=cache
                )
        except (InvalidQuery, UnknownCollection, UpstreamError, UpstreamTimeout, UpstreamUnreachable) as error:
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
        result = await self._dispatch_search(
            request,
            collections=collections,
            bbox=bbox,
            datetime_value=search_request.datetime,
            limit=search_request.limit,
            token=search_request.token,
        )
        if result is None:
            return await super().post_search(search_request, request, **kwargs)
        result["links"] = await SearchLinks(request=request).get_links(extra_links=result["links"])
        return result

    async def get_search(
        self,
        request: Request,
        collections: list[str] | None = None,
        bbox: tuple[float, ...] | None = None,
        datetime: str | None = None,
        limit: int | None = None,
        token: str | None = None,
        **kwargs: Any,
    ) -> ItemCollection:
        _reject_disallowed_keys(request.query_params.keys())
        result = await self._dispatch_search(
            request, collections=collections, bbox=bbox, datetime_value=datetime, limit=limit, token=token
        )
        if result is None:
            return await super().get_search(
                request, collections=collections, bbox=bbox, datetime=datetime, limit=limit, token=token, **kwargs
            )
        result["links"] = await SearchLinks(request=request).get_links(extra_links=result["links"])
        return result

    # -- dispatch -----------------------------------------------------------------

    async def _adapter_of(self, collection_id: str, request: Request) -> AdapterKind | None:
        """``earthx:source.adapter`` of a collection pgstac already knows about.

        Reuses ``super().get_collection`` on purpose: an unknown collection raises
        pgstac's own ``NotFoundError`` here exactly as it would for ``GET
        /collections/{id}`` (adr/0005 rule I) — there is no second lookup to keep
        in sync with it.
        """
        collection = await self.get_collection(collection_id, request=request)
        source = collection.get("earthx:source")
        if not isinstance(source, dict):
            return None
        try:
            return AdapterKind(source.get("adapter"))
        except ValueError:
            return None

    async def _all_collection_ids(self, request: Request) -> list[str]:
        collections = await self.all_collections(request=request)
        return [c["id"] for c in collections.get("collections", [])]

    async def _dispatch_search(
        self,
        request: Request,
        *,
        collections: list[str] | None,
        bbox: tuple[float, ...] | None,
        datetime_value: str | None,
        limit: int | None,
        token: str | None,
    ) -> ItemCollection | None:
        """``None`` means: nothing here is federated, let ``super()`` answer as usual."""
        target_ids = collections or await self._all_collection_ids(request)
        federated_ids = [cid for cid in target_ids if await self._adapter_of(cid, request) is not None]
        native_ids = [cid for cid in target_ids if cid not in federated_ids]

        if not federated_ids:
            return None

        if len(federated_ids) == 1 and not native_ids:
            # The one path M1's registry (one dataset) ever reaches.
            return await self._federated_page(
                federated_ids[0], request, bbox=bbox, datetime_value=datetime_value, limit=limit, token=token
            )

        # More than one source active at once (several federated collections, or a
        # mix of federated and native): rejected rather than merged. A merge across
        # heterogeneous sources needs a real second dataset to build and test
        # against (M2) - not reachable at all with today's registry (one dataset),
        # so a best-effort concatenation nobody could verify stayed correct would
        # only look tested. Otto, before merge (docs/ENTSCHEIDUNGSLOG.md).
        LOGGER.warning("rejected a search spanning more than one source at once: %s", target_ids)
        raise HTTPException(
            status_code=400,
            detail="a search spanning more than one source is not supported yet; name exactly one collection",
        )

    async def _federated_page(
        self,
        collection_id: str,
        request: Request,
        *,
        bbox: tuple[float, ...] | None,
        datetime_value: str | None,
        limit: int | None,
        token: str | None,
    ) -> ItemCollection:
        start, end = _datetime_bounds(datetime_value)
        params = SearchParams(
            bbox=tuple(bbox) if bbox else None,
            start=start,
            end=end,
            limit=limit or SearchParams().limit,
            page_token=_strip_forward_token(token),
        )
        try:
            async with _cache_for(request) as cache:
                page = await adapter_search_items(
                    collection_id, params, gateway=_gateway_of(request), cache=cache
                )
        except (InvalidQuery, UnknownCollection, UpstreamError, UpstreamTimeout, UpstreamUnreachable) as error:
            raise _adapter_error_to_http(error) from error
        return await self._to_item_collection(page, request)

    async def _to_item_collection(self, page: ItemPage, request: Request) -> ItemCollection:
        links = await PagingLinks(request=request, next=page.next_page_token, prev=None).get_links()
        return cast(
            ItemCollection,
            {
                "type": "FeatureCollection",
                "features": [dict(item) for item in page.items],
                "links": links,
                "numberMatched": page.matched if page.matched is not None else len(page.items),
                "numberReturned": len(page.items),
            },
        )
