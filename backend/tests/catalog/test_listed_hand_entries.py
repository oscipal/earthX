"""The hand entries of the repo under ``backend/catalog/listed/`` (M5-17 plan §3, §7).

The loader itself is tested with synthetic entries in ``test_listed_files.py``; these tests hold the real files to what
M5-17 asked for: each reads and round-trips, its category and keywords fit the catalogue, it never reaches the
registry, and the access of each source is the one the plan names. Nothing here goes out.
"""

from __future__ import annotations

import pytest

from earthx.catalog.categories import load_categories
from earthx.catalog.datasets import CATALOG_DIR, registry
from earthx.catalog.entry_files import read_yaml, to_plain
from earthx.catalog.listed import (
    LISTED_DIR,
    DataKind,
    DeliveryKind,
    link_host,
    listed_keywords,
    load_listed,
    to_listed_collection,
)
from earthx.catalog.registry import AccountKind, LicenseTier

HAND_ENTRIES = {entry.dataset_id: entry for entry, _ in load_listed()}
#: Words that show a keyword list is German too (adr/0026 F7); one per entry is enough.
GERMAN = {"corine-land-cover": "landbedeckung", "landsat-c2-l2": "oberflächenreflexion"}


def test_the_listed_path_holds_exactly_the_two_entries_of_m5_17() -> None:
    assert sorted(HAND_ENTRIES) == ["corine-land-cover", "landsat-c2-l2"]


@pytest.mark.parametrize("dataset_id", sorted(HAND_ENTRIES))
def test_each_file_round_trips(dataset_id: str) -> None:
    path = LISTED_DIR / f"{dataset_id}.yaml"
    assert to_plain(HAND_ENTRIES[dataset_id]) == read_yaml(path)


def test_no_hand_entry_shares_an_id_with_a_full_or_retired_entry() -> None:
    datasets = registry()
    full = {config.dataset_id for config in datasets} | {gone.dataset_id for gone in datasets.retired}
    assert not full & set(HAND_ENTRIES)


def test_the_registry_never_holds_a_hand_entry() -> None:
    """Misuse: a listed entry read into a process would make it a dataset with a viewer (M5-35 B5)."""
    ids = {config.dataset_id for config in registry()}
    assert "corine-land-cover" not in ids and "landsat-c2-l2" not in ids
    assert not (CATALOG_DIR / "datasets" / "corine-land-cover.yaml").exists()


@pytest.mark.parametrize("dataset_id", sorted(HAND_ENTRIES))
def test_the_category_is_one_of_the_catalogue(dataset_id: str) -> None:
    assert HAND_ENTRIES[dataset_id].category in load_categories().ids


@pytest.mark.parametrize("dataset_id", sorted(HAND_ENTRIES))
def test_the_keywords_survive_normalization_in_english_and_german(dataset_id: str) -> None:
    entry = HAND_ENTRIES[dataset_id]
    kept = listed_keywords(entry.keywords, entry.category)
    assert len(kept) == len(entry.keywords), "a keyword was dropped or stands twice"
    assert GERMAN[dataset_id] in kept


@pytest.mark.parametrize("dataset_id", sorted(HAND_ENTRIES))
def test_a_hand_entry_stays_in_the_catalogue_tier_with_a_link_to_the_source(dataset_id: str) -> None:
    entry = HAND_ENTRIES[dataset_id]
    assert entry.license.tier is LicenseTier.CATALOG
    assert entry.source_url.startswith("https://")
    document = to_listed_collection(entry)
    via = [link for link in document["links"] if link["rel"] == "via"]
    assert via == [{"rel": "via", "href": entry.source_url, "title": "Source"}]
    assert not {"earthx:viewer", "earthx:capabilities", "earthx:source"} & set(document)


def test_corine_needs_a_free_account_and_is_downloaded_at_the_source() -> None:
    entry = HAND_ENTRIES["corine-land-cover"]
    assert (entry.access.account, entry.access.delivery) == (AccountKind.FREE_ACCOUNT, DeliveryKind.DOWNLOAD)
    assert entry.access.account_provider
    assert (entry.category, entry.data_kind) == ("land_cover", DataKind.VECTOR)
    assert link_host(entry.source_url) == "land.copernicus.eu"


def test_landsat_is_requester_pays_and_has_an_open_end() -> None:
    entry = HAND_ENTRIES["landsat-c2-l2"]
    assert (entry.access.account, entry.access.delivery) == (AccountKind.REQUESTER_PAYS, DeliveryKind.DOWNLOAD)
    assert (entry.category, entry.data_kind) == ("optical", DataKind.RASTER)
    assert entry.temporal_extent.end is None
    assert link_host(entry.source_url) == "www.usgs.gov"


@pytest.mark.parametrize("dataset_id", sorted(HAND_ENTRIES))
def test_the_period_is_in_order(dataset_id: str) -> None:
    period = HAND_ENTRIES[dataset_id].temporal_extent
    assert period.start is not None
    assert period.end is None or period.start < period.end
