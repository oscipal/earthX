"""T-C: loading a registry entry into a real pgstac.

The acceptance criteria of M1-04: the collection is in pgstac with the right flags,
an entry without an explicitly set capability is rejected (that one is T-A, in
tests/catalog), and loading is idempotent.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace

import psycopg
import pytest

from earthx.catalog.datasets import COP_DEM_GLO_30, REGISTRY, SENTINEL_2_L2A
from earthx.catalog.load import main
from earthx.catalog.pgstac import (
    PgstacError,
    check_pgstac_version,
    database_pgstac_version,
    expected_pgstac_version,
    load_collection,
    load_registry,
    read_collection,
    remove_gone_collections,
    use_pgstac_search_path,
)
from earthx.catalog.registry import DatasetRegistry


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
        # An explicit "unknown" is a null that must not vanish on the way (M4-19b).
        assert stored["earthx:band_units"]["red"] == "1"
        assert "scl" in stored["earthx:band_units"] and stored["earthx:band_units"]["scl"] is None

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
        load_collection(conn, SENTINEL_2_L2A)
        load_collection(conn, replace(SENTINEL_2_L2A, title="Sentinel-2 L2A (Collection 1)"))
        stored = read_collection(conn, SENTINEL_2_L2A.dataset_id)

        assert stored["title"] == "Sentinel-2 L2A (Collection 1)"
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM pgstac.collections WHERE id = %s", (SENTINEL_2_L2A.dataset_id,))
            assert cur.fetchone()[0] == 1

    def test_loading_the_registry_writes_every_entry(self, conn) -> None:
        outcome = load_registry(conn, REGISTRY)
        assert outcome.written == tuple(entry.dataset_id for entry in REGISTRY)
        for dataset_id in outcome.written:
            assert read_collection(conn, dataset_id) is not None

    def test_an_unknown_collection_is_absent_not_empty(self, conn) -> None:
        """adr/0005 rule I rests on this: not stored is not "stored and empty"."""
        load_collection(conn, SENTINEL_2_L2A)
        assert read_collection(conn, "does-not-exist") is None

    def test_deleting_needs_pgstac_on_the_search_path(self, conn) -> None:
        """pgstac's delete trigger says `DELETE FROM partition_stats`, unqualified.

        Without the schema on the search_path it fails with a missing relation that
        names neither the collection nor the statement that was sent.
        """
        load_collection(conn, SENTINEL_2_L2A)
        conn.execute('SET search_path TO "$user", public')
        with pytest.raises(psycopg.errors.UndefinedTable, match="partition_stats"):
            conn.execute("DELETE FROM pgstac.collections WHERE id = %s", (SENTINEL_2_L2A.dataset_id,))

    def test_with_the_search_path_set_deleting_works(self, conn) -> None:
        load_collection(conn, SENTINEL_2_L2A)
        use_pgstac_search_path(conn)
        conn.execute("DELETE FROM pgstac.collections WHERE id = %s", (SENTINEL_2_L2A.dataset_id,))
        assert read_collection(conn, SENTINEL_2_L2A.dataset_id) is None

    def test_pgstac_reads_it_back_as_a_collection(self, conn) -> None:
        """Not our own SELECT: pgstac's own accessor has to accept what we wrote."""
        load_collection(conn, SENTINEL_2_L2A)
        with conn.cursor() as cur:
            cur.execute("SELECT pgstac.get_collection(%s)", (SENTINEL_2_L2A.dataset_id,))
            content = cur.fetchone()[0]
        assert content["id"] == SENTINEL_2_L2A.dataset_id


def _item(collection: str) -> dict[str, object]:
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": "GONE_ITEM",
        "collection": collection,
        "geometry": {"type": "Point", "coordinates": [0, 0]},
        "bbox": [0, 0, 0, 0],
        "properties": {"datetime": "2026-01-01T00:00:00Z"},
        "assets": {},
        "links": [],
    }


