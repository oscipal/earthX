"""STAC Collection Search with ``q`` on ``/stac/collections`` (adr/0026 §4.5, F6, F9; M5-22 plan §3.7).

``GET`` takes ``q``, ``bbox``, ``datetime``, ``region``, ``entry``, ``limit`` and ``token`` (``offset`` with ``q``);
``POST`` takes the same in its body and an area as ``intersects`` as well (F6), so that this platform's own frontend
never puts an area in a URL. Without any parameter the answer is the list of every full entry as before (plan A5);
that path stays in :class:`~earthx.api.federating_client.FederatingCoreCrudClient` until the frontend pages (M5-40
plan F2).

With ``q`` the ids come from :func:`~earthx.catalog.search.search_datasets` in rank order, full entries only until
M5-42 (M5-40 plan F7); a page holds at most :data:`MAX_TEXT_PAGE` collections and goes on by ``offset``. Without ``q``
full and listed entries come in one order, title then id (M5-40 plan F3): the full ones of the filter from the same
search, the listed ones a page at a time from ``earthx_listed_entry``; a page holds :data:`DEFAULT_PAGE` collections
unless ``limit`` says otherwise, at most :data:`MAX_LISTING_PAGE`, and goes on by the keyset ``token`` of its last
entry. ``numberMatched`` is exact up to :data:`MAX_COUNTED` and left out above (plan F4). The answer carries no score.

``q`` is no free-text query in the sense of the Free-text extension: commas are ordinary separators, and the ranked
search also lists datasets without a word in common with the query. The landing page therefore claims Collection
Search but not Free-text (adr/0026 §4.5). Nothing here logs ``q`` or an area (plan §3.7).
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime as Instant
from typing import Annotated, Any

import attr
from buildpg import render
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from stac_fastapi.extensions.collection_search import CollectionSearchPostExtension
from stac_fastapi.extensions.collection_search.collection_search import CollectionSearchConformanceClasses
from stac_fastapi.pgstac.models.links import CollectionLinks, CollectionSearchPagingLinks, merge_params
from stac_fastapi.types.config import ApiSettings
from stac_fastapi.types.rfc3339 import str_to_interval
from stac_fastapi.types.search import APIRequest
from stac_pydantic.api.search import Intersection

from earthx.catalog.listed_search import ListedFilter, count_listed, full_entries, listed_page
from earthx.catalog.search import MAX_QUERY_CHARS, SearchResult, box_area, search_datasets

#: adr/0026 §4.4: at most 20 hits per page of a text search.
MAX_TEXT_PAGE = 20
#: The most collections one page lists, the cap of the library (``stac_fastapi.types.search.Limit``): the answer without
#: any parameter until the frontend pages (M5-40 plan F2).
MAX_PAGE = 10_000
#: A page of the catalogue without text (M5-40 plan F3).
DEFAULT_PAGE = 100
MAX_LISTING_PAGE = 1_000
#: Up to here ``numberMatched`` is exact; above it the field is left out (M5-40 plan F4).
MAX_COUNTED = 10_000
#: The two kinds of entries a page can be held to (M5-40 plan F3).
ENTRY_KINDS = ("full", "listed")
_REGION = re.compile(r"[A-Z]{2}(-[A-Z0-9]{1,3})?")
_MAX_REGIONS = 50
_MAX_TOKEN = 1_000

Q_DESCRIPTION = (
    "Text to search the datasets for, German or English; typing errors and abbreviations are fine. Ranked by this "
    "platform's dataset search (full text with a glossary of terms, and trigrams for typing errors), not a Boolean "
    f"free-text query: a comma is an ordinary separator. At most {MAX_QUERY_CHARS} characters; only spaces is no "
    f"text. With text, a page holds at most {MAX_TEXT_PAGE} collections."
)
_BBOX_DESCRIPTION = (
    "Only datasets whose extent meets this box: west, south, east, north in degrees (WGS 84); a west edge east of the "
    "east edge crosses the antimeridian."
)
_REGION_DESCRIPTION = (
    "Only datasets in one of these regions: ISO 3166-1 codes of states, ISO 3166-2 codes of the subdivisions of DE, AT, "
    "CH and LI, separated by commas."
)
_ENTRY_DESCRIPTION = "Only full entries (with display) or only listed ones (a catalogue entry with a link)."
_TOKEN_DESCRIPTION = "The page after another, as its `next` link names it; without `q` only."
_DATETIME_DESCRIPTION = (
    "Only datasets whose time extent overlaps this instant or interval (RFC 3339, `..` for an open end). A dataset "
    "without a time axis stays and is named in `ignored_filters`."
)


@attr.s
class CollectionsGetRequest(APIRequest):
    """The query parameters of ``GET /stac/collections``; parsed and checked in :func:`read_query`."""

    q: Annotated[str | None, Query(description=Q_DESCRIPTION)] = attr.ib(default=None)
    bbox: Annotated[str | None, Query(description=_BBOX_DESCRIPTION)] = attr.ib(default=None)
    datetime: Annotated[str | None, Query(description=_DATETIME_DESCRIPTION)] = attr.ib(default=None)
    region: Annotated[str | None, Query(description=_REGION_DESCRIPTION)] = attr.ib(default=None)
    entry: Annotated[str | None, Query(description=_ENTRY_DESCRIPTION)] = attr.ib(default=None)
    limit: Annotated[int | None, Query(ge=1, description="Collections per page.")] = attr.ib(default=None)
    offset: Annotated[int | None, Query(ge=0, description="Collections to skip; with `q` only.")] = attr.ib(
        default=None
    )
    token: Annotated[str | None, Query(description=_TOKEN_DESCRIPTION)] = attr.ib(default=None)


class CollectionsPostRequest(BaseModel):
    """The body of ``POST /stac/collections``; a field it does not know is a ``400``."""

    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(None, description=Q_DESCRIPTION)
    bbox: list[float] | None = Field(None, description=_BBOX_DESCRIPTION + " Mutually exclusive with `intersects`.")
    intersects: Intersection | None = Field(None, description="Only datasets whose coverage meets this geometry.")
    datetime: str | None = Field(None, description=_DATETIME_DESCRIPTION)
    region: list[str] | None = Field(None, description=_REGION_DESCRIPTION.replace(", separated by commas", ""))
    entry: str | None = Field(None, description=_ENTRY_DESCRIPTION)
    limit: int | None = Field(None, ge=1, description="Collections per page.")
    offset: int | None = Field(None, ge=0, description="Collections to skip; with `q` only.")
    token: str | None = Field(None, description=_TOKEN_DESCRIPTION)


def collection_search_extension(client: Any, settings: ApiSettings) -> CollectionSearchPostExtension:
    """Collection Search with ``GET`` and ``POST``; its conformance classes are those of Collection Search alone."""
    return CollectionSearchPostExtension(
        client=client,
        settings=settings,
        GET=CollectionsGetRequest,
        POST=CollectionsPostRequest,
        conformance_classes=[
            CollectionSearchConformanceClasses.COLLECTIONSEARCH.value,
            CollectionSearchConformanceClasses.BASIS.value,
        ],
    )


def keep_searches_out_of_errors(app: FastAPI, path: str) -> None:
    """A malformed request to ``path`` gets a ``400`` that repeats none of its input.

    The handler of stac-fastapi answers with the body and the value of every field it refused, which for a search
    are the text and the area. Every other route keeps that answer.
    """
    previous = app.exception_handlers[RequestValidationError]

    async def handler(request: Request, error: Exception) -> Any:
        if request.url.path != path or not isinstance(error, RequestValidationError):
            return await _maybe_await(previous(request, error))
        fields = [{"loc": problem["loc"], "msg": problem["msg"], "type": problem["type"]} for problem in error.errors()]
        return JSONResponse(content=jsonable_encoder({"detail": fields}), status_code=400)

    app.add_exception_handler(RequestValidationError, handler)


async def _maybe_await(value: Any) -> Any:
    return await value if hasattr(value, "__await__") else value


@dataclass(frozen=True, slots=True)
class CollectionQuery:
    """A checked search: text, area as GeoJSON, period with open ends as ``None``, regions, kind of entry, and the page:
    ``offset`` with text, ``after`` (the key of the last entry of the page before) without."""

    text: str | None
    area: Mapping[str, Any] | None
    period: tuple[Instant | None, Instant | None] | None
    limit: int
    offset: int
    regions: tuple[str, ...] = ()
    entry: str | None = None
    after: tuple[str, str] | None = None


def _bad(detail: str) -> HTTPException:
    # No message names a coordinate or the text: an error body is no place for either (projektplan.md 7, point 6).
    return HTTPException(status_code=400, detail=detail)


def _box(values: Sequence[float]) -> Mapping[str, Any]:
    if len(values) == 6:
        values = (values[0], values[1], values[3], values[4])
    if len(values) != 4:
        raise _bad("bbox needs four values: west, south, east, north")
    west, south, east, north = values
    if not all(-180.0 <= value <= 180.0 for value in (west, east)):
        raise _bad("bbox longitudes are outside ±180")
    if not all(-90.0 <= value <= 90.0 for value in (south, north)):
        raise _bad("bbox latitudes are outside ±90")
    if south > north:
        raise _bad("bbox is upside down: south is above north")
    if west <= east:
        return box_area(west, south, east, north)
    # Across the antimeridian: the part up to 180° E and the part from 180° W.
    halves = [box_area(west, south, 180.0, north), box_area(-180.0, south, east, north)]
    return {"type": "MultiPolygon", "coordinates": [half["coordinates"] for half in halves]}


def _positions(node: Any) -> list[Sequence[float]]:
    if isinstance(node, Sequence) and node and all(isinstance(value, int | float) for value in node):
        return [node]
    if isinstance(node, Sequence):
        return [position for child in node for position in _positions(child)]
    return []


def _check_positions(geometry: Mapping[str, Any]) -> None:
    for part in geometry.get("geometries", []):
        _check_positions(part)
    for position in _positions(geometry.get("coordinates", [])):
        if not (-180.0 <= position[0] <= 180.0 and -90.0 <= position[1] <= 90.0):
            raise _bad("intersects has a position outside ±180 / ±90")


def _geometry(geometry: Any) -> Mapping[str, Any]:
    dumped = geometry.model_dump(mode="json", exclude_none=True)
    _check_positions(dumped)
    return dumped


def _bbox_param(value: str) -> list[float]:
    try:
        return [float(part) for part in value.split(",")]
    except ValueError:
        raise _bad("bbox is a list of numbers separated by commas") from None


def _period(value: str | None) -> tuple[Instant | None, Instant | None] | None:
    if value is None:
        return None
    parsed = str_to_interval(value)  # a 400 of its own for a malformed or reversed interval
    if parsed is None:
        return None
    return parsed if isinstance(parsed, tuple) else (parsed, parsed)


def _regions(value: Sequence[str] | str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    codes = [code.strip() for code in value.split(",")] if isinstance(value, str) else list(value)
    if not codes or len(codes) > _MAX_REGIONS or not all(isinstance(c, str) and _REGION.fullmatch(c) for c in codes):
        raise _bad(f"region is a list of at most {_MAX_REGIONS} ISO 3166 codes")
    return tuple(sorted(set(codes)))


def encode_token(key: tuple[str, str]) -> str:
    """The ``token`` of the page after the entry with this key: opaque to a client, nothing secret in it."""
    return base64.urlsafe_b64encode(json.dumps(list(key), ensure_ascii=False).encode("utf-8")).decode("ascii")


def _decode_token(token: str) -> tuple[str, str]:
    if len(token) > _MAX_TOKEN:
        raise _bad("token is not one this API gave out")
    try:
        key = json.loads(base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8"))
    except (UnicodeError, binascii.Error, ValueError):
        raise _bad("token is not one this API gave out") from None
    if not (isinstance(key, list) and len(key) == 2 and all(isinstance(part, str) for part in key)):
        raise _bad("token is not one this API gave out")
    return key[0], key[1]


def read_query(
    *,
    q: str | None,
    bbox: Sequence[float] | str | None,
    intersects: Any | None,
    datetime: str | None,
    limit: int | None,
    offset: int | None,
    region: Sequence[str] | str | None = None,
    entry: str | None = None,
    token: str | None = None,
) -> CollectionQuery:
    """The checked search of one request; anything that is no valid search is a ``400``."""
    if q is not None and len(q) > MAX_QUERY_CHARS:
        raise _bad(f"q is longer than {MAX_QUERY_CHARS} characters")
    text = q if q is not None and q.strip() else None
    if bbox is not None and intersects is not None:
        raise _bad("bbox and intersects ask two different questions; send one")
    area = None
    if bbox is not None:
        area = _box(_bbox_param(bbox) if isinstance(bbox, str) else bbox)
    elif intersects is not None:
        area = _geometry(intersects)
    if entry is not None and entry not in ENTRY_KINDS:
        raise _bad(f"entry is one of {', '.join(ENTRY_KINDS)}")
    if text is not None:
        if token is not None:
            raise _bad("with q, pages go by offset, not by token")
        return CollectionQuery(
            text=text,
            area=area,
            period=_period(datetime),
            limit=min(limit or MAX_TEXT_PAGE, MAX_TEXT_PAGE),
            offset=offset or 0,
            regions=_regions(region),
            entry=entry,
        )
    if offset is not None:
        raise _bad("without q, pages go by the token of the next link, not by offset")
    return CollectionQuery(
        text=None,
        area=area,
        period=_period(datetime),
        limit=min(limit or DEFAULT_PAGE, MAX_LISTING_PAGE),
        offset=0,
        regions=_regions(region),
        entry=entry,
        after=None if token is None else _decode_token(token),
    )


async def _collections(request: Request, ids: Sequence[str]) -> list[dict[str, Any]]:
    """The collection documents of ``ids`` from pgstac, in that order, with the links of ``/collections``."""
    if not ids:
        return []
    async with request.app.state.get_connection(request, "r") as conn:
        statement, values = render(
            "SELECT * FROM collection_search(:req::text::jsonb);",
            req=json.dumps({"ids": list(ids), "limit": len(ids)}),
        )
        found = await conn.fetchval(statement, *values)
    by_id = {collection["id"]: collection for collection in found["collections"]}
    # A dataset that a catalogue load removed between the search and this read is no longer a collection.
    collections = [by_id[dataset_id] for dataset_id in ids if dataset_id in by_id]
    for collection in collections:
        collection["links"] = await CollectionLinks(collection_id=collection["id"], request=request).get_links(
            extra_links=collection.get("links")
        )
        collection.pop("parent_ids", None)
    return collections


def _next_link(request: Request, body: Mapping[str, Any] | None, name: str, value: int | str) -> dict[str, Any]:
    """The link to the next page: the same search with ``name`` (``offset`` or ``token``) set to ``value``."""
    if body is None:
        return {
            "rel": "next",
            "type": "application/json",
            "method": "GET",
            "href": merge_params(str(request.url), {name: [str(value)]}),
        }
    return {
        "rel": "next",
        "type": "application/json",
        "method": "POST",
        "href": str(request.url),
        "body": {**body, name: value},
    }


async def _with_links(request: Request, collection: dict[str, Any]) -> dict[str, Any]:
    collection["links"] = await CollectionLinks(collection_id=collection["id"], request=request).get_links(
        extra_links=collection.get("links")
    )
    return collection


async def search_collections(
    request: Request, query: CollectionQuery, *, body: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """One page of collections for ``query``; ``body`` is the POST body a next page repeats (``None`` for ``GET``)."""
    if query.text is None:
        return await _catalogue_page(request, query, body=body)
    async with request.app.state.earthx_cache_pool.connection() as conn:
        result: SearchResult = await search_datasets(conn, query.text, area=query.area, period=query.period)
        ids = result.ids if query.entry != "listed" else ()
        if query.regions and ids:
            kept = {dataset_id for _, dataset_id in await full_entries(conn, ids, query.regions)}
            ids = tuple(dataset_id for dataset_id in ids if dataset_id in kept)
    page = ids[query.offset : query.offset + query.limit]
    collections = await _collections(request, page)
    links = await CollectionSearchPagingLinks(request=request).get_links()
    if query.offset + query.limit < len(ids):
        links.append(_next_link(request, body, "offset", query.offset + query.limit))
    answer: dict[str, Any] = {
        "collections": collections,
        "links": links,
        "numberMatched": len(ids),
        "numberReturned": len(collections),
    }
    _add_ignored(answer, {i: names for i, names in result.ignored_filters_by_collection.items() if i in page})
    return answer


def _add_ignored(answer: dict[str, Any], ignored: Mapping[str, Sequence[str]]) -> None:
    if ignored:
        answer["ignored_filters"] = sorted({name for names in ignored.values() for name in names})
        answer["ignored_filters_by_collection"] = {i: list(names) for i, names in ignored.items()}


async def _catalogue_page(
    request: Request, query: CollectionQuery, *, body: Mapping[str, Any] | None
) -> dict[str, Any]:
    """One page of full and listed entries in the order of the catalogue (M5-40 plan F3), without text.

    The full entries of the filter (few) are all known before the page; the listed ones are read a page at a time,
    one more than the page holds, so that the answer knows whether a next page exists without counting.
    """
    where = ListedFilter(area=query.area, period=query.period, regions=query.regions)
    full: list[tuple[str, str]] = []
    ignored: dict[str, tuple[str, ...]] = {}
    async with request.app.state.earthx_cache_pool.connection() as conn:
        if query.entry != "listed":
            result: SearchResult = await search_datasets(conn, None, area=query.area, period=query.period)
            full = await full_entries(conn, result.ids, query.regions)
            ignored.update(result.ignored_filters_by_collection)
        listed = (
            [] if query.entry == "full" else await listed_page(conn, where, after=query.after, limit=query.limit + 1)
        )
        full_after = [key for key in full if query.after is None or key > query.after]
        merged = sorted(
            [(key, None) for key in full_after] + [((row.sort_title, row.dataset_id), row) for row in listed]
        )
        page, more = merged[: query.limit], len(merged) > query.limit
        matched: int | None = len(full)
        if query.entry != "full":
            counted = (
                await count_listed(conn, where, cap=MAX_COUNTED + 1 - len(full)) if len(full) <= MAX_COUNTED else 0
            )
            matched = len(full) + counted if len(full) + counted <= MAX_COUNTED else None
    documents = {c["id"]: c for c in await _collections(request, [key[1] for key, row in page if row is None])}
    collections = []
    for (_, dataset_id), row in page:
        if row is None:
            if dataset_id in documents:
                collections.append(documents[dataset_id])
            continue
        collections.append(await _with_links(request, row.content))
        if row.period_ignored:
            ignored[dataset_id] = ("datetime",)
    links = await CollectionSearchPagingLinks(request=request).get_links()
    if more and page:
        links.append(_next_link(request, body, "token", encode_token(page[-1][0])))
    answer: dict[str, Any] = {"collections": collections, "links": links, "numberReturned": len(collections)}
    if matched is not None:
        answer["numberMatched"] = matched
    _add_ignored(answer, {i: names for i, names in ignored.items() if i in {c["id"] for c in collections}})
    return answer
