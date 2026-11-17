"""The seed of the harvest, ``backend/catalog/sources/`` (M5-19 plan §4.1, F7)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from earthx.catalog.datasets import CATALOG_DIR
from earthx.catalog.entry_files import EntryFileError
from earthx.catalog.sources import CkanFilter, SourceProtocol, StacFilter, read_source, read_sources

STAC = """\
source_id: example-stac
protocol: stac-api
endpoint: https://stac.example.org/api/v1
catalog_page: https://stac.example.org/browser/#/collections/{id}
filter:
  collection_prefixes: []
max_requests_per_run: 20
full_every_days: 1
maturity: stable
enabled: true
"""


def _write(tmp_path: Path, text: str, name: str = "example-stac.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


class TestTheReleasedSeed:
    def test_the_five_sources_otto_released(self) -> None:
        sources = read_sources()
        assert set(sources) == {"fsdi-stac", "earth-search", "govdata", "opendata-swiss", "data-gv-at"}
        assert {s.source_id for s in sources.values() if s.protocol is SourceProtocol.STAC_API} == {
            "fsdi-stac",
            "earth-search",
        }

    def test_data_gv_at_is_held_until_ottos_first_run(self) -> None:
        # F7 = 1: the endpoint is not confirmed from a session.
        sources = read_sources()
        assert not sources["data-gv-at"].enabled
        assert all(source.enabled for key, source in sources.items() if key != "data-gv-at")

    def test_no_ckan_source_filters_on_the_spatial_field(self) -> None:
        # Otto, 17.11.2026: finds without an extent are kept, so no source drops them on the server either.
        for source in read_sources().values():
            if isinstance(source.filter, CkanFilter):
                assert source.filter.fq is None or "spatial" not in source.filter.fq

    def test_a_full_govdata_run_fits_its_budget(self) -> None:
        # 165 427 datasets at 100 per page (plan §4.3).
        assert read_sources()["govdata"].max_requests_per_run >= 1_700


class TestReading:
    def test_a_valid_file(self, tmp_path: Path) -> None:
        source = read_source(_write(tmp_path, STAC))
        assert source.host == "stac.example.org"
        assert source.filter == StacFilter(())

    def test_a_missing_directory_has_no_sources(self, tmp_path: Path) -> None:
        assert read_sources(tmp_path / "none") == {}

    def test_a_readme_is_allowed_a_stray_file_not(self, tmp_path: Path) -> None:
        shutil.copy(CATALOG_DIR / "sources" / "README.md", tmp_path / "README.md")
        _write(tmp_path, STAC)
        assert set(read_sources(tmp_path)) == {"example-stac"}
        (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
        with pytest.raises(EntryFileError, match="only <source_id>.yaml"):
            read_sources(tmp_path)

    @pytest.mark.parametrize(
        ("old", "new", "message"),
        [
            ("enabled: true\n", "", "exactly the fields"),
            ("enabled: true\n", "enabled: true\nextra: 1\n", "exactly the fields"),
            ("protocol: stac-api", "protocol: oai-pmh", "protocol is one of"),
            ("https://stac.example.org/api/v1\n", "http://stac.example.org/api/v1\n", "endpoint is an https"),
            ("https://stac.example.org/api/v1\n", "https://stac.example.org/api/v1/\n", "endpoint is an https"),
            ("https://stac.example.org/api/v1\n", "https://192.0.2.1/api\n", "not a host name"),
            ("{id}", "{name}", "names {id} once"),
            ("{id}", "{id}/{id}", "names {id} once"),
            ("https://stac.example.org/browser", "ftp://stac.example.org/browser", "catalog_page is null or an https"),
            ("collection_prefixes: []", "fq: null", "collection_prefixes, nothing else"),
            ("collection_prefixes: []", "collection_prefixes: ['a b']", "list of collection id prefixes"),
            ("max_requests_per_run: 20", "max_requests_per_run: 0", "max_requests_per_run is a whole number"),
            ("max_requests_per_run: 20", "max_requests_per_run: true", "max_requests_per_run is a whole number"),
            ("full_every_days: 1", "full_every_days: 400", "full_every_days is a whole number"),
            ("maturity: stable", "maturity: great", "maturity is a maturity"),
            ("enabled: true", "enabled: yes", "enabled is true or false"),
        ],
    )
    def test_a_wrong_field_is_named_never_its_value(self, tmp_path: Path, old: str, new: str, message: str) -> None:
        assert old in STAC
        with pytest.raises(EntryFileError, match=message):
            read_source(_write(tmp_path, STAC.replace(old, new)))

    def test_the_file_is_named_after_its_source(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFileError, match="named after it"):
            read_source(_write(tmp_path, STAC, name="other.yaml"))

    @pytest.mark.parametrize("source_id", ["listed", "proto-stac"])
    def test_reserved_ids(self, tmp_path: Path, source_id: str) -> None:
        # M5-40 A10: `listed` belongs to the hand entries; `proto-` to adr/0024.
        text = STAC.replace("source_id: example-stac", f"source_id: {source_id}")
        with pytest.raises(EntryFileError, match="reserved"):
            read_source(_write(tmp_path, text, name=f"{source_id}.yaml"))

    def test_a_ckan_filter(self, tmp_path: Path) -> None:
        text = (
            STAC.replace("protocol: stac-api", "protocol: ckan")
            .replace("{id}", "{name}")
            .replace("  collection_prefixes: []", "  fq: 'res_format:CSV'\n  publisher_field: organization")
        )
        assert read_source(_write(tmp_path, text)).filter == CkanFilter("res_format:CSV", "organization")

    @pytest.mark.parametrize(
        "body", ["  fq: ''\n  publisher_field: organization", "  fq: null\n  publisher_field: author"]
    )
    def test_a_wrong_ckan_filter(self, tmp_path: Path, body: str) -> None:
        text = (
            STAC.replace("protocol: stac-api", "protocol: ckan")
            .replace("{id}", "{name}")
            .replace("  collection_prefixes: []", body)
        )
        with pytest.raises(EntryFileError, match="fq is null|publisher_field is"):
            read_source(_write(tmp_path, text))
