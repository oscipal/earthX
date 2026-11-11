"""What the mosaic tile of the tiler decides before `access` reads a pixel (M4-17b, plan M4-17 §4, §5).

The scenes of one overpass reach the tiler as a **selection** (M5-30b part 3, adr/0032 §10.2): a list of item ids
that is created once (``POST /collections/{dataset}/mosaic``) and named in the tile URL by an id that is the hash of its
content, never an id of a stored search (adr/0006 §4.2 M1, §5). This module holds the parts of that path that need
neither the request nor the registry's HTTP mapping, so that they read and test alone; `api.tiler` composes them into
the path dependency and maps :class:`~earthx.api.item_source.OrderRefused` to the answer of each refusal.

* the **limits**, as constants — a **budget per tile** (files and time, adr/0032 §6.2) instead of a first zoom level
  and a number of scenes; a tile over it is a part of the picture, said in a header and nowhere on the map;
* the **shape of a selection** — two to :data:`MAX_SELECTION_ITEMS` distinct ids that look like ids and one to four
  distinct assets, in a body of at most :data:`MAX_SELECTION_BODY_BYTES` — and the **shape of the query** of a tile, with
  none of the parameters that could carry an area, a free expression or an address;
* the **item fetches** (§4.3) — one running fetch per item however many tiles ask for it, and at most four at a time in
  the whole process; and the fetches in **batches** by which a selection is created;
* the **overpass** (§4.2 step 5) and the **footprints** that cut the list down to the scenes a tile touches.

Nothing here is kept after the request that asked: the fetches that are running are the only state,
and an entry leaves with its fetch.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import morecantile
import psycopg
from pydantic import BaseModel, ConfigDict
from shapely.errors import ShapelyError
from shapely.geometry import box
from shapely.geometry import shape as shapely_shape
from shapely.geometry.base import BaseGeometry

from earthx.adapters.federated_search import ITEM_ID, MAX_IDS
from earthx.api.item_source import (
    ItemBatchSource,
    ItemSource,
    OrderRefused,
    fetch_item_or_refuse,
    fetch_items_or_refuse,
    malformed_item_detail,
)
from earthx.catalog.mosaic_selection import SELECTION_ID
from earthx.catalog.registry import MissingProperty, ViewerInfo, overpass_key

LOGGER = logging.getLogger("earthx.api.mosaic_tiles")

__all__ = [
    "MAX_ITEM_FETCHES",
    "MAX_MOSAIC_OPERATOR_ASSETS",
    "MAX_MOSAIC_REQUEST_BYTES",
    "MAX_SELECTION_BODY_BYTES",
    "MAX_SELECTION_ITEMS",
    "MIN_MOSAIC_ITEMS",
    "PARTIAL_HEADER",
    "ROUTER_PREFIX",
    "TILE_FILE_BUDGET",
    "TILE_TIME_BUDGET_S",
    "ItemFetches",
    "SelectionRequest",
    "TileOutcome",
    "TileOutcomeHeaders",
    "TileScenes",
    "check_length",
    "check_one_overpass",
    "check_query",
    "check_selection",
    "check_selection_id",
    "fetch_items",
    "fetch_selection_items",
    "footprints_of",
    "mosaic_tile",
    "scenes_touching",
    "touching_scenes",
    "union_bounds",
]

#: Where the routes of one selection begin; the factory adds ``/tiles/…`` and ``/{tileMatrixSetId}/tilejson.json``.
ROUTER_PREFIX = "/collections/{dataset}/mosaic/{selection}"

# The limits of plan §5, with the measurement that gives each of them. Constants in the code and not a
# field of the registry (KE6): they follow the tile grid and the source, not the dataset.
MIN_MOSAIC_ITEMS = 2
#: Scenes in one selection (adr/0032 §10.2): a protection for the table and the creation, not a limit of the picture —
#: a tile reads at most :data:`TILE_FILE_BUDGET` files whatever the selection holds. The ids no longer sit in the URL.
MAX_SELECTION_ITEMS = 2000
#: The body of the creation: 2 000 ids of at most 255 characters would be 520 kB; real ids are 20 to 60.
MAX_SELECTION_BODY_BYTES = 128 * 1024
#: Files one tile reads at most, in the order of the mosaic (adr/0032 §6.2, F6): scenes, or scenes times the assets of
#: a tile with steps. Set from Otto's run of 11.11.2026 (plan M5-30b §8.6): a file of swissALTI3D costs 55-85 ms with
#: four threads, cold or warm alike (opening and warping, not the network), so 32 files take 1.8-2.8 s; a z13 tile
#: needs up to 25.
TILE_FILE_BUDGET = 32
#: Seconds one tile reads for at most (adr/0032 §6.2): under the 5 s of pgstac, because a map asks for many tiles at
#: once; about 1.4 times what 32 files of swissALTI3D took cold (plan M5-30b §8.6).
TILE_TIME_BUDGET_S = 4.0
#: The header of a tile that shows only a part of its scenes: how many it left out, or ``time`` after the budget ran
#: out. No mark on the map (Otto, 11.11.2026); the header is for a client that wants to say it.
PARTIAL_HEADER = "X-EarthX-Partial"
#: Item fetches at the source at the same time, in the whole process: under the five connections of the
#: cache pool (`api.dependencies`) and the six per host of the gateway (`gateway.policy`).
MAX_ITEM_FETCHES = 4
#: Assets a mosaic tile with steps reads (NM4-04 F3): 12 scenes x 4 assets = 48 files at most for one tile. NDVI
#: takes 2, a masked NDVI 3, a masked EVI 4; the item tile takes 16, but reads one scene. The limit counts the assets
#: the shown band needs, not those the URL names (NM4-43d).
MAX_MOSAIC_OPERATOR_ASSETS = 4
#: Path and query of a mosaic tile request as they arrive (NM4-04 F5): uvicorn takes 65 535 bytes, nginx and the CDNs
#: in front of it in M6 often 8 kB for the whole request line; 1 kB is left for a prefix, method and version. The URL no
#: longer carries the ids (M5-30b part 3), so this holds the parameters of the steps.
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


def check_query(query: Mapping[str, Any] | Any, declared: Collection[str]) -> None:
    """``400`` for a query parameter the route does not declare.

    ``query`` is the request's query parameters and ``declared`` the names the route declares (its own
    and those of its dependencies). A name outside them is refused instead of dropped: FastAPI drops a
    parameter a route does not declare without a word, and a mosaic that quietly ignored ``bbox``, a
    ``filter`` or ``BBOX `` would look like an answer to a question it never heard — and the TileJSON
    would copy it into the tile URLs it hands out (Q8, plan §4.1). The list of what is allowed, not of
    what is forbidden: no spelling of an area gets past it. The scenes and the asset are named by the selection in the
    path; ``item`` and ``asset`` are no parameters any more (M5-30b part 3).
    """
    for name in query:
        if name not in declared:
            raise OrderRefused(400, "a mosaic tile takes the parameters of its display only", "order")


def check_selection_id(selection: str) -> None:
    """``400`` for an id that is not 32 lowercase hex characters, before anything is looked up."""
    if not SELECTION_ID.match(selection):
        raise OrderRefused(400, "a selection id is 32 lowercase hexadecimal characters", "order")


class SelectionRequest(BaseModel):
    """Body of ``POST /collections/{dataset}/mosaic``: the scenes of one overpass and the assets they are read from.

    Only the shape is the model's; what the lists may hold is :func:`check_selection`, so that a refusal never echoes a
    list of two thousand ids back. A field the route does not know is refused, as a parameter of a tile it does not declare is.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[str]
    assets: list[str]


