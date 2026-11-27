"""Command line entry point: bring a database up to date with the registry.

    python -m earthx.catalog.load

Runs the migrations this package owns, checks that pgstac matches the pin, writes
every registry entry as a collection, removes the federated collections the registry
no longer lists, removes the pyramid rows of prototype sources the registry does not carry (adr/0024 R6; the worker
deletes their objects), brings the index of the dataset search in line (M5-22b), writes the region outlines and the
hand entries of ``listed/`` into the table of listed entries and applies ``blocked.yaml`` to it (M5-40), publishes
the stacks of the approved files under ``approvals/`` and hides again what a revoked one published (M5-20), marks the
listings a full entry names (``also_listed_as``) as its duplicates, brings the
rows of the published listed entries in the search index in line, and commits. After the commit it gives every row of
the index without a vector of the model one, a batch per transaction (M5-23), where the image has the model.
Idempotent from end to end: a second run migrates nothing, rewrites the same
collections and writes no row of the search index. At its end it prints the time
of each step (``time <step>: <seconds> s``), nothing of the entries (M5-66).

Not part of the four processes of architekturplan.md 3.2 — it is the step that
prepares the catalogue for them, like `pypgstac migrate` prepares the schema.
Connection details come from the environment (``PGHOST`` and friends).
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from earthx.catalog.approvals import load_approvals, publish
from earthx.catalog.datasets import registry
from earthx.catalog.embedding import MODEL_ENV, load_embedder
from earthx.catalog.licences import load_licences
from earthx.catalog.listed import load_blocked, load_catalog_tags, load_listed, load_regions
from earthx.catalog.listed_store import apply_blocklist, supersede, write_hand_entries, write_regions
from earthx.catalog.listing_store import mark_listings, withdraw
from earthx.catalog.municipalities import load_municipalities, write_municipalities
from earthx.catalog.pgstac import PgstacError, load_registry, remove_prototype_overviews
from earthx.catalog.registry import ConfigError
from earthx.catalog.schema import apply_migrations
from earthx.catalog.search_index import write_embeddings, write_listed_search_index, write_search_index
from earthx.catalog.sources import read_sources


class _Steps:
    """The time of each step of a run, printed at its end (M5-66): names and seconds, nothing of the entries."""

    def __init__(self) -> None:
        self.times: list[tuple[str, float]] = []

    @contextmanager
    def __call__(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.times.append((name, time.perf_counter() - started))

    def print(self) -> None:
        for name, seconds in self.times:
            print(f"time {name}: {seconds:.2f} s")
        print(f"time total: {sum(seconds for _, seconds in self.times):.2f} s")


def main() -> int:
    step = _Steps()
    try:
        with step("read files"):
            datasets = registry()
            # Every file is read and checked before the database is touched: a bad line stops the run with nothing
            # written.
            hand_entries = load_listed()
            blocklist = load_blocked()
            regions = load_regions()
            load_catalog_tags()
            # Checked like every file of the image, though only the report of the harvest reads them (adr/0033 §6.2).
            licences = load_licences(read_sources())
            approvals = load_approvals()
            municipalities = load_municipalities()
            embedder = load_embedder()
    except ConfigError as error:
        print(f"load failed: {error}", file=sys.stderr)
        return 1
    try:
        # One transaction for the whole run: either the database ends up matching the
        # registry, or it is left exactly as it was.
        with psycopg.connect(autocommit=False) as conn:
            # Each statement runs once per run: compiling it costs more than it saves (0.85 s of the hashes of 10⁵
            # listed entries, M5-66).
            conn.execute("SET LOCAL jit = off")
            with step("migrations"):
                applied = apply_migrations(conn)
            with step("collections"):
                outcome = load_registry(conn, datasets)
                prototype_rows = remove_prototype_overviews(conn, [config.dataset_id for config in datasets])
            with step("search index of full entries"):
                index = write_search_index(conn, datasets)
            full_ids = [config.dataset_id for config in datasets] + [gone.dataset_id for gone in datasets.retired]
            with step("regions"):
                regions_changed = write_regions(conn, regions)
            with step("municipalities"):
                # After the regions: a municipality refers to its canton.
                municipalities_changed = write_municipalities(conn, municipalities)
            with step("hand entries and blocklist"):
                # First the rows a full entry took over: a hand entry that went full leaves listed/ in the same
                # commit, and its row is then superseded, not a tombstone (adr/0033 §11).
                superseded = supersede(conn, full_ids)
                listed, blocked_hand = write_hand_entries(conn, hand_entries, blocklist, full_ids=full_ids)
                tombstones = apply_blocklist(conn, blocklist)
            with step("listings of full entries"):
                # The listings a full entry names (also_listed_as) are its duplicates, whatever the last report knew
                # (§11).
                taken_over = mark_listings(conn, datasets.listings)
            with step("licence rules taken back"):
                # A licence rule Otto took back hides its entries at once (adr/0033 §9), before anything is published.
                withdrawn = withdraw(conn, licences.granted)
            with step("approvals"):
                published = publish(conn, approvals)
            with step("search index of listed entries"):
                # Last: the listed entries of the index are the ones published now.
                listed_index = write_listed_search_index(conn, full_ids)
            with step("commit"):
                conn.commit()
            embedded = None
            if embedder is not None:
                # After the commit, a batch per transaction (M5-42 F6 = 1): an interrupted run keeps what it embedded,
                # and the next one embeds the rest.
                with step("embeddings"):
                    started = time.perf_counter()
                    embedded = write_embeddings(conn, embedder)
                    embedding_seconds = time.perf_counter() - started
    except (ConfigError, PgstacError, psycopg.Error) as error:
        print(f"load failed: {error}", file=sys.stderr)
        return 1

    print(f"migrations applied: {', '.join(applied) if applied else 'none'}")
    print(f"collections written: {', '.join(outcome.written)}")
    print(f"collections removed: {', '.join(outcome.removed) if outcome.removed else 'none'}")
    print(f"overview rows of prototype sources removed: {prototype_rows}")
    print(f"search index written: {', '.join(index.written) if index.written else 'none'}")
    print(f"search index removed: {', '.join(index.removed) if index.removed else 'none'}")
    print(f"search index rows of listed entries written: {listed_index.written}, removed: {listed_index.removed}")
    if embedded is None:
        print(f"embeddings: none, no model configured ({MODEL_ENV})")
    else:
        rate = embedded.written / embedding_seconds if embedded.written else 0.0
        print(f"embeddings written: {embedded.written} of {embedded.missing} in {embedding_seconds:.1f} s ({rate:.0f}/s)")
    print(f"region rows changed: {regions_changed}")
    print(f"municipality rows changed: {municipalities_changed}")
    print(f"listed hand entries written: {', '.join(listed) if listed else 'none'}")
    print(f"listed hand entries left out as blocked: {', '.join(blocked_hand) if blocked_hand else 'none'}")
    print(f"listed entries superseded by a full entry: {', '.join(superseded) if superseded else 'none'}")
    print(f"listed entries taken over by a full entry (also_listed_as): {', '.join(taken_over) if taken_over else 'none'}")
    print(f"listed entries turned into tombstones by the blocklist: {tombstones}")
    print(f"listed entries back on the waiting list, their licence rule taken back: {withdrawn}")
    for name, count in sorted(published.published.items()):
        print(f"listed entries published by {name}: {count}")
    for name, count in sorted(published.revoked.items()):
        print(f"listed entries hidden again by the revoked {name}: {count}")
    for name in published.stale:
        print(f"approval not applied, its stack expired (a later report took it over): {name}")
    step.print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
