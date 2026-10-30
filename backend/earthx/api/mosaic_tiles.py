"""What the mosaic tile of the tiler decides before `access` reads a pixel (M4-17b, plan M4-17 §4, §5).

The scenes of one overpass reach the tiler as a list of item ids in the URL (adr/0006 §4.2 M1, never
an id of a stored search). This module holds the parts of that path that need neither the request nor
the registry's HTTP mapping, so that they read and test alone; `api.tiler` composes them into the path
dependency and maps :class:`~earthx.api.item_source.OrderRefused` to the answer of each refusal.

* the **limits** of §5, as constants, because they hang on the tile grid and the source, not on a
  dataset;
* the **shape of the query** — one asset (one to four with steps, NM4-04), two to 64 distinct ids that
  look like ids, at most :data:`MAX_MOSAIC_REQUEST_BYTES` in all, and none of the parameters that could
  carry an area, a free expression or an address;
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
import math
from collections.abc import Collection, Mapping, Sequence
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
    "MAX_MOSAIC_OPERATOR_ASSETS",
    "MAX_MOSAIC_REQUEST_BYTES",
    "MAX_SCENES_PER_TILE",
    "MIN_MOSAIC_ITEMS",
    "MIN_MOSAIC_ZOOM",
    "ROUTER_PREFIX",
    "ItemFetches",
    "check_length",
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
#: Assets a mosaic tile with steps reads (NM4-04 F3): 12 scenes x 4 assets = 48 files at most for one tile. NDVI
#: takes 2, a masked NDVI 3, a masked EVI 4; the item tile takes 16, but reads one scene. The limit counts the assets
#: the shown band needs, not those the URL names (NM4-43d).
MAX_MOSAIC_OPERATOR_ASSETS = 4
#: Path and query of a mosaic request as they arrive (NM4-04 F5): uvicorn takes 65 535 bytes, nginx and the CDNs
#: in front of it in M6 often 8 kB for the whole request line; 1 kB is left for a prefix, method and version.
MAX_MOSAIC_REQUEST_BYTES = 7168

#: Failures of the item cache itself: the database went away, the pool had no connection to give
#: (``PoolTimeout`` and ``PoolClosed`` are ``OperationalError``s) or the table is missing.
_CACHE_FAILURES = (psycopg.Error,)


def check_length(raw_path: bytes, query_string: bytes) -> None:
    """``414`` for a request longer than :data:`MAX_MOSAIC_REQUEST_BYTES`, before anything is fetched.

    The limit holds with and without steps: a URL that works here works behind the proxy of M6 too.
    """
    length = len(raw_path) + (len(query_string) + 1 if query_string else 0)
    if length > MAX_MOSAIC_REQUEST_BYTES:
        raise OrderRefused(
            414, f"a mosaic request takes at most {MAX_MOSAIC_REQUEST_BYTES} bytes, not {length}", "order"
        )


def check_query(
    query: Mapping[str, Any] | Any,
    declared: Collection[str],
    items: Sequence[str],
    assets: Sequence[str],
    *,
    steps: bool = False,
) -> list[str]:
    """The item ids of the URL, sorted, or the ``400`` the query earns.

    ``query`` is the request's query parameters and ``declared`` the names the route declares (its own
    and those of its dependencies). A name outside them is refused instead of dropped: FastAPI drops a
    parameter a route does not declare without a word, and a mosaic that quietly ignored ``bbox``, a
    ``filter`` or ``BBOX `` would look like an answer to a question it never heard — and the TileJSON
    would copy it into the tile URLs it hands out (Q8, plan §4.1). The list of what is allowed, not of
    what is forbidden: no spelling of an area gets past it. With ``steps`` (``op`` in the query) a tile names one
    or more assets, each once; how many of them it reads (at most :data:`MAX_MOSAIC_OPERATOR_ASSETS`) is judged
    after the band it shows is known, because it reads only the assets that band needs (NM4-43d).

    Sorting makes the answer to an error independent of the order the client wrote its ids in; the
    order of the pixels never depends on it either (§4.4).
    """
    for name in query:
        if name not in declared:
            raise OrderRefused(400, "a mosaic tile takes item, asset and the parameters of its display only", "order")
    if steps:
        if not assets or len(set(assets)) != len(assets):
            raise OrderRefused(400, "with op, name each asset once", "order")
    elif len(assets) != 1:
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
            # The kind of failure only: the driver's text can name the host and the user.
            LOGGER.warning("the item cache failed under a mosaic tile: %s", type(result).__name__)
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
                outline = shapely_shape(item["geometry"])
            else:
                bbox = item["bbox"]
                if len(bbox) == 4:
                    west, south, east, north = bbox
                elif len(bbox) == 6:  # with heights: [w, s, z, e, n, z]
                    west, south, _, east, north, _ = bbox
                else:
                    raise ValueError("a bbox has four or six numbers")
                outline = box(west, south, east, north)
            # An empty outline, or one with a NaN, would end as a hole in the mosaic or a NaN extent.
            if outline.is_empty or not all(map(math.isfinite, outline.bounds)):
                raise ValueError("no usable outline")
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, ShapelyError):
            raise OrderRefused(502, malformed_item_detail(item_id), "items") from None
        outlines[item_id] = outline
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