def check_selection(items: Sequence[str], assets: Sequence[str]) -> tuple[list[str], list[str]]:
    """The item ids and the assets of a selection, each sorted, or the ``400`` it earns.

    Two to :data:`MAX_SELECTION_ITEMS` ids, each once and shaped like an id; one to :data:`MAX_MOSAIC_OPERATOR_ASSETS`
    assets, each once. The messages name the rule and never an id, so that a refusal stays short.
    """
    if not MIN_MOSAIC_ITEMS <= len(items) <= MAX_SELECTION_ITEMS:
        raise OrderRefused(
            400, f"a selection takes {MIN_MOSAIC_ITEMS} to {MAX_SELECTION_ITEMS} items, not {len(items)}", "order"
        )
    if len(set(items)) != len(items):
        raise OrderRefused(400, "name each item once", "order")
    if not all(isinstance(item_id, str) and ITEM_ID.match(item_id) for item_id in items):
        raise OrderRefused(400, "an item id has the shape the sources give theirs", "order")
    if not 1 <= len(assets) <= MAX_MOSAIC_OPERATOR_ASSETS:
        raise OrderRefused(400, f"a selection takes 1 to {MAX_MOSAIC_OPERATOR_ASSETS} assets, not {len(assets)}", "order")
    if len(set(assets)) != len(assets) or not all(isinstance(key, str) and 1 <= len(key) <= 128 for key in assets):
        raise OrderRefused(400, "name each asset once, as a key of at most 128 characters", "order")
    return sorted(items), sorted(assets)


def mosaic_tile(path_params: Mapping[str, Any]) -> tuple[morecantile.TileMatrixSet, morecantile.Tile] | None:
    """The tile a request asks for, or ``None`` for a TileJSON, which names none.

    ``404`` for a tile outside the matrix, the answer a tile outside an item gets too. Every level of the
    released range has a mosaic (adr/0032 §6.2); what a tile costs is bounded by its budget, not its level.
    """
    if "z" not in path_params:
        return None
    try:
        tms = morecantile.tms.get(str(path_params["tileMatrixSetId"]))
        zoom, column, row = (int(path_params[name]) for name in ("z", "x", "y"))
    except (KeyError, ValueError, morecantile.errors.MorecantileError):
        raise OrderRefused(400, "not a tile of a grid this tiler serves", "order") from None
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


