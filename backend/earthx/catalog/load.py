"""Command line entry point: bring a database up to date with the registry.

    python -m earthx.catalog.load

Runs the migrations this package owns, checks that pgstac matches the pin, writes
every registry entry as a collection, removes the federated collections the registry
no longer lists, brings the index of the dataset search in line (M5-22b), and commits.
Idempotent from end to end: a second run migrates nothing, rewrites the same
collections and writes no row of the search index.

Not part of the four processes of architekturplan.md 3.2 — it is the step that
prepares the catalogue for them, like `pypgstac migrate` prepares the schema.
Connection details come from the environment (``PGHOST`` and friends).
"""

from __future__ import annotations

import sys

import psycopg

from earthx.catalog.datasets import registry
from earthx.catalog.pgstac import PgstacError, load_registry
from earthx.catalog.registry import ConfigError
from earthx.catalog.schema import apply_migrations
from earthx.catalog.search_index import write_search_index


def main() -> int:
    try:
        datasets = registry()
    except ConfigError as error:
        print(f"load failed: {error}", file=sys.stderr)
        return 1
    try:
        # One transaction for the whole run: either the database ends up matching the
        # registry, or it is left exactly as it was.
        with psycopg.connect(autocommit=False) as conn:
            applied = apply_migrations(conn)
            outcome = load_registry(conn, datasets)
            index = write_search_index(conn, datasets)
            conn.commit()
    except (PgstacError, psycopg.Error) as error:
        print(f"load failed: {error}", file=sys.stderr)
        return 1

    print(f"migrations applied: {', '.join(applied) if applied else 'none'}")
    print(f"collections written: {', '.join(outcome.written)}")
    print(f"collections removed: {', '.join(outcome.removed) if outcome.removed else 'none'}")
    print(f"search index written: {', '.join(index.written) if index.written else 'none'}")
    print(f"search index removed: {', '.join(index.removed) if index.removed else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
