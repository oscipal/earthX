"""Tiles of a job result, read from the object store without a database (M4-13c-5, plan §3.4).

``/results/{result_id}/…`` is the tile side of a finished raster job. The browser learns the
``result_id`` from the ``tiles`` link of the job's results document (`processing_route`); the
tiler knows no job, no recipe and no database row — only the file at
``results/{result_id}/result.tif`` and what the store itself says about it:

* **Its life.** The bucket rule deletes a result 7 days after it was written
  (`objectstore.results.RESULT_TTL`, adr/0015 §7.3), so ``Last-Modified + 7 days`` is the day it
  goes. A minute before that the route answers ``410`` (`MIN_REMAINING`); a file that is not there
  answers ``404``. The supervisor uploads before it closes the run and sets ``expires_at`` to the
  finish plus 7 days, so the tiler never serves past the API's own end of life.
* **Its bytes.** GDAL opens the file over ``/vsicurl/`` with a URL that `objectstore` signed for the
  internal endpoint, good for 15 minutes. That URL is not an address from a source and does not pass
  `gateway` (KLAERUNGEN B8, Nachtrag 2026-10-05, adr/0015 Nachtrag 2026-10-20); it never leaves this
  process. The tiler holds one read-only key of its own (`earthx-tiler`), not the worker's.

What this process remembers is two small entries per result for a few seconds — the ``HEAD`` answer (60 s)
and the signed URL (10 minutes, so that GDAL's read cache, which is keyed by URL, still hits for the next
tile). Neither is state a second instance would miss: two instances answer a URL the same way.

Not here, on purpose: ``op``, ``expression`` and every other free parameter (``400``), and statistics,
info and point queries (plan M4-13c §5).
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import HTTPException, Path, Request
from starlette.concurrency import run_in_threadpool
from titiler.core.dependencies import BidxParams

from earthx.access.tiles import EarthxTilerFactory
from earthx.objectstore.errors import ObjectStoreError, ResultExpiring, ResultNotFound
from earthx.objectstore.results import MIN_REMAINING, RESULT_TTL, Store, is_result_id, result_modified, signed_read
from earthx.readers.cog import AssetPath

LOGGER = logging.getLogger("earthx.api.result_tiles")

ROUTER_PREFIX = "/results/{result_id}"
RESULT_FILE = "result.tif"
# `AssetPath` carries a dataset and an item for the statistics cache of a source; a result has neither,
# and its statistics are not served (plan M4-13c §5).
_NO_DATASET = "results"

# How long the answer of a `HEAD` is believed (plan §3.4: "höchstens 60 s").
HEAD_KEPT = timedelta(seconds=60)
# A signed URL is reused for 10 of its 15 minutes: GDAL's read cache is keyed by the URL, and a fresh
# signature for every tile would make each one open the file again.
URL_REUSED = timedelta(minutes=10)
CACHE_SIZE = 128

# TiTiler's free parameters, and the operator of a source's tile: a result is read as it is.
_REFUSED_PARAMETERS = ("expression", "algorithm", "algorithm_params", "op", "op_version", "params")

# GDAL asks `HEAD` first; a URL signed for GET is refused for it, and the fallback costs a request.
GDAL_OPTIONS = {"CPL_VSIL_CURL_USE_HEAD": "NO"}


@dataclass(slots=True)
class _Entry:
    modified: datetime
    checked: float
    url: str | None = None
    signed: float = 0.0


class ResultSources:
    """The store as the tiler reads it: when a result was written, and a URL for GDAL."""

    def __init__(
        self,
        store: Store,
        *,
        clock: Callable[[], float],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._clock = clock
        self._now = now
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = threading.Lock()

    def url(self, result_id: str) -> str:
        """A readable URL for ``result.tif``; :class:`ResultNotFound` or :class:`ResultExpiring` otherwise.

        Blocking (a ``HEAD`` to the store at most every 60 s per result): called off the event loop.
        """
        with self._lock:
            entry = self._entries.get(result_id)
        if entry is None or self._clock() - entry.checked >= HEAD_KEPT.total_seconds():
            modified = result_modified(self._store, result_id, RESULT_FILE)
            # Asked again, the file is the same: the URL signed for it stays good for its own 10 minutes.
            entry = _Entry(modified, self._clock(), *(() if entry is None else (entry.url, entry.signed)))
        end = entry.modified + RESULT_TTL
        if end - self._now() < MIN_REMAINING:
            raise ResultExpiring("the result expires in less than 60 seconds")
        if entry.url is None or self._clock() - entry.signed >= URL_REUSED.total_seconds():
            entry.url = signed_read(self._store, result_id, RESULT_FILE, not_after=end, now=self._now())
            entry.signed = self._clock()
        with self._lock:
            self._entries[result_id] = entry
            self._entries.move_to_end(result_id)
            while len(self._entries) > CACHE_SIZE:
                self._entries.popitem(last=False)
        return entry.url


def gdal_path(url: str) -> str:
    """The path GDAL reads: the signed URL, as it came from `objectstore`."""
    return f"/vsicurl/{url}"


async def result_path(
    request: Request, result_id: Annotated[str, Path(description="the result of a finished job")]
) -> AssetPath:
    """Turn a ``result_id`` into something a reader may open — and nothing else.

    The shape is checked before anything is read, so a made-up identifier costs no request to the
    store. ``404`` for a result that is not there and for one that was never written, ``410`` from a minute
    before its end, ``503`` when the store cannot be reached or this process has no key for it.
    """
    for name in _REFUSED_PARAMETERS:
        if name in request.query_params:
            raise HTTPException(status_code=400, detail=f"{name!r} is not accepted on a result's tiles")
    if not is_result_id(result_id):
        raise HTTPException(status_code=404, detail="there is no such result")
    sources: ResultSources | None = getattr(request.app.state, "earthx_results", None)
    if sources is None:
        raise HTTPException(status_code=503, detail="results are not served by this process")
    try:
        url = await run_in_threadpool(sources.url, result_id)
    except ResultNotFound:
        raise HTTPException(status_code=404, detail="there is no such result") from None
    except ResultExpiring:
        raise HTTPException(status_code=410, detail="the result has expired") from None
    except ObjectStoreError:
        LOGGER.warning("the result store could not be read")
        raise HTTPException(status_code=503, detail="the result store is not available; try again") from None
    return AssetPath(gdal_path(url), dataset_id=_NO_DATASET, item_id="", asset=RESULT_FILE)


class ResultTilerFactory(EarthxTilerFactory):
    """TiTiler's tile and TileJSON routes over a result, and no others."""

    def register_routes(self) -> None:
        self.tile()
        self.tilejson()


def result_environment(request: Request) -> dict[str, str]:
    """The central GDAL configuration (M1-03) plus the one setting a signed URL needs."""
    return {**request.app.state.earthx_gdal_options, **GDAL_OPTIONS}


def _no_process() -> None:
    return None


def build_result_factory() -> ResultTilerFactory:
    return ResultTilerFactory(
        path_dependency=result_path,
        # `BidxParams`, not TiTiler's default: that one takes an `expression`.
        layer_dependency=BidxParams,
        # No `algorithm`: TiTiler's default would put it into the schema (`_REFUSED_PARAMETERS` answers it).
        process_dependency=_no_process,
        environment_dependency=result_environment,
        router_prefix=ROUTER_PREFIX,
        name="result-tiles",
    )
