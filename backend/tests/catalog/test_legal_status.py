"""``legal_status`` and ``legal_note`` of an entry (adr/0024 R3, M5-13 plan §3.4)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from earthx.catalog.collection import to_stac_collection
from earthx.catalog.registry import PROTOTYPE_PREFIX, ConfigError, DatasetConfig, LegalStatus
from tests.catalog.entries import REGISTRY

NOTE = "The terms of use name no licence for redistribution."


def _prototype(entry: DatasetConfig) -> DatasetConfig:
    return replace(
        entry, dataset_id=PROTOTYPE_PREFIX + entry.dataset_id, legal_status=LegalStatus.UNCLEAR, legal_note=NOTE
    )


@pytest.mark.parametrize("entry", list(REGISTRY), ids=lambda entry: entry.dataset_id)
def test_every_released_entry_is_cleared(entry: DatasetConfig) -> None:
    assert entry.legal_status is LegalStatus.CLEARED
    assert entry.legal_note is None
    assert not entry.dataset_id.startswith(PROTOTYPE_PREFIX)


def test_a_prototype_entry_has_the_prefix_the_status_and_a_note(valid_config: DatasetConfig) -> None:
    entry = _prototype(valid_config)
    assert entry.dataset_id == "proto-test-dataset"


def test_unclear_without_the_prefix_is_refused(valid_config: DatasetConfig) -> None:
    with pytest.raises(ConfigError, match="needs an id starting with 'proto-'"):
        replace(valid_config, legal_status=LegalStatus.UNCLEAR, legal_note=NOTE)


def test_the_prefix_with_cleared_is_refused(valid_config: DatasetConfig) -> None:
    with pytest.raises(ConfigError, match="needs legal_status unclear"):
        replace(valid_config, dataset_id="proto-test-dataset")


@pytest.mark.parametrize("note", [None, "", "   "], ids=["none", "empty", "blank"])
def test_unclear_needs_a_note(valid_config: DatasetConfig, note: str | None) -> None:
    with pytest.raises(ConfigError, match="needs a legal_note"):
        replace(_prototype(valid_config), legal_note=note)


def test_cleared_carries_no_note(valid_config: DatasetConfig) -> None:
    with pytest.raises(ConfigError, match="legal_note belongs to legal_status unclear only"):
        replace(valid_config, legal_note=NOTE)


def test_a_status_that_is_no_legal_status_is_refused(valid_config: DatasetConfig) -> None:
    with pytest.raises(ConfigError, match="legal_status must be one of"):
        replace(valid_config, legal_status="cleared")


def test_the_prefix_is_matched_at_the_start_only(valid_config: DatasetConfig) -> None:
    entry = replace(valid_config, dataset_id="not-proto-dataset")
    assert entry.legal_status is LegalStatus.CLEARED


def test_the_collection_carries_both_fields(valid_config: DatasetConfig) -> None:
    cleared = to_stac_collection(valid_config)
    assert (cleared["earthx:legal_status"], cleared["earthx:legal_note"]) == ("cleared", None)
    unclear = to_stac_collection(_prototype(valid_config))
    assert (unclear["earthx:legal_status"], unclear["earthx:legal_note"]) == ("unclear", NOTE)
