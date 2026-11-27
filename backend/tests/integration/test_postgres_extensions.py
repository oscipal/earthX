"""T-C: the Postgres of every place offers what the catalogue builds on (M5-43, adr/0026 §14 points 4 and 5).

Compose and CI build compose/postgres/Dockerfile; the cloud session builds pgvector in the setup of its environment
(docs/cloud-umgebung.md §5). A place that falls behind would only show up once M5-23 creates the vector column, so this
asks the database itself: pgvector at the floor of 0.8.4, and a `halfvec` column with an HNSW index that works.
"""

from __future__ import annotations

import psycopg
import pytest

PGVECTOR_FLOOR = (0, 8, 4)


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def _default_version(conn: psycopg.Connection, name: str) -> str | None:
    row = conn.execute("SELECT default_version FROM pg_available_extensions WHERE name = %s", (name,)).fetchone()
    return None if row is None else row[0]


@pytest.mark.parametrize("name", ["postgis", "pg_trgm", "unaccent", "vector"])
def test_the_extensions_the_catalogue_needs_are_available(conn: psycopg.Connection, name: str) -> None:
    assert _default_version(conn, name) is not None, f"extension {name} is not installed in this Postgres"


def test_pgvector_is_at_least_the_floor(conn: psycopg.Connection) -> None:
    available = _default_version(conn, "vector")
    assert available is not None
    assert _version(available) >= PGVECTOR_FLOOR, f"pgvector {available} is older than 0.8.4"


def test_the_installed_pgvector_is_the_one_offered(conn: psycopg.Connection) -> None:
    """An extension created under an older image keeps its old SQL until `ALTER EXTENSION vector UPDATE`."""
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    installed = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()[0]
    assert installed == _default_version(conn, "vector")


def test_hnsw_on_halfvec_finds_the_nearest_row(conn: psycopg.Connection) -> None:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute("CREATE TEMP TABLE m5_43_vectors (id int PRIMARY KEY, emb halfvec(3))")
    conn.execute("INSERT INTO m5_43_vectors VALUES (1, '[1,0,0]'), (2, '[0,1,0]'), (3, '[0,0,1]')")
    conn.execute("CREATE INDEX ON m5_43_vectors USING hnsw (emb halfvec_cosine_ops)")
    conn.execute("SET LOCAL enable_seqscan = off")
    query = "SELECT id FROM m5_43_vectors ORDER BY emb <=> '[0.1,0.9,0]'::halfvec LIMIT 1"
    plan = "\n".join(row[0] for row in conn.execute(f"EXPLAIN {query}"))
    assert "m5_43_vectors_emb_idx" in plan
    assert conn.execute(query).fetchone()[0] == 2


def test_a_vector_of_the_wrong_dimension_is_refused(conn: psycopg.Connection) -> None:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute("CREATE TEMP TABLE m5_43_dims (emb halfvec(3))")
    with pytest.raises(psycopg.errors.DataException, match="expected 3 dimensions"):
        conn.execute("INSERT INTO m5_43_dims VALUES ('[1,0]')")


def test_a_version_below_the_floor_is_recognised() -> None:
    assert _version("0.8.3") < PGVECTOR_FLOOR <= _version("0.8.4") < _version("0.10.0")