def _count(conn, table: str, collection: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM pgstac.{table} WHERE collection = %s", (collection,))
        return cur.fetchone()[0]


class TestRemovingWhatLeftTheRegistry:
    """adr/0017 rule IV, F5: the registry is the single source, so a federated collection that
    left it leaves pgstac in the same run, and nothing else does."""

    GONE = replace(SENTINEL_2_L2A, dataset_id="gone-dataset", source=replace(SENTINEL_2_L2A.source, source_collection_id="gone-dataset"))

    def test_a_federated_collection_that_left_is_removed_with_its_items(self, conn) -> None:
        load_collection(conn, self.GONE)
        conn.execute("SELECT pgstac.create_item(%s::jsonb)", (json.dumps(_item(self.GONE.dataset_id)),))
        assert _count(conn, "items", self.GONE.dataset_id) == 1

        outcome = load_registry(conn, REGISTRY)

        assert outcome.removed == (self.GONE.dataset_id,)
        assert read_collection(conn, self.GONE.dataset_id) is None
        assert _count(conn, "items", self.GONE.dataset_id) == 0

    def test_the_collections_of_the_registry_stay_untouched(self, conn) -> None:
        load_registry(conn, REGISTRY)
        before = {entry.dataset_id: read_collection(conn, entry.dataset_id) for entry in REGISTRY}
        load_collection(conn, self.GONE)

        load_registry(conn, REGISTRY)

        assert {entry.dataset_id: read_collection(conn, entry.dataset_id) for entry in REGISTRY} == before

    def test_a_materialized_collection_is_never_removed(self, conn) -> None:
        """The DEM's tiles exist nowhere else; only a decision of its own would delete them."""
        load_collection(conn, COP_DEM_GLO_30)

        outcome = load_registry(conn, DatasetRegistry((SENTINEL_2_L2A,)))

        assert outcome.removed == ()
        assert read_collection(conn, COP_DEM_GLO_30.dataset_id) is not None

    def test_a_collection_that_is_not_ours_is_left_alone(self, conn) -> None:
        foreign = {"id": "foreign", "type": "Collection", "stac_version": "1.0.0", "description": "x", "license": "MIT",
                   "extent": {"spatial": {"bbox": [[-180, -90, 180, 90]]}, "temporal": {"interval": [[None, None]]}}, "links": []}
        conn.execute("SELECT pgstac.create_collection(%s::jsonb)", (json.dumps(foreign),))

        outcome = load_registry(conn, REGISTRY)

        assert outcome.removed == ()
        assert read_collection(conn, "foreign") is not None

    def test_a_second_run_removes_nothing(self, conn) -> None:
        load_collection(conn, self.GONE)
        assert load_registry(conn, REGISTRY).removed == (self.GONE.dataset_id,)
        assert load_registry(conn, REGISTRY).removed == ()

    def test_an_empty_registry_still_removes_by_the_rule(self, conn) -> None:
        load_collection(conn, self.GONE)
        assert remove_gone_collections(conn, DatasetRegistry(())) == (self.GONE.dataset_id,)


class TestTheEntryPoint:
    """`python -m earthx.catalog.load` is what makes the acceptance criterion true
    outside a test: it commits, so the collection is still there afterwards."""

    @pytest.fixture
    def cleanup(self) -> Iterator[None]:
        """This one really writes, so it really has to tidy up after itself."""
        yield
        with psycopg.connect(autocommit=True) as conn:
            use_pgstac_search_path(conn)
            conn.execute("DELETE FROM pgstac.collections WHERE id = %s", (SENTINEL_2_L2A.dataset_id,))

    def test_it_commits_the_collection(self, require_postgres_env, cleanup) -> None:
        assert main() == 0
        with psycopg.connect(autocommit=True) as conn:
            stored = read_collection(conn, SENTINEL_2_L2A.dataset_id)
        assert stored is not None
        assert stored["earthx:source"]["source_collection_id"] == "sentinel-2-c1-l2a"

    def test_running_it_twice_changes_nothing(self, require_postgres_env, cleanup) -> None:
        assert main() == 0
        with psycopg.connect(autocommit=True) as conn:
            first = read_collection(conn, SENTINEL_2_L2A.dataset_id)

        assert main() == 0
        with psycopg.connect(autocommit=True) as conn:
            second = read_collection(conn, SENTINEL_2_L2A.dataset_id)
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM pgstac.collections WHERE id = %s", (SENTINEL_2_L2A.dataset_id,))
                assert cur.fetchone()[0] == 1
        assert first == second
