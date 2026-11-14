"""The index of the dataset search: written by catalog-load, checked when api starts (M5-22 plan §3.4, A3)."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest

import earthx.api.main
from earthx.api.main import build_app
from earthx.catalog.load import main as load_catalog
from earthx.catalog.registry import DatasetRegistry, OverviewMode, OverviewResampling
from earthx.catalog.search_index import (
    SearchIndexMismatch,
    check_search_index,
    compare_index,
    write_search_index,
)
from earthx.catalog.search_text import search_text
from tests.catalog.entries import REGISTRY, SENTINEL_2_L2A, SWISSALTI3D

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
