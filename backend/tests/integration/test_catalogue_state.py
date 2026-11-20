"""The catalogue of the worker's database, loaded once and again only when a test changed it (M5-61 F1).

`Catalogue` in `tests/integration/conftest.py`; against the real Postgres like every T-C test. Each test here makes a
`Catalogue` of its own; what it changes, the one of the run notices by the fingerprint and loads again.
"""

from __future__ import annotations

import psycopg
import pytest

from tests.integration.conftest import Catalogue, catalogue_fingerprint


def _commit(statement: str) -> None:
    with psycopg.connect(autocommit=True) as conn:
        conn.execute(statement)


def _rows() -> tuple[object, ...]:
    return tuple(None if seen is None else seen[0] for seen in catalogue_fingerprint())


def test_it_loads_once_and_not_again_while_nothing_changed(require_postgres_env: None) -> None:
    catalogue = Catalogue()
    catalogue.ensure()
    catalogue.ensure()
    catalogue.ensure()
    assert catalogue.loads == 1


@pytest.mark.parametrize(
    "change",
    [
        "DELETE FROM public.earthx_listed_entry WHERE ctid = (SELECT min(ctid) FROM public.earthx_listed_entry)",
        "UPDATE pgstac.collections SET content = content WHERE id = (SELECT min(id) FROM pgstac.collections)",
        "SELECT pgstac.delete_collection((SELECT min(id) FROM pgstac.collections))",
    ],
    ids=["a-listed-row-deleted", "a-collection-rewritten-unchanged", "a-collection-deleted"],
)
def test_a_committed_change_is_seen_and_loaded_away(require_postgres_env: None, change: str) -> None:
    """What `catalog-load` writes comes back. (It does not write a region part again that is gone without its outline
    file changing; that held before M5-61 just the same.)"""
    catalogue = Catalogue()
    catalogue.ensure()
    before, rows = catalogue_fingerprint(), _rows()
    _commit(change)
    assert catalogue_fingerprint() != before
    catalogue.ensure()
    assert catalogue.loads == 2
    assert _rows() == rows


def test_a_rolled_back_change_is_no_change(require_postgres_env: None) -> None:
    catalogue = Catalogue()
    catalogue.ensure()
    with psycopg.connect() as conn:
        conn.execute("DELETE FROM public.earthx_listed_entry")
        conn.rollback()
    catalogue.ensure()
    assert catalogue.loads == 1


def test_another_state_undoes_the_last_one_loads_and_sets_itself_up(require_postgres_env: None) -> None:
    catalogue = Catalogue()
    done: list[str] = []
    catalogue.ensure("one", setup=lambda: done.append("set up one"), undo=lambda: done.append("undo one"))
    catalogue.ensure("one", setup=lambda: done.append("set up one"))
    catalogue.ensure("two", setup=lambda: done.append("set up two"))
    assert done == ["set up one", "undo one", "set up two"]
    assert catalogue.loads == 2


@pytest.mark.parametrize(
    ("next_fixtures", "undone"),
    [(["catalogue", "tmp_path"], False), (["catalogue_loaded"], True), (None, True)],
    ids=["next-asks-for-it", "next-asks-for-another", "last-test"],
)
def test_a_state_with_an_undo_stays_only_for_a_next_test_of_its_owner(
    require_postgres_env: None, next_fixtures: list[str] | None, undone: bool
) -> None:
    catalogue = Catalogue()
    done: list[str] = []
    catalogue.ensure("listed", undo=lambda: done.append("undo"), owner="catalogue")
    catalogue.leave(next_fixtures)
    assert done == (["undo"] if undone else [])
    assert (catalogue.state is None) is undone


def test_a_state_without_an_undo_stays_for_any_next_test(require_postgres_env: None) -> None:
    catalogue = Catalogue()
    catalogue.ensure()
    catalogue.leave(None)
    assert catalogue.state == "registry"


def test_the_index_an_app_writes_for_its_own_registry_is_no_change(require_postgres_env: None) -> None:
    """Every `api` a test starts writes the index of its registry first (`_search_index_of_the_app`)."""
    catalogue = Catalogue()
    catalogue.ensure()
    _commit("DELETE FROM public.earthx_dataset_search WHERE ctid = (SELECT min(ctid) FROM public.earthx_dataset_search)")
    catalogue.ensure()
    assert catalogue.loads == 1
