"""Loading registry entries into our own pgstac.

The registry is the single source (KLAERUNGEN B13, point 3): a collection in pgstac
is written from a ``DatasetConfig``, never edited in the database by hand. Loading is
idempotent, so running it again after a deployment changes nothing.

Connection details come from the environment only (``PGHOST`` and friends, the same
variables the compose topology sets). There is no default pointing at a real database
and no connection string in code.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version

import psycopg

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.registry import PROTOTYPE_PREFIX, DatasetConfig, DatasetRegistry, ItemHolding

# pgstac.upsert_items stages a batch through `items_staging_upsert`; a very large
# generator (the Copernicus DEM's 26,450 tiles, M3-11b) is sent in pieces so this
# process never holds one multi-hundred-megabyte JSON array in memory at once.
ITEM_BATCH_SIZE = 1000


class PgstacError(RuntimeError):
    """The database is not in a state this code can work with."""


def expected_pgstac_version() -> str:
    """The pgstac version we are built against — the pin in requirements.txt.

    Read from the installed ``pypgstac`` rather than written down here, so that the
    version lives in exactly one place. M1-08 pins it and runs the migration as a
    compose service; this module only checks that the database agrees.
    """
    try:
        return installed_version("pypgstac")
    except PackageNotFoundError as error:  # pragma: no cover - a broken install
        raise PgstacError(
            "pypgstac is not installed; it is pinned in backend/requirements.txt"
        ) from error


def database_pgstac_version(conn: psycopg.Connection) -> str:
    """The pgstac version installed in this database."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('pgstac.migrations')")
        row = cur.fetchone()
        if row is None or row[0] is None:
            raise PgstacError(
                "no pgstac schema in this database — run `pypgstac migrate` "
                "(compose does it in the pgstac-migrate service)"
            )
        # pgstac's own accessor, for the same reason the tests read a collection back
        # through get_collection: ordering pgstac.migrations by datetime is ambiguous
        # when several rows are written in one transaction.
        cur.execute("SELECT pgstac.get_version()")
        row = cur.fetchone()
    if row is None or row[0] is None:
        raise PgstacError("pgstac reports no version — the schema was never migrated")
    return str(row[0])


def check_pgstac_version(conn: psycopg.Connection) -> str:
    """Fail loudly when the database speaks a different pgstac than we expect.

    A mismatch is not a warning: the collection shape and the functions we call are
    what changes between pgstac releases, and a half-understood schema fails later,
    further from the cause.
    """
    found = database_pgstac_version(conn)
    expected = expected_pgstac_version()
    if found != expected:
        raise PgstacError(
            f"pgstac version mismatch: database has {found}, pypgstac pins {expected}. "
            "Run `pypgstac migrate` against this database, or align the pin in "
            "backend/requirements.txt."
        )
    return found


def use_pgstac_search_path(conn: psycopg.Connection) -> None:
    """Put ``pgstac`` on the connection's search_path, as pgstac's own roles have it.

    pgstac's functions and triggers reference their tables unqualified — deleting a
    collection, for instance, runs ``DELETE FROM partition_stats`` from a trigger. A
    connection that does not carry the schema on its search_path fails there with a
    missing relation that has nothing to do with the statement that was sent.

    Our own bookkeeping table is schema-qualified (``public.earthx_migrations``), so
    this cannot pull it into the pgstac schema.
    """
    conn.execute("SET search_path TO pgstac, public")


def load_collection(conn: psycopg.Connection, config: DatasetConfig) -> None:
    """Write one registry entry as a STAC collection. Idempotent."""
    collection = to_stac_collection(config)
    with conn.cursor() as cur:
        cur.execute("SELECT pgstac.upsert_collection(%s::jsonb)", (json.dumps(collection),))


@dataclass(frozen=True, slots=True)
class LoadOutcome:
    """What one run of :func:`load_registry` did: the ids written, in registry order, and those removed."""

    written: tuple[str, ...]
    removed: tuple[str, ...]


