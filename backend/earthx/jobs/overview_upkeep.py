"""What keeps the pyramids honest after they are built: extend, expire, delete what nobody owns (M5-30b part 8b-3, adr/0032 §5.3, §8.4).

**Extension** (:func:`extend`). The term of a pyramid is 30 days from ``checked_at``. The worker never asks the source
itself (`jobs` may import neither `adapters` nor `gateway`): an unchanged `materialize` run writes ``confirmed_at`` through
`catalog`, and when that is later than ``checked_at``, every object of the version is copied onto itself with
``checked-at`` = ``confirmed_at`` (:func:`~earthx.objectstore.overviews.extend_version`, no read at the source, no byte
sent) and ``checked_at`` follows. A changed version is a new request and a new build; a source that cannot be reached
confirms nothing, so nothing is extended. A prototype source is never extended. Until the `harvester` takes over the
schedule (M5-24) `materialize` runs by hand; without a run the pyramid expires, at the latest after 31 days by the bucket
rule. The extension is only possible within the window, because the bucket rule may delete a part of the objects after it and an
extension would make a pyramid with holes look whole. A version whose objects are gone by the time it is to be extended is
expired like any other.

**Expiry** (:func:`sweep`). A ready pyramid whose term ran out (30 days, a prototype source's 7) is closed as ``failed``
with ``expired`` (the row first, by a conditional update) and then loses its objects. An unconfirmed one is not built
again by the hourly round; a successful `materialize` run of the same version makes it buildable again
(``catalog.pgstac.rearm_overview``). A confirmation holds an ordinary pyramid back from expiry only while the extension is
possible (:data:`~earthx.jobs.overviews.EXTEND_WINDOW`, just under 31 days from ``checked_at``); a prototype source's pyramid
is never held back. That is
what makes the 7 days of a prototype source real, since the bucket rule has 31 for everything under ``overviews/``.

**Orphans** (:func:`sweep`). Objects under ``overviews/`` that belong to no pyramid are deleted: those of a dataset and
version with no row in `earthx_overview` (the rows of a prototype source that `catalog-load` removed, an upload whose build
was given back) and those of a row that will not be built again (a failure that is not retried, an expired pyramid; see
:func:`~earthx.jobs.overviews.protected_versions`). The keys are
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
    """Expire the pyramids whose term ran out and delete the objects that belong to no pyramid."""
    expired = 0
    for dataset_id, version, checked_at in overviews.expired(conn):
        # The row first: only the caller whose conditional update matched deletes the objects, so a pyramid that was
        # extended or taken over meanwhile keeps them. A failure of the store after it leaves objects of a row that is
        # no longer protected: the orphan sweep below takes them in the next round.
        if overviews.mark_expired(conn, dataset_id, version, checked_at):
            expired += 1
            delete_version(store, dataset_id, version)
    keys = list(overview_keys(store))
    protected = overviews.protected_versions(conn)
    stray = [key for key in keys if _owner(key) not in protected]
    orphans = delete_keys(store, stray) if stray else 0
    if expired or orphans:
        LOGGER.info("overview pyramids swept", extra={"expired": expired, "orphans": orphans})
    return Swept(expired, orphans)


def extend(
    conn: psycopg.Connection, store: Store, datasets: set[str] | frozenset[str] | list[str], stopping: threading.Event
) -> int:
    """Extend the pyramids of ``datasets`` that the source confirmed after their ``checked_at``; the number extended.

    Only within :data:`~earthx.jobs.overviews.EXTEND_WINDOW` of ``checked_at`` (:func:`~earthx.jobs.overviews.to_extend`,
    asked again before each pyramid, since an earlier one can take hours). A failure of the object store ends the round and
    the next one tries again from the same state: ``checked_at`` moves only after every object carries the new time.
    """
    extended = 0
    for dataset_id, version, confirmed_at in overviews.to_extend(conn, datasets):
        if stopping.is_set():
            break
        if (dataset_id, version, confirmed_at) not in overviews.to_extend(conn, [dataset_id]):
            continue  # extended, expired or taken over since the list was made
        try:
            rewritten = extend_version(store, dataset_id, version, confirmed_at)
        except ResultNotFound:
            rewritten = 0
        if rewritten == 0:
            # Nothing left to extend: the bucket rule was faster. The pyramid is over, and as in :func:`sweep` the row
            # is closed first and the objects deleted only by the caller whose update matched.
            row = conn.execute(
                "SELECT checked_at FROM public.earthx_overview WHERE dataset_id = %s AND version = %s AND status = 'ready'",
                (dataset_id, version),
            ).fetchone()
            if row is not None and overviews.mark_expired(conn, dataset_id, version, row[0], lost=True):
                delete_version(store, dataset_id, version)
            continue
        if overviews.mark_extended(conn, dataset_id, version, confirmed_at):
            extended += 1
    if extended:
        LOGGER.info("overview pyramids extended", extra={"pyramids": extended})
    return extended
