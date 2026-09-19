"""T-C: loading a registry entry into a real pgstac.

The acceptance criteria of M1-04: the collection is in pgstac with the right flags,
an entry without an explicitly set capability is rejected (that one is T-A, in
tests/catalog), and loading is idempotent.
"""

from __future__ import annotations

import pytest

from earthx.catalog.datasets import REGISTRY, SENTINEL_2_L2A
from earthx.catalog.pgstac import (
    PgstacError,
    check_pgstac_version,
    database_pgstac_version,
    expected_pgstac_version,
    load_collection,
    load_registry,
    read_collection,
)


class TestVersionCheck:
    def test_the_database_matches_the_pin(self, conn) -> None:
        """One pin, in requirements.txt; this only checks the database agrees."""
        assert check_pgstac_version(conn) == expected_pgstac_version()

    def test_the_version_is_read_from_the_database_not_assumed(self, conn) -> None:
        assert database_pgstac_version(conn) == expected_pgstac_version()

    def test_a_database_without_pgstac_says_so(self, conn) -> None:
        """The message has to name the fix, not just the symptom.

        The schema really is dropped, inside the transaction the fixture rolls back —
        a search_path trick would not test it, because the lookup is schema-qualified.
        """
        conn.execute("DROP SCHEMA pgstac CASCADE")
        with pytest.raises(PgstacError, match="pypgstac migrate"):
            database_pgstac_version(conn)

    def test_a_version_mismatch_names_both_versions(self, conn) -> None:
        """Silently working against a different pgstac fails later, further from here."""
        conn.execute("UPDATE pgstac.migrations SET version = '0.0.1-not-real'")
        with pytest.raises(PgstacError, match="0.0.1-not-real"):
            check_pgstac_version(conn)


class TestLoading:
    def test_the_collection_lands_in_pgstac(self, conn) -> None:
        load_collection(conn, SENTINEL_2_L2A)
        stored = read_collection(conn, SENTINEL_2_L2A.dataset_id)
        assert stored is not None
        assert stored["id"] == "sentinel-2-c1-l2a"
        assert stored["license"] == "proprietary"

    def test_the_earthx_fields_survive_the_round_trip(self, conn) -> None:
        """They are the reason we keep collections ourselves (architekturplan.md 5.2)."""
        load_collection(conn, SENTINEL_2_L2A)
        stored = read_collection(conn, SENTINEL_2_L2A.dataset_id)
        assert stored["earthx:source"]["source_collection_id"] == "sentinel-2-c1-l2a"
        assert stored["earthx:capabilities"]["quad_pol"] is False
        assert stored["earthx:license_flags"]["tier"] == "processing"
        assert stored["earthx:license_flags"]["terms_url"].endswith("Sentinel_Data_Legal_Notice")

    def test_loading_twice_leaves_one_row(self, conn) -> None:
        """Acceptance criterion: loading is idempotent."""
        load_collection(conn, SENTINEL_2_L2A)
        first = read_collection(conn, SENTINEL_2_L2A.dataset_id)
        load_collection(conn, SENTINEL_2_L2A)
        second = read_collection(conn, SENTINEL_2_L2A.dataset_id)

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pgstac.collections WHERE id = %s", (SENTINEL_2_L2A.dataset_id,))
            assert cur.fetchone()[0] == 1
        assert first == second

    def test_a_changed_entry_replaces_the_stored_one(self, conn) -> None:
        from dataclasses import replace

        load_collection(conn, SENTINEL_2_L2A)
        load_collection(conn, replace(SENTINEL_2_L2A, title="Sentinel-2 L2A (Collection 1)"))
        stored = read_collection(conn, SENTINEL_2_L2A.dataset_id)

        assert stored["title"] == "Sentinel-2 L2A (Collection 1)"
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pgstac.collections WHERE id = %s", (SENTINEL_2_L2A.dataset_id,))
            assert cur.fetchone()[0] == 1

    def test_loading_the_registry_writes_every_entry(self, conn) -> None:
        written = load_registry(conn, REGISTRY)
        assert written == tuple(entry.dataset_id for entry in REGISTRY)
        for dataset_id in written:
            assert read_collection(conn, dataset_id) is not None

    def test_an_unknown_collection_is_absent_not_empty(self, conn) -> None:
        """adr/0005 rule I rests on this: not stored is not "stored and empty"."""
        load_collection(conn, SENTINEL_2_L2A)
        assert read_collection(conn, "does-not-exist") is None

    def test_pgstac_reads_it_back_as_a_collection(self, conn) -> None:
        """Not our own SELECT: pgstac's own accessor has to accept what we wrote."""
        load_collection(conn, SENTINEL_2_L2A)
        with conn.cursor() as cur:
            cur.execute("SELECT pgstac.get_collection(%s)", (SENTINEL_2_L2A.dataset_id,))
            content = cur.fetchone()[0]
        assert content["id"] == SENTINEL_2_L2A.dataset_id