def remove_gone_collections(conn: psycopg.Connection, registry: DatasetRegistry) -> tuple[str, ...]:
    """Delete the federated collections the registry no longer lists, with their items (adr/0017 rule IV, F5).

    The registry is the single source (B13 point 3): a dataset that left it must not stay in pgstac,
    or the STAC API would list it on. Only a collection that carries our own ``earthx:source`` with
    ``item_holding`` ``federated`` is removed. A materialized one holds items nobody else has
    (the DEM's tiles) and goes only by a decision of its own, and a collection that is not ours is
    left as it is. Returns the ids removed, sorted.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM pgstac.collections "
            "WHERE content->'earthx:source'->>'item_holding' = %s AND NOT (id = ANY(%s)) ORDER BY id",
            (ItemHolding.FEDERATED.value, [config.dataset_id for config in registry]),
        )
        gone = [row[0] for row in cur.fetchall()]
        for dataset_id in gone:
            cur.execute("SELECT pgstac.delete_collection(%s)", (dataset_id,))
    return tuple(gone)


def load_registry(conn: psycopg.Connection, registry: DatasetRegistry) -> LoadOutcome:
    """Write every entry and remove the federated collections that left the registry.

    Checks first that the database matches the pin. One run, one caller's transaction.
    """
    check_pgstac_version(conn)
    use_pgstac_search_path(conn)
    written = []
    for config in registry:
        load_collection(conn, config)
        written.append(config.dataset_id)
    return LoadOutcome(tuple(written), remove_gone_collections(conn, registry))


def read_collection(conn: psycopg.Connection, dataset_id: str) -> dict[str, object] | None:
    """The stored collection, or None. For tests and for a look from the outside."""
    with conn.cursor() as cur:
        cur.execute("SELECT content FROM pgstac.collections WHERE id = %s", (dataset_id,))
        row = cur.fetchone()
    return None if row is None else row[0]


def upsert_items(conn: psycopg.Connection, config: DatasetConfig, items: Iterable[Mapping[str, object]]) -> int:
    """Write the items of one materialized dataset into pgstac. Idempotent.

    Refuses a federated entry outright (KLAERUNGEN B13 point 3, M3-11a §3.5): items
    of a federated collection are never a second stored truth nobody reads — they
    stay a live question to the source. Refuses an item whose own ``collection``
    field does not name ``config.dataset_id``, rather than silently filing it under
    a different collection than whatever built it claims.

    The transaction is the caller's, exactly like :func:`load_collection` — nothing
    here commits. Returns the number of items sent to pgstac.
    """
    if config.source.item_holding is not ItemHolding.MATERIALIZED:
        raise PgstacError(
            f"{config.dataset_id} is a federated dataset; its items are never written to pgstac "
            "(KLAERUNGEN B13 point 3 — that would be a second truth nobody reads)"
        )
    count = 0
    batch: list[dict[str, object]] = []
    for item in items:
        item_collection = item.get("collection")
        if item_collection != config.dataset_id:
            raise PgstacError(
                f"{config.dataset_id}: item {item.get('id')!r} names collection "
                f"{item_collection!r}, not this dataset"
            )
        batch.append(dict(item))
        count += 1
        if len(batch) >= ITEM_BATCH_SIZE:
            _upsert_item_batch(conn, batch)
            batch = []
    if batch:
        _upsert_item_batch(conn, batch)
    return count


def _upsert_item_batch(conn: psycopg.Connection, items: list[dict[str, object]]) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pgstac.upsert_items(%s::jsonb)", (json.dumps(items),))


def delete_items_except(conn: psycopg.Connection, config: DatasetConfig, keep_ids: Iterable[str]) -> int:
    """Delete every item of a materialized collection not named in ``keep_ids``.

    The other half of ``adr/0009`` §7.3's "delsert": a tile a fresh
    ``tileList.txt`` no longer lists has to leave pgstac too, not just stop
    being written (M3-11b plan §3.4). Refuses a federated entry outright, the
    same guard :func:`upsert_items` already carries — a federated collection's
    items are never our own pgstac's to delete from.

    Like :func:`upsert_items`, the transaction is the caller's; this neither
    commits nor rolls back. Schema-qualified (``pgstac.items``), so unlike
    :func:`load_registry` this needs no ``search_path`` set on ``conn`` first.
    Returns the number of rows removed.
    """
    if config.source.item_holding is not ItemHolding.MATERIALIZED:
        raise PgstacError(
            f"{config.dataset_id} is a federated dataset; its items are never in our own pgstac to delete from"
        )
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM pgstac.items WHERE collection = %s AND NOT (id = ANY(%s))",
            (config.dataset_id, list(keep_ids)),
        )
        return cur.rowcount


@dataclass(frozen=True, slots=True)
class MaterializeRunRecord:
    """One row of ``public.earthx_materialize_runs`` (M3-11b plan §3.5, F5).

    ``status`` is ``"loaded"`` or ``"unchanged"`` — the same two outcomes
    :class:`earthx.adapters.cop_dem_bucket.MaterializeOutcome` reports. A run
    that failed is never recorded at all: its transaction rolls back
    (``discovery.materialize``), and it reports itself on stderr with a
    non-zero exit code instead.
    """

    dataset_id: str
    started_at: datetime
    finished_at: datetime
    status: str
    source_version: str
    items_written: int
    items_deleted: int
    listed: int
    missing: int
    withheld: int


def last_source_version(conn: psycopg.Connection, dataset_id: str) -> str | None:
    """The ``source_version`` of the most recent recorded run, or ``None`` if
    there has never been one — the materialize command's own "did the source
    change" question (``adr/0009`` §7.3), answered without asking the source
    for anything but a conditional ``GET`` first.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_version FROM public.earthx_materialize_runs "
            "WHERE dataset_id = %s ORDER BY started_at DESC LIMIT 1",
            (dataset_id,),
        )
        row = cur.fetchone()
    return None if row is None else row[0]


