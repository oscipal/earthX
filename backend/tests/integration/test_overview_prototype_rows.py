"""T-C: `catalog-load` without the prototype switch removes the pyramid rows of `proto-*` (M5-30b part 8b-3, adr/0024 R6)."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from earthx.catalog.load import main
from earthx.catalog.pgstac import remove_prototype_overviews
from earthx.catalog.registry import PROTOTYPE_PREFIX
from earthx.catalog.schema import discover_migrations

from .conftest import SHIPPED_TABLES

VERSION = "0123456789abcdef"


@pytest.fixture
def schema(conn: psycopg.Connection) -> psycopg.Connection:
    """The tables of the migrations, fresh, inside the test's transaction."""
    for table in SHIPPED_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    for migration in discover_migrations():
        conn.execute(migration.sql)
    return conn


def _rows(conn: psycopg.Connection) -> tuple[list[str], list[str]]:
    pyramids = [r[0] for r in conn.execute("SELECT dataset_id FROM public.earthx_overview ORDER BY 1")]
    requests = [r[0] for r in conn.execute("SELECT dataset_id FROM public.earthx_overview_request ORDER BY 1")]
    return pyramids, requests


def _both(conn: psycopg.Connection, *dataset_ids: str) -> None:
    for dataset_id in dataset_ids:
        conn.execute(
            "INSERT INTO public.earthx_overview (dataset_id, version, status, checked_at) VALUES (%s, %s, 'ready', now())",
            (dataset_id, VERSION),
        )
        conn.execute(
            "INSERT INTO public.earthx_overview_request (dataset_id, source_version) VALUES (%s, 'v1')", (dataset_id,)
        )


def test_the_prefix_is_the_one_of_the_registry() -> None:
    assert PROTOTYPE_PREFIX == "proto-"


def test_every_row_and_request_of_a_prototype_source_goes_and_no_other(schema: psycopg.Connection) -> None:
    _both(schema, "proto-a", "proto-b", "cop-dem-glo-30", "my-proto-c", "proto")
    assert remove_prototype_overviews(schema, ["cop-dem-glo-30"]) == 4
    assert _rows(schema) == (["cop-dem-glo-30", "my-proto-c", "proto"],) * 2


def test_a_prototype_entry_the_registry_carries_keeps_its_rows(schema: psycopg.Connection) -> None:
    """With the switch on, the entries that are loaded keep their pyramids; one that left the directory loses them."""
    _both(schema, "proto-a", "proto-b")
    assert remove_prototype_overviews(schema, ["proto-a"]) == 2
    assert _rows(schema) == (["proto-a"], ["proto-a"])


def test_it_is_idempotent_and_an_empty_database_is_fine(schema: psycopg.Connection) -> None:
    assert remove_prototype_overviews(schema, []) == 0
    _both(schema, "proto-a")
    assert remove_prototype_overviews(schema, []) == 2
    assert remove_prototype_overviews(schema, []) == 0


def test_a_name_that_only_looks_like_the_prefix_is_not_touched(schema: psycopg.Connection) -> None:
    """``%`` and ``_`` are not wildcards here: the prefix is compared, not matched."""
    _both(schema, "proto_a", "protoa", "PROTO-a")
    assert remove_prototype_overviews(schema, []) == 0


class TestTheEntryPoint:
    """`python -m earthx.catalog.load` commits, and the real registry carries no `proto-` entry in CI."""

    @pytest.fixture
    def rows(self, require_postgres_env: None) -> Iterator[None]:
        with psycopg.connect(autocommit=True) as conn:
            main()  # the tables of the migrations
            _both(conn, "proto-x")
            _both(conn, "kept-by-main")
        yield
        with psycopg.connect(autocommit=True) as conn:
            for table in ("earthx_overview", "earthx_overview_request"):
                conn.execute(f"DELETE FROM public.{table} WHERE dataset_id IN ('proto-x', 'kept-by-main')")

    def test_it_removes_the_rows_of_a_prototype_source_and_says_so(
        self, rows: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main() == 0
        assert "overview rows of prototype sources removed: 2" in capsys.readouterr().out
        with psycopg.connect(autocommit=True) as conn:
            pyramids, requests = _rows(conn)
        assert "proto-x" not in pyramids + requests
        assert "kept-by-main" in pyramids and "kept-by-main" in requests
