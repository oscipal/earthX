"""The index of the dataset search: written by catalog-load, checked when api starts (M5-22 plan §3.4, A3)."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest

import earthx.api.main
import earthx.catalog.search_index
from earthx.api.main import build_app
from earthx.catalog.load import main as load_catalog
from earthx.catalog.registry import DatasetRegistry, OverviewMode, OverviewResampling
from earthx.catalog.search_index import (
    IndexOutcome,
    ListedIndexOutcome,
    SearchIndexMismatch,
    check_search_index,
    compare_index,
    write_listed_search_index,
    write_search_index,
)
from earthx.catalog.search_text import search_text
from tests.catalog.entries import REGISTRY, SENTINEL_2_L2A, SWISSALTI3D
from tests.integration.listed_rows import insert_row

pytestmark = pytest.mark.anyio

# swissALTI3D without its substitute, for a registry of this one entry (`overview_substitute` has to name an entry).
ALONE = dataclasses.replace(
    SWISSALTI3D,
    viewer=dataclasses.replace(
        SWISSALTI3D.viewer,
        overview=OverviewMode.PYRAMID,
        overview_resampling=OverviewResampling.AVERAGE,
        overview_substitute=None,
    ),
)


@pytest.fixture
def conn(conn: psycopg.Connection) -> psycopg.Connection:
    """The rolled-back connection, with the index emptied inside its transaction: another run may have committed one."""
    conn.execute("DELETE FROM public.earthx_dataset_search")
    return conn


def _rows(conn: psycopg.Connection) -> dict[str, tuple]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT dataset_id, text_hash, west, south, east, north, time_start, time_end, has_time_axis, item_holding"
            " FROM public.earthx_dataset_search"
        )
        return {row[0]: row[1:] for row in cur.fetchall()}


def test_every_entry_gets_a_row_with_its_hash_and_extent(conn):
    outcome = write_search_index(conn, REGISTRY)
    assert set(outcome.written) == {config.dataset_id for config in REGISTRY}
    rows = _rows(conn)
    assert rows["swissalti3d"][0] == search_text(SWISSALTI3D).text_hash
    assert rows["swissalti3d"][1:5] == SWISSALTI3D.spatial_extent.bbox
    # An open end stays open (NULL); the time axis and the holding come from the entry.
    assert rows["sentinel-2-c1-l2a"][5:] == (SENTINEL_2_L2A.temporal_extent.start, None, True, "federated")
    assert rows["cop-dem-glo-30"][7:] == (False, "materialized")


def test_a_second_run_writes_nothing(conn):
    write_search_index(conn, REGISTRY)
    assert write_search_index(conn, REGISTRY).written == ()


def test_only_a_changed_entry_is_written_again(conn):
    write_search_index(conn, REGISTRY)
    retitled = dataclasses.replace(SWISSALTI3D, description=SWISSALTI3D.description + " Changed.")
    entries = tuple(retitled if config.dataset_id == "swissalti3d" else config for config in REGISTRY)
    assert write_search_index(conn, DatasetRegistry(entries)).written == ("swissalti3d",)


def test_a_new_extent_alone_is_written_again(conn):
    write_search_index(conn, REGISTRY)
    later = dataclasses.replace(
        SENTINEL_2_L2A,
        temporal_extent=dataclasses.replace(SENTINEL_2_L2A.temporal_extent, end=datetime(2030, 1, 1, tzinfo=UTC)),
    )
    entries = tuple(later if config.dataset_id == SENTINEL_2_L2A.dataset_id else config for config in REGISTRY)
    assert write_search_index(conn, DatasetRegistry(entries)).written == (SENTINEL_2_L2A.dataset_id,)


def test_a_row_without_an_entry_is_removed(conn):
    write_search_index(conn, REGISTRY)
    outcome = write_search_index(conn, DatasetRegistry((ALONE,)))
    assert outcome.removed == tuple(sorted(c.dataset_id for c in REGISTRY if c.dataset_id != "swissalti3d"))
    assert set(_rows(conn)) == {"swissalti3d"}


def test_the_document_holds_all_three_configurations(conn):
    write_search_index(conn, DatasetRegistry((ALONE,)))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT document @@ phraseto_tsquery('german', 'Höhenmodelle'), document @@ to_tsquery('simple', 'dtm'),"
            " document @@ phraseto_tsquery('english', 'terrain models') FROM public.earthx_dataset_search"
        )
        assert cur.fetchone() == (True, True, True)


def test_catalog_load_writes_the_index_and_says_so(capsys):
    assert load_catalog() == 0
    assert load_catalog() == 0
    out = capsys.readouterr().out
    assert "search index written: none" in out and "search index removed: none" in out


# --- the start check ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "problem"),
    [
        ({}, "no row for a, b"),
        ({"a": "1", "b": "0"}, "an old search text or extent for b"),
        ({"a": "1", "b": "2", "c": "3"}, "rows without an entry for c"),
    ],
)
def test_compare_names_each_difference(stored, problem):
    assert compare_index({"a": "1", "b": "2"}, stored) == [problem]


def test_compare_finds_nothing_in_a_matching_index():
    assert compare_index({"a": "1"}, {"a": "1"}) == []


@pytest.fixture
def committed_index(require_postgres_env: None) -> Iterator[psycopg.Connection]:
    """A connection whose writes to the index are committed, so that the async check sees them; emptied afterwards."""
    with psycopg.connect(autocommit=True) as connection:
        yield connection
        connection.execute("DELETE FROM public.earthx_dataset_search")


async def test_the_check_passes_on_the_index_of_the_registry(committed_index, aconn):
    write_search_index(committed_index, REGISTRY)
    await check_search_index(REGISTRY, aconn)


async def test_the_check_refuses_an_old_text_and_names_the_dataset(committed_index, aconn):
    write_search_index(committed_index, REGISTRY)
    committed_index.execute(
        "UPDATE public.earthx_dataset_search SET text_hash = 'old' WHERE dataset_id = 'swissalti3d'"
    )
    with pytest.raises(SearchIndexMismatch, match="an old search text or extent for swissalti3d"):
        await check_search_index(REGISTRY, aconn)


async def test_the_check_refuses_an_old_extent_with_the_text_unchanged(committed_index, aconn):
    # A mission end added to an entry changes no word, but the time filter reads it.
    write_search_index(committed_index, REGISTRY)
    committed_index.execute(
        "UPDATE public.earthx_dataset_search SET time_end = '2030-01-01T00:00:00Z' WHERE dataset_id = 'sentinel-2-c1-l2a'"
    )
    with pytest.raises(SearchIndexMismatch, match="an old search text or extent for sentinel-2-c1-l2a"):
        await check_search_index(REGISTRY, aconn)


async def test_the_check_refuses_a_row_without_an_entry(committed_index, aconn):
    # A prototype row in an instance that does not load prototypes would be one (adr/0024 R5).
    write_search_index(committed_index, REGISTRY)
    with pytest.raises(SearchIndexMismatch, match="rows without an entry for swissalti3d"):
        await check_search_index(DatasetRegistry(tuple(c for c in REGISTRY if c.dataset_id != "swissalti3d")), aconn)


async def test_the_check_refuses_an_empty_index(committed_index, aconn):
    with pytest.raises(SearchIndexMismatch, match="no row for"):
        await check_search_index(REGISTRY, aconn)


async def test_api_does_not_start_on_an_old_index(committed_index, monkeypatch):
    # The bare check, without the fixture that writes the index for each test's app first.
    monkeypatch.setattr(earthx.api.main, "check_search_index", check_search_index)
    write_search_index(committed_index, REGISTRY)
    committed_index.execute(
        "UPDATE public.earthx_dataset_search SET text_hash = 'old' WHERE dataset_id = 'swissalti3d'"
    )
    app = build_app(REGISTRY)
    with pytest.raises(SearchIndexMismatch, match="swissalti3d"):
        async with app.router.lifespan_context(app):
            pass


# --- listed entries ----------------------------------------------------------------------------------------------------


def _listed_rows(conn: psycopg.Connection) -> dict[str, tuple]:
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_id, title, text_a, item_holding FROM public.earthx_dataset_search WHERE entry = 'listed'")
        return {row[0]: row[1:] for row in cur.fetchall()}


@pytest.fixture
def listed(conn: psycopg.Connection) -> psycopg.Connection:
    """Within the rolled-back transaction: no listed row but a published one, one in review, and a duplicate of it."""
    conn.execute("DELETE FROM public.earthx_listed_entry")
    insert_row(conn, "main-entry", title="Neophyten der Schweiz")
    insert_row(conn, "in-review", state="in_review", title="Baumkataster der Stadt")
    insert_row(conn, "duplicate", state="duplicate", source_id="src-2", title="Götterbaum (Ailanthus altissima)")
    return conn


def test_a_published_listed_entry_gets_a_row_with_the_titles_of_its_duplicates(listed):
    outcome = write_listed_search_index(listed, [])
    assert (outcome.written, outcome.removed) == (1, 0)
    title, text_a, item_holding = _listed_rows(listed)["main-entry"]
    assert title == "Neophyten der Schweiz" and item_holding is None
    assert "Götterbaum (Ailanthus altissima)" in text_a.splitlines()


def test_the_names_of_its_regions_come_from_the_place_names(listed):
    listed.execute("UPDATE public.earthx_listed_entry SET regions = '{CH,CH-ZH}' WHERE dataset_id = 'main-entry'")
    write_listed_search_index(listed, [])
    text_b = listed.execute("SELECT text_b FROM public.earthx_dataset_search WHERE dataset_id = 'main-entry'").fetchone()
    assert {"Schweiz", "Switzerland", "Zürich"} <= set(text_b[0].splitlines())


def test_a_changed_duplicate_or_salt_rewrites_the_row_of_the_main_entry(listed, monkeypatch):
    write_listed_search_index(listed, [])
    listed.execute(
        "UPDATE public.earthx_listed_entry SET content_sha256 = repeat('b', 64),"
        " content = jsonb_set(content, '{title}', '\"Götterbaum\"') WHERE dataset_id = 'duplicate'"
    )
    assert write_listed_search_index(listed, []) == ListedIndexOutcome(1, 0)
    assert "Götterbaum" in _listed_rows(listed)["main-entry"][1]
    monkeypatch.setattr(earthx.catalog.search_index, "listed_text_salt", lambda: "another version")
    assert write_listed_search_index(listed, []) == ListedIndexOutcome(1, 0)


def test_a_second_run_writes_nothing_and_a_changed_title_rewrites_one_row(listed):
    write_listed_search_index(listed, [])
    assert write_listed_search_index(listed, []) == ListedIndexOutcome(0, 0)
    listed.execute(
        "UPDATE public.earthx_listed_entry SET content = jsonb_set(content, '{title}', '\"Neophyten\"'),"
        " content_sha256 = repeat('c', 64) WHERE dataset_id = 'main-entry'"
    )
    assert write_listed_search_index(listed, []) == ListedIndexOutcome(1, 0)


def test_a_row_goes_when_its_entry_is_no_longer_published_or_a_full_entry_took_its_id(listed):
    write_listed_search_index(listed, [])
    assert write_listed_search_index(listed, ["main-entry"]) == ListedIndexOutcome(0, 1)
    write_listed_search_index(listed, [])
    listed.execute("UPDATE public.earthx_listed_entry SET state = 'blocked' WHERE dataset_id = 'main-entry'")
    assert write_listed_search_index(listed, []) == ListedIndexOutcome(0, 1)
    assert _listed_rows(listed) == {}


async def test_the_start_check_and_the_full_rows_leave_a_listed_row_alone(committed_index, aconn):
    write_search_index(committed_index, REGISTRY)
    try:
        with committed_index.transaction():
            insert_row(committed_index, "main-entry")
            write_listed_search_index(committed_index, [config.dataset_id for config in REGISTRY])
        assert "main-entry" in _listed_rows(committed_index)
        assert write_search_index(committed_index, REGISTRY) == IndexOutcome((), ())
        await check_search_index(REGISTRY, aconn)
    finally:
        committed_index.execute("DELETE FROM public.earthx_listed_entry WHERE dataset_id = 'main-entry'")


def test_a_full_entry_takes_over_the_row_of_a_listed_one_with_its_id(listed):
    listed.execute("UPDATE public.earthx_listed_entry SET dataset_id = 'swissalti3d' WHERE dataset_id = 'main-entry'")
    write_listed_search_index(listed, [])
    assert set(write_search_index(listed, DatasetRegistry((ALONE,))).written) == {"swissalti3d"}
    assert _listed_rows(listed) == {}
