"""Where the tile route finds the tile of an overview pyramid (M5-30b part 9, adr/0032 §5.2, plan §8.11).

A dataset with ``viewer.overview: pyramid`` (GLO-30, WorldCover) draws the levels below ``min_zoom`` from a pyramid in
the platform's own object store, ``overviews/{dataset}/{version}/{z}/{x}/{y}.tif``; a substitute (swissALTI3D) draws the
pyramid of its stand-in below the stand-in's own ``min_zoom``. This module answers two questions for the path
dependency of that route, and nothing else:

* **Which version?** The newest ``ready`` row of ``earthx_overview`` for the dataset whose term has not run out
  (:func:`earthx.catalog.pgstac.overview_state_async`). Asked at most every :data:`READY_KEPT` for a ready answer and every
  :data:`UNREADY_KEPT` for the others, per dataset, in this process: a view asks for a dozen tiles at once and the rows
  change when a build ends, not per tile. Neither is state a second instance would miss: two instances read the same rows.
* **The bytes.** One ``GetObject`` with the read key of the tiler (`objectstore`, KLAERUNGEN B8 Nachtrag, adr/0015
  §14c: the store is our own and does not pass `gateway`), in the thread pool because the client is blocking. A tile
  without data is not stored, so an absent object is a tile with nothing in it: ``404``, like a tile outside an item.

What the answers mean for the map is :func:`refusal_of`: no pyramid is a ``404`` with ``X-EarthX-Overview`` saying why,
never a read of the original files (they are why a pyramid exists).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import morecantile
import psycopg
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from earthx.catalog.pgstac import OverviewState, overview_state_async
from earthx.objectstore.errors import ObjectStoreError
from earthx.objectstore.overviews import EXTEND_WINDOW, PROTOTYPE_PREFIX, read_tile, term_of
from earthx.objectstore.results import Store

LOGGER = logging.getLogger("earthx.api.overview_tiles")

__all__ = [
    "OVERVIEW_HEADER",
    "OVERVIEW_SOURCE",
    "READY_KEPT",
    "UNREADY_KEPT",
    "OverviewSources",
    "is_prototype",
    "refusal_of",
]

#: Says why a tile of a pyramid is missing: ``building`` or ``failed`` (adr/0032 §5.2).
OVERVIEW_HEADER = "X-EarthX-Overview"
#: The value of ``X-EarthX-Source`` for a tile read from a dataset's own pyramid (a stand-in's tile says ``substitute``).
OVERVIEW_SOURCE = "overview"
#: How long (seconds) the version a ready answer names is believed. The old version's objects stay for their term, so a
#: version that was replaced meanwhile still gives a good picture.
READY_KEPT = 30.0
#: How long the other answers are believed: short, so that a map that asks again finds the pyramid soon after the build ends.
UNREADY_KEPT = 5.0
_CACHE_SIZE = 64


def is_prototype(dataset_id: str) -> bool:
    """Whether the dataset is a prototype source: its tiles are never kept (adr/0024 R7)."""
    return dataset_id.startswith(PROTOTYPE_PREFIX)


def refusal_of(state: OverviewState) -> HTTPException:
    """The ``404`` of a dataset that has no pyramid to read, with the reason in ``X-EarthX-Overview``.

    ``building`` for a build that is running and for a dataset with no row at all (the hourly round of the worker asks for the
    missing pyramid of a materialized dataset, and an unmaterialized one has no tile to show); ``failed`` for a build that
    failed and for a pyramid that expired (an expired one is built again by the next successful run of ``materialize``). The
    answer is not kept by a cache (``no-store``): it changes as soon as the build ends, under the same URL.
    """
    reason = "failed" if state.status == "failed" else "building"
    return HTTPException(
        status_code=404,
        detail=f"there is no overview of this dataset yet ({reason}); zoom in for the original files",
        headers={OVERVIEW_HEADER: reason, "Cache-Control": "no-store"},
    )


class OverviewSources:
    """The pyramids as the tiler reads them: which version is ready, and the bytes of one tile."""

    def __init__(
        self,
        store: Store,
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._clock = clock
        self._now = now
        self._states: dict[str, tuple[float, OverviewState]] = {}

    async def state(self, pool: Any, dataset_id: str) -> OverviewState:
        """The state of the pyramid of ``dataset_id``; ``503`` where the database is not there or fails."""
        kept = self._states.get(dataset_id)
        if kept is not None:
            at, state = kept
            if self._clock() - at < (READY_KEPT if state.status == "ready" else UNREADY_KEPT):
                return state
        if pool is None:
            raise HTTPException(status_code=503, detail="overviews need the catalogue database, which is not reachable")
        now = self._now()
        # A confirmation holds a pyramid back only inside the window the worker can still extend it in, and never for a
        # prototype source (the same rule as the worker's sweep, `jobs.overviews`).
        confirmed_after = None if is_prototype(dataset_id) else now - EXTEND_WINDOW
        try:
            async with pool.connection() as conn:
                state = await overview_state_async(conn, dataset_id, fresh_after=now - term_of(dataset_id), confirmed_after=confirmed_after)
        except psycopg.Error as error:
            # The kind of failure only: the driver's text can name the host and the user.
            LOGGER.warning("the catalogue failed under the tile of an overview: %s", type(error).__name__)
            raise HTTPException(
                status_code=503, detail="overviews need the catalogue database, which is not reachable"
            ) from None
        if len(self._states) >= _CACHE_SIZE:
            self._states.clear()
        self._states[dataset_id] = (self._clock(), state)
        return state

    async def tile(
        self, dataset_id: str, version: str, grid: tuple[morecantile.TileMatrixSet, morecantile.Tile]
    ) -> bytes:
        """The bytes of the stored tile; ``404`` for none (a tile without data is not stored), ``503`` if the store fails."""
        tile = grid[1]
        try:
            stored = await run_in_threadpool(read_tile, self._store, dataset_id, version, tile.z, tile.x, tile.y)
        except ObjectStoreError as error:
            # The class only: an object store error names the operation, never the key, and the log keeps no more.
            LOGGER.warning("the overview store could not be read: %s", type(error).__name__)
            raise HTTPException(status_code=503, detail="the overview store is not available; try again") from None
        if stored is None:
            raise HTTPException(status_code=404, detail="the tile has no data")
        return stored.data
