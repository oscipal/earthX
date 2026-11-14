"""What keeps the pyramids honest after they are built: extend, expire, delete what nobody owns (M5-30b part 8b-3, adr/0032 §5.3, §8.4).

**Extension** (:func:`extend`). The term of a pyramid is 30 days from ``checked_at``. The worker never asks the source
itself (`jobs` may import neither `adapters` nor `gateway`): an unchanged `materialize` run writes ``confirmed_at`` through
`catalog`, and when that is later than ``checked_at``, every object of the version is copied onto itself with
``checked-at`` = ``confirmed_at`` (:func:`~earthx.objectstore.overviews.extend_version`, no read at the source, no byte
sent) and ``checked_at`` follows. A changed version is a new request and a new build; a source that cannot be reached
confirms nothing, so nothing is extended. A prototype source is never extended. Until the `harvester` takes over the
schedule (M5-24) `materialize` runs by hand; without a run the pyramid expires, at the latest after 31 days by the bucket
rule. A version whose objects are gone by the time it is to be extended is expired like any other.

**Expiry** (:func:`sweep`). A ready pyramid whose term ran out (30 days, a prototype source's 7) loses its objects and its
row becomes ``failed`` with ``expired``: nothing builds it again until the next source version is asked for. That is
what makes the 7 days of a prototype source real, since the bucket rule has 31 for everything under ``overviews/``.

**Orphans** (:func:`sweep`). Objects under ``overviews/`` whose dataset and version have no row in `earthx_overview` (the
rows of a prototype source that `catalog-load` removed, an upload whose build was given back) are deleted. The keys are
listed *before* the rows are read, so a build that starts in between has its row and keeps its objects.

The extension copies thousands of objects and runs in the thread of the builds; the expiry and the orphans are a few
requests and run in the hourly round of the maintenance thread. Neither logs a dataset, a version or a key.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import psycopg

from earthx.jobs import overviews
from earthx.objectstore.errors import ResultNotFound
from earthx.objectstore.overviews import delete_keys, delete_version, extend_version, overview_keys
from earthx.objectstore.results import Store

__all__ = ["Swept", "extend", "sweep"]

LOGGER = logging.getLogger("earthx.jobs")


@dataclass(frozen=True, slots=True)
class Swept:
    expired: int = 0
    orphans: int = 0


def _owner(key: str) -> tuple[str, str] | None:
    """``(dataset, version)`` of a key ``overviews/{dataset}/{version}/...``, ``None`` for any other shape."""
    parts = key.split("/")
    return (parts[1], parts[2]) if len(parts) >= 4 and parts[0] == "overviews" else None


def sweep(conn: psycopg.Connection, store: Store) -> Swept:
    """Expire the pyramids whose term ran out and delete the objects that have no row."""
    expired = 0
    for dataset_id, version, checked_at in overviews.expired(conn):
        delete_version(store, dataset_id, version)
        if overviews.mark_expired(conn, dataset_id, version, checked_at):
            expired += 1
    keys = list(overview_keys(store))
    rows = overviews.known_versions(conn)
    stray = [key for key in keys if _owner(key) not in rows]
    orphans = delete_keys(store, stray) if stray else 0
    if expired or orphans:
        LOGGER.info("overview pyramids swept", extra={"expired": expired, "orphans": orphans})
    return Swept(expired, orphans)


def extend(
    conn: psycopg.Connection, store: Store, datasets: set[str] | frozenset[str] | list[str], stopping: threading.Event
) -> int:
    """Extend the pyramids of ``datasets`` that the source confirmed after their ``checked_at``; the number extended.

    A failure of the object store ends the round and the next one tries again from the same state: ``checked_at`` moves
    only after every object carries the new time.
    """
    extended = 0
    for dataset_id, version, confirmed_at in overviews.to_extend(conn, datasets):
        if stopping.is_set():
            break
        try:
            rewritten = extend_version(store, dataset_id, version, confirmed_at)
        except ResultNotFound:
            rewritten = 0
        if rewritten == 0:
            # Nothing left to extend: the bucket rule was faster. The pyramid is over; the next version builds a new one.
            row = conn.execute(
                "SELECT checked_at FROM public.earthx_overview WHERE dataset_id = %s AND version = %s AND status = 'ready'",
                (dataset_id, version),
            ).fetchone()
            if row is not None:
                delete_version(store, dataset_id, version)
                overviews.mark_expired(conn, dataset_id, version, row[0])
            continue
        if overviews.mark_extended(conn, dataset_id, version, confirmed_at):
            extended += 1
    if extended:
        LOGGER.info("overview pyramids extended", extra={"pyramids": extended})
    return extended
