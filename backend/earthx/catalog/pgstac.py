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
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version

import psycopg

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.registry import DatasetConfig, DatasetRegistry


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
