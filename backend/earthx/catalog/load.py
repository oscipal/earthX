"""Command line entry point: bring a database up to date with the registry.

    python -m earthx.catalog.load

Runs the migrations this package owns, checks that pgstac matches the pin, writes
every registry entry as a collection, removes the federated collections the registry
no longer lists, removes the pyramid rows of prototype sources the registry does not carry (adr/0024 R6; the worker
deletes their objects), brings the index of the dataset search in line (M5-22b), writes the region outlines and the
hand entries of ``listed/`` into the table of listed entries and applies ``blocked.yaml`` to it (M5-40), and commits.
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
from earthx.catalog.listed import load_blocked, load_listed, load_regions
from earthx.catalog.listed_store import apply_blocklist, supersede, write_hand_entries, write_regions
from earthx.catalog.pgstac import PgstacError, load_registry, remove_prototype_overviews
from earthx.catalog.registry import ConfigError
from earthx.catalog.schema import apply_migrations
from earthx.catalog.search_index import write_search_index


def main() -> int:
    try:
        datasets = registry()
        # Every file is read and checked before the database is touched: a bad line stops the run with nothing written.
        hand_entries = load_listed()
        blocklist = load_blocked()
        regions = load_regions()
    except ConfigError as error:
        print(f"load failed: {error}", file=sys.stderr)
        return 1
    try:
        # One transaction for the whole run: either the database ends up matching the
        # registry, or it is left exactly as it was.
        with psycopg.connect(autocommit=False) as conn:
            applied = apply_migrations(conn)
            outcome = load_registry(conn, datasets)
            prototype_rows = remove_prototype_overviews(conn, [config.dataset_id for config in datasets])
            index = write_search_index(conn, datasets)
            full_ids = [config.dataset_id for config in datasets] + [gone.dataset_id for gone in datasets.retired]
            regions_changed = write_regions(conn, regions)
            # First the rows a full entry took over: a hand entry that went full leaves listed/ in the same commit,
            # and its row is then superseded, not a tombstone (adr/0033 §11).
            superseded = supersede(conn, full_ids)
            listed, blocked_hand = write_hand_entries(conn, hand_entries, blocklist, full_ids=full_ids)
            tombstones = apply_blocklist(conn, blocklist)
            conn.commit()
    except (ConfigError, PgstacError, psycopg.Error) as error:
        print(f"load failed: {error}", file=sys.stderr)
        return 1

    print(f"migrations applied: {', '.join(applied) if applied else 'none'}")
    print(f"collections written: {', '.join(outcome.written)}")
    print(f"collections removed: {', '.join(outcome.removed) if outcome.removed else 'none'}")
    print(f"overview rows of prototype sources removed: {prototype_rows}")
    print(f"search index written: {', '.join(index.written) if index.written else 'none'}")
    print(f"search index removed: {', '.join(index.removed) if index.removed else 'none'}")
    print(f"region rows changed: {regions_changed}")
    print(f"listed hand entries written: {', '.join(listed) if listed else 'none'}")
    print(f"listed hand entries left out as blocked: {', '.join(blocked_hand) if blocked_hand else 'none'}")
    print(f"listed entries superseded by a full entry: {', '.join(superseded) if superseded else 'none'}")
    print(f"listed entries turned into tombstones by the blocklist: {tombstones}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
