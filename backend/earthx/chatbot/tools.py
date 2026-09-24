"""The three read tools, and the one entry point a model would call them through.

Each tool is one or a few requests against the public STAC API, sent through the
gateway like any other outgoing request (KLAERUNGEN B8). The address of the API is
handed in; this module never learns it from anywhere else and never reaches the
platform in-process, so it has exactly the rights of an outside client.

``search_collections`` filters locally because the API offers no
``collection-search`` extension (api/main.py, ``_ENABLED_EXTENSIONS``). With a
handful of collections that is enough; M5's hybrid search replaces the filter and
keeps the signature (plan m7a §2).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from earthx.chatbot import summaries, validation
from earthx.chatbot.validation import InvalidArgument
from earthx.gateway import Gateway, GatewayError, UpstreamError

# The STAC API pages its collection list. Enough for any catalogue this tool is
# meant for; past that the answer says it stopped rather than fetching on.
MAX_COLLECTION_PAGES = 10
DEFAULT_SEARCH_LIMIT = 10
AVAILABILITY_SAMPLE = 10


class UnknownCollection(LookupError):
    """The API does not know this collection id."""


class CatalogTools:
    """The read tools, bound to one STAC API and one gateway."""

    def __init__(self, gateway: Gateway, stac_root: str) -> None:
        self._gateway = gateway
        self._root = stac_root.rstrip("/")

    async def search_collections(
        self,
        query: object = None,
        bbox: object = None,
        datetime: object = None,
        limit: object = None,
    ) -> dict[str, Any]:
        """Collections whose text contains every word of ``query`` and whose extent overlaps."""
        words = validation.query(query).lower().split()
        box = validation.bbox(bbox)
        bounds = validation.interval(datetime)
        count = validation.limit(limit, DEFAULT_SEARCH_LIMIT)
        collections, complete = await self._all_collections()
        hits = [c for c in collections if summaries.matches(c, words, box, bounds)]
        return {
            "collections": [summaries.collection_brief(c) for c in hits[:count]],
            "total_matches": len(hits),
            "catalogue_complete": complete,
        }

    async def get_collection(self, collection_id: object) -> dict[str, Any]:
        """Title, description, licence, extent and the ``earthx:`` fields of one collection."""
        cid = validation.collection_id(collection_id)
        try:
            response = await self._gateway.get(f"{self._root}/collections/{cid}")
        except UpstreamError as error:
            if error.status_code == 404:
                raise UnknownCollection(cid) from error
            raise
        return summaries.collection_detail(_object(response.json()))

    async def check_availability(self, collection_id: object, bbox: object, datetime: object) -> dict[str, Any]:
        """How many items of a collection fall into a box and an interval."""
        cid = validation.collection_id(collection_id)
        box = validation.bbox(bbox)
        bounds = validation.interval(datetime)
        if box is None or bounds is None:
            raise InvalidArgument("check_availability needs both bbox and datetime")
        body = {
            "collections": [cid],
            "bbox": list(box),
            "datetime": validation.stac_datetime(bounds),
            "limit": AVAILABILITY_SAMPLE,
        }
        try:
            # A search changes nothing, so repeating it after a 503 is safe.
            response = await self._gateway.post_json(f"{self._root}/search", json=body, retry=True)
        except UpstreamError as error:
            if error.status_code == 404:
                raise UnknownCollection(cid) from error
            raise
        return summaries.availability(cid, _object(response.json()))

    async def _all_collections(self) -> tuple[list[dict[str, Any]], bool]:
        """Every collection, following ``next`` links up to the page limit."""
        url: str | None = f"{self._root}/collections"
        found: list[dict[str, Any]] = []
        for _ in range(MAX_COLLECTION_PAGES):
            page = _object((await self._gateway.get(url)).json())
            batch = page.get("collections")
            if isinstance(batch, list):
                found.extend(c for c in batch if isinstance(c, dict))
            url = _next_href(page)
            if url is None:
                return found, True
        return found, False


def _object(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("the STAC API answered with something other than a JSON object")
    return payload


def _next_href(page: dict[str, Any]) -> str | None:
    """The ``next`` link of a GET page. Where it points, the gateway checks again."""
    links = page.get("links")
    if not isinstance(links, list):
        return None
    for link in links:
        if isinstance(link, dict) and link.get("rel") == "next" and isinstance(link.get("href"), str):
            if str(link.get("method") or "GET").upper() != "GET":
                return None
            return link["href"]
    return None


_BBOX_SCHEMA = {
    "type": "array",
    "items": {"type": "number"},
    "minItems": 4,
    "maxItems": 4,
    "description": "WGS84 box [west, south, east, north] in degrees; west <= east.",
}
_DATETIME_SCHEMA = {
    "type": "string",
    "description": "One ISO 8601 instant, or 'start/end' with '..' for an open end, e.g. '2024-06-01/2024-06-30'.",
}

# Tool definitions in the JSON Schema shape LLM tool APIs and MCP both read. No
# model uses them yet (plan m7a F2); they are here so the contract is fixed and
# tested before one does.
TOOL_SPECS: tuple[dict[str, Any], ...] = (
    {
        "name": "search_collections",
        "description": (
            "Find datasets (STAC collections) in the EarthX catalogue by words and, optionally, "
            "by area and time. Returns id, title, short description, licence and extent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words that must all appear, e.g. 'sentinel optical'."},
                "bbox": _BBOX_SCHEMA,
                "datetime": _DATETIME_SCHEMA,
                "limit": {"type": "integer", "minimum": 1, "maximum": validation.MAX_LIMIT},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_collection",
        "description": "Details of one dataset: description, licence and licence flags, extent, capabilities.",
        "input_schema": {
            "type": "object",
            "properties": {"collection_id": {"type": "string"}},
            "required": ["collection_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_availability",
        "description": (
            "Count the scenes of one dataset in an area and time range, with the earliest and "
            "latest date found. Use before recommending a dataset for a place and period."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"collection_id": {"type": "string"}, "bbox": _BBOX_SCHEMA, "datetime": _DATETIME_SCHEMA},
            "required": ["collection_id", "bbox", "datetime"],
            "additionalProperties": False,
        },
    },
)

_PARAMETERS = {spec["name"]: frozenset(spec["input_schema"]["properties"]) for spec in TOOL_SPECS}
_REQUIRED = {spec["name"]: frozenset(spec["input_schema"].get("required", ())) for spec in TOOL_SPECS}


async def call_tool(tools: CatalogTools, name: object, arguments: object) -> dict[str, Any]:
    """Run a tool a caller named, and turn every refusal into an answer.

    A model may name a tool that does not exist or pass arguments no tool takes;
    both come back as an ``error`` it can read and correct, as does every failure
    of the API behind the tools. Nothing raised here reaches the caller.
    """
    if not isinstance(name, str) or name not in _PARAMETERS:
        return {"error": f"unknown tool; available: {', '.join(sorted(_PARAMETERS))}"}
    if not isinstance(arguments, Mapping):
        return {"error": "arguments must be an object"}
    unexpected = set(arguments) - _PARAMETERS[name]
    if unexpected:
        return {"error": f"{name} takes no argument(s) {', '.join(sorted(map(str, unexpected)))}"}
    missing = _REQUIRED[name] - set(arguments)
    if missing:
        return {"error": f"{name} needs argument(s) {', '.join(sorted(missing))}"}
    handler: Callable[..., Awaitable[dict[str, Any]]] = getattr(tools, name)
    try:
        return await handler(**arguments)
    except InvalidArgument as error:
        return {"error": str(error)}
    except UnknownCollection as error:
        return {"error": f"no collection with id {error.args[0]!r}"}
    except UpstreamError as error:
        return {"error": f"the catalogue answered {error.status_code}"}
    except GatewayError:
        return {"error": "the catalogue could not be reached or refused the request"}
    except ValueError:
        return {"error": "the catalogue answered with something that is not valid STAC JSON"}