def last_loaded_count(conn: psycopg.Connection, dataset_id: str) -> int | None:
    """``listed`` of the most recent run that loaded items, or ``None`` if there has never been one.

    Only an estimate of how long the next run is; an "unchanged" run lists nothing and does not count.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT listed FROM public.earthx_materialize_runs "
            "WHERE dataset_id = %s AND status = 'loaded' ORDER BY started_at DESC LIMIT 1",
            (dataset_id,),
        )
        row = cur.fetchone()
    return None if row is None else row[0]


def record_materialize_run(conn: psycopg.Connection, record: MaterializeRunRecord) -> None:
    """Append one row. A run is never updated after it is written (migration
    004's own docstring) — a new run is always a new row.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.earthx_materialize_runs
                (dataset_id, started_at, finished_at, status, source_version,
                 items_written, items_deleted, listed, missing, withheld)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.dataset_id,
                record.started_at,
                record.finished_at,
                record.status,
                record.source_version,
                record.items_written,
                record.items_deleted,
                record.listed,
                record.missing,
                record.withheld,
            ),
        )


def request_overview(conn: psycopg.Connection, dataset_id: str, source_version: str) -> None:
    """Ask for the overview pyramid of ``source_version`` of a dataset (M5-30b part 8b, adr/0032 §5.2, F1).

    The worker builds it (`jobs`, which reads this table with SQL; `discovery` writes through here and may not import
    `jobs`). Idempotent per dataset and version: asking again only moves ``requested_at``, so a version that came back
    is the latest again. The transaction is the caller's, like :func:`record_materialize_run`.
    """
    conn.execute(
        """
        INSERT INTO public.earthx_overview_request (dataset_id, source_version) VALUES (%s, %s)
        ON CONFLICT (dataset_id, source_version) DO UPDATE SET requested_at = now()
        """,
        (dataset_id, source_version),
    )


def confirm_overview(conn: psycopg.Connection, dataset_id: str, source_version: str) -> bool:
    """Record that the source still has ``source_version``, for the pyramid built from it (M5-30b part 8b-3, adr/0032 §5.3).

    Called by an unchanged `materialize` run: ``confirmed_at`` of the ready pyramid of that version becomes now, and the
    worker then extends its term (`jobs`, which reads this column with SQL). ``True`` if a ready pyramid was marked;
    ``False`` when there is none (not built yet, failed, expired), which is no error: nothing is asked for here. A
    prototype source's pyramid is never confirmed: it is never extended (adr/0032 §8.4), so a confirmation would only
    keep it from expiring. The transaction is the caller's, like :func:`request_overview`.
    """
    row = conn.execute(
        """
        UPDATE public.earthx_overview SET confirmed_at = now(), updated_at = now()
        WHERE dataset_id = %s AND version = public.earthx_overview_version(%s) AND status = 'ready'
          AND left(dataset_id, %s) <> %s
        RETURNING 1
        """,
        (dataset_id, source_version, len(PROTOTYPE_PREFIX), PROTOTYPE_PREFIX),
    ).fetchone()
    return row is not None


#: The failure kinds `jobs` retries for a pyramid and the attempts it makes (`jobs.overviews.RETRYABLE_BUILD`,
#: `jobs.overviews.MAX_ATTEMPTS`);
#: `catalog` may not import `jobs`, a test holds the copies together.
_RETRYABLE = ("source_timeout", "source_5xx", "lease_lost", "source_unreachable")
_MAX_ATTEMPTS = 3


