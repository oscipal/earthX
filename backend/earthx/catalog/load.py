"""Command line entry point: bring a database up to date with the registry.

    python -m earthx.catalog.load

Runs the migrations this package owns, checks that pgstac matches the pin, writes
every registry entry as a collection, and commits. Idempotent from end to end: a
second run migrates nothing and rewrites the same collections.

Not part of the four processes of architekturplan.md 3.2 — it is the step that
prepares the catalogue for them, like `pypgstac migrate` prepares the schema.
Connection details come from the environment (``PGHOST`` and friends).
"""

from __future__ import annotations

import sys

import psycopg

from earthx.catalog.datasets import REGISTRY
from earthx.catalog.pgstac import PgstacError, load_registry
from earthx.catalog.schema import apply_migrations


def main() -> int:
    try:
        # One transaction for the whole run: either the database ends up matching the
        # registry, or it is left exactly as it was.
        with psycopg.connect(autocommit=False) as conn:
            applied = apply_migrations(conn)
            written = load_registry(conn, REGISTRY)
            conn.commit()
    except (PgstacError, psycopg.Error) as error:
        print(f"load failed: {error}", file=sys.stderr)
        return 1

    print(f"migrations applied: {', '.join(applied) if applied else 'none'}")
    print(f"collections written: {', '.join(written)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
