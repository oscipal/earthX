"""STAC Collection Search with ``q`` on ``/stac/collections`` (adr/0026 §4.5, F6, F9; M5-22 plan §3.7).

``GET`` takes ``q``, ``bbox``, ``datetime``, ``limit`` and ``offset``; ``POST`` takes the same in its body and an area
as ``intersects`` as well (F6), so that this platform's own frontend never puts an area in a URL. Without any
parameter the answer is the list of every collection as before (plan A5); that path stays in
:class:`~earthx.api.federating_client.FederatingCoreCrudClient`.

Everything else asks :func:`~earthx.catalog.search.search_datasets` for the ids, in rank order with text and by id
without (plan A6), and fetches the collection documents of one page from pgstac. With ``q`` a page holds at most
:data:`MAX_TEXT_PAGE` collections, whatever ``limit`` asks (plan A5); without, a page holds every match unless
``limit`` says less. The answer carries no score.

``q`` is no free-text query in the sense of the Free-text extension: commas are ordinary separators, and the ranked
search also lists datasets without a word in common with the query. The landing page therefore claims Collection
Search but not Free-text (adr/0026 §4.5). Nothing here logs ``q`` or an area (plan §3.7).
"""

from __future__ import annotations

import json
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

from earthx.catalog.search import MAX_QUERY_CHARS, SearchResult, box_area, search_datasets

#: adr/0026 §4.4: at most 20 hits per page of a text search.
MAX_TEXT_PAGE = 20
#: The most collections one page lists, the cap of the library (``stac_fastapi.types.search.Limit``).
MAX_PAGE = 10_000

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
    limit: Annotated[int | None, Query(ge=1, description="Collections per page.")] = attr.ib(default=None)
    offset: Annotated[int | None, Query(ge=0, description="Collections to skip.")] = attr.ib(default=None)


class CollectionsPostRequest(BaseModel):
    """The body of ``POST /stac/collections``; a field it does not know is a ``400``."""

    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(None, description=Q_DESCRIPTION)
    bbox: list[float] | None = Field(None, description=_BBOX_DESCRIPTION + " Mutually exclusive with `intersects`.")
    intersects: Intersection | None = Field(None, description="Only datasets whose coverage meets this geometry.")
    datetime: str | None = Field(None, description=_DATETIME_DESCRIPTION)
    limit: int | None = Field(None, ge=1, description="Collections per page.")
    offset: int | None = Field(None, ge=0, description="Collections to skip.")


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
    """A checked search: text, area as GeoJSON, period with open ends as ``None``, and the page."""

    text: str | None
    area: Mapping[str, Any] | None
    period: tuple[Instant | None, Instant | None] | None
    limit: int
    offset: int


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


def read_query(
    *,
    q: str | None,
    bbox: Sequence[float] | str | None,
    intersects: Any | None,
    datetime: str | None,
    limit: int | None,
    offset: int | None,
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
    most = MAX_TEXT_PAGE if text is not None else MAX_PAGE
    return CollectionQuery(
        text=text,
        area=area,
        period=_period(datetime),
        limit=min(limit or most, most),
        offset=offset or 0,
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


def _next_link(request: Request, body: Mapping[str, Any] | None, offset: int) -> dict[str, Any]:
    if body is None:
        return {
            "rel": "next",
            "type": "application/json",
            "method": "GET",
            "href": merge_params(str(request.url), {"offset": [str(offset)]}),
        }
    return {
        "rel": "next",
        "type": "application/json",
        "method": "POST",
        "href": str(request.url),
        "body": {**body, "offset": offset},
    }


async def search_collections(
    request: Request, query: CollectionQuery, *, body: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """One page of collections for ``query``; ``body`` is the POST body a next page repeats (``None`` for ``GET``)."""
    async with request.app.state.earthx_cache_pool.connection() as conn:
        result: SearchResult = await search_datasets(conn, query.text, area=query.area, period=query.period)
    page = result.ids[query.offset : query.offset + query.limit]
    collections = await _collections(request, page)
    links = await CollectionSearchPagingLinks(request=request).get_links()
    if query.offset + query.limit < len(result.ids):
        links.append(_next_link(request, body, query.offset + query.limit))
    answer: dict[str, Any] = {
        "collections": collections,
        "links": links,
        "numberMatched": len(result.ids),
        "numberReturned": len(collections),
    }
    ignored = {i: list(names) for i, names in result.ignored_filters_by_collection.items() if i in page}
    if ignored:
        answer["ignored_filters"] = sorted({name for names in ignored.values() for name in names})
        answer["ignored_filters_by_collection"] = ignored
    return answer
