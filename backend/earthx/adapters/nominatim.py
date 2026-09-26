"""Place search over Nominatim (M3-07a, `prototyp-inventar.md` F2).

Builds the request, sends it through ``gateway``, and turns the answer into an
outline (simplified under a point cap) plus a bounding box in our own field order —
the same split of duties as ``earth_search.py``: what varies by source stays here,
what does not (the cache-fails-soft rule, E5) is a small helper next to it.

Cache and the shared rate slot are handed in as protocols, not imported: this module
knows nothing about Postgres (architekturplan.md 3.1, `adapters` may import only
`gateway` and `catalog`'s models). The concrete Postgres classes live in
`earthx.catalog.geocode_cache`; `api.geocode_route` wires the two together, the same
split ``adapters/cache.py`` documents for the search cache.

**Rate is not a performance concern here, it is the usage policy**
(`docs/plans/m3-07a-ortssuche-backend.md` §2.1): at most one request per second to
``nominatim.openstreetmap.org``, summed over every process. :func:`geocode` reserves
a slot before it ever sends, refuses to send if the slot is too far out
(:class:`RateLimited`), and never retries the request itself — a retry would be a
second request with no slot of its own.

**No search text and no result reaches a log line here.** Only the module's own
caller (`api.geocode_route`) logs, and only counts and outcomes — this module raises
typed exceptions instead of logging so that the text never has to pass through a
logger to get there.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from shapely.errors import ShapelyError
from shapely.geometry import mapping as shapely_mapping
from shapely.geometry import shape as shapely_shape
from shapely.validation import make_valid

from earthx.adapters.federated_search import MAX_INTERSECTS_POINTS
from earthx.gateway import Gateway, UpstreamError

LOGGER = logging.getLogger("earthx.adapters.nominatim")

# --- Request shape (plan §7, measured in the plan step, plan §3) -----------------

SEARCH_PATH = "/search"
FORMAT = "jsonv2"
RESULT_LIMIT = 5
ACCEPT_LANGUAGE = "en"  # D25: surface text is English-only, no language choice
# Small at the source (spares bytes without flattening a small place, plan §3): the
# adaptive simplification below does the rest, up to MAX_OUTLINE_POINTS.
POLYGON_THRESHOLD = 0.001
MAX_QUERY_CHARS = 200

# M3-08's own cap for `intersects`, reused rather than duplicated: an outline under
# this cap needs no further simplification to be usable as a search AOI later.
MAX_OUTLINE_POINTS = MAX_INTERSECTS_POINTS
MAX_SIMPLIFY_STEPS = 12

# --- Rate slot (plan §9) -----------------------------------------------------------

RATE_SLOT_NAME = "nominatim"
MAX_WAIT_S = 2.0
# Fixed, not `Retry-After`: `UpstreamError` carries only a status and an excerpt, no
# headers (gateway/client.py) — reading one would need widening the gateway for a
# response this rare, not worth it until a `429` is actually seen (plan §9).
PUSH_BACK_ON_429_S = 30.0

# --- Cache (plan §8) ---------------------------------------------------------------

TTL_HIT_S = 30 * 24 * 60 * 60
TTL_EMPTY_S = 24 * 60 * 60
# Bumped whenever the stored shape changes, so a row from an older release counts as
# a miss instead of being misread (the same rule TOKEN_VERSION follows).
CACHE_SCHEMA_VERSION = 1

_WHITESPACE = re.compile(r"\s+")
# Control characters that are not plain whitespace — real whitespace is already
# collapsed away by the time this runs, so this only ever catches something odd
# (`\x00`, an escape byte, …), never a search text that was merely all spaces.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

Bbox = tuple[float, float, float, float]  # west, south, east, north — our order


class InvalidQuery(ValueError):
    """The search text breaks one of our own rules, before anything is sent."""


class RateLimited(RuntimeError):
    """No slot within the wait budget, or the source itself answered ``429``.

    ``retry_after_s`` is what the caller (the route) should tell its own caller,
    not a promise Nominatim made — for a same-process reservation this is our own
    ``MAX_WAIT_S`` overrun; for an upstream ``429`` it is :data:`PUSH_BACK_ON_429_S`.
    """

    def __init__(self, retry_after_s: float) -> None:
        super().__init__(f"no slot within the wait budget, retry after {retry_after_s:.1f}s")
        self.retry_after_s = retry_after_s


class UpstreamShapeError(RuntimeError):
    """The source answered something that is not a place-search result list."""


@runtime_checkable
class GeocodeCache(Protocol):
    """A key-value store with an expiry — the shape `catalog.geocode_cache` fills.

    Structurally checked, like `adapters/cache.py`'s `SearchCache`: `adapters` may
    not import `catalog`'s Postgres classes directly (architekturplan.md 3.1), so the
    shape is declared on this side and the concrete store is handed in by the route.
    """

    async def get(self, key: str) -> dict[str, Any] | None:
        """The stored value, or None if it is absent or expired."""
        ...

    async def set(self, key: str, value: dict[str, Any], *, ttl_s: float) -> None:
        """Store a value for ``ttl_s`` seconds, replacing whatever was under it."""
        ...


@runtime_checkable
class RateSlot(Protocol):
    """One shared pointer per named upstream, moved forward by whoever asks next.

    Not a lock: reserving never blocks and holds nothing open while a caller waits
    on the delay it returns (plan §9). A caller that cannot reserve at all (the store
    is unreachable) gets the exception, not a silent "send anyway" — unlike
    :class:`GeocodeCache`, whose failure is the caller's to shrug off (E5).
    """

    async def reserve(self, name: str) -> float:
        """Seconds to wait before sending, at least 0. Always reserves; never blocks."""
        ...

    async def push_back(self, name: str, *, seconds: float) -> None:
        """Move the shared pointer forward by at least ``seconds`` more."""
        ...


@dataclass(frozen=True, slots=True)
class GeocodeResult:
    name: str
    display_name: str
    kind: str
    bbox: Bbox
    outline: dict[str, Any] | None
    outline_simplified: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "kind": self.kind,
            "bbox": list(self.bbox),
            "outline": self.outline,
            "outline_simplified": self.outline_simplified,
        }


ATTRIBUTION = "© OpenStreetMap contributors"
ATTRIBUTION_URL = "https://www.openstreetmap.org/copyright"
LICENSE = "ODbL-1.0"


@dataclass(frozen=True, slots=True)
class GeocodeResponse:
    results: tuple[GeocodeResult, ...]
    from_cache: bool

    def to_payload(self) -> dict[str, Any]:
        """The answer for M3-07b — attribution on every answer, even an empty one."""
        return {
            "results": [result.to_dict() for result in self.results],
            "attribution": ATTRIBUTION,
            "attribution_url": ATTRIBUTION_URL,
            "license": LICENSE,
        }


def normalize_query_text(text: str) -> str:
    """Trim, collapse whitespace, and enforce the caps — before anything is sent.

    Order matters: whitespace is collapsed *before* the control-character check, so
    a text that is only spaces or tabs fails as "empty", not as "contains control
    characters" — those are two different tests in the plan (§11).
    """
    normalized = _WHITESPACE.sub(" ", text).strip()
    if not normalized:
        raise InvalidQuery("search text is empty")
    if _CONTROL_CHARS.search(normalized):
        raise InvalidQuery("search text contains control characters")
    if len(normalized) > MAX_QUERY_CHARS:
        raise InvalidQuery(f"search text is over {MAX_QUERY_CHARS} characters")
    return normalized


def _cache_key(query: str) -> str:
    """A hash of the normalised text and every fixed parameter that shapes the
    answer — never the text itself (projektplan.md 7, point 6). Plain SHA-256, the
    same construction `federated_search.search_fingerprint` uses for a search: the
    input space here is free text, not a handful of floats, so there is no narrow
    domain to guess and no need for the keyed HMAC `gateway`'s query digest uses."""
    payload = json.dumps(
        {
            "q": query.casefold(),
            "format": FORMAT,
            "threshold": POLYGON_THRESHOLD,
            "limit": RESULT_LIMIT,
            "language": ACCEPT_LANGUAGE,
            "max_points": MAX_OUTLINE_POINTS,
            "v": CACHE_SCHEMA_VERSION,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _point_count(geom: Any) -> int:
    if geom.geom_type == "Polygon":
        return len(geom.exterior.coords) + sum(len(ring.coords) for ring in geom.interiors)
    if geom.geom_type == "MultiPolygon":
        return sum(_point_count(part) for part in geom.geoms)
    return 0


def _outline_for(raw_geometry: Any, max_points: int) -> tuple[dict[str, Any] | None, bool]:
    """The result's own outline, simplified under ``max_points`` — or ``None``.

    ``None`` for anything that is not polygonal (a point or a road), for a geometry
    that stays invalid after `make_valid`, and for one that cannot be brought under
    the cap: a caller that cannot use the outline still gets the bounding box.
    """
    if not isinstance(raw_geometry, dict) or raw_geometry.get("type") not in ("Polygon", "MultiPolygon"):
        return None, False
    try:
        geom = shapely_shape(raw_geometry)
    except (ShapelyError, ValueError, TypeError):
        return None, False
    if not geom.is_valid:
        try:
            geom = make_valid(geom)
        except ShapelyError:
            return None, False
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            return None, False
    simplified = False
    tolerance = POLYGON_THRESHOLD
    for _ in range(MAX_SIMPLIFY_STEPS):
        if _point_count(geom) <= max_points:
            return shapely_mapping(geom), simplified
        tolerance *= 2
        geom = geom.simplify(tolerance, preserve_topology=True)
        simplified = True
    if _point_count(geom) <= max_points:
        return shapely_mapping(geom), simplified
    return None, False


def _bbox_from(raw: Any) -> Bbox | None:
    """Nominatim's ``[south, north, west, east]``, as our ``[west, south, east,
    north]`` — or ``None`` for anything that is not a sane box (plan §3, §7):
    the wrong count, unparsable numbers, a flipped or out-of-range box."""
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    try:
        south, north, west, east = (float(value) for value in raw)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= south <= north <= 90.0):
        return None
    if not (-180.0 <= west <= 180.0 and -180.0 <= east <= 180.0):
        return None
    if west > east:
        return None
    return (west, south, east, north)


def _parse_results(payload: Any) -> tuple[GeocodeResult, ...]:
    """Every usable hit — a hit missing a name or a sane box is dropped, not the
    whole answer; an answer that is not a list at all is (adr/0004 §3.4's "silently
    something else" would otherwise apply here too)."""
    if not isinstance(payload, list):
        raise UpstreamShapeError("place search did not answer with a list")
    results: list[GeocodeResult] = []
    for hit in payload:
        if not isinstance(hit, dict):
            continue
        display_name = hit.get("display_name")
        if not isinstance(display_name, str) or not display_name:
            continue
        bbox = _bbox_from(hit.get("boundingbox"))
        if bbox is None:
            continue
        raw_name = hit.get("name")
        name = raw_name if isinstance(raw_name, str) and raw_name else display_name
        kind = "/".join(part for part in (hit.get("category"), hit.get("type")) if isinstance(part, str) and part)
        outline, simplified = _outline_for(hit.get("geojson"), MAX_OUTLINE_POINTS)
        results.append(
            GeocodeResult(
                name=name,
                display_name=display_name,
                kind=kind or "unknown",
                bbox=bbox,
                outline=outline,
                outline_simplified=simplified,
            )
        )
    return tuple(results)


def _to_stored(results: tuple[GeocodeResult, ...]) -> dict[str, Any]:
    return {"v": CACHE_SCHEMA_VERSION, "results": [result.to_dict() for result in results]}


def _response_from_stored(stored: Any) -> GeocodeResponse | None:
    """None counts as a cache miss — a row from an older release, or damaged, is
    asked of the source again rather than answered wrongly (E5, the rule
    `federated_search.page_from_stored`'s caller already follows for the search
    cache)."""
    if not isinstance(stored, dict) or stored.get("v") != CACHE_SCHEMA_VERSION:
        return None
    entries = stored.get("results")
    if not isinstance(entries, list):
        return None
    try:
        results = tuple(
            GeocodeResult(
                name=entry["name"],
                display_name=entry["display_name"],
                kind=entry["kind"],
                bbox=tuple(entry["bbox"]),
                outline=entry["outline"],
                outline_simplified=entry["outline_simplified"],
            )
            for entry in entries
        )
    except (KeyError, TypeError):
        return None
    return GeocodeResponse(results=results, from_cache=True)


async def _cache_get(cache: GeocodeCache | None, key: str) -> GeocodeResponse | None:
    if cache is None:
        return None
    try:
        stored = await cache.get(key)
    except Exception:
        # E5: a cache that fails makes the platform slower, never wrong.
        LOGGER.warning("geocode cache unreadable, asking the source instead", exc_info=True)
        return None
    return None if stored is None else _response_from_stored(stored)


async def _cache_set(cache: GeocodeCache | None, key: str, results: tuple[GeocodeResult, ...]) -> None:
    if cache is None:
        return
    ttl_s = TTL_HIT_S if results else TTL_EMPTY_S
    try:
        await cache.set(key, _to_stored(results), ttl_s=ttl_s)
    except Exception:
        LOGGER.warning("geocode cache not writable, answer is not stored", exc_info=True)


async def _fetch(gateway: Gateway, query: str, *, base_url: str, user_agent: str) -> Any:
    response = await gateway.get(
        f"{base_url}{SEARCH_PATH}",
        params={
            "q": query,
            "format": FORMAT,
            "polygon_geojson": 1,
            "polygon_threshold": POLYGON_THRESHOLD,
            "limit": RESULT_LIMIT,
            "accept-language": ACCEPT_LANGUAGE,
            "dedupe": 1,
        },
        headers={"User-Agent": user_agent},
        # No repeat of our own: a retry would be a second request with no slot of
        # its own (plan §9). The gateway's own timeout/connection-error retries
        # would have the same problem, which is why `retry=False` covers those too,
        # not only the status-code retries.
        retry=False,
    )
    try:
        return response.json()
    except ValueError as error:
        raise UpstreamShapeError("place search did not answer with JSON") from error


async def geocode(
    text: str,
    *,
    gateway: Gateway,
    base_url: str,
    user_agent: str,
    cache: GeocodeCache | None,
    rate_slot: RateSlot,
    max_wait_s: float = MAX_WAIT_S,
) -> GeocodeResponse:
    """Resolve a place name to an outline and a bounding box.

    Raises :class:`InvalidQuery` for a text that breaks our own rules,
    :class:`RateLimited` when no slot is available soon enough or the source itself
    is rate-limiting us, :class:`UpstreamShapeError` for an answer that cannot be
    read, and whatever :mod:`earthx.gateway` raises for everything else upstream.
    A cache hit takes neither a slot nor a request.
    """
    query = normalize_query_text(text)
    key = _cache_key(query)
    cached = await _cache_get(cache, key)
    if cached is not None:
        return cached

    delay = await rate_slot.reserve(RATE_SLOT_NAME)
    if delay > max_wait_s:
        # The slot just reserved is left unused — the pointer only ever moves
        # forward, so this can only make the rate lower, never higher (plan §9).
        raise RateLimited(delay)
    if delay > 0:
        await asyncio.sleep(delay)

    try:
        payload = await _fetch(gateway, query, base_url=base_url, user_agent=user_agent)
    except UpstreamError as error:
        if error.status_code == 429:
            await rate_slot.push_back(RATE_SLOT_NAME, seconds=PUSH_BACK_ON_429_S)
            raise RateLimited(PUSH_BACK_ON_429_S) from error
        raise

    results = _parse_results(payload)
    await _cache_set(cache, key, results)
    return GeocodeResponse(results=results, from_cache=False)


__all__ = [
    "ATTRIBUTION",
    "ATTRIBUTION_URL",
    "LICENSE",
    "MAX_WAIT_S",
    "RATE_SLOT_NAME",
    "Bbox",
    "GeocodeCache",
    "GeocodeResponse",
    "GeocodeResult",
    "InvalidQuery",
    "RateSlot",
    "RateLimited",
    "UpstreamShapeError",
    "geocode",
    "normalize_query_text",
]
