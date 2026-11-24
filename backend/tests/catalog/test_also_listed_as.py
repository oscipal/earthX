"""The listings of a full entry in harvested catalogues (``also_listed_as``, Otto, 24.11.2026): the field, its checks at
load time and the key a find gets from it."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from earthx.catalog.datasets import CATALOG_DIR, read_registry, registry
from earthx.catalog.registry import ConfigError, DatasetRegistry
from earthx.discovery.dedupe import Member, main_entries, with_listings
from tests.catalog.entries import REGISTRY

SWISSALTI3D_LISTING = (
    "opendata-swiss:691cb471-c3b5-48ec-a107-d0ad612fa70b@bundesamt-fur-landestopografie-swisstopo"
)
SOURCES = frozenset({"opendata-swiss", "govdata", "fsdi-stac"})


def _entry(dataset_id: str, *listings: str):  # type: ignore[no-untyped-def]
    return replace(REGISTRY.get("swissalti3d"), dataset_id=dataset_id, also_listed_as=tuple(listings))


def _registry(*entries):  # type: ignore[no-untyped-def]
    """The entries and the dataset they draw below their ``min_zoom`` (their ``overview_substitute``)."""
    return DatasetRegistry((*entries, REGISTRY.get("cop-dem-glo-30")), source_ids=SOURCES)


class TestTheField:
    def test_swissalti3d_names_its_listing_at_opendata_swiss(self) -> None:
        assert REGISTRY.get("swissalti3d").also_listed_as == (SWISSALTI3D_LISTING,)
        assert dict(registry().listings) == {SWISSALTI3D_LISTING: "swissalti3d"}

    def test_it_may_be_left_out(self) -> None:
        assert REGISTRY.get("sentinel-2-c1-l2a").also_listed_as == ()

    @pytest.mark.parametrize(
        "value",
        ["no-colon", "Opendata:x", "opendata-swiss:", "opendata-swiss: x", "x:y", "opendata-swiss:a b", "opendata-swiss:" + "a" * 301],
    )
    def test_a_wrong_listing_is_refused(self, value: str) -> None:
        with pytest.raises(ConfigError, match="also_listed_as holds '<source id>:<identifier>'"):
            _entry("x-entry", value)

    def test_a_listing_twice_in_one_entry_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="names a listing twice"):
            _entry("x-entry", SWISSALTI3D_LISTING, SWISSALTI3D_LISTING)


class TestTheLoadCheck:
    def test_a_source_that_does_not_exist_is_refused(self) -> None:
        entry = _entry("x-entry", "no-such-source:abc")
        with pytest.raises(ConfigError, match="'no-such-source', which is no source"):
            _registry(entry)

    def test_one_listing_at_two_entries_is_refused(self) -> None:
        first, second = _entry("first-entry", SWISSALTI3D_LISTING), _entry("second-entry", SWISSALTI3D_LISTING)
        with pytest.raises(ConfigError, match="at first-entry and at second-entry: it belongs to one"):
            _registry(first, second)

    def test_two_listings_at_two_entries_are_fine(self) -> None:
        first, second = _entry("first-entry", "opendata-swiss:a"), _entry("second-entry", "govdata:a")
        assert dict(_registry(first, second).listings) == {
            "opendata-swiss:a": "first-entry",
            "govdata:a": "second-entry",
        }


@pytest.fixture
def catalog(tmp_path: Path) -> Path:
    copy = tmp_path / "catalog"
    shutil.copytree(CATALOG_DIR / "datasets", copy / "datasets")
    for name in ("retired.yaml", "hosts.yaml", "categories.yaml"):
        shutil.copy(CATALOG_DIR / name, copy / name)
    shutil.copytree(CATALOG_DIR / "sources", copy / "sources")
    return copy


class TestTheFilesAreLoaded:
    def test_a_listing_named_by_two_files_stops_the_load(self, catalog: Path) -> None:
        # The load error of Otto's task 3: the key of swissalti3d named again by another full entry.
        path = catalog / "datasets" / "bev-als-dgm.yaml"
        path.write_text(path.read_text(encoding="utf-8") + f"also_listed_as:\n- {SWISSALTI3D_LISTING}\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="belongs to one"):
            read_registry(catalog)

    def test_a_source_that_is_not_in_sources_stops_the_load(self, catalog: Path) -> None:
        path = catalog / "datasets" / "bev-als-dgm.yaml"
        path.write_text(path.read_text(encoding="utf-8") + "also_listed_as:\n- no-such-source:abc\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="which is no source"):
            read_registry(catalog)

    def test_the_shipped_files_load(self) -> None:
        assert dict(read_registry().listings) == {SWISSALTI3D_LISTING: "swissalti3d"}


class TestTheKeyOfAFind:
    def test_a_find_gets_the_key_from_its_identifier_and_its_source(self) -> None:
        identifier = SWISSALTI3D_LISTING.split(":", 1)[1]
        keys = with_listings("opendata-swiss", [f"id:{identifier}"], {SWISSALTI3D_LISTING})
        assert keys == (f"also:{SWISSALTI3D_LISTING}", f"id:{identifier}")

    @pytest.mark.parametrize(
        ("source_id", "keys"),
        [
            ("govdata", ["id:691cb471-c3b5-48ec-a107-d0ad612fa70b@bundesamt-fur-landestopografie-swisstopo"]),
            ("opendata-swiss", ["id:another-identifier"]),
            ("opendata-swiss", ["doi:10.1/x"]),
            (None, ["id:691cb471-c3b5-48ec-a107-d0ad612fa70b@bundesamt-fur-landestopografie-swisstopo"]),
        ],
    )
    def test_any_other_find_gets_none(self, source_id: str | None, keys: list[str]) -> None:
        assert with_listings(source_id, keys, {SWISSALTI3D_LISTING}) == tuple(keys)

    def test_the_listing_is_a_duplicate_of_the_full_entry_and_a_neighbour_is_not(self) -> None:
        identifier = SWISSALTI3D_LISTING.split(":", 1)[1]
        listing = {SWISSALTI3D_LISTING}
        members = [
            Member("swissalti3d", (f"also:{SWISSALTI3D_LISTING}",), (0,)),
            Member("opendata-swiss.a", with_listings("opendata-swiss", [f"id:{identifier}"], listing), (2, 2), "opendata-swiss"),
            Member("opendata-swiss.relief-mono", with_listings("opendata-swiss", ["id:relief-mono@swisstopo"], listing), (2, 2), "opendata-swiss"),
            Member("opendata-swiss.relief-multi", with_listings("opendata-swiss", ["id:relief-multi@swisstopo"], listing), (2, 2), "opendata-swiss"),
        ]
        assert main_entries(members) == {"opendata-swiss.a": "swissalti3d"}
