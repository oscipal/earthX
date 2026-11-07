"""The YAML entries are the Python entries they replace, value for value (M5-13 plan §3.3, F2).

Only for the commit that holds both; the next one removes the Python entries and this test with them.
"""

from __future__ import annotations

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.datasets import REGISTRY, load_registry

LOADED = load_registry()


def test_the_files_hold_exactly_the_python_entries() -> None:
    assert sorted(entry.dataset_id for entry in LOADED) == sorted(entry.dataset_id for entry in REGISTRY)


@pytest.mark.parametrize("dataset_id", [entry.dataset_id for entry in REGISTRY])
def test_each_entry_is_equal_field_for_field(dataset_id: str) -> None:
    assert LOADED.get(dataset_id) == REGISTRY.get(dataset_id)


@pytest.mark.parametrize("dataset_id", [entry.dataset_id for entry in REGISTRY])
def test_each_collection_is_equal(dataset_id: str) -> None:
    assert to_stac_collection(LOADED.get(dataset_id)) == to_stac_collection(REGISTRY.get(dataset_id))


def test_the_retired_datasets_are_equal() -> None:
    assert LOADED.retired == REGISTRY.retired
