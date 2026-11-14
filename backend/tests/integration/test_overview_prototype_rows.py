"""T-C: `catalog-load` without the prototype switch removes the pyramid rows of `proto-*` (M5-30b part 8b-3, adr/0024 R6)."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from earthx.catalog.load import main
from earthx.catalog.pgstac import confirm_overview, rearm_overview, remove_prototype_overviews
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


class TestConfirmationAndRearming:
    """`confirm_overview` and `rearm_overview` against the tables of the migrations (M5-30b part 8b-3, review of #349)."""

    @staticmethod
    def _row(conn: psycopg.Connection, dataset_id: str, status: str, kind: str | None = None, attempts: int = 1) -> str:
        row = conn.execute(
            """
            INSERT INTO public.earthx_overview (dataset_id, version, status, failure_kind, attempts, checked_at, lease_until)
            VALUES (%(d)s, public.earthx_overview_version('v1'), %(s)s, %(k)s, %(a)s,
                    CASE WHEN %(s)s = 'ready' THEN now() END,
                    CASE WHEN %(s)s = 'building' THEN now() + interval '1 minute' END)
            RETURNING version
            """,
            {"d": dataset_id, "s": status, "k": kind, "a": attempts},
        ).fetchone()
        return row[0]

    @staticmethod
    def _left(conn: psycopg.Connection, dataset_id: str) -> list[tuple[str, str | None]]:
        return conn.execute(
            "SELECT status, failure_kind FROM public.earthx_overview WHERE dataset_id = %s", (dataset_id,)
        ).fetchall()

    def test_a_prototype_pyramid_is_never_confirmed(self, schema: psycopg.Connection) -> None:
        """Review finding 1: a confirmation would keep a pyramid alive that is never extended."""
        self._row(schema, "proto-a", "ready")
        self._row(schema, "dem", "ready")
        assert not confirm_overview(schema, "proto-a", "v1")
        assert confirm_overview(schema, "dem", "v1")
        confirmed = schema.execute("SELECT dataset_id, confirmed_at IS NOT NULL FROM public.earthx_overview ORDER BY 1")
        assert confirmed.fetchall() == [("dem", True), ("proto-a", False)]

    @pytest.mark.parametrize(
        ("kind", "attempts"),
        [("source_4xx", 1), ("expired", 1), ("child_crashed", 2), ("source_timeout", 3), ("lease_lost", 3), ("unknown", 1)],
    )
    def test_a_failure_that_will_not_be_tried_again_is_deleted_and_the_request_stands(
        self, schema: psycopg.Connection, kind: str, attempts: int
    ) -> None:
        self._row(schema, "dem", "failed", kind, attempts)
        assert rearm_overview(schema, "dem", "v1")
        assert self._left(schema, "dem") == []
        assert schema.execute("SELECT source_version FROM public.earthx_overview_request").fetchall() == [("v1",)]

    @pytest.mark.parametrize("kind", ["source_timeout", "source_5xx", "lease_lost"])
    def test_a_failure_that_waits_for_its_retry_is_left_alone(self, schema: psycopg.Connection, kind: str) -> None:
        """The retry rules (3 attempts, an hour) stay as they are."""
        self._row(schema, "dem", "failed", kind, 2)
        assert not rearm_overview(schema, "dem", "v1")
        assert self._left(schema, "dem") == [("failed", kind)]
        assert schema.execute("SELECT count(*) FROM public.earthx_overview_request").fetchone() == (0,)

    @pytest.mark.parametrize("status", ["ready", "building"])
    def test_a_pyramid_that_is_ready_or_building_is_left_alone(self, schema: psycopg.Connection, status: str) -> None:
        self._row(schema, "dem", status)
        assert not rearm_overview(schema, "dem", "v1")
        assert [row[0] for row in self._left(schema, "dem")] == [status]

    def test_another_version_and_another_dataset_are_left_alone(self, schema: psycopg.Connection) -> None:
        self._row(schema, "dem", "failed", "expired")
        self._row(schema, "land", "failed", "expired")
        assert not rearm_overview(schema, "dem", "v2")
        assert self._left(schema, "dem") == [("failed", "expired")] and self._left(schema, "land") == [("failed", "expired")]

    def test_nothing_to_rearm_is_no_error(self, schema: psycopg.Connection) -> None:
        assert not rearm_overview(schema, "dem", "v1")

    def test_the_copies_of_the_retry_rules_are_those_of_jobs(self) -> None:
        from earthx.catalog import pgstac
        from earthx.jobs import overviews, queue

        assert set(pgstac._RETRYABLE) == set(queue.RETRYABLE)
        assert pgstac._MAX_ATTEMPTS == overviews.MAX_ATTEMPTS