async def fetch_selection_items(
    batch_source: ItemBatchSource, dataset: str, item_ids: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """Every item of a selection, in pages of :data:`~earthx.adapters.federated_search.MAX_IDS` ids, one after the other.

    One request for a hundred ids, not one for each: two thousand scenes are twenty requests to the source, and they
    follow each other so that the creation of a selection does not press on it. A failure maps as in
    :func:`fetch_items`: the cache of the catalogue failing is a ``503`` with its reason, an id the source does not
    return a ``404`` that names it.
    """
    fetched: dict[str, dict[str, Any]] = {}
    for start in range(0, len(item_ids), MAX_IDS):
        try:
            fetched |= await fetch_items_or_refuse(batch_source, dataset, item_ids[start : start + MAX_IDS])
        except _CACHE_FAILURES as error:
            LOGGER.warning("the catalogue database failed under a mosaic selection: %s", type(error).__name__)
            raise OrderRefused(503, "mosaic tiles need the catalogue database, and it is not reachable", "items") from None
    return fetched


def check_one_overpass(items: Mapping[str, dict[str, Any]], viewer: ViewerInfo) -> None:
    """The scenes of a mosaic belong to one overpass, by the key the registry names (P19).

    The rule of the mosaic job (`api.intake`), with the same words: a mosaic over two overpasses is a
    time series, and a tile cannot show one.
    """
    keys: dict[str, tuple[str, ...]] = {}
    for item_id in sorted(items):
        try:
            keys[item_id] = overpass_key(items[item_id], viewer)
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


@dataclass(frozen=True, slots=True)
class TileScenes:
    """The scenes one tile reads, in the order of the mosaic, and how many that touch it the budget left out."""

    read: list[str]
    left_out: int


def touching_scenes(
    order: Sequence[str], outlines: Mapping[str, BaseGeometry], grid: tuple[morecantile.TileMatrixSet, morecantile.Tile]
) -> list[str]:
    """The ids of ``order`` whose outline meets the tile, in the same order; ``404`` where none does."""
    tms, tile = grid
    area = box(*tms.bounds(tile))
    touching = [item_id for item_id in order if outlines[item_id].intersects(area)]
    if not touching:
        raise OrderRefused(404, "the tile does not touch these items", "items")
    return touching


def scenes_touching(
    order: Sequence[str],
    outlines: Mapping[str, BaseGeometry],
    grid: tuple[morecantile.TileMatrixSet, morecantile.Tile],
    *,
    files_per_scene: int = 1,
    touching: Sequence[str] | None = None,
) -> TileScenes:
    """The ids of ``order`` whose outline meets the tile, in the same order, as far as the budget reaches.

    ``404`` where none does. Where more do than :data:`TILE_FILE_BUDGET` files allow, the tile reads the first of
    them in the order of the mosaic and says how many it left out (adr/0032 §6.2): the same URL always gives the same
    picture, and a CDN may keep it. ``files_per_scene`` is the number of assets each scene is read from. ``touching``
    is the answer of :func:`touching_scenes` where the caller has it already.
    """
    if files_per_scene < 1:
        raise ValueError("a scene is read from at least one file")
    if touching is None:
        touching = touching_scenes(order, outlines, grid)
    reach = max(1, TILE_FILE_BUDGET // files_per_scene)
    read = list(touching[:reach])
    LOGGER.info("mosaic tile reads %d of %d scenes", len(read), len(order))
    return TileScenes(read, len(touching) - len(read))


class TileOutcome:
    """What a mosaic tile knows about itself only after its scenes are chosen or read: kept for the response headers."""

    __slots__ = ("budget", "left_out")

    def __init__(self) -> None:
        self.left_out = 0
        self.budget: Any = None  # the `access.mosaic_tiles.ReadBudget` of the tile, once there is one

    @property
    def timed_out(self) -> bool:
        return bool(self.budget is not None and self.budget.timed_out)

    #: Where the outcome of a request lives in its ASGI scope, for the path dependency to find.
    SCOPE_KEY = "earthx.tile_outcome"

    @classmethod
    def of(cls, scope: Mapping[str, Any]) -> TileOutcome | None:
        outcome = scope.get(cls.SCOPE_KEY)
        return outcome if isinstance(outcome, cls) else None


class TileOutcomeHeaders:
    """ASGI middleware: :data:`PARTIAL_HEADER` on a mosaic tile that left scenes out, and ``no-store`` after its time ran out.

    TiTiler's tile route builds its own response, and the read that may run out of time ends inside it; so the path
    dependency and the reader write a :class:`TileOutcome` that lives in the request's scope, and the headers are set
    when the response starts. Only the paths under ``/collections/{dataset}/mosaic/`` get an outcome.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or "/mosaic/" not in scope.get("path", ""):
            await self.app(scope, receive, send)
            return
        outcome = TileOutcome()
        scope[TileOutcome.SCOPE_KEY] = outcome

        async def with_headers(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start" and (outcome.left_out or outcome.timed_out):
                headers = list(message.get("headers", []))
                partial = str(outcome.left_out).encode()
                if outcome.timed_out:
                    headers = [header for header in headers if header[0].lower() != b"cache-control"]
                    headers.append((b"cache-control", b"no-store"))
                    partial = b"time"
                headers.append((PARTIAL_HEADER.lower().encode(), partial))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, with_headers)