def rearm_overview(conn: psycopg.Connection, dataset_id: str, source_version: str) -> bool:
    """Make a pyramid buildable again after a successful run saw its version (M5-30b part 8b-3, adr/0032 §5).

    A pyramid of ``source_version`` that is ``failed`` and will not be tried again by itself (a failure that is not
    retryable, ``expired`` included, or one whose attempts are used up) is deleted; the request for that version stands,
    so the worker's next claim builds it as a new one, with its attempts counted from 1. A failure that is still
    waiting for its retry is left alone (the retry rules stay as they are), and so is every other state. ``True`` if a
    row was deleted. The transaction is the caller's.
    """
    row = conn.execute(
        """
        DELETE FROM public.earthx_overview
        WHERE dataset_id = %s AND version = public.earthx_overview_version(%s) AND status = 'failed'
          AND (NOT failure_kind = ANY(%s) OR attempts >= %s)
        RETURNING 1
        """,
        (dataset_id, source_version, list(_RETRYABLE), _MAX_ATTEMPTS),
    ).fetchone()
    if row is not None:
        request_overview(conn, dataset_id, source_version)
    return row is not None


def remove_prototype_overviews(conn: psycopg.Connection, registered: Collection[str]) -> int:
    """Delete the pyramid rows and requests of prototype sources that are not in the registry; the number of rows deleted.

    `catalog-load` without the prototype switch loads no ``proto-`` entry, so every such row goes (adr/0024 R6,
    plan M5-30b §8.10, Otto 13.11.2026). The objects under ``overviews/proto-*`` then have no row, and the hourly round of
    the worker deletes them: `catalog` does not reach the object store. With the switch on, the rows of the entries that
    are loaded stay. The transaction is the caller's.
    """
    keep = sorted(registered)
    deleted = 0
    for table in ("earthx_overview", "earthx_overview_request"):
        deleted += conn.execute(
            f"DELETE FROM public.{table} WHERE left(dataset_id, %s) = %s AND NOT (dataset_id = ANY(%s))",
            (len(PROTOTYPE_PREFIX), PROTOTYPE_PREFIX, keep),
        ).rowcount
    return deleted


@dataclass(frozen=True, slots=True)
class OverviewState:
    """What the tile route needs to know of the pyramid of one dataset (plan M5-30b §8.11).

    ``ready`` has a ``version``: the newest pyramid whose term has not run out. ``building`` means a build is running;
    ``failed`` a build that failed (``failure_kind`` names it; a retry that is waiting still reads ``failed``) or a pyramid
    whose term ran out (``expired``); ``none`` that there is no row at all.
    """

    status: str
    version: str | None = None
    failure_kind: str | None = None


