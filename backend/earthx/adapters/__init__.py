"""Source protocols: discovery, search, access resolution, aggregation.

One adapter per source protocol (architekturplan.md 6.1). The first one speaks Earth
Search v1 and answers search, access resolution and — since M2-05 — the coverage
aggregation of adr/0004 for Sentinel-2 L2A; discovery follows with the harvester (M5).

Everything an adapter sends goes through ``gateway``; what it needs to know about a
dataset it reads from ``catalog``. Which adapter serves which collection is decided
by the caller from ``earthx:source`` (adr/0005 rule I) — from M1-07 on that caller is
the federating client in ``api``.
"""

from earthx.adapters.cache import CacheValue, SearchCache
from earthx.adapters.earth_search import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    InvalidQuery,
    ItemPage,
    SearchParams,
    UnknownCollection,
    UnsupportedSource,
    UpstreamShapeError,
    get_item,
    search_items,
)
from earthx.adapters.earth_search_coverage import aggregate_coverage

__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "CacheValue",
    "InvalidQuery",
    "ItemPage",
    "SearchCache",
    "SearchParams",
    "UnknownCollection",
    "UnsupportedSource",
    "UpstreamShapeError",
    "aggregate_coverage",
    "get_item",
    "search_items",
]
