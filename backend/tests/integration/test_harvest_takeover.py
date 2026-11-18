"""T-C: migration 027 takes over a full pass that stopped before it kept its place (Otto, 18.11.2026).

Otto's first full run of opendata.swiss read 102 pages and failed on 429s, before a run kept where it stood. The
statement of migration 027 that takes such a pass over runs here on a source of its own, in a transaction that is
rolled back: the next run goes on at the offset of the package with the largest key, as the listing is sorted by id.
"""

from __future__ import annotations

import psycopg
import pytest

from earthx.catalog.harvest_store import harvest_state
from earthx.catalog.schema import MIGRATIONS_DIR

SOURCE = "t-takeover"
OTHER = "t-takeover-done"


def _takeover_statement() -> str:
    text = (MIGRATIONS_DIR / "027_harvest_pass.sql").read_text(encoding="utf-8")
    start = text.index("INSERT INTO public.earthx_harvest_source AS h")
    return text[start : text.index(";", start) + 1]


def _run(conn: psycopg.Connection, source_id: str, status: str, stop_reason: str | None) -> int:
    return conn.execute(
        "INSERT INTO public.earthx_harvest_run (source_id, kind, status, lease_until, finished_at, stop_reason)"
        " VALUES (%s, 'full', %s, clock_timestamp(), clock_timestamp(), %s) RETURNING run_id",
        (source_id, status, stop_reason),
    ).fetchone()[0]


def _finds(conn: psycopg.Connection, source_id: str, run_id: int, keys: list[str]) -> None:
    for key in keys:
        conn.execute(
            "INSERT INTO public.earthx_record_state (source_id, source_key, state, reason, last_seen_run)"
            " VALUES (%s, %s, 'invalid', 'no_link', %s)",
            (source_id, key, run_id),
        )


def test_a_stopped_full_pass_goes_on_after_its_largest_key(conn: psycopg.Connection) -> None:
    robots = _run(conn, SOURCE, "interrupted", "robots")
    failed = _run(conn, SOURCE, "failed", "upstream")
    # Byte order, as the search index sorts: upper case before lower case, '-' before digits.
    keys = ["0a-1", "0a-2", "9f", "B", "a-z"]
    _finds(conn, SOURCE, failed, keys)
    done = _run(conn, OTHER, "done", None)
    _finds(conn, OTHER, done, ["x"])
    conn.execute(_takeover_statement())
    opened = harvest_state(conn, SOURCE).open_pass
    assert opened is not None and robots < failed
    assert (opened.run_id, opened.start, opened.last_key, opened.total, opened.read, opened.moved) == (
        failed,
        4,
        "a-z",
        None,
        5,
        False,
    )
    # A source with a done full run has nothing to take over.
    assert harvest_state(conn, OTHER).open_pass is None


def test_the_takeover_leaves_an_open_pass_as_it_is(conn: psycopg.Connection) -> None:
    failed = _run(conn, SOURCE, "failed", "upstream")
    _finds(conn, SOURCE, failed, ["a", "b"])
    conn.execute(
        "INSERT INTO public.earthx_harvest_source (source_id, pass_run_id, pass_started_at, pass_start, pass_read,"
        " pass_moved) VALUES (%s, %s, clock_timestamp(), 7, 8, true)",
        (SOURCE, failed),
    )
    conn.execute(_takeover_statement())
    opened = harvest_state(conn, SOURCE).open_pass
    assert opened is not None and (opened.start, opened.read, opened.moved) == (7, 8, True)


@pytest.mark.parametrize("statement", [_takeover_statement()])
def test_the_statement_is_found_in_the_migration(statement: str) -> None:
    assert statement.startswith("INSERT INTO") and statement.endswith("WHERE h.pass_run_id IS NULL;")
