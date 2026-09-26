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
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version

import psycopg

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.registry import DatasetConfig, DatasetRegistry, ItemHolding

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


def load_registry(conn: psycopg.Connection, registry: DatasetRegistry) -> tuple[str, ...]:
    """Write every entry, after checking that the database matches the pin.

    Returns the ids written, in registry order.
    """
    check_pgstac_version(conn)
    use_pgstac_search_path(conn)
    written = []
    for config in registry:
        load_collection(conn, config)
        written.append(config.dataset_id)
    return tuple(written)


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