async def overview_state_async(
    conn: psycopg.AsyncConnection,
    dataset_id: str,
    *,
    fresh_after: datetime,
    confirmed_after: datetime | None = None,
) -> OverviewState:
    """The state of the pyramid of a dataset for the tile route: the newest ready version in its term, else the state of the rest.

    A ready pyramid counts while ``checked_at`` is later than ``fresh_after`` (the caller subtracts the term of the dataset
    from now). The source's confirmation (``confirmed_at`` after ``checked_at``) holds it back only while the worker can still
    extend it, as the worker's own sweep reads it (adr/0032 §5.3): ``confirmed_after`` is the start of that window (now minus
    ``EXTEND_WINDOW``), and a pyramid checked before it expires whatever the confirmation. ``None`` (a prototype source: it is
    never extended, adr/0032 §8.4) means a confirmation counts for nothing. The hourly round of the worker closes the
    expired rows, and the route does not wait for it. Without a ready pyramid a running build is ``building``, otherwise the
    newest row decides: ``failed``, an expired ready row as ``failed`` with the kind ``expired``. Read-only on the caller's
    connection, like :func:`fetch_item`.
    """
    if fresh_after.tzinfo is None or (confirmed_after is not None and confirmed_after.tzinfo is None):
        raise ValueError("fresh_after and confirmed_after must be timezone-aware")
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT status, version, failure_kind, checked_at, confirmed_at
            FROM public.earthx_overview WHERE dataset_id = %s ORDER BY created_at DESC LIMIT 50
            """,
            (dataset_id,),
        )
        rows = await cur.fetchall()
    if not rows:
        return OverviewState("none")
    for status, version, _, checked_at, confirmed_at in rows:
        extendable = (
            confirmed_after is not None
            and confirmed_at is not None
            and confirmed_at > checked_at
            and checked_at > confirmed_after
        )
        if status == "ready" and (checked_at > fresh_after or extendable):
            return OverviewState("ready", version)
    if any(status == "building" for status, *_ in rows):
        return OverviewState("building")
    status, _, kind, *_ = rows[0]
    return OverviewState("failed", failure_kind="expired" if status == "ready" else kind)


async def fetch_item(conn: psycopg.AsyncConnection, dataset_id: str, item_id: str) -> dict[str, object] | None:
    """One item of a materialized dataset's own pgstac collection, or ``None``.

    ``conn`` is the caller's, from the same pool the tiler already holds for the
    search cache (``api/dependencies.py::cache_pool``) — this commits and closes
    nothing itself, the convention :class:`~earthx.catalog.search_cache.PostgresSearchCache`
    already follows. The federated read path (``earthx.adapters.get_item``) is not
    an alternative here: a federated dataset has no items in this database at all.
    """
    async with conn.cursor() as cur:
        await cur.execute("SELECT pgstac.get_item(%s, %s)", (item_id, dataset_id))
        row = await cur.fetchone()
    return None if row is None or row[0] is None else row[0]


def search_items_in_bbox(
    conn: psycopg.Connection,
    dataset_id: str,
    bbox: tuple[float, float, float, float],
    limit: int,
    period: tuple[datetime | None, datetime | None] = (None, None),
) -> list[dict[str, object]]:
    """Up to ``limit`` items of a materialized dataset whose footprint meets ``bbox`` (EPSG:4326), and whose time meets
    ``period`` where one end is given (open ends as ``None``; a series of days, M5-11).

    Through pgstac's own ``search``, so the items come back whole, as ``get_item`` gives them. Used by the
    measurement of the tile path (M5-30b, `api.measure_tiles`); like :func:`fetch_item` it commits nothing.
    """
    if limit < 1:
        raise ValueError("limit is at least 1")
    use_pgstac_search_path(conn)
    query: dict[str, object] = {"collections": [dataset_id], "bbox": list(bbox), "limit": limit}
    if period != (None, None):
        query["datetime"] = "/".join(".." if end is None else end.isoformat() for end in period)
    with conn.cursor() as cur:
        cur.execute("SELECT pgstac.search(%s::jsonb)", (json.dumps(query),))
        row = cur.fetchone()
    if row is None or row[0] is None:
        return []
    return list(row[0].get("features") or [])[:limit]


async def search_items_by_ids(
    conn: psycopg.AsyncConnection, dataset_id: str, item_ids: Sequence[str]
) -> list[dict[str, object]]:
    """The items of a materialized dataset's own collection with these ids, whole, as ``get_item`` gives them.

    One query for all of them, where :func:`fetch_item` is one per item: a selection of a thousand scenes is created
    from a few of these (M5-30b part 3). An id without an item is left out of the answer, not an error; the caller says
    which. Like :func:`fetch_item` it uses the caller's connection and commits nothing; the search path of pgstac is set
    for the transaction only, so it does not stay on a pooled connection.
    """
    if not item_ids:
        return []
    query = {"collections": [dataset_id], "ids": list(item_ids), "limit": len(item_ids)}
    async with conn.transaction(), conn.cursor() as cur:
        await cur.execute("SET LOCAL search_path TO pgstac, public")
        await cur.execute("SELECT pgstac.search(%s::jsonb)", (json.dumps(query),))
        row = await cur.fetchone()
    if row is None or row[0] is None:
        return []
    return list(row[0].get("features") or [])


async def search_items_in_bbox_async(
    conn: psycopg.AsyncConnection, dataset_id: str, bbox: tuple[float, float, float, float], limit: int
) -> list[dict[str, object]]:
    """:func:`search_items_in_bbox` on the caller's async connection, from the pool of the tiler (plan M5-30b §4.8).

    The pool's connections are in autocommit, and its connections are shared: ``search_path`` is set for one transaction
    only (``SET LOCAL``), never for the connection, which the next user of the pool would inherit.
    """
    if limit < 1:
        raise ValueError("limit is at least 1")
    query = {"collections": [dataset_id], "bbox": list(bbox), "limit": limit}
    async with conn.transaction():
        await conn.execute("SET LOCAL search_path TO pgstac, public")
        async with conn.cursor() as cur:
            await cur.execute("SELECT pgstac.search(%s::jsonb)", (json.dumps(query),))
            row = await cur.fetchone()
    if row is None or row[0] is None:
        return []
    return list(row[0].get("features") or [])[:limit]


async def read_item_holdings(conn: psycopg.AsyncConnection) -> dict[str, str | None]:
    """``earthx:source.item_holding`` of every collection in pgstac, by collection id.

    ``None`` where a collection carries no such field (one not written by
    :func:`load_collection`). Read at the start of `api` and `tiler`, which compare
    it with the registry (M4-01a, adr/0011 §7 D2); like :func:`fetch_item` it uses
    the caller's connection and commits nothing.
    """
    async with conn.cursor() as cur:
        await cur.execute("SELECT id, content->'earthx:source'->>'item_holding' FROM pgstac.collections")
        rows = await cur.fetchall()
    return {row[0]: row[1] for row in rows}
