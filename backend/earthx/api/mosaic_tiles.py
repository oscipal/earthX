"""What the mosaic tile of the tiler decides before `access` reads a pixel (M4-17b, plan M4-17 §4, §5).

The scenes of one overpass reach the tiler as a list of item ids in the URL (adr/0006 §4.2 M1, never
an id of a stored search). This module holds the parts of that path that need neither the request nor
the registry's HTTP mapping, so that they read and test alone; `api.tiler` composes them into the path
dependency and maps :class:`~earthx.api.item_source.OrderRefused` to the answer of each refusal.

* the **limits** of §5, as constants, because they hang on the tile grid and the source, not on a
  dataset;
* the **shape of the query** — one asset, two to 64 distinct ids that look like ids, and none of the
  parameters that could carry an area, an operator or an address;
* the **item fetches** (§4.3) — one running fetch per item however many tiles ask for it, and at
  most four at a time in the whole process;
* the **overpass** (§4.2 step 5) and the **footprints** that cut the list down to the scenes a tile
  touches.

Nothing here is kept after the request that asked: the fetches that are running are the only state,
and an entry leaves with its fetch.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import Any

import morecantile
import psycopg
from shapely.errors import ShapelyError
from shapely.geometry import box
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry

from earthx.adapters.federated_search import ITEM_ID
from earthx.api.item_source import ItemSource, OrderRefused, fetch_item_or_refuse, malformed_item_detail
from earthx.catalog.registry import MissingProperty, ViewerInfo, group_key

LOGGER = logging.getLogger("earthx.api.mosaic_tiles")

__all__ = [
    "MAX_ITEM_FETCHES",
    "MAX_MOSAIC_ITEMS",
    "MAX_SCENES_PER_TILE",
    "MIN_MOSAIC_ITEMS",
    "MIN_MOSAIC_ZOOM",
    "ROUTER_PREFIX",
    "ItemFetches",
    "check_one_overpass",
    "check_query",
    "fetch_items",
    "footprints_of",
    "mosaic_tile",
    "scenes_touching",
    "union_bounds",
]

#: Where the mosaic routes begin; the factory adds ``/tiles/…`` and ``/{tileMatrixSetId}/tilejson.json``.
ROUTER_PREFIX = "/collections/{dataset}/mosaic"

# The limits of plan §5, with the measurement that gives each of them. Constants in the code and not a
# field of the registry (KE6): they follow the tile grid and the source, not the dataset.
MIN_MOSAIC_ITEMS = 2
#: Overpasses over a country-sized area have up to 60 scenes (§2.2); 64 ids are about 2.4 kB of URL (§2.7).
MAX_MOSAIC_ITEMS = 64
#: Scenes one tile may read after the footprint filter: at most 9 at z8 in six overpasses (§2.2).
MAX_SCENES_PER_TILE = 12
#: Below z8 a tile touches up to 13 (z7) or 27 (z6) scenes, which is the overview's job, not the tile path's.
MIN_MOSAIC_ZOOM = 8
#: Item fetches at the source at the same time, in the whole process: under the five connections of the
#: cache pool (`api.dependencies`) and the six per host of the gateway (`gateway.policy`).
MAX_ITEM_FETCHES = 4

# What can carry an area, an operator or an address. FastAPI drops a query parameter a route does not
# declare without a word, so each one is refused here by name: a mosaic that quietly ignored `bbox`
# would look like an answer to a question it never heard (Q8, plan §4.1).
_REFUSED_PARAMETERS = frozenset(
    {"expression", "algorithm", "algorithm_params", "op", "op_version", "params"}
    | {"bbox", "aoi", "geometry", "intersects", "url"}
)

#: Failures of the item cache itself: the database went away or the pool had no connection to give
#: (``PoolTimeout`` and ``PoolClosed`` are ``OperationalError``s).
_CACHE_FAILURES = (psycopg.OperationalError, psycopg.InterfaceError)


def check_query(query: Mapping[str, Any] | Any, items: Sequence[str], assets: Sequence[str]) -> list[str]:
    """The item ids of the URL, sorted, or the ``400`` the query earns.

    ``query`` is the request's query parameters: their names are checked, case-blind, against the
    parameters a mosaic does not take. Sorting makes the answer to an error independent of the order
    the client wrote its ids in; the order of the pixels never depends on it either (§4.4).
    """
    for name in query:
        if str(name).lower() in _REFUSED_PARAMETERS:
            raise OrderRefused(400, f"{name!r} is not accepted on a mosaic tile", "order")
    if len(assets) != 1:
        raise OrderRefused(400, "name one asset", "order")
    if not MIN_MOSAIC_ITEMS <= len(items) <= MAX_MOSAIC_ITEMS:
        raise OrderRefused(
            400, f"a mosaic takes {MIN_MOSAIC_ITEMS} to {MAX_MOSAIC_ITEMS} items, not {len(items)}", "order"
        )
    if len(set(items)) != len(items):
        raise OrderRefused(400, "name each item once", "order")
    if not all(ITEM_ID.match(item_id) for item_id in items):
        raise OrderRefused(400, "an item id has the shape the sources give theirs", "order")
    return sorted(items)


def mosaic_tile(path_params: Mapping[str, Any]) -> tuple[morecantile.TileMatrixSet, morecantile.Tile] | None:
    """The tile a request asks for, or ``None`` for a TileJSON, which names none.

    ``400`` below :data:`MIN_MOSAIC_ZOOM`, before any item is fetched; ``404`` for a tile outside the
    matrix, the answer a tile outside an item gets too.
    """
    if "z" not in path_params:
        return None
    try:
        tms = morecantile.tms.get(str(path_params["tileMatrixSetId"]))
        zoom, column, row = (int(path_params[name]) for name in ("z", "x", "y"))
    except (KeyError, ValueError, morecantile.errors.MorecantileError):
        raise OrderRefused(400, "not a tile of a grid this tiler serves", "order") from None
    if zoom < MIN_MOSAIC_ZOOM:
        raise OrderRefused(400, f"mosaic tiles start at z{MIN_MOSAIC_ZOOM}", "order")
    if not tms.is_valid(column, row, zoom):
        raise OrderRefused(404, "the tile does not touch these items", "items")
    return tms, morecantile.Tile(column, row, zoom)


class ItemFetches:
    """The item fetches of mosaic requests: one running fetch per item, four at a time in all (§4.3).

    A tile of a cold overpass needs the metadata of every item in its URL, and the six tiles of a map
    view ask at the same moment. Without this each would fetch each item itself — up to six times the
    load on the source, for a page of the map. A second request for an item that is being fetched waits
    for that fetch; an entry leaves with the end of its fetch, so nothing outlives the request that
    wanted it. The item cache (24 h) is behind the fetch, as for every tile.
    """

    def __init__(self, limit: int = MAX_ITEM_FETCHES) -> None:
        self._limit = limit
        self._loop: asyncio.AbstractEventLoop | None = None
        self._slots = asyncio.Semaphore(limit)
        self._running: dict[tuple[str, str], asyncio.Task[dict[str, Any]]] = {}

    def _follow(self, loop: asyncio.AbstractEventLoop) -> None:
        # A process has one event loop. A test client may start one per request, and neither a semaphore
        # nor a task is any use in another loop than the one it was made in.
        if loop is not self._loop:
            self._loop = loop
            self._slots = asyncio.Semaphore(self._limit)
            self._running = {}

    async def get(self, source: ItemSource, dataset: str, item_id: str) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        self._follow(loop)
        key = (dataset, item_id)
        task = self._running.get(key)
        if task is None:
            task = loop.create_task(self._fetch(source, dataset, item_id))
            self._running[key] = task
            task.add_done_callback(lambda done: self._finished(key, done))
        # Shielded: one request that gives up must not cancel the fetch the others wait for.
        return await asyncio.shield(task)

    async def _fetch(self, source: ItemSource, dataset: str, item_id: str) -> dict[str, Any]:
        async with self._slots:
            return await fetch_item_or_refuse(source, dataset, item_id)

    def _finished(self, key: tuple[str, str], task: asyncio.Task[dict[str, Any]]) -> None:
        if self._running.get(key) is task:
            del self._running[key]
        if not task.cancelled():
            task.exception()  # a fetch every waiter gave up on must not log "never retrieved"


async def fetch_items(
    fetches: ItemFetches, source: ItemSource, dataset: str, item_ids: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """Every item of the URL, or the :class:`OrderRefused` of the first that failed, in id order.

    A source failure maps as it does for a tile of one item (`fetch_item_or_refuse`). A failure of the
    item cache itself is a ``503`` with its reason — never a ``500`` (Otto, plan §11 Auflage 3): the
    mosaic is the one tile that cannot do without the cache (§4.3 point 4).
    """
    results = await asyncio.gather(*(fetches.get(source, dataset, item_id) for item_id in item_ids), return_exceptions=True)
    fetched: dict[str, dict[str, Any]] = {}
    for item_id, result in zip(item_ids, results, strict=True):
        if isinstance(result, _CACHE_FAILURES):
            LOGGER.warning("the item cache failed under a mosaic tile", exc_info=result)
            raise OrderRefused(503, "mosaic tiles need the item cache, and it is not reachable", "items")
        if isinstance(result, BaseException):
            raise result
        fetched[item_id] = result
    return fetched


def check_one_overpass(items: Mapping[str, dict[str, Any]], viewer: ViewerInfo) -> None:
    """The scenes of a mosaic belong to one overpass, by the key the registry names (P19).

    The rule of the mosaic job (`api.intake`), with the same words: a mosaic over two overpasses is a
    time series, and a tile cannot show one.
    """
    keys: dict[str, tuple[str, ...]] = {}
    for item_id in sorted(items):
        try:
            keys[item_id] = group_key(items[item_id], viewer, viewer.results_group_by)
        except MissingProperty as error:
            raise OrderRefused(502, f"item {item_id!r} lacks {error}, which names its overpass", "items") from None
    first = next(iter(keys))
    apart = [item_id for item_id, key in keys.items() if key != keys[first]]
    if apart:
        raise OrderRefused(
            422,
            f"the scenes of a mosaic belong to one overpass; {', '.join(apart[:10])} differ from {first}",
            "items",
        )


def footprints_of(items: Mapping[str, dict[str, Any]]) -> dict[str, BaseGeometry]:
    """The outline of each item, from its ``geometry`` and, where that is missing, its ``bbox`` (KE2).

    An item with neither is the source's mistake, the same ``502`` as any item that arrives broken.
    """
    outlines: dict[str, BaseGeometry] = {}
    for item_id, item in items.items():
        try:
            if item.get("geometry"):
                outlines[item_id] = shapely_shape(item["geometry"])
            else:
                west, south, *rest = item["bbox"]  # [w, s, e, n], or [w, s, z, e, n, z] with heights
                east, north = rest if len(rest) == 2 else rest[1:3]
                outlines[item_id] = box(west, south, east, north)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, ShapelyError):
            raise OrderRefused(502, malformed_item_detail(item_id), "items") from None
    return outlines


def union_bounds(outlines: Mapping[str, BaseGeometry]) -> tuple[float, float, float, float]:
    """West, south, east, north in EPSG:4326 over every item of the URL: the extent of the layer."""
    west, south, east, north = zip(*(outline.bounds for outline in outlines.values()), strict=True)
    return min(west), min(south), max(east), max(north)


def scenes_touching(
    order: Sequence[str],
    outlines: Mapping[str, BaseGeometry],
    grid: tuple[morecantile.TileMatrixSet, morecantile.Tile],
) -> list[str]:
    """The ids of ``order`` whose outline meets the tile, in the same order.

    ``404`` where none does and ``422`` ("zoom in") where more than :data:`MAX_SCENES_PER_TILE` do —
    never a partial picture (KE3): a tile that left scenes out would show a gap no one can explain.
    """
    tms, tile = grid
    area = box(*tms.bounds(tile))
    touching = [item_id for item_id in order if outlines[item_id].intersects(area)]
    if not touching:
        raise OrderRefused(404, "the tile does not touch these items", "items")
    if len(touching) > MAX_SCENES_PER_TILE:
        raise OrderRefused(
            422,
            f"{len(touching)} scenes meet this tile, at most {MAX_SCENES_PER_TILE} are read; zoom in",
            "items",
        )
    LOGGER.info("mosaic tile reads %d of %d scenes", len(touching), len(order))
    return touching
