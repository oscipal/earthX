"""The items a pyramid build reads, out of a real pgstac (M5-30b part 8b-2, `jobs.overview_builder.write_items`)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest

from earthx.catalog.pgstac import load_collection, upsert_items, use_pgstac_search_path
from earthx.jobs import overview_builder
from tests.integration.test_pgstac_search_bbox import MATERIALIZED, _item

OTHER = replace(
    MATERIALIZED,
    dataset_id="earthx-test-overview-items-other",
    source=replace(MATERIALIZED.source, source_collection_id="earthx-test-overview-items-other"),
)


@pytest.fixture
def loaded(require_postgres_env: None) -> Iterator[None]:
    with psycopg.connect(autocommit=True) as conn:
        load_collection(conn, MATERIALIZED)
        load_collection(conn, OTHER)
        upsert_items(conn, MATERIALIZED, [_item(f"t{n}", float(n)) for n in range(5)])
        upsert_items(conn, OTHER, [{**_item("x0", 20.0), "collection": OTHER.dataset_id}])
    yield
    with psycopg.connect(autocommit=True) as conn:
        use_pgstac_search_path(conn)
        for config in (MATERIALIZED, OTHER):
            conn.execute("SELECT pgstac.delete_collection(%s)", (config.dataset_id,))


def _written(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_the_items_of_the_collection_are_written_whole_in_the_order_of_their_ids(loaded: None, tmp_path: Path) -> None:
    with psycopg.connect(autocommit=True) as conn:
        count = overview_builder.write_items(conn, MATERIALIZED.dataset_id, tmp_path / "items.jsonl", lambda: None)
    items = _written(tmp_path / "items.jsonl")
    assert count == 5 and [item["id"] for item in items] == [f"t{n}" for n in range(5)]
    assert all(item["bbox"] and item["assets"]["visual"]["href"].endswith(f"{item['id']}.tif") for item in items)
    assert all(item["collection"] == MATERIALIZED.dataset_id for item in items), "the other collection is not read"


def test_the_pages_are_read_in_turn_and_the_lease_is_renewed_after_each(
    loaded: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(overview_builder, "_PAGE", 2)
    beats: list[int] = []
    with psycopg.connect(autocommit=True) as conn:
        count = overview_builder.write_items(
            conn, MATERIALIZED.dataset_id, tmp_path / "items.jsonl", lambda: beats.append(1)
        )
    assert count == 5 and len(beats) == 3, "2 + 2 + 1"
    assert [item["id"] for item in _written(tmp_path / "items.jsonl")] == [f"t{n}" for n in range(5)]


def test_a_collection_without_items_or_without_a_name_gives_nothing(loaded: None, tmp_path: Path) -> None:
    with psycopg.connect(autocommit=True) as conn:
        assert overview_builder.write_items(conn, "no-such-collection", tmp_path / "a.jsonl", lambda: None) == 0
        assert overview_builder.write_items(conn, "", tmp_path / "b.jsonl", lambda: None) == 0
    assert (tmp_path / "a.jsonl").read_text() == ""
